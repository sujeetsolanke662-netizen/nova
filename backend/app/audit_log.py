"""Tamper-evident, append-only audit log for every action NOVA takes.

Entries are stored as JSON Lines (one JSON object per line) in a hash chain:
each entry commits to the hash of the entry before it, so editing, deleting,
reordering, or inserting a past entry changes a hash somewhere down the
chain and is detectable by ``verify_chain``. This is the same idea as a
lightweight blockchain ledger, without any of the distributed/consensus
machinery - it's just a local, append-only, self-checking log.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None

GENESIS_HASH = "0" * 64

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "audit_log.jsonl"


def _canonical_bytes(entry_without_hash: dict) -> bytes:
    """Canonical JSON serialization used as the hash input.

    Sorted keys and no whitespace ambiguity (compact separators), so the
    same logical content always hashes to the same bytes regardless of how
    the dict was built.
    """
    return json.dumps(entry_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_entry_hash(entry_without_hash: dict) -> str:
    return hashlib.sha256(_canonical_bytes(entry_without_hash)).hexdigest()


def _locked_file(path: Path, mode: str):
    f = open(path, mode)
    if fcntl is not None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    return f


def append_entry(
    action_type: str,
    target_paths: list[str],
    reason: str,
    actor: str = "nova_engine",
    log_path: str | Path = DEFAULT_LOG_PATH,
) -> dict:
    """Append a new tamper-evident entry to the audit log.

    Opens the log file for append with an exclusive lock held across the
    read-last-entry + write-new-entry sequence, so concurrent writers from
    a single process can't interleave and corrupt the hash chain.
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Open in r+ (creating the file first if needed) so we can hold one lock
    # across both reading the previous tail and appending the new line.
    log_path.touch(exist_ok=True)

    with _locked_file(log_path, "r+") as f:
        prev_hash = GENESIS_HASH
        next_id = 0

        lines = [line for line in f.read().splitlines() if line.strip()]
        if lines:
            last_entry = json.loads(lines[-1])
            prev_hash = last_entry["entry_hash"]
            next_id = last_entry["entry_id"] + 1

        entry_without_hash = {
            "entry_id": next_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "target_paths": list(target_paths),
            "reason": reason,
            "actor": actor,
            "prev_hash": prev_hash,
        }
        entry_hash = _compute_entry_hash(entry_without_hash)
        entry = {**entry_without_hash, "entry_hash": entry_hash}

        f.seek(0, os.SEEK_END)
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())

    return entry


def read_log(log_path: str | Path = DEFAULT_LOG_PATH) -> list[dict]:
    """Return all entries from the log, in order."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []

    with _locked_file(log_path, "r") as f:
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        lines = [line for line in f.read().splitlines() if line.strip()]

    return [json.loads(line) for line in lines]


def verify_chain(log_path: str | Path = DEFAULT_LOG_PATH) -> tuple[bool, int | None]:
    """Verify the integrity of the whole hash chain.

    For each entry, recomputes its hash from its own content and checks:
      1. it matches the entry's stored entry_hash (content wasn't edited)
      2. its prev_hash matches the previous entry's entry_hash (nothing was
         deleted, reordered, or inserted between them)

    Returns (True, None) if everything checks out, or (False, entry_id) for
    the first entry where a check fails. An empty or missing log is
    trivially valid.
    """
    entries = read_log(log_path)
    if not entries:
        return True, None

    expected_prev_hash = GENESIS_HASH
    for entry in entries:
        entry_id = entry.get("entry_id")

        entry_without_hash = {k: v for k, v in entry.items() if k != "entry_hash"}
        recomputed_hash = _compute_entry_hash(entry_without_hash)

        if recomputed_hash != entry.get("entry_hash"):
            return False, entry_id

        if entry.get("prev_hash") != expected_prev_hash:
            return False, entry_id

        expected_prev_hash = entry["entry_hash"]

    return True, None
