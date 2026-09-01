"""Exact-duplicate detector for NOVA.

Given the scanner's file metadata list, finds groups of files with
byte-identical content. Size is checked first since it's nearly free (the
scanner already collected it): a file whose size is unique in the input
can't have a duplicate, so it's never hashed at all. Only files that share
a size with at least one other file get hashed.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict


def compute_file_hash(path: str, algorithm: str = "sha256", chunk_size: int = 65536) -> str:
    """Hash a file's contents, streaming it in chunks rather than reading it
    fully into memory."""
    hasher = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_exact_duplicates(files: list[dict]) -> list[dict]:
    """Group files with identical content.

    Returns a list of {"hash": str, "size_bytes": int, "paths": [str, ...]}
    for every content hash shared by 2+ files, skipping any group of size 1.
    A file that can no longer be read when it comes time to hash it (e.g.
    removed between the scan and this call) is left out of grouping rather
    than raising.
    """
    by_size: dict[int, list[dict]] = defaultdict(list)
    for f in files:
        by_size[f["size_bytes"]].append(f)

    by_hash: dict[str, list[str]] = defaultdict(list)
    hash_sizes: dict[str, int] = {}

    for size, group in by_size.items():
        if len(group) < 2:
            continue
        for f in group:
            try:
                file_hash = compute_file_hash(f["path"])
            except OSError:
                continue
            by_hash[file_hash].append(f["path"])
            hash_sizes[file_hash] = size

    return [
        {"hash": file_hash, "size_bytes": hash_sizes[file_hash], "paths": paths}
        for file_hash, paths in by_hash.items()
        if len(paths) >= 2
    ]
