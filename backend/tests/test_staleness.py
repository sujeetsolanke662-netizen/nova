from datetime import datetime, timedelta

from backend.app.staleness import (
    DUPLICATE_WEIGHT,
    LOCATION_WEIGHT,
    RECENCY_WEIGHT,
    SIZE_WEIGHT,
    score_all,
    score_staleness,
)

NOW = datetime(2026, 1, 1, 12, 0, 0)


def _file_meta(path, size_bytes, days_since_access, extension=""):
    accessed = NOW - timedelta(days=days_since_access)
    return {
        "path": path,
        "size_bytes": size_bytes,
        "last_accessed": accessed.timestamp(),
        "last_modified": accessed.timestamp(),
        "extension": extension,
    }


def test_fresh_small_non_duplicate_file_scores_low():
    file_meta = _file_meta("/home/user/project/report.pdf", 1024, days_since_access=0.1, extension=".pdf")

    result = score_staleness(file_meta, duplicate_groups=[], now=NOW)

    assert result["path"] == file_meta["path"]
    assert result["staleness_score"] < 0.1


def test_old_duplicate_large_downloads_file_scores_high():
    file_meta = _file_meta(
        "/home/user/Downloads/old_movie.mp4", 800 * 1024 * 1024, days_since_access=1000
    )
    duplicate_groups = [
        {
            "hash": "abc123",
            "size_bytes": file_meta["size_bytes"],
            "paths": [file_meta["path"], "/home/user/backup/old_movie_copy.mp4"],
        }
    ]

    result = score_staleness(file_meta, duplicate_groups, now=NOW)

    assert result["staleness_score"] > 0.9


def test_factor_weights_sum_to_one():
    assert abs((RECENCY_WEIGHT + DUPLICATE_WEIGHT + LOCATION_WEIGHT + SIZE_WEIGHT) - 1.0) < 1e-9


def test_recency_curve_saturates_rather_than_growing_unboundedly():
    # Same everything else (small, non-duplicate, normal location) so the
    # only difference between the two scores is recency.
    two_years = _file_meta("/home/user/project/notes.txt", 1024, days_since_access=365 * 2)
    ten_years = _file_meta("/home/user/project/notes.txt", 1024, days_since_access=365 * 10)

    score_two_years = score_staleness(two_years, duplicate_groups=[], now=NOW)["staleness_score"]
    score_ten_years = score_staleness(ten_years, duplicate_groups=[], now=NOW)["staleness_score"]

    assert score_ten_years >= score_two_years
    assert score_ten_years - score_two_years < 0.01


def test_score_all_returns_results_sorted_most_stale_first():
    fresh = _file_meta("/home/user/project/report.pdf", 1024, days_since_access=1)
    stale = _file_meta(
        "/home/user/Downloads/big_archive.zip", 600 * 1024 * 1024, days_since_access=900
    )
    medium = _file_meta("/home/user/Downloads/notes.txt", 1024, days_since_access=200)

    duplicate_groups = [
        {
            "hash": "xyz",
            "size_bytes": stale["size_bytes"],
            "paths": [stale["path"], "/home/user/backup/big_archive.zip"],
        }
    ]

    results = score_all([medium, fresh, stale], duplicate_groups)

    assert [r["path"] for r in results] == [stale["path"], medium["path"], fresh["path"]]
    scores = [r["staleness_score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_factors_list_always_has_four_expected_entries():
    expected_names = {"recency_factor", "duplicate_factor", "location_factor", "size_factor"}

    cases = [
        _file_meta("/home/user/project/report.pdf", 1024, days_since_access=0),
        _file_meta("/home/user/Downloads/big.zip", 999 * 1024 * 1024, days_since_access=5000),
        _file_meta("/tmp/scratch.tmp", 0, days_since_access=1),
    ]

    for file_meta in cases:
        result = score_staleness(file_meta, duplicate_groups=[], now=NOW)
        assert len(result["factors"]) == 4
        assert {f["name"] for f in result["factors"]} == expected_names
        for factor in result["factors"]:
            assert set(factor.keys()) == {"name", "contribution", "explanation"}
            assert isinstance(factor["explanation"], str) and factor["explanation"]
