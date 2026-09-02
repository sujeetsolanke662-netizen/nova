"""Quarantine action engine: the only place NOVA actually moves a file.

Everything upstream of this module (recommendation.py, guardrails.py) only
scores and classifies - it never touches the filesystem. This module is
where a recommendation turns into a real, but reversible, action: the
file is moved (not deleted) into a quarantine directory, and a manifest
records enough to move it straight back.

The manifest is a JSON-Lines, append-only log - the same pattern as
audit_log.py - so history is never mutated in place. A quarantine item's
current state is derived by taking the LATEST manifest line for its
quarantine_id (see ``read_manifest``), not by editing a single row.

CRITICAL invariant: ``quarantine_file`` re-checks ``classify_path`` itself
before touching the filesystem. It never trusts that a caller (e.g. an API
handler acting on a recommendation) already checked - this function is the
last line of defense before a real, hard-to-reverse filesystem change.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import audit_log
from .audit_log import DEFAULT_LOG_PATH
from .guardrails import REVIEWABLE, classify_path

DEFAULT_QUARANTINE_DIR = Path(__file__).resolve().parent.parent / "data" / "quarantine"
DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "quarantine_manifest.jsonl"

STATUS_QUARANTINED = "quarantined"
STATUS_RESTORED = "restored"
STATUS_PURGED = "purged"


class QuarantineError(Exception):
    """Raised when a quarantine or restore action can't be safely performed."""


def _append_manifest_line(entry: dict, manifest_path: str | Path) -> None:
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_manifest(manifest_path: str | Path = DEFAULT_MANIFEST_PATH) -> list[dict]:
    """Return the latest manifest entry per quarantine_id, in first-seen order.

    The manifest is append-only: restoring or purging an item appends a new
    line rather than mutating the original "quarantined" line. Callers care
    about current state, so this collapses each quarantine_id down to its
    most recently appended entry.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return []

    lines = [line for line in manifest_path.read_text().splitlines() if line.strip()]

    latest_by_id: dict[str, dict] = {}
    order: list[str] = []
    for line in lines:
        entry = json.loads(line)
        qid = entry["quarantine_id"]
        if qid not in latest_by_id:
            order.append(qid)
        latest_by_id[qid] = entry

    return [latest_by_id[qid] for qid in order]


def quarantine_file(
    path: str,
    reason: str,
    protected_patterns: list[dict],
    scan_roots: list[str],
    quarantine_dir: str | Path = DEFAULT_QUARANTINE_DIR,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    audit_log_path: str | Path = DEFAULT_LOG_PATH,
) -> dict:
    """Move ``path`` into quarantine, recording a manifest entry.

    Re-checks ``classify_path`` with ``log=True`` before doing anything -
    this is the real enforcement point for a filesystem-changing action, so
    a block must land in the audit trail exactly like recommendation.py's
    own re-check does. If the path isn't "reviewable" (i.e. it's protected,
    or outside any configured scan root), this raises QuarantineError and
    never touches the filesystem.
    """
    resolved = Path(path).expanduser().resolve(strict=False)

    classification = classify_path(
        str(resolved), protected_patterns, scan_roots, log=True, log_path=audit_log_path
    )
    if classification != REVIEWABLE:
        raise QuarantineError(
            f"Refusing to quarantine '{resolved}': classified as '{classification}', "
            f"not 'reviewable'."
        )

    if not resolved.is_file():
        raise QuarantineError(f"Cannot quarantine '{resolved}': not a file, or does not exist.")

    quarantine_dir = Path(quarantine_dir)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    quarantine_id = str(uuid.uuid4())
    quarantined_path = quarantine_dir / f"{quarantine_id}_{resolved.name}"

    shutil.move(str(resolved), str(quarantined_path))

    entry = {
        "quarantine_id": quarantine_id,
        "original_path": str(resolved),
        "quarantined_path": str(quarantined_path),
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "status": STATUS_QUARANTINED,
    }
    _append_manifest_line(entry, manifest_path)

    audit_log.append_entry(
        action_type="quarantine",
        target_paths=[str(resolved)],
        reason=reason,
        log_path=audit_log_path,
    )

    return entry


def restore_file(
    quarantine_id: str,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    audit_log_path: str | Path = DEFAULT_LOG_PATH,
) -> dict:
    """Move a quarantined file back to its original location.

    Raises QuarantineError if the id is unknown, if it isn't currently in
    "quarantined" status (already restored or purged), or if something new
    now occupies the original path - restoring must never silently
    overwrite whatever is there now.
    """
    entries = read_manifest(manifest_path)
    latest = next((e for e in entries if e["quarantine_id"] == quarantine_id), None)

    if latest is None:
        raise QuarantineError(f"No quarantine entry found with id '{quarantine_id}'.")

    if latest["status"] != STATUS_QUARANTINED:
        raise QuarantineError(
            f"Cannot restore '{quarantine_id}': current status is "
            f"'{latest['status']}', not 'quarantined'."
        )

    original_path = Path(latest["original_path"])
    quarantined_path = Path(latest["quarantined_path"])

    if original_path.exists():
        raise QuarantineError(
            f"Cannot restore '{quarantine_id}': something already exists at "
            f"'{original_path}'. Refusing to overwrite it."
        )

    if not quarantined_path.exists():
        raise QuarantineError(
            f"Cannot restore '{quarantine_id}': quarantined file is missing at "
            f"'{quarantined_path}'."
        )

    original_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(quarantined_path), str(original_path))

    updated_entry = {**latest, "status": STATUS_RESTORED}
    _append_manifest_line(updated_entry, manifest_path)

    audit_log.append_entry(
        action_type="restore",
        target_paths=[str(original_path)],
        reason=f"restored from quarantine ({quarantine_id})",
        log_path=audit_log_path,
    )

    return updated_entry


def list_quarantined(manifest_path: str | Path = DEFAULT_MANIFEST_PATH) -> list[dict]:
    """Return the latest manifest entries currently in "quarantined" status."""
    return [e for e in read_manifest(manifest_path) if e["status"] == STATUS_QUARANTINED]
