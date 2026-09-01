"""Filesystem scanner for NOVA.

Walks a directory tree and collects size/timestamp/extension metadata for
every file that guardrails classifies as in-scope and reviewable. This is
read-only inspection, not an enforcement decision, so classify_path() is
always called with log=False here - see guardrails.py's module docstring
for why a real "block this action" audit entry is a different call site.
"""

from __future__ import annotations

import os
from pathlib import Path

from .guardrails import OUTSIDE_SCAN_SCOPE, PROTECTED, classify_path


def _resolve(path: str | os.PathLike) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_within_any_root(path: Path, resolved_roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in resolved_roots)


def scan_directory(
    root: str, scan_roots: list[str], protected_patterns: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Walk `root` and collect metadata for every non-protected, in-scope file.

    Returns (files, skipped): `files` is a list of metadata dicts (path,
    size_bytes, last_accessed, last_modified, extension); `skipped` is a
    list of {"path": str, "reason": str} for entries that couldn't be
    stat'd or that were excluded as unsafe symlinks.

    Symlinked directories are only followed if their resolved target falls
    inside one of `scan_roots` (so a link can't be used to escape scan
    scope) and hasn't already been visited (so a circular symlink can't
    cause infinite recursion). Symlinked files are likewise only collected
    if their resolved target is within `scan_roots`.
    """
    resolved_roots = [_resolve(r) for r in scan_roots]
    root_path = _resolve(root)

    files: list[dict] = []
    skipped: list[dict] = []
    visited_dirs: set[Path] = {root_path}

    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
        current_dir = Path(dirpath)

        # os.walk with followlinks=False already refuses to recurse into a
        # symlinked directory on its own, but it still lists it in
        # dirnames. We want to allow following a symlinked directory when
        # it's safe (inside scan scope, not already visited) rather than
        # unconditionally skipping it, so we resolve each one ourselves and
        # rewrite dirnames in place to control exactly what gets walked.
        kept_dirnames = []
        for name in dirnames:
            child = current_dir / name
            if not child.is_symlink():
                kept_dirnames.append(name)
                continue
            try:
                real_child = child.resolve(strict=True)
            except OSError as e:
                skipped.append({"path": str(child), "reason": str(e)})
                continue
            if real_child in visited_dirs or not _is_within_any_root(real_child, resolved_roots):
                continue
            visited_dirs.add(real_child)
            kept_dirnames.append(name)
        dirnames[:] = kept_dirnames

        for filename in filenames:
            file_path = current_dir / filename

            if file_path.is_symlink():
                try:
                    real_file = file_path.resolve(strict=True)
                except OSError as e:
                    skipped.append({"path": str(file_path), "reason": str(e)})
                    continue
                if not _is_within_any_root(real_file, resolved_roots):
                    skipped.append(
                        {"path": str(file_path), "reason": "symlink target outside scan roots"}
                    )
                    continue
                file_path = real_file
            else:
                file_path = file_path.resolve(strict=False)

            classification = classify_path(
                str(file_path), protected_patterns, scan_roots, log=False
            )
            if classification in (PROTECTED, OUTSIDE_SCAN_SCOPE):
                continue

            try:
                stat_result = file_path.stat()
            except OSError as e:
                skipped.append({"path": str(file_path), "reason": str(e)})
                continue

            files.append(
                {
                    "path": str(file_path),
                    "size_bytes": stat_result.st_size,
                    "last_accessed": stat_result.st_atime,
                    "last_modified": stat_result.st_mtime,
                    "extension": file_path.suffix,
                }
            )

    return files, skipped
