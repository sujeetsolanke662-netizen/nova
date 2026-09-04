#!/usr/bin/env python3
"""Scalability benchmark for NOVA's core file-processing pipeline.

Standalone tool, not a pytest test - run this manually to get real,
reportable throughput/memory numbers (e.g. for the hackathon
presentation). It is NOT part of `pytest backend/tests`.

Generates a synthetic file tree of a given size, then times each pipeline
stage separately with time.perf_counter():
    - scanner.scan_directory()
    - dedup.find_exact_duplicates()
    - staleness.score_all()
    - the full recommendation.generate_recommendations() end-to-end (this
      re-does scan/dedup/staleness internally - that's expected, it's
      reported as its own real-world number since it's what the
      /api/recommendations endpoint actually calls)

Usage:
    python -m backend.scripts.benchmark_scan --file-count 10000
    python -m backend.scripts.benchmark_scan --file-count 25000 --keep
    python -m backend.scripts.benchmark_scan --file-count 5000 --tmp-dir /path/to/dir

Deliberately does NOT generate any file with an extension in
near_dedup.py's IMAGE_EXTENSIONS or TEXT_EXTENSIONS. That module does a
naive O(n^2) pairwise comparison within each family, by its own admission
("fine for a hackathon-scale demo dataset... would not scale to a large
photo library or codebase"). Generating tens of thousands of .txt/.jpg
files here would benchmark that known, already-documented limitation
instead of the scan/dedup/staleness throughput this tool exists to
measure - so every synthetic file uses an extension outside both sets.

Also does NOT touch the project's real audit log: generate_recommendations()
writes an audit entry for every non-"keep" recommendation, so this script
points audit_log_path at a throwaway file next to the generated tree,
never at backend/data/audit_log.jsonl.
"""

from __future__ import annotations

import argparse
import math
import random
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.app.dedup import find_exact_duplicates  # noqa: E402
from backend.app.recommendation import generate_recommendations  # noqa: E402
from backend.app.scanner import scan_directory  # noqa: E402
from backend.app.staleness import score_all  # noqa: E402

# Realistic file extensions, deliberately none of them in near_dedup.py's
# IMAGE_EXTENSIONS/TEXT_EXTENSIONS - see module docstring above.
EXTENSIONS = [".log", ".dat", ".bin", ".zip", ".tar", ".dmg", ".pdf", ".mp4", ".iso"]

SMALL_RANGE = (1_000, 10_000)  # 1-10 KB
MEDIUM_RANGE = (100_000, 1_000_000)  # 100 KB - 1 MB
LARGE_RANGE = (5_000_000, 10_000_000)  # 5-10 MB

# "A handful" of large files - a small fraction that grows slowly with N,
# not a fixed count that would vanish at scale or a fixed percentage that
# would blow past the disk budget at scale (each large file is ~500-1000x
# a small one, so even a couple of percent of large files dominates total
# size). Medium is a modest slice; everything else is small. Chosen so the
# default 10,000-file run lands comfortably under the ~500MB target.
LARGE_FRACTION = 0.002
MEDIUM_FRACTION = 0.045
DUPLICATE_FRACTION = 0.15

FILES_PER_DIR = 30  # target average files per leaf directory
TREE_DEPTH = 4  # realistic nesting - real filesystems aren't flat


def _content_for(index: int, size: int) -> bytes:
    """Cheap, unique-per-index synthetic content of exactly `size` bytes.

    Deterministic and fast (no CSPRNG overhead) rather than os.urandom -
    all that's actually needed for a non-duplicate file here is that its
    bytes differ from every other non-duplicate file's, which a unique
    index guarantees trivially.
    """
    marker = f"nova-benchmark-file-{index}-".encode()
    repeats = size // len(marker) + 1
    return (marker * repeats)[:size]


def _make_size(category: str) -> int:
    if category == "large":
        return random.randint(*LARGE_RANGE)
    if category == "medium":
        return random.randint(*MEDIUM_RANGE)
    return random.randint(*SMALL_RANGE)


def _leaf_dirs(root: Path, file_count: int) -> list[Path]:
    """Create a several-levels-deep directory tree and return its leaves."""
    num_leaves = max(1, file_count // FILES_PER_DIR)
    branching = max(2, math.ceil(num_leaves ** (1 / TREE_DEPTH)))

    leaves = []
    for index in range(num_leaves):
        n = index
        parts = []
        for _ in range(TREE_DEPTH):
            parts.append(f"dir_{n % branching}")
            n //= branching
        parts.reverse()
        leaf = root.joinpath(*parts)
        leaf.mkdir(parents=True, exist_ok=True)
        leaves.append(leaf)
    return leaves


def generate_synthetic_tree(root: Path, file_count: int) -> int:
    """Populate `root` with `file_count` synthetic files spread across a
    realistic directory tree, with a realistic size mix and ~15% exact
    duplicates. Returns total bytes written.
    """
    leaves = _leaf_dirs(root, file_count)

    large_count = max(1, round(file_count * LARGE_FRACTION))
    medium_count = max(1, round(file_count * MEDIUM_FRACTION))
    small_count = file_count - large_count - medium_count

    categories = ["large"] * large_count + ["medium"] * medium_count + ["small"] * small_count
    random.shuffle(categories)

    dup_count = round(file_count * DUPLICATE_FRACTION)
    duplicate_flags = [False] * file_count
    for i in random.sample(range(file_count), min(dup_count, file_count)):
        duplicate_flags[i] = True

    # Duplicates copy an existing same-category file's exact bytes, so the
    # realized size distribution matches the category ratios above even
    # with duplicates included, and find_exact_duplicates() has real,
    # byte-identical groups to find - not coincidentally-equal-size files.
    originals_by_category: dict[str, list[Path]] = {"small": [], "medium": [], "large": []}
    total_bytes = 0

    for i in range(file_count):
        category = categories[i]
        leaf = leaves[i % len(leaves)]
        ext = random.choice(EXTENSIONS)
        path = leaf / f"file_{i:07d}{ext}"

        if duplicate_flags[i] and originals_by_category[category]:
            source = random.choice(originals_by_category[category])
            shutil.copyfile(source, path)
            size = source.stat().st_size
        else:
            size = _make_size(category)
            path.write_bytes(_content_for(i, size))
            originals_by_category[category].append(path)

        total_bytes += size

    return total_bytes


def format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NOVA scan-pipeline scalability benchmark.")
    parser.add_argument("--file-count", type=int, default=10_000)
    parser.add_argument(
        "--tmp-dir",
        type=str,
        default=None,
        help="Directory to generate the synthetic tree in (default: a fresh temp dir)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Don't delete the generated tree (and its throwaway audit log) afterward",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for synthetic tree generation, so repeated runs "
        "(e.g. before/after a code change) generate an identical tree and "
        "are actually comparable, not confounded by run-to-run randomness "
        "in file sizes/duplicate counts. Pass a different value for a "
        "fresh random tree.",
    )
    args = parser.parse_args(argv)
    random.seed(args.seed)

    tmp_dir = Path(args.tmp_dir).expanduser() if args.tmp_dir else Path(
        tempfile.mkdtemp(prefix="nova_benchmark_")
    )

    # Refuse to run against a directory that already has content: this
    # script deletes tmp_dir wholesale at the end unless --keep is passed,
    # and it must never risk deleting something it didn't create itself.
    if tmp_dir.exists() and any(tmp_dir.iterdir()):
        print(
            f"Refusing to run: '{tmp_dir}' already exists and is not empty. "
            "Pass an empty or nonexistent --tmp-dir.",
            file=sys.stderr,
        )
        return 1

    tmp_dir.mkdir(parents=True, exist_ok=True)
    audit_log_path = tmp_dir.parent / f"{tmp_dir.name}_audit_log.jsonl"

    print(f"Generating {args.file_count} synthetic files under {tmp_dir} ...")
    gen_start = time.perf_counter()
    total_bytes = generate_synthetic_tree(tmp_dir, args.file_count)
    gen_elapsed = time.perf_counter() - gen_start
    print(f"  done in {gen_elapsed:.2f}s ({format_bytes(total_bytes)} written)\n")

    scan_roots = [str(tmp_dir)]
    protected_patterns: list[dict] = []

    try:
        print("Running scanner.scan_directory() ...")
        t0 = time.perf_counter()
        files, skipped = scan_directory(str(tmp_dir), scan_roots, protected_patterns)
        scan_elapsed = time.perf_counter() - t0
        print(f"  {len(files)} files scanned, {len(skipped)} skipped, in {scan_elapsed:.2f}s\n")

        print("Running dedup.find_exact_duplicates() ...")
        t0 = time.perf_counter()
        duplicate_groups = find_exact_duplicates(files)
        dedup_elapsed = time.perf_counter() - t0
        dup_file_count = sum(len(g["paths"]) for g in duplicate_groups)
        print(
            f"  {len(duplicate_groups)} duplicate groups "
            f"({dup_file_count} files) in {dedup_elapsed:.2f}s\n"
        )

        print("Running staleness.score_all() ...")
        t0 = time.perf_counter()
        score_all(files, duplicate_groups)
        staleness_elapsed = time.perf_counter() - t0
        print(f"  scored {len(files)} files in {staleness_elapsed:.2f}s\n")

        print("Running recommendation.generate_recommendations() end-to-end ...")
        t0 = time.perf_counter()
        result = generate_recommendations(
            str(tmp_dir), scan_roots, protected_patterns, audit_log_path=audit_log_path
        )
        full_pipeline_elapsed = time.perf_counter() - t0
        print(
            f"  {result['scanned_count']} scanned, "
            f"{len(result['recommendations'])} recommendations, "
            f"in {full_pipeline_elapsed:.2f}s\n"
        )

        peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_mb = peak_rss_kb / 1024  # ru_maxrss is KB on Linux

        scan_throughput = len(files) / scan_elapsed if scan_elapsed > 0 else float("inf")

        print("=" * 62)
        print("NOVA scan pipeline benchmark summary")
        print("=" * 62)
        print(f"{'Files generated:':<36}{args.file_count}")
        print(f"{'Total size generated:':<36}{format_bytes(total_bytes)}")
        print(f"{'scan_directory():':<36}{scan_elapsed:.2f}s")
        print(f"{'find_exact_duplicates():':<36}{dedup_elapsed:.2f}s")
        print(f"{'score_all():':<36}{staleness_elapsed:.2f}s")
        print(f"{'generate_recommendations() (full):':<36}{full_pipeline_elapsed:.2f}s")
        print(f"{'Scan throughput:':<36}{scan_throughput:.1f} files/sec")
        print(f"{'Peak memory (RSS):':<36}{peak_mb:.1f} MB")
        print("=" * 62)

    finally:
        if args.keep:
            print(f"\n--keep passed: leaving {tmp_dir} (and {audit_log_path}) in place.")
        else:
            print(f"\nCleaning up {tmp_dir} ...")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            audit_log_path.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
