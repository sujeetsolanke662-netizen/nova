from datetime import datetime, timedelta

import numpy as np

from backend.app.forecasting import (
    forecast_capacity,
    generate_synthetic_history,
    get_disk_usage,
    load_snapshots,
    record_usage_snapshot,
)

DEMO_PATH = "/demo/disk"
TOTAL_BYTES = 1_000_000_000


def _snapshot_log(tmp_path):
    return tmp_path / "usage_snapshots.jsonl"


def _record_series(log_path, used_percents, path=DEMO_PATH, total_bytes=TOTAL_BYTES):
    now = datetime.now()
    n = len(used_percents)
    for i, used_percent in enumerate(used_percents):
        record_usage_snapshot(
            path,
            used_bytes=int(total_bytes * used_percent / 100.0),
            total_bytes=total_bytes,
            timestamp=now - timedelta(days=n - 1 - i),
            snapshot_log_path=log_path,
        )


def test_insufficient_data_returns_correct_counts(tmp_path):
    log_path = _snapshot_log(tmp_path)
    _record_series(log_path, [30.0, 32.0])

    result = forecast_capacity(DEMO_PATH, snapshot_log_path=log_path)

    assert result == {
        "status": "insufficient_data",
        "snapshots_available": 2,
        "snapshots_needed": 3,
    }


def test_zero_snapshots_returns_insufficient_data(tmp_path):
    log_path = _snapshot_log(tmp_path)

    result = forecast_capacity(DEMO_PATH, snapshot_log_path=log_path)

    assert result == {
        "status": "insufficient_data",
        "snapshots_available": 0,
        "snapshots_needed": 3,
    }


def test_increasing_trend_produces_reasonable_finite_days_until_full(tmp_path):
    log_path = _snapshot_log(tmp_path)
    # Clearly increasing: +2 percentage points of disk used per day.
    _record_series(log_path, [30.0 + 2.0 * i for i in range(10)])

    result = forecast_capacity(DEMO_PATH, days_ahead=30, snapshot_log_path=log_path)

    assert result["status"] == "ok"
    assert result["trend_bytes_per_day"] > 0
    assert result["days_until_full"] is not None
    assert 0 < result["days_until_full"] < 10_000
    assert result["projected_used_percent_in_30_days"] > result["current_used_percent"]
    assert result["current_used_percent"] == 48.0  # 30 + 2*9


def test_flat_trend_produces_none_days_until_full(tmp_path):
    log_path = _snapshot_log(tmp_path)
    _record_series(log_path, [50.0] * 10)

    result = forecast_capacity(DEMO_PATH, snapshot_log_path=log_path)

    assert result["status"] == "ok"
    assert result["days_until_full"] is None


def test_decreasing_trend_produces_none_days_until_full(tmp_path):
    log_path = _snapshot_log(tmp_path)
    _record_series(log_path, [60.0 - 2.0 * i for i in range(10)])

    result = forecast_capacity(DEMO_PATH, snapshot_log_path=log_path)

    assert result["status"] == "ok"
    assert result["trend_bytes_per_day"] < 0
    assert result["days_until_full"] is None


def test_generate_synthetic_history_produces_requested_count_and_increasing_trend(tmp_path):
    log_path = _snapshot_log(tmp_path)
    path = str(tmp_path)

    generate_synthetic_history(path, days=60, snapshot_log_path=log_path)

    snapshots = load_snapshots(path, snapshot_log_path=log_path)
    assert len(snapshots) == 60

    timestamps = [datetime.fromisoformat(s["timestamp"]) for s in snapshots]
    assert timestamps == sorted(timestamps)

    earliest = timestamps[0]
    x = np.array([(t - earliest).total_seconds() / 86400.0 for t in timestamps])
    y = np.array([s["used_bytes"] for s in snapshots], dtype=float)
    slope, _ = np.polyfit(x, y, 1)

    # Noisy day-to-day, but the overall direction must be upward.
    assert slope > 0


def test_generate_synthetic_history_feeds_forecast_capacity_to_ok_status(tmp_path):
    log_path = _snapshot_log(tmp_path)
    path = str(tmp_path)

    generate_synthetic_history(path, days=30, snapshot_log_path=log_path)

    result = forecast_capacity(path, snapshot_log_path=log_path)

    assert result["status"] == "ok"


def test_get_disk_usage_returns_sane_values_for_real_path(tmp_path):
    result = get_disk_usage(str(tmp_path))

    assert result["total_bytes"] > 0
    assert result["used_bytes"] >= 0
    assert result["free_bytes"] >= 0
    assert result["used_bytes"] + result["free_bytes"] <= result["total_bytes"]
    assert 0 <= result["used_percent"] <= 100
