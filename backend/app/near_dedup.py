"""Near-duplicate detector for NOVA.

Extends dedup.py's byte-identical matching to catch files that are similar
but not byte-identical: photos re-saved/re-compressed/lightly-edited, and
text/code files with a handful of lines changed.

Two independent techniques, one per file family:

- Images: perceptual hashing (imagehash's phash) reduces an image to a
  small hash such that visually similar images have hashes a small Hamming
  distance apart.
- Text/code: MinHash (datasketch) estimates Jaccard similarity between the
  shingle sets of two files without materializing those sets pairwise.

Both find_near_duplicate_* functions group files with a naive union-find
over all pairs within their filtered subset. That's O(n^2) comparisons,
which is fine for a hackathon-scale demo dataset but would not scale to a
large photo library or codebase — a real deployment would want an
approximate-nearest-neighbor index (e.g. FAISS, or LSH via datasketch's
own MinHashLSH) instead of pairwise comparison. Not worth building here.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import imagehash
from datasketch import MinHash
from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".java", ".c", ".cpp", ".json", ".yaml", ".html", ".css",
}

# Cap on how many bytes of a file get read for MinHash shingling, so one
# huge log file doesn't blow up scan time in a demo.
MAX_TEXT_BYTES = 200_000


class _UnionFind:
    """Minimal disjoint-set structure for grouping paths transitively."""

    def __init__(self, items: list[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_a] = root_b

    def groups(self) -> list[list[str]]:
        members: dict[str, list[str]] = defaultdict(list)
        for item in self._parent:
            members[self.find(item)].append(item)
        return list(members.values())


def compute_image_phash(path: str) -> str | None:
    """Compute a perceptual hash for an image file, as a hex string.

    Returns None if the file can't be read as an image (wrong format,
    truncated/corrupt file, unsupported mode, etc.) rather than raising, so
    one bad file doesn't abort a whole scan.
    """
    try:
        with Image.open(path) as img:
            return str(imagehash.phash(img))
    except Exception:
        # PIL can raise a wide variety of exceptions on corrupt or
        # unsupported files (UnidentifiedImageError, OSError, SyntaxError
        # on truncated files, etc.) - any of them means "not a usable
        # image", so treat them uniformly.
        return None


def find_near_duplicate_images(files: list[dict], hamming_threshold: int = 5) -> list[dict]:
    """Group image files whose perceptual hashes are close.

    Returns [{"similarity_type": "image_near_duplicate", "paths": [...],
    "avg_hamming_distance": float}, ...] for every group of 2+ files.
    """
    image_files = [f for f in files if Path(f["path"]).suffix.lower() in IMAGE_EXTENSIONS]

    hashes: dict[str, imagehash.ImageHash] = {}
    for f in image_files:
        hex_hash = compute_image_phash(f["path"])
        if hex_hash is None:
            continue
        hashes[f["path"]] = imagehash.hex_to_hash(hex_hash)

    paths = list(hashes)
    uf = _UnionFind(paths)
    pair_distances: dict[tuple[str, str], int] = {}

    # O(n^2) over the image subset - fine for a hackathon demo dataset; a
    # real deployment with a large photo library would need an
    # approximate-nearest-neighbor index (e.g. FAISS) instead.
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            path_a, path_b = paths[i], paths[j]
            distance = hashes[path_a] - hashes[path_b]
            if distance <= hamming_threshold:
                uf.union(path_a, path_b)
                pair_distances[(path_a, path_b)] = distance

    result = []
    for members in uf.groups():
        if len(members) < 2:
            continue
        member_set = set(members)
        distances = [
            d for (a, b), d in pair_distances.items() if a in member_set and b in member_set
        ]
        avg_distance = sum(distances) / len(distances) if distances else 0.0
        result.append(
            {
                "similarity_type": "image_near_duplicate",
                "paths": members,
                "avg_hamming_distance": avg_distance,
            }
        )
    return result


def compute_minhash_signature(path: str, shingle_size: int = 5, num_perm: int = 128) -> MinHash | None:
    """Build a MinHash signature over character shingles of a text file.

    Reads at most MAX_TEXT_BYTES of the file. Returns None if the file
    can't be decoded as UTF-8 text (binary files) or can't be read at all.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_TEXT_BYTES)
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    shingles = {text[i : i + shingle_size] for i in range(max(0, len(text) - shingle_size + 1))}
    if not shingles and text:
        shingles = {text}

    signature = MinHash(num_perm=num_perm)
    for shingle in shingles:
        signature.update(shingle.encode("utf-8"))
    return signature


def find_near_duplicate_text(files: list[dict], jaccard_threshold: float = 0.8) -> list[dict]:
    """Group text/code files whose estimated Jaccard similarity is high.

    Returns [{"similarity_type": "text_near_duplicate", "paths": [...],
    "avg_similarity": float}, ...] for every group of 2+ files.
    """
    text_files = [f for f in files if Path(f["path"]).suffix.lower() in TEXT_EXTENSIONS]

    signatures: dict[str, MinHash] = {}
    for f in text_files:
        signature = compute_minhash_signature(f["path"])
        if signature is None:
            continue
        signatures[f["path"]] = signature

    paths = list(signatures)
    uf = _UnionFind(paths)
    pair_similarities: dict[tuple[str, str], float] = {}

    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            path_a, path_b = paths[i], paths[j]
            similarity = signatures[path_a].jaccard(signatures[path_b])
            if similarity >= jaccard_threshold:
                uf.union(path_a, path_b)
                pair_similarities[(path_a, path_b)] = similarity

    result = []
    for members in uf.groups():
        if len(members) < 2:
            continue
        member_set = set(members)
        similarities = [
            s for (a, b), s in pair_similarities.items() if a in member_set and b in member_set
        ]
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        result.append(
            {
                "similarity_type": "text_near_duplicate",
                "paths": members,
                "avg_similarity": avg_similarity,
            }
        )
    return result


def find_all_near_duplicates(files: list[dict]) -> list[dict]:
    """Run both near-duplicate detectors and merge their results."""
    return find_near_duplicate_images(files) + find_near_duplicate_text(files)
