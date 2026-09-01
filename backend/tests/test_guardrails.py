from pathlib import Path

import pytest
import yaml

from backend.app.guardrails import (
    classify_path,
    is_protected,
    load_protected_patterns,
    OUTSIDE_SCAN_SCOPE,
    PROTECTED,
    REVIEWABLE,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "protected_paths.yaml"


@pytest.fixture(scope="module")
def patterns():
    return load_protected_patterns(str(CONFIG_PATH))


@pytest.fixture(autouse=True)
def audit_calls(monkeypatch):
    """Capture audit_log.append_entry calls instead of touching real disk.

    Autouse so no test in this file - existing or new - accidentally writes
    to the real audit log file just because it happens to exercise a
    protected-path code path.
    """
    calls = []

    def fake_append_entry(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr("backend.app.guardrails.audit_log.append_entry", fake_append_entry)
    return calls


def test_config_loads_correctly(patterns):
    assert len(patterns) > 0
    categories = {entry["category"] for entry in patterns}
    assert {
        "ssh_keys",
        "gpg",
        "git_internals",
        "system",
        "encrypted_or_external_mounts",
    } <= categories
    for entry in patterns:
        assert set(entry.keys()) >= {"pattern", "category", "reason"}
        assert entry["reason"]  # non-empty, human-readable


def test_malformed_yaml_raises_clear_error(tmp_path):
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text("patterns: [this is: not, valid: yaml")

    with pytest.raises(ValueError, match="Malformed YAML"):
        load_protected_patterns(str(bad_config))


def test_missing_patterns_key_raises_clear_error(tmp_path):
    config = tmp_path / "no_patterns.yaml"
    config.write_text(yaml.safe_dump({"something_else": []}))

    with pytest.raises(ValueError, match="top-level 'patterns' list"):
        load_protected_patterns(str(config))


def test_ssh_key_is_protected(patterns, audit_calls):
    ssh_key = Path.home() / ".ssh" / "id_rsa"

    protected, reason = is_protected(str(ssh_key), patterns)

    assert protected is True
    assert "ssh" in reason.lower() or "lock" in reason.lower()

    # log defaults to False - a protection check by itself must not write
    # to the audit log unless the caller opts in.
    assert audit_calls == []


def test_git_internal_file_is_protected(tmp_path, patterns, audit_calls):
    git_file = tmp_path / "myrepo" / ".git" / "HEAD"
    git_file.parent.mkdir(parents=True)
    git_file.write_text("ref: refs/heads/main\n")

    protected, reason = is_protected(str(git_file), patterns)

    assert protected is True
    assert "git" in reason.lower() or "repository" in reason.lower()
    assert audit_calls == []


def test_normal_file_in_scan_root_is_reviewable(tmp_path, patterns, audit_calls):
    scan_root = tmp_path / "Downloads"
    scan_root.mkdir()
    normal_file = scan_root / "old_installer.dmg"
    normal_file.write_text("not actually a dmg")

    result = classify_path(str(normal_file), patterns, [str(scan_root)])

    assert result == REVIEWABLE
    # Not protected, so no guardrail_block entry should be logged.
    assert audit_calls == []


def test_file_outside_scan_roots_is_outside_scan_scope(tmp_path, patterns):
    scan_root = tmp_path / "Downloads"
    scan_root.mkdir()
    other_dir = tmp_path / "SomewhereElse"
    other_dir.mkdir()
    outside_file = other_dir / "file.txt"
    outside_file.write_text("hello")

    result = classify_path(str(outside_file), patterns, [str(scan_root)])

    assert result == OUTSIDE_SCAN_SCOPE


def test_symlink_resolving_into_protected_dir_is_caught(tmp_path):
    # Use a config scoped to this test's own tmp_path so we don't need to
    # touch real system directories to prove the point: an innocent-looking
    # path that *resolves* into a protected directory must still be caught.
    vault = tmp_path / "vault"
    vault.mkdir()
    secret = vault / "secret.txt"
    secret.write_text("do not touch")

    custom_patterns = [
        {
            "pattern": str(vault) + "/**",
            "category": "test_vault",
            "reason": "test-only protected vault",
        }
    ]

    innocent_dir = tmp_path / "totally_normal_folder"
    innocent_dir.symlink_to(vault, target_is_directory=True)
    innocent_path = innocent_dir / "secret.txt"

    protected, reason = is_protected(str(innocent_path), custom_patterns)

    assert protected is True
    assert reason == "test-only protected vault"


def test_symlinked_protected_path_is_classified_as_protected_even_in_scan_root(tmp_path, audit_calls):
    vault = tmp_path / "vault"
    vault.mkdir()
    secret = vault / "secret.txt"
    secret.write_text("do not touch")

    custom_patterns = [
        {
            "pattern": str(vault) + "/**",
            "category": "test_vault",
            "reason": "test-only protected vault",
        }
    ]

    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    link = scan_root / "looks_safe.txt"
    link.symlink_to(secret)

    result = classify_path(str(link), custom_patterns, [str(scan_root)])

    assert result == PROTECTED
    # log defaults to False here too, passed through from classify_path.
    assert audit_calls == []


# --- log parameter: opt-in audit logging ---


def test_is_protected_log_false_does_not_write_audit_entry(patterns, audit_calls):
    ssh_key = Path.home() / ".ssh" / "id_rsa"

    protected, _reason = is_protected(str(ssh_key), patterns, log=False)

    assert protected is True
    assert audit_calls == []


def test_is_protected_log_true_writes_audit_entry(patterns, audit_calls):
    ssh_key = Path.home() / ".ssh" / "id_rsa"

    protected, reason = is_protected(str(ssh_key), patterns, log=True)

    assert protected is True
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["action_type"] == "guardrail_block"
    assert call["target_paths"] == [str(ssh_key.expanduser().resolve(strict=False))]
    assert call["reason"] == reason


def test_is_protected_log_true_on_non_matching_path_does_not_log(tmp_path, patterns, audit_calls):
    normal_file = tmp_path / "notes.txt"
    normal_file.write_text("hello")

    protected, reason = is_protected(str(normal_file), patterns, log=True)

    assert protected is False
    assert reason is None
    # log=True only writes an entry when the path actually matches -
    # there's nothing to log about a path that wasn't blocked.
    assert audit_calls == []


def test_classify_path_log_true_writes_audit_entry_for_protected_path(tmp_path, audit_calls):
    vault = tmp_path / "vault"
    vault.mkdir()
    secret = vault / "secret.txt"
    secret.write_text("do not touch")

    custom_patterns = [
        {
            "pattern": str(vault) + "/**",
            "category": "test_vault",
            "reason": "test-only protected vault",
        }
    ]

    result = classify_path(str(secret), custom_patterns, [], log=True)

    assert result == PROTECTED
    assert len(audit_calls) == 1
    assert audit_calls[0]["action_type"] == "guardrail_block"
    assert audit_calls[0]["reason"] == "test-only protected vault"


def test_classify_path_log_defaults_to_false(tmp_path, audit_calls):
    vault = tmp_path / "vault"
    vault.mkdir()
    secret = vault / "secret.txt"
    secret.write_text("do not touch")

    custom_patterns = [
        {
            "pattern": str(vault) + "/**",
            "category": "test_vault",
            "reason": "test-only protected vault",
        }
    ]

    result = classify_path(str(secret), custom_patterns, [])

    assert result == PROTECTED
    assert audit_calls == []
