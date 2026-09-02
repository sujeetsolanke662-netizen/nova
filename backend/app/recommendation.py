"""Recommendation engine for NOVA.

This is the orchestration layer: it runs the scanner, both duplicate
detectors, and the staleness scorer, then turns their combined output into
a single, explainable list of per-file recommendations - gated by
guardrails at the very last step before anything is returned.

Two duplicate signals feed in at different confidence levels and are kept
deliberately separate:

- Exact (byte-identical) duplicates are the only thing confident enough to
  ever be "auto_apply" - and only for the copies that aren't the oldest;
  the oldest copy in a group is always kept. Exact duplicates are also the
  only duplicate signal that counts toward staleness.duplicate_factor.
- Near-duplicates (perceptual/MinHash) are a lower-confidence signal: they
  can push a file to "review_recommended" but never to "auto_apply", and
  they intentionally do not feed staleness scoring at all.

Every file passes through guardrails.classify_path() a second time here,
even though scanner.scan_directory() already filtered protected paths out
of its own results. That's not redundant by accident: this is the actual
point where NOVA decides to recommend an action on a file, so it's the
real enforcement call site (log=True) - see guardrails.py's module
docstring. Re-checking here means the guarantee "a protected file never
appears in a recommendation" doesn't solely depend on the scanner's
internal filtering being correct.
"""

from __future__ import annotations

from pathlib import Path

from . import audit_log
from .audit_log import DEFAULT_LOG_PATH
from .dedup import find_exact_duplicates
from .guardrails import PROTECTED, classify_path
from .near_dedup import find_all_near_duplicates
from .scanner import scan_directory
from .staleness import score_all

# staleness_score at or above this makes a file "review_recommended" on its
# own, independent of any duplicate signal.
STALENESS_REVIEW_THRESHOLD = 0.6

AUTO_APPLY = "auto_apply"
REVIEW_RECOMMENDED = "review_recommended"
KEEP = "keep"


def _kept_path(paths: list[str], file_meta_by_path: dict[str, dict]) -> str:
    """The file to keep from an exact-duplicate group: the oldest copy by
    last_modified. Ties are broken by path for determinism."""
    return min(paths, key=lambda p: (file_meta_by_path[p]["last_modified"], p))


def _index_exact_groups(
    groups: list[dict], file_meta_by_path: dict[str, dict]
) -> dict[str, tuple[dict, str]]:
    """Map each path to (its exact-duplicate group, that group's kept path)."""
    index: dict[str, tuple[dict, str]] = {}
    for group in groups:
        kept = _kept_path(group["paths"], file_meta_by_path)
        for path in group["paths"]:
            index[path] = (group, kept)
    return index


def _index_near_groups(groups: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for group in groups:
        for path in group["paths"]:
            index[path] = group
    return index


def _build_reason(
    staleness_result: dict,
    exact_group: dict | None,
    is_kept: bool,
    kept_path: str | None,
    near_group: dict | None,
) -> str:
    clauses = []

    if exact_group is not None:
        if is_kept:
            clauses.append(
                f"kept as the oldest of {len(exact_group['paths'])} byte-identical copies"
            )
        else:
            clauses.append(f"a byte-identical duplicate of {kept_path}, safe to auto-remove")

    if near_group is not None:
        kind = "image" if near_group["similarity_type"] == "image_near_duplicate" else "text/code"
        clauses.append(f"a near-duplicate {kind} match")

    stale_score = staleness_result["staleness_score"]
    factor_explanations = [
        f["explanation"] for f in staleness_result["factors"] if f["contribution"] > 0
    ]
    if factor_explanations:
        clauses.append(f"staleness score {stale_score:.2f} ({', '.join(factor_explanations)})")
    elif not clauses:
        clauses.append(f"staleness score {stale_score:.2f}")

    sentence = "; ".join(clauses)
    return sentence[:1].upper() + sentence[1:] + "."


def generate_recommendations(
    root: str,
    scan_roots: list[str],
    protected_patterns: list[dict],
    audit_log_path: str | Path = DEFAULT_LOG_PATH,
) -> dict:
    """Run the full scan -> dedup -> staleness -> guardrail pipeline and
    produce a gated, explainable list of per-file recommendations.

    See the module docstring for how exact vs. near duplicates are treated
    differently, and why guardrails are re-checked here rather than only
    trusted from the scan step. ``audit_log_path`` is threaded through to
    every audit_log write this function makes (both the guardrail_block
    check below and the recommend/auto_apply entries) - callers should
    always pass their actual configured audit log path (e.g.
    Settings.audit_log_path), or every entry silently lands in the
    module's own default log instead of the one the rest of the
    application reads from.
    """
    files, skipped = scan_directory(root, scan_roots, protected_patterns)

    exact_groups = find_exact_duplicates(files)
    near_groups = find_all_near_duplicates(files)

    # Only exact duplicates count toward staleness's duplicate_factor - near
    # matches are a lower-confidence signal and must not blend into a score
    # that claims duplicate_factor is either 0.0 or 1.0.
    scored = score_all(files, exact_groups)
    staleness_by_path = {result["path"]: result for result in scored}

    file_meta_by_path = {f["path"]: f for f in files}
    exact_index = _index_exact_groups(exact_groups, file_meta_by_path)
    near_index = _index_near_groups(near_groups)

    recommendations = []
    protected_count = 0

    for file_meta in files:
        path = file_meta["path"]

        # Real enforcement decision point - log=True records the block.
        classification = classify_path(
            path, protected_patterns, scan_roots, log=True, log_path=audit_log_path
        )
        if classification == PROTECTED:
            protected_count += 1
            continue

        staleness_result = staleness_by_path[path]

        exact_group, kept_path = exact_index.get(path, (None, None))
        near_group = near_index.get(path)
        is_kept = exact_group is not None and kept_path == path

        if exact_group is not None and not is_kept:
            recommended_action = AUTO_APPLY
        elif exact_group is not None and is_kept:
            # The retained copy of a duplicate group: not eligible for
            # auto_apply, but still worth a human glancing at.
            recommended_action = REVIEW_RECOMMENDED
        elif staleness_result["staleness_score"] >= STALENESS_REVIEW_THRESHOLD:
            recommended_action = REVIEW_RECOMMENDED
        elif near_group is not None:
            recommended_action = REVIEW_RECOMMENDED
        else:
            recommended_action = KEEP

        duplicate_of = kept_path if (exact_group is not None and not is_kept) else None

        near_duplicate_of = None
        if near_group is not None:
            others = [p for p in near_group["paths"] if p != path]
            near_duplicate_of = others or None

        if recommended_action != KEEP:
            reason = _build_reason(staleness_result, exact_group, is_kept, kept_path, near_group)
            audit_log.append_entry(
                action_type="auto_apply" if recommended_action == AUTO_APPLY else "recommend",
                target_paths=[path],
                reason=reason,
                log_path=audit_log_path,
            )

        recommendations.append(
            {
                "path": path,
                "recommended_action": recommended_action,
                "staleness_score": staleness_result["staleness_score"],
                "factors": staleness_result["factors"],
                "duplicate_of": duplicate_of,
                "near_duplicate_of": near_duplicate_of,
            }
        )

    return {
        "scanned_count": len(files),
        "skipped_count": len(skipped),
        "protected_count": protected_count,
        "recommendations": recommendations,
    }
