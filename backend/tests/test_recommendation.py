import os
import time
from pathlib import Path

import pytest

from backend.app.recommendation import generate_recommendations

GIT_INTERNALS_PATTERN = [
    {
        "pattern": "**/.git/**",
        "category": "git_internals",
        "reason": "Git internal object store and metadata.",
    }
]


@pytest.fixture
def audit_calls(monkeypatch):
    """Capture every audit_log.append_entry call instead of touching disk.

    guardrails.py and recommendation.py both do `from . import audit_log`,
    so patching the attribute on the shared backend.app.audit_log module
    intercepts calls from both call sites (real enforcement inside
    classify_path/is_protected, and the recommend/auto_apply calls made
    directly by generate_recommendations).
    """
    calls = []

    def fake_append_entry(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr("backend.app.audit_log.append_entry", fake_append_entry)
    return calls


def _touch(path: Path, days_ago: float) -> None:
    """Backdate a file's atime/mtime by `days_ago` days."""
    when = time.time() - days_ago * 86400
    os.utime(path, (when, when))


@pytest.fixture
def scan_tree(tmp_path):
    """A realistic small tree: an exact-duplicate trio with distinct
    mtimes, a near-duplicate code pair, one fresh/normal file, and one
    protected .git-internal file."""
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()

    duplicate_content = "duplicate payload\n" * 50
    dup_oldest = scan_root / "dup_oldest.txt"
    dup_middle = scan_root / "dup_middle.txt"
    dup_newest = scan_root / "dup_newest.txt"
    dup_oldest.write_text(duplicate_content)
    dup_middle.write_text(duplicate_content)
    dup_newest.write_text(duplicate_content)
    _touch(dup_oldest, days_ago=30)
    _touch(dup_middle, days_ago=15)
    _touch(dup_newest, days_ago=5)

    base_text = "\n".join(f"def function_{i}():\n    return {i}" for i in range(300))
    near_text = base_text.replace("function_3", "function_three").replace(
        "function_10", "function_ten"
    )
    near_a = scan_root / "near_a.py"
    near_b = scan_root / "near_b.py"
    near_a.write_text(base_text)
    near_b.write_text(near_text)

    fresh_file = scan_root / "fresh_notes.txt"
    fresh_file.write_text("just wrote this, still relevant")

    protected_dir = scan_root / "repo" / ".git"
    protected_dir.mkdir(parents=True)
    protected_file = protected_dir / "config"
    protected_file.write_text("[core]\n\trepositoryformatversion = 0\n")

    return {
        "scan_root": scan_root,
        "dup_oldest": dup_oldest,
        "dup_middle": dup_middle,
        "dup_newest": dup_newest,
        "near_a": near_a,
        "near_b": near_b,
        "fresh_file": fresh_file,
        "protected_file": protected_file,
    }


def test_protected_file_never_appears_in_recommendations(scan_tree, audit_calls):
    scan_root = scan_tree["scan_root"]

    result = generate_recommendations(
        str(scan_root), [str(scan_root)], GIT_INTERNALS_PATTERN
    )

    paths_in_output = {r["path"] for r in result["recommendations"]}
    protected_resolved = str(scan_tree["protected_file"].resolve())

    assert protected_resolved not in paths_in_output
    assert all(".git" not in p for p in paths_in_output)
    # scan_directory already filters protected paths out before
    # generate_recommendations' own files list, so the redundant guardrail
    # re-check here finds nothing left to catch.
    assert result["protected_count"] == 0


def test_exact_duplicate_group_gets_one_auto_apply_and_kept_is_oldest(scan_tree, audit_calls):
    scan_root = scan_tree["scan_root"]

    result = generate_recommendations(
        str(scan_root), [str(scan_root)], GIT_INTERNALS_PATTERN
    )

    dup_paths = {
        str(scan_tree["dup_oldest"].resolve()),
        str(scan_tree["dup_middle"].resolve()),
        str(scan_tree["dup_newest"].resolve()),
    }
    by_path = {r["path"]: r for r in result["recommendations"]}
    dup_recs = {p: by_path[p] for p in dup_paths}

    auto_apply = [p for p, r in dup_recs.items() if r["recommended_action"] == "auto_apply"]
    non_auto_apply = [p for p, r in dup_recs.items() if r["recommended_action"] != "auto_apply"]

    assert len(auto_apply) == 2
    assert len(non_auto_apply) == 1

    kept_path = non_auto_apply[0]
    assert kept_path == str(scan_tree["dup_oldest"].resolve())
    assert dup_recs[kept_path]["recommended_action"] == "review_recommended"
    assert dup_recs[kept_path]["duplicate_of"] is None

    for p in auto_apply:
        assert dup_recs[p]["duplicate_of"] == kept_path


def test_near_duplicate_pair_marked_review_recommended(scan_tree, audit_calls):
    scan_root = scan_tree["scan_root"]

    result = generate_recommendations(
        str(scan_root), [str(scan_root)], GIT_INTERNALS_PATTERN
    )

    near_a_path = str(scan_tree["near_a"].resolve())
    near_b_path = str(scan_tree["near_b"].resolve())
    by_path = {r["path"]: r for r in result["recommendations"]}

    assert by_path[near_a_path]["recommended_action"] == "review_recommended"
    assert by_path[near_b_path]["recommended_action"] == "review_recommended"
    assert by_path[near_a_path]["near_duplicate_of"] == [near_b_path]
    assert by_path[near_b_path]["near_duplicate_of"] == [near_a_path]


def test_fresh_normal_file_recommended_keep(scan_tree, audit_calls):
    scan_root = scan_tree["scan_root"]

    result = generate_recommendations(
        str(scan_root), [str(scan_root)], GIT_INTERNALS_PATTERN
    )

    fresh_path = str(scan_tree["fresh_file"].resolve())
    by_path = {r["path"]: r for r in result["recommendations"]}

    assert by_path[fresh_path]["recommended_action"] == "keep"
    assert by_path[fresh_path]["staleness_score"] < 0.6
    assert by_path[fresh_path]["duplicate_of"] is None
    assert by_path[fresh_path]["near_duplicate_of"] is None


def test_audit_log_receives_entry_for_every_non_keep_recommendation(scan_tree, audit_calls):
    scan_root = scan_tree["scan_root"]

    result = generate_recommendations(
        str(scan_root), [str(scan_root)], GIT_INTERNALS_PATTERN
    )

    non_keep = [r for r in result["recommendations"] if r["recommended_action"] != "keep"]
    keep = [r for r in result["recommendations"] if r["recommended_action"] == "keep"]

    assert len(keep) == 1  # only fresh_notes.txt
    assert len(non_keep) == 5  # 3 dup files + 2 near-dup files

    logged_paths = [call["target_paths"][0] for call in audit_calls]
    for rec in non_keep:
        assert rec["path"] in logged_paths

    auto_apply_calls = [c for c in audit_calls if c["action_type"] == "auto_apply"]
    recommend_calls = [c for c in audit_calls if c["action_type"] == "recommend"]
    assert len(auto_apply_calls) == 2
    assert len(recommend_calls) == 3
    assert len(audit_calls) == 5

    for call in audit_calls:
        assert call["reason"]


def test_scanned_and_recommendation_counts_are_consistent(scan_tree, audit_calls):
    scan_root = scan_tree["scan_root"]

    result = generate_recommendations(
        str(scan_root), [str(scan_root)], GIT_INTERNALS_PATTERN
    )

    assert result["scanned_count"] == 6  # 3 dup + 2 near-dup + 1 fresh
    assert result["skipped_count"] == 0
    assert result["protected_count"] == 0
    assert len(result["recommendations"]) == result["scanned_count"] - result["protected_count"]


def test_redundant_guardrail_check_catches_protected_file_even_if_scan_leaked_it(
    tmp_path, monkeypatch, audit_calls
):
    """generate_recommendations must not solely rely on scan_directory's own
    protected-path filtering: it re-checks classify_path() itself before
    finalizing any recommendation. Simulate scan_directory "leaking" a
    protected file through to prove that second gate actually blocks it."""
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()

    normal_file = scan_root / "normal.txt"
    normal_file.write_text("a perfectly normal file")

    leaked_git_dir = scan_root / "repo" / ".git"
    leaked_git_dir.mkdir(parents=True)
    leaked_protected_file = leaked_git_dir / "config"
    leaked_protected_file.write_text("[core]\n")

    def _meta(path: Path) -> dict:
        st = path.stat()
        return {
            "path": str(path),
            "size_bytes": st.st_size,
            "last_accessed": st.st_atime,
            "last_modified": st.st_mtime,
            "extension": path.suffix,
        }

    def fake_scan_directory(root, scan_roots, protected_patterns):
        return [_meta(normal_file), _meta(leaked_protected_file)], []

    monkeypatch.setattr("backend.app.recommendation.scan_directory", fake_scan_directory)

    result = generate_recommendations(
        str(scan_root), [str(scan_root)], GIT_INTERNALS_PATTERN
    )

    assert result["scanned_count"] == 2
    assert result["protected_count"] == 1
    paths_in_output = {r["path"] for r in result["recommendations"]}
    assert str(leaked_protected_file) not in paths_in_output
    assert len(result["recommendations"]) == 1

    guardrail_calls = [c for c in audit_calls if c["action_type"] == "guardrail_block"]
    assert len(guardrail_calls) == 1
    assert guardrail_calls[0]["target_paths"] == [str(leaked_protected_file)]
