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


def _read_last_line_bytes(f) -> bytes | None:
    """Read just the last non-empty line of an open binary file.

    Seeks backward from the end in fixed-size chunks rather than loading
    the whole file, so the cost of finding the tail is bounded by the
    length of the last line (almost always one chunk), not by total file
    size. `f` must be a binary-mode file object.
    """
    f.seek(0, os.SEEK_END)
    file_size = f.tell()
    if file_size == 0:
        return None

    chunk_size = 4096
    position = file_size
    data = b""

    while position > 0:
        read_size = min(chunk_size, position)
        position -= read_size
        f.seek(position)
        data = f.read(read_size) + data

        stripped = data.rstrip(b"\n")
        if b"\n" in stripped:
            return stripped.rsplit(b"\n", 1)[-1]
        if position == 0:
            return stripped if stripped else None

    return None


def _load_tail_from_disk(f) -> tuple[int, str]:
    """Determine (next_entry_id, prev_hash) from just the log's last line.

    Falls back to genesis (entry_id 0, all-zero prev_hash) if the file has
    no entries yet - same as the empty-file case always has.
    """
    last_line = _read_last_line_bytes(f)
    if not last_line:
        return 0, GENESIS_HASH

    last_entry = json.loads(last_line.decode("utf-8"))
    return last_entry["entry_id"] + 1, last_entry["entry_hash"]


# In-memory cache of (next_entry_id, prev_hash) per log_path, populated on
# first use per process and updated directly after each append - see
# append_entry()'s docstring for why. Keyed by resolved absolute path so
# different spellings of the same file share one entry.
_append_cache: dict[str, tuple[int, str]] = {}


def _reset_append_cache(log_path: str | Path | None = None) -> None:
    """Clear append_entry()'s in-memory tail cache.

    Pass a specific log_path to drop just that entry, or omit it to clear
    everything. Tests that hand-edit a log file or otherwise change it on
    disk outside append_entry() itself must call this first - otherwise a
    stale cached (next_entry_id, prev_hash) from an earlier call would
    silently paper over the change instead of picking it back up.
    """
    if log_path is None:
        _append_cache.clear()
    else:
        _append_cache.pop(str(Path(log_path).resolve()), None)


def append_entry(
    action_type: str,
    target_paths: list[str],
    reason: str,
    actor: str = "nova_engine",
    log_path: str | Path = DEFAULT_LOG_PATH,
) -> dict:
    """Append a new tamper-evident entry to the audit log.

    Opens the log file for append with an exclusive lock held across the
    whole read-previous-entry + write-new-entry sequence, so concurrent
    writers from a single process can't interleave and corrupt the hash
    chain. That's true whether or not the cache below is warm: the lock is
    grabbed unconditionally, before the cache is even consulted, so it
    still serializes concurrent callers exactly as before.

    The previous entry's hash and the next entry_id are cached in memory
    per log_path after the first call, instead of re-reading and
    re-parsing the *entire* file on every append - that was O(n) per call
    and O(n^2) over a run appending n entries, which is what
    backend/scripts/benchmark_scan.py's numbers surfaced. On a cache miss
    (first call for this log_path in this process, or after
    _reset_append_cache()), this still only reads the file's last line
    (see _read_last_line_bytes), never the whole thing. verify_chain() is
    intentionally untouched by any of this - it's the one place that must
    always re-derive trust from the full file on disk, never from this
    cache.
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch(exist_ok=True)

    cache_key = str(log_path.resolve())

    with _locked_file(log_path, "rb+") as f:
        cached = _append_cache.get(cache_key)
        if cached is None:
            next_id, prev_hash = _load_tail_from_disk(f)
        else:
            next_id, prev_hash = cached

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
        f.write((json.dumps(entry, sort_keys=True) + "\n").encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())

        _append_cache[cache_key] = (next_id + 1, entry_hash)

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
