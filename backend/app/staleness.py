"""Staleness scoring for NOVA.

This deliberately replaces what would elsewhere be a trained model with a
transparent, hand-weighted formula: every factor is named, normalized to
0.0-1.0, and reported with its own weighted contribution and a
plain-language explanation. That's a design choice for full
explainability (the "factors" list is what the UI shows the user to
justify a score), not a placeholder for something fancier later.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

RECENCY_WEIGHT = 0.45
DUPLICATE_WEIGHT = 0.30
LOCATION_WEIGHT = 0.15
SIZE_WEIGHT = 0.10

assert math.isclose(RECENCY_WEIGHT + DUPLICATE_WEIGHT + LOCATION_WEIGHT + SIZE_WEIGHT, 1.0)

# Days-scale for the recency saturating curve: 1 - exp(-days / this). Larger
# means it takes longer for the recency factor to approach its 1.0 ceiling.
RECENCY_SCALE_DAYS = 90.0

# Reference size (bytes) at which size_factor reaches its full 1.0
# contribution; files at or above this size are treated as equally
# "worth reclaiming" from a size standpoint.
SIZE_REFERENCE_BYTES = 500 * 1024 * 1024  # 500 MB

# Path segments (case-insensitive, matched as whole path components) that
# indicate a typically-temporary/junk location. Module-level so it's easy
# to extend without touching the scoring logic.
JUNK_LOCATION_SEGMENTS = [
    "downloads",
    "tmp",
    "temp",
    "cache",
    ".cache",
]


def _recency_factor(file_meta: dict, now: datetime) -> tuple[float, str]:
    last_accessed = datetime.fromtimestamp(file_meta["last_accessed"])
    days_since_access = max((now - last_accessed).total_seconds() / 86400.0, 0.0)

    sub_score = 1.0 - math.exp(-days_since_access / RECENCY_SCALE_DAYS)
    explanation = f"not accessed in {days_since_access:.0f} days"
    return sub_score, explanation


def _duplicate_factor(file_meta: dict, duplicate_groups: list[dict]) -> tuple[float, str]:
    path = file_meta["path"]
    is_duplicate = any(
        len(group["paths"]) >= 2 and path in group["paths"] for group in duplicate_groups
    )

    if is_duplicate:
        return 1.0, "duplicate of another file"
    return 0.0, "no duplicate copies found"


def _location_factor(file_meta: dict) -> tuple[float, str]:
    parts = [p.lower() for p in Path(file_meta["path"]).parts]
    matched = next((segment for segment in JUNK_LOCATION_SEGMENTS if segment in parts), None)

    if matched:
        return 1.0, f"sitting in a typically temporary folder ('{matched}')"
    return 0.0, "not in a typically temporary folder"


def _size_factor(file_meta: dict, reference_bytes: float) -> tuple[float, str]:
    size_bytes = file_meta["size_bytes"]
    sub_score = min(size_bytes / reference_bytes, 1.0)

    size_mb = size_bytes / (1024 * 1024)
    if size_mb >= 1:
        explanation = f"{size_mb:.1f} MB - reclaiming it would free up meaningful space"
    else:
        explanation = f"{size_bytes} bytes - a small file"
    return sub_score, explanation


def score_staleness(
    file_meta: dict,
    duplicate_groups: list[dict],
    now: datetime | None = None,
    size_reference_bytes: float = SIZE_REFERENCE_BYTES,
) -> dict:
    """Score one file's staleness as a weighted sum of four named factors.

    Every sub-score is normalized to 0.0-1.0 before weighting, so the
    returned "factors" list can be shown to a user as an itemized
    breakdown of exactly why a file scored the way it did.
    """
    if now is None:
        now = datetime.now()

    recency_score, recency_explanation = _recency_factor(file_meta, now)
    duplicate_score, duplicate_explanation = _duplicate_factor(file_meta, duplicate_groups)
    location_score, location_explanation = _location_factor(file_meta)
    size_score, size_explanation = _size_factor(file_meta, size_reference_bytes)

    factors = [
        {
            "name": "recency_factor",
            "contribution": RECENCY_WEIGHT * recency_score,
            "explanation": recency_explanation,
        },
        {
            "name": "duplicate_factor",
            "contribution": DUPLICATE_WEIGHT * duplicate_score,
            "explanation": duplicate_explanation,
        },
        {
            "name": "location_factor",
            "contribution": LOCATION_WEIGHT * location_score,
            "explanation": location_explanation,
        },
        {
            "name": "size_factor",
            "contribution": SIZE_WEIGHT * size_score,
            "explanation": size_explanation,
        },
    ]

    return {
        "path": file_meta["path"],
        "staleness_score": sum(f["contribution"] for f in factors),
        "factors": factors,
    }


def score_all(files: list[dict], duplicate_groups: list[dict]) -> list[dict]:
    """Score every file and return the results sorted most-stale first."""
    scored = [score_staleness(f, duplicate_groups) for f in files]
    scored.sort(key=lambda result: result["staleness_score"], reverse=True)
    return scored
