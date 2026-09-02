from pathlib import Path

import pytest

from backend.app.quarantine import (
    QuarantineError,
    list_quarantined,
    quarantine_file,
    read_manifest,
    restore_file,
)

PROTECTED_PATTERNS = [
    {
        "pattern": "**/.git/**",
        "category": "git_internals",
        "reason": "Git internal object store and metadata.",
    }
]


@pytest.fixture
def paths(tmp_path):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    quarantine_dir = tmp_path / "quarantine"
    manifest_path = tmp_path / "quarantine_manifest.jsonl"
    audit_log_path = tmp_path / "audit_log.jsonl"
    return {
        "scan_root": scan_root,
        "quarantine_dir": quarantine_dir,
        "manifest_path": manifest_path,
        "audit_log_path": audit_log_path,
    }


def _quarantine(path: Path, reason, paths, scan_roots=None):
    return quarantine_file(
        str(path),
        reason,
        PROTECTED_PATTERNS,
        scan_roots if scan_roots is not None else [str(paths["scan_root"])],
        quarantine_dir=paths["quarantine_dir"],
        manifest_path=paths["manifest_path"],
        audit_log_path=paths["audit_log_path"],
    )


def test_quarantining_a_file_moves_it_to_quarantine_dir(paths):
    target = paths["scan_root"] / "old_download.dmg"
    target.write_text("some bytes")

    entry = _quarantine(target, "stale, not opened in 200 days", paths)

    assert not target.exists()
    quarantined_path = Path(entry["quarantined_path"])
    assert quarantined_path.exists()
    assert quarantined_path.read_text() == "some bytes"
    assert quarantined_path.parent == paths["quarantine_dir"]

    assert entry["original_path"] == str(target.resolve())
    assert entry["status"] == "quarantined"
    assert entry["reason"] == "stale, not opened in 200 days"
    assert "quarantine_id" in entry


def test_quarantining_two_files_with_same_basename_does_not_collide(paths):
    sub_a = paths["scan_root"] / "a"
    sub_b = paths["scan_root"] / "b"
    sub_a.mkdir()
    sub_b.mkdir()
    file_a = sub_a / "notes.txt"
    file_b = sub_b / "notes.txt"
    file_a.write_text("from a")
    file_b.write_text("from b")

    entry_a = _quarantine(file_a, "reason a", paths)
    entry_b = _quarantine(file_b, "reason b", paths)

    assert Path(entry_a["quarantined_path"]).read_text() == "from a"
    assert Path(entry_b["quarantined_path"]).read_text() == "from b"
    assert entry_a["quarantined_path"] != entry_b["quarantined_path"]


def test_quarantining_a_protected_file_is_refused_and_not_moved(paths):
    git_dir = paths["scan_root"] / ".git"
    git_dir.mkdir()
    protected_file = git_dir / "config"
    protected_file.write_text("git internals")

    with pytest.raises(QuarantineError):
        _quarantine(protected_file, "attempted quarantine of protected file", paths)

    assert protected_file.exists()
    assert protected_file.read_text() == "git internals"
    assert list_quarantined(paths["manifest_path"]) == []


def test_quarantining_path_outside_scan_scope_is_refused(paths):
    outside = paths["scan_root"].parent / "outside.txt"
    outside.write_text("not in scope")

    with pytest.raises(QuarantineError):
        _quarantine(outside, "should not be allowed", paths)

    assert outside.exists()


def test_restoring_a_quarantined_file_moves_it_back(paths):
    target = paths["scan_root"] / "restore_me.txt"
    target.write_text("payload")

    entry = _quarantine(target, "test reason", paths)
    restored = restore_file(
        entry["quarantine_id"],
        manifest_path=paths["manifest_path"],
        audit_log_path=paths["audit_log_path"],
    )

    assert restored["status"] == "restored"
    assert target.exists()
    assert target.read_text() == "payload"
    assert not Path(entry["quarantined_path"]).exists()


def test_restoring_an_already_restored_id_raises(paths):
    target = paths["scan_root"] / "restore_twice.txt"
    target.write_text("payload")

    entry = _quarantine(target, "test reason", paths)
    restore_file(
        entry["quarantine_id"], manifest_path=paths["manifest_path"], audit_log_path=paths["audit_log_path"]
    )

    with pytest.raises(QuarantineError):
        restore_file(
            entry["quarantine_id"],
            manifest_path=paths["manifest_path"],
            audit_log_path=paths["audit_log_path"],
        )


def test_restoring_nonexistent_id_raises(paths):
    with pytest.raises(QuarantineError):
        restore_file(
            "00000000-0000-0000-0000-000000000000",
            manifest_path=paths["manifest_path"],
            audit_log_path=paths["audit_log_path"],
        )


def test_restoring_when_original_path_now_occupied_raises(paths):
    target = paths["scan_root"] / "reoccupied.txt"
    target.write_text("original payload")

    entry = _quarantine(target, "test reason", paths)

    # Something new now lives at the original path.
    target.write_text("new file, unrelated")

    with pytest.raises(QuarantineError):
        restore_file(
            entry["quarantine_id"],
            manifest_path=paths["manifest_path"],
            audit_log_path=paths["audit_log_path"],
        )

    # The new occupant must survive untouched, and the quarantined copy
    # must not have been silently discarded either.
    assert target.read_text() == "new file, unrelated"
    assert Path(entry["quarantined_path"]).exists()
    assert Path(entry["quarantined_path"]).read_text() == "original payload"


def test_list_quarantined_only_shows_currently_quarantined_items(paths):
    target1 = paths["scan_root"] / "one.txt"
    target2 = paths["scan_root"] / "two.txt"
    target1.write_text("1")
    target2.write_text("2")

    entry1 = _quarantine(target1, "reason 1", paths)
    entry2 = _quarantine(target2, "reason 2", paths)

    restore_file(
        entry1["quarantine_id"], manifest_path=paths["manifest_path"], audit_log_path=paths["audit_log_path"]
    )

    active = list_quarantined(paths["manifest_path"])
    active_ids = {e["quarantine_id"] for e in active}

    assert active_ids == {entry2["quarantine_id"]}


def test_read_manifest_returns_latest_status_per_id(paths):
    target = paths["scan_root"] / "history.txt"
    target.write_text("data")

    entry = _quarantine(target, "reason", paths)
    restore_file(
        entry["quarantine_id"], manifest_path=paths["manifest_path"], audit_log_path=paths["audit_log_path"]
    )

    all_entries = read_manifest(paths["manifest_path"])
    matching = [e for e in all_entries if e["quarantine_id"] == entry["quarantine_id"]]

    # Only the latest state for this id should be returned, not both lines.
    assert len(matching) == 1
    assert matching[0]["status"] == "restored"


def test_quarantine_and_restore_are_recorded_in_audit_log(paths):
    from backend.app.audit_log import read_log

    target = paths["scan_root"] / "audited.txt"
    target.write_text("data")

    entry = _quarantine(target, "audit reason", paths)
    restore_file(
        entry["quarantine_id"], manifest_path=paths["manifest_path"], audit_log_path=paths["audit_log_path"]
    )

    entries = read_log(paths["audit_log_path"])
    action_types = [e["action_type"] for e in entries]

    assert "quarantine" in action_types
    assert "restore" in action_types
