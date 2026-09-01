"""Sensitive-path guardrails: the hard safety gate for NOVA.

Nothing in NOVA's scoring or recommendation logic runs before a path has
passed through this module. If ``is_protected`` returns True for a path,
that path must never be surfaced anywhere in NOVA's output — not in the
review queue, not in an auto-apply list, not even as "found but skipped".

Matching is always done against the fully resolved absolute path (symlinks
followed, ``~`` expanded) so that a symlink can't be used to sneak a
protected file past the gate under an innocent-looking name.

TODO: There is no real-enforcement call site yet (i.e. nothing in the
recommendation engine or apt-clutter pipeline actually decides whether to
act on a file by calling these functions). When that lands, the call that
gates a real action MUST pass ``log=True`` so the block is recorded in the
audit log. Read-only inspection (e.g. an API endpoint that just answers
"would this be blocked?") must keep passing ``log=False`` (the default) -
see backend/app/main.py's /api/guardrails/check for the reasoning.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

import yaml

from . import audit_log

PROTECTED = "protected"
OUTSIDE_SCAN_SCOPE = "outside_scan_scope"
REVIEWABLE = "reviewable"

_GLOB_METACHARS = set("*?[")


def load_protected_patterns(config_path: str) -> list[dict]:
    """Load and validate the protected-path pattern list from YAML.

    Raises ValueError with a clear message if the file is missing required
    structure, and ValueError (wrapping the underlying yaml.YAMLError) if
    the YAML itself is malformed.
    """
    try:
        with open(config_path, "r") as f:
            raw_text = f.read()
    except OSError as e:
        raise ValueError(f"Could not read protected paths config '{config_path}': {e}") from e

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        raise ValueError(f"Malformed YAML in protected paths config '{config_path}': {e}") from e

    if not isinstance(data, dict) or "patterns" not in data:
        raise ValueError(
            f"Protected paths config '{config_path}' must have a top-level 'patterns' list"
        )

    patterns = data["patterns"]
    if not isinstance(patterns, list):
        raise ValueError(f"'patterns' in '{config_path}' must be a list")

    required_keys = ("pattern", "category", "reason")
    for i, entry in enumerate(patterns):
        if not isinstance(entry, dict) or not all(k in entry for k in required_keys):
            raise ValueError(
                f"Pattern entry #{i} in '{config_path}' must have "
                f"'pattern', 'category', and 'reason' keys, got: {entry!r}"
            )

    return patterns


def _resolve(path: str | os.PathLike) -> Path:
    """Expand ~ and resolve symlinks/.. to get the canonical absolute path."""
    return Path(path).expanduser().resolve(strict=False)


def _matches_pattern(resolved_str: str, pattern: str) -> bool:
    expanded = os.path.expanduser(pattern)

    # Glob match. fnmatch treats "*" (and therefore "**") as matching any
    # sequence of characters, including "/" - which is intentionally
    # permissive for a safety gate: better to over-match than under-match.
    if fnmatch.fnmatchcase(resolved_str, expanded):
        return True

    # Prefix-based directory match, so "/etc/**" also protects "/etc"
    # itself (not just its contents), as long as the prefix before "/**"
    # has no remaining glob metacharacters of its own.
    if expanded.endswith("/**"):
        prefix = expanded[:-3]
        if not any(ch in prefix for ch in _GLOB_METACHARS):
            prefix_resolved = str(_resolve(prefix))
            if resolved_str == prefix_resolved or resolved_str.startswith(prefix_resolved + os.sep):
                return True

    return False


def is_protected(path: str, patterns: list[dict], log: bool = False) -> tuple[bool, str | None]:
    """Check whether a path is protected.

    Returns (True, reason) for the first matching pattern, else (False, None).
    Matching is done against the resolved absolute path so symlinks pointing
    into a protected directory are caught even if the literal path looks safe.

    ``log`` controls whether a match writes a "guardrail_block" audit entry.
    It defaults to False - logging is opt-in - because this function is
    called both for real enforcement (actually blocking a file from the
    recommendation queue, which belongs in the audit trail) and for
    read-only inspection (e.g. "would this be blocked?" queries, which do
    not represent a real action and must not pollute the ledger). Pass
    log=True only from a real-enforcement call site.
    """
    resolved_str = str(_resolve(path))

    for entry in patterns:
        if _matches_pattern(resolved_str, entry["pattern"]):
            if log:
                audit_log.append_entry(
                    action_type="guardrail_block",
                    target_paths=[resolved_str],
                    reason=entry["reason"],
                )
            return True, entry["reason"]

    return False, None


def classify_path(path: str, patterns: list[dict], scan_roots: list[str], log: bool = False) -> str:
    """Classify a path as "protected", "outside_scan_scope", or "reviewable".

    Protection always takes priority: a protected path is reported as
    "protected" even if it also happens to fall under a scan root, since
    the guardrail must never be bypassed just because a directory was
    configured for scanning.

    ``log`` is passed straight through to ``is_protected`` - see there for
    when it should be True vs. False.
    """
    resolved = _resolve(path)

    protected, _ = is_protected(str(resolved), patterns, log=log)
    if protected:
        return PROTECTED

    resolved_str = str(resolved)
    for root in scan_roots:
        root_resolved = str(_resolve(root))
        if resolved_str == root_resolved or resolved_str.startswith(root_resolved + os.sep):
            return REVIEWABLE

    return OUTSIDE_SCAN_SCOPE
