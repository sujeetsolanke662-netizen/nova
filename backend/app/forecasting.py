"""Capacity forecasting for NOVA.

Deliberately simple linear trend extrapolation over historical disk-usage
snapshots, not a trained model - same explainability reasoning as
staleness.py: the slope, projection, and current reading are all reported
directly rather than hidden inside a black-box prediction.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

DEFAULT_SNAPSHOT_LOG = Path(__file__).resolve().parent.parent / "data" / "usage_snapshots.jsonl"

MIN_SNAPSHOTS_FOR_FORECAST = 3


def get_disk_usage(path: str) -> dict:
    """Real total/used/free bytes for the filesystem containing `path`."""
    total, used, free = shutil.disk_usage(path)
    used_percent = (used / total * 100.0) if total else 0.0
    return {
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "used_percent": used_percent,
    }


def record_usage_snapshot(
    path: str,
    used_bytes: int,
    total_bytes: int,
    timestamp: datetime | None = None,
    snapshot_log_path: str | Path = DEFAULT_SNAPSHOT_LOG,
) -> dict:
    """Append one usage snapshot to the log.

    JSON Lines, one object per line, append-only - the same on-disk shape
    as audit_log.py, minus the hash chain: these are periodic measurements,
    not accountable actions, so there's nothing here that needs tamper
    evidence.
    """
    if timestamp is None:
        timestamp = datetime.now()

    used_percent = (used_bytes / total_bytes * 100.0) if total_bytes else 0.0

    entry = {
        "path": path,
        "used_bytes": used_bytes,
        "total_bytes": total_bytes,
        "used_percent": used_percent,
        "timestamp": timestamp.isoformat(),
    }

    log_path = Path(snapshot_log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")

    return entry


def load_snapshots(path: str, snapshot_log_path: str | Path = DEFAULT_SNAPSHOT_LOG) -> list[dict]:
    """All snapshots recorded for `path`, sorted by timestamp ascending."""
    log_path = Path(snapshot_log_path)
    if not log_path.exists():
        return []

    with open(log_path, "r") as f:
        lines = [line for line in f.read().splitlines() if line.strip()]

    all_entries = [json.loads(line) for line in lines]
    matching = [e for e in all_entries if e["path"] == path]
    matching.sort(key=lambda e: e["timestamp"])
    return matching


def forecast_capacity(
    path: str,
    days_ahead: int = 30,
    snapshot_log_path: str | Path = DEFAULT_SNAPSHOT_LOG,
) -> dict:
    """Fit a linear trend to historical used_bytes over time and project it
    forward `days_ahead` days.

    Returns {"status": "insufficient_data", ...} rather than extrapolating
    from too few points to mean anything. Otherwise returns "status": "ok"
    plus the fitted trend and its projections - every number here comes
    straight from the linear fit, nothing is hidden.
    """
    snapshots = load_snapshots(path, snapshot_log_path)

    if len(snapshots) < MIN_SNAPSHOTS_FOR_FORECAST:
        return {
            "status": "insufficient_data",
            "snapshots_available": len(snapshots),
            "snapshots_needed": MIN_SNAPSHOTS_FOR_FORECAST,
        }

    timestamps = [datetime.fromisoformat(s["timestamp"]) for s in snapshots]
    earliest = timestamps[0]
    days_since_start = np.array(
        [(t - earliest).total_seconds() / 86400.0 for t in timestamps]
    )
    used_bytes = np.array([s["used_bytes"] for s in snapshots], dtype=float)
    total_bytes = snapshots[-1]["total_bytes"]

    slope, intercept = np.polyfit(days_since_start, used_bytes, 1)

    current_day = days_since_start[-1]
    current_used_bytes = used_bytes[-1]
    current_used_percent = (current_used_bytes / total_bytes * 100.0) if total_bytes else 0.0

    projected_used_bytes = slope * (current_day + days_ahead) + intercept
    projected_used_percent = (projected_used_bytes / total_bytes * 100.0) if total_bytes else 0.0

    # A flat or decreasing trend never reaches 100% - reporting a negative
    # or infinite "days until full" would be nonsensical, so None instead.
    days_until_full = None
    if slope > 0 and total_bytes:
        day_trend_reaches_full = (total_bytes - intercept) / slope
        remaining_days = day_trend_reaches_full - current_day
        if remaining_days > 0:
            days_until_full = remaining_days

    return {
        "status": "ok",
        "current_used_percent": current_used_percent,
        f"projected_used_percent_in_{days_ahead}_days": projected_used_percent,
        "trend_bytes_per_day": slope,
        "days_until_full": days_until_full,
    }


def generate_synthetic_history(
    path: str,
    days: int = 60,
    starting_used_percent: float = 40.0,
    daily_growth_percent: float = 0.8,
    noise_std: float = 0.3,
    snapshot_log_path: str | Path = DEFAULT_SNAPSHOT_LOG,
) -> None:
    """Seed a believable demo dataset of `days` past usage snapshots.

    FOR DEMO/DEV USE ONLY - this is not a production code path. It writes
    `days` synthetic snapshots into the past following a linear growth
    curve plus gaussian noise, so a capacity-forecasting demo has a
    believable trend to show instead of one real (and likely flat or
    empty) data point. `total_bytes` comes from a real get_disk_usage()
    call, so the numbers stay consistent with whatever machine this is run
    on; only `used_bytes` is synthetic.
    """
    total_bytes = get_disk_usage(path)["total_bytes"]
    now = datetime.now()

    for i in range(days):
        days_ago = days - 1 - i
        timestamp = now - timedelta(days=days_ago)

        used_percent = starting_used_percent + daily_growth_percent * i
        used_percent += np.random.normal(0, noise_std)
        used_percent = max(0.0, min(used_percent, 100.0))

        used_bytes = int(total_bytes * used_percent / 100.0)

        record_usage_snapshot(
            path,
            used_bytes=used_bytes,
            total_bytes=total_bytes,
            timestamp=timestamp,
            snapshot_log_path=snapshot_log_path,
        )
