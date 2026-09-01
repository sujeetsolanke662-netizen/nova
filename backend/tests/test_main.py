from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(autouse=True)
def audit_calls(monkeypatch):
    """Capture (rather than really write) any audit_log.append_entry call.

    Mocked here (same pattern as test_guardrails.py) so exercising the
    /api/guardrails/check endpoint in these tests never touches real disk,
    and so tests can assert on whether a call happened at all.
    """
    calls = []

    def fake_append_entry(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr("backend.app.guardrails.audit_log.append_entry", fake_append_entry)
    return calls


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A TestClient with scan roots and the audit log pointed at tmp_path.

    Env vars are set before the client (and therefore the lifespan
    handler, which reads get_settings() on startup) is created, so each
    test gets an isolated Settings without touching real machine state.
    """
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    audit_log_path = tmp_path / "audit_log.jsonl"

    monkeypatch.setenv("NOVA_SCAN_ROOTS", str(scan_root))
    monkeypatch.setenv("NOVA_AUDIT_LOG_PATH", str(audit_log_path))

    with TestClient(app) as test_client:
        yield test_client, scan_root, audit_log_path


def test_health_returns_ok():
    with TestClient(app) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_guardrails_check_classifies_protected_path(client):
    test_client, _scan_root, _audit_log_path = client
    ssh_key = str(Path.home() / ".ssh" / "id_rsa")

    response = test_client.get("/api/guardrails/check", params={"path": ssh_key})

    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "protected"
    assert body["reason"]
    assert "ssh" in body["reason"].lower() or "lock" in body["reason"].lower()


def test_guardrails_check_never_writes_audit_entry_even_when_repeated(client, audit_calls):
    test_client, _scan_root, _audit_log_path = client
    ssh_key = str(Path.home() / ".ssh" / "id_rsa")

    for _ in range(3):
        response = test_client.get("/api/guardrails/check", params={"path": ssh_key})
        assert response.status_code == 200
        assert response.json()["classification"] == "protected"

    # Read-only inspection must never log, no matter how many times the
    # same protected path is checked - see the log=False comment on this
    # endpoint in main.py.
    assert audit_calls == []


def test_guardrails_check_classifies_reviewable_path(client):
    test_client, scan_root, _audit_log_path = client
    normal_file = scan_root / "old_installer.dmg"
    normal_file.write_text("not actually a dmg")

    response = test_client.get("/api/guardrails/check", params={"path": str(normal_file)})

    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "reviewable"
    assert body["reason"] is None


def test_apt_clutter_scan_returns_list(client, monkeypatch):
    test_client, _scan_root, _audit_log_path = client

    fake_findings = [
        {
            "category": "orphaned_package",
            "description": "'foo' is no longer required by any installed package.",
            "estimated_size_bytes": 123,
            "safe_to_auto_apply": False,
            "target_paths": ["foo"],
        }
    ]
    monkeypatch.setattr("backend.app.main.scan_apt_clutter", lambda: fake_findings)

    response = test_client.get("/api/apt-clutter/scan")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body == fake_findings


def test_audit_log_verify_valid_on_fresh_empty_log(client):
    test_client, _scan_root, audit_log_path = client
    assert not audit_log_path.exists()

    response = test_client.get("/api/audit-log/verify")

    assert response.status_code == 200
    assert response.json() == {"valid": True, "broken_at_entry": None}


def test_audit_log_endpoint_returns_empty_list_for_fresh_log(client):
    test_client, _scan_root, _audit_log_path = client

    response = test_client.get("/api/audit-log")

    assert response.status_code == 200
    assert response.json() == []
