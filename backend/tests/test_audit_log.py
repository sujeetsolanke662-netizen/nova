import json
from pathlib import Path

import pytest

from backend.app.audit_log import (
    GENESIS_HASH,
    append_entry,
    read_log,
    verify_chain,
)


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "audit_log.jsonl"


def test_appending_multiple_entries_builds_valid_chain(log_path):
    append_entry("recommend", ["/home/user/Downloads/old.dmg"], "stale, not opened in 200 days", log_path=log_path)
    append_entry("quarantine", ["/home/user/Downloads/old.dmg"], "moved to quarantine after approval", log_path=log_path)
    append_entry(
        "guardrail_block",
        ["/home/user/.ssh/id_rsa"],
        "protected path, refused to act",
        actor="user:yash",
        log_path=log_path,
    )

    ok, bad_id = verify_chain(log_path)
    assert ok is True
    assert bad_id is None

    entries = read_log(log_path)
    assert len(entries) == 3


def test_genesis_entry_has_all_zero_prev_hash(log_path):
    entry = append_entry("recommend", ["/tmp/a.txt"], "exact duplicate, 100% confidence", log_path=log_path)

    assert entry["entry_id"] == 0
    assert entry["prev_hash"] == GENESIS_HASH
    assert entry["prev_hash"] == "0" * 64


def test_second_entry_chains_to_first(log_path):
    first = append_entry("recommend", ["/tmp/a.txt"], "reason one", log_path=log_path)
    second = append_entry("restore", ["/tmp/a.txt"], "reason two", log_path=log_path)

    assert second["entry_id"] == 1
    assert second["prev_hash"] == first["entry_hash"]


def test_tampering_with_a_field_is_detected(log_path):
    append_entry("recommend", ["/tmp/a.txt"], "original reason", log_path=log_path)
    append_entry("quarantine", ["/tmp/a.txt"], "second reason", log_path=log_path)
    append_entry("restore", ["/tmp/a.txt"], "third reason", log_path=log_path)

    lines = log_path.read_text().splitlines()
    tampered = json.loads(lines[1])
    tampered["reason"] = "tampered reason - never happened"
    lines[1] = json.dumps(tampered, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n")

    ok, bad_id = verify_chain(log_path)
    assert ok is False
    assert bad_id == 1


def test_deleting_middle_entry_breaks_chain_at_right_point(log_path):
    append_entry("recommend", ["/tmp/a.txt"], "reason zero", log_path=log_path)
    append_entry("quarantine", ["/tmp/a.txt"], "reason one", log_path=log_path)
    append_entry("restore", ["/tmp/a.txt"], "reason two", log_path=log_path)
    append_entry("auto_apply", ["/tmp/a.txt"], "reason three", log_path=log_path)

    lines = log_path.read_text().splitlines()
    # Delete entry_id 1 (the second line), leaving entries 0, 2, 3.
    del lines[1]
    log_path.write_text("\n".join(lines) + "\n")

    ok, bad_id = verify_chain(log_path)
    assert ok is False
    # The break is detected at the entry immediately following the gap,
    # since its prev_hash no longer matches the (now different) preceding
    # entry's hash.
    assert bad_id == 2


def test_empty_or_nonexistent_log_verifies_as_trivially_valid(log_path):
    ok, bad_id = verify_chain(log_path)
    assert ok is True
    assert bad_id is None
    assert read_log(log_path) == []

    log_path.write_text("")
    ok, bad_id = verify_chain(log_path)
    assert ok is True
    assert bad_id is None


def test_read_log_returns_entries_in_order_with_expected_fields(log_path):
    append_entry(
        "recommend",
        ["/home/user/Downloads/dup1.zip", "/home/user/Downloads/dup2.zip"],
        "exact duplicate, 100% confidence",
        actor="nova_engine",
        log_path=log_path,
    )
    append_entry(
        "auto_apply",
        ["/home/user/Downloads/dup2.zip"],
        "staleness score 0.91, not opened in 214 days",
        actor="user:yash",
        log_path=log_path,
    )

    entries = read_log(log_path)

    assert [e["entry_id"] for e in entries] == [0, 1]

    expected_keys = {
        "entry_id",
        "timestamp",
        "action_type",
        "target_paths",
        "reason",
        "actor",
        "prev_hash",
        "entry_hash",
    }
    for entry in entries:
        assert set(entry.keys()) == expected_keys

    assert entries[0]["action_type"] == "recommend"
    assert entries[0]["target_paths"] == [
        "/home/user/Downloads/dup1.zip",
        "/home/user/Downloads/dup2.zip",
    ]
    assert entries[0]["actor"] == "nova_engine"

    assert entries[1]["action_type"] == "auto_apply"
    assert entries[1]["reason"] == "staleness score 0.91, not opened in 214 days"
    assert entries[1]["actor"] == "user:yash"
    assert entries[1]["prev_hash"] == entries[0]["entry_hash"]
