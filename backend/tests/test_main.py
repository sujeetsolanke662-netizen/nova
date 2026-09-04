import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.app.audit_log import append_entry as real_append_entry
from backend.app.audit_log import read_log
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
    quarantine_dir = tmp_path / "quarantine"
    quarantine_manifest_path = tmp_path / "quarantine_manifest.jsonl"
    snapshot_log_path = tmp_path / "usage_snapshots.jsonl"

    monkeypatch.setenv("NOVA_SCAN_ROOTS", str(scan_root))
    monkeypatch.setenv("NOVA_AUDIT_LOG_PATH", str(audit_log_path))
    monkeypatch.setenv("NOVA_QUARANTINE_DIR", str(quarantine_dir))
    monkeypatch.setenv("NOVA_QUARANTINE_MANIFEST_PATH", str(quarantine_manifest_path))
    monkeypatch.setenv("NOVA_SNAPSHOT_LOG_PATH", str(snapshot_log_path))

    with TestClient(app) as test_client:
        yield test_client, scan_root, audit_log_path


def test_health_returns_ok():
    with TestClient(app) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["llm_available"], bool)


def test_lifespan_startup_loads_the_llm(monkeypatch):
    """The model must load once at boot (see main.py's lifespan handler),
    not lazily on the first /api/copilot/ask request - that's the whole
    point of the startup change: move the slow, unpredictable load cost
    off the request path. Mocked here rather than exercised for real so
    this test stays fast; the real load is covered by manual end-to-end
    verification."""
    mock_load_llm = Mock()
    monkeypatch.setattr("backend.app.main.load_llm", mock_load_llm)

    mock_load_llm.assert_not_called()

    with TestClient(app):
        pass

    mock_load_llm.assert_called_once()


def test_lifespan_startup_survives_missing_llm_model(monkeypatch, caplog):
    """A missing/misconfigured .gguf must never take the whole server
    down - main.py's lifespan handler must catch LLMModelNotFoundError
    specifically, log a clear warning, and keep booting normally. Forces
    a genuinely cold load attempt (rather than mocking load_llm() away,
    like test_lifespan_startup_loads_the_llm above) so this exercises the
    real path-check-then-raise behavior, not just the try/except shape."""
    monkeypatch.setattr("backend.app.llm_answer._llm_instance", None)
    monkeypatch.setenv("NOVA_LLM_MODEL_PATH", "/definitely/does/not/exist.gguf")

    with caplog.at_level(logging.WARNING, logger="backend.app.main"):
        with TestClient(app) as test_client:
            response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "llm_available": False}
    assert any("LLM model file not found" in record.message for record in caplog.records)


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


def test_apt_clutter_apply_endpoint_returns_result_on_success(client, monkeypatch):
    test_client, _scan_root, _audit_log_path = client

    finding = {
        "category": "stale_deb_cache",
        "description": "stale cache file",
        "estimated_size_bytes": 100,
        "safe_to_auto_apply": True,
        "target_paths": ["/var/cache/apt/archives/foo_1.0_amd64.deb"],
    }
    fake_result = {"applied": True, "finding": finding}

    captured = {}

    def fake_apply_finding(f, audit_log_path=None):
        captured["finding"] = f
        captured["audit_log_path"] = audit_log_path
        return fake_result

    monkeypatch.setattr("backend.app.main.apply_finding", fake_apply_finding)

    response = test_client.post("/api/apt-clutter/apply", json={"finding": finding})

    assert response.status_code == 200
    assert response.json() == fake_result
    assert captured["finding"] == finding
    assert str(captured["audit_log_path"]) == str(_audit_log_path)


def test_apt_clutter_apply_endpoint_maps_unsafe_apply_error_to_400(client, monkeypatch):
    test_client, _scan_root, _audit_log_path = client

    from backend.app.apt_clutter import UnsafeApplyError

    def fake_apply_finding(f, audit_log_path=None):
        raise UnsafeApplyError("not marked safe_to_auto_apply")

    monkeypatch.setattr("backend.app.main.apply_finding", fake_apply_finding)

    finding = {
        "category": "old_kernel",
        "description": "an old kernel",
        "estimated_size_bytes": 100,
        "safe_to_auto_apply": False,
        "target_paths": ["linux-image-old"],
    }

    response = test_client.post("/api/apt-clutter/apply", json={"finding": finding})

    assert response.status_code == 400
    assert "detail" in response.json()
    assert "safe_to_auto_apply" in response.json()["detail"]


def test_recommendations_valid_root_returns_expected_shape(client, monkeypatch):
    test_client, scan_root, _audit_log_path = client

    fake_result = {
        "scanned_count": 1,
        "skipped_count": 0,
        "protected_count": 0,
        "recommendations": [
            {
                "path": str(scan_root / "old.zip"),
                "recommended_action": "review_recommended",
                "staleness_score": 0.75,
                "factors": [],
                "duplicate_of": None,
                "near_duplicate_of": None,
            }
        ],
    }
    monkeypatch.setattr("backend.app.main.generate_recommendations", lambda *a, **k: fake_result)

    response = test_client.get("/api/recommendations", params={"root": str(scan_root)})

    assert response.status_code == 200
    assert response.json() == fake_result


def test_recommendations_nonexistent_root_returns_400(client):
    test_client, scan_root, _audit_log_path = client
    missing_root = scan_root / "does_not_exist"

    response = test_client.get("/api/recommendations", params={"root": str(missing_root)})

    assert response.status_code == 400
    assert "detail" in response.json()


def test_recommendations_root_outside_scan_roots_returns_400(client, tmp_path):
    test_client, _scan_root, _audit_log_path = client
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    response = test_client.get("/api/recommendations", params={"root": str(outside_dir)})

    assert response.status_code == 400
    assert "detail" in response.json()


def test_copilot_search_valid_query_returns_expected_shape(client, monkeypatch):
    test_client, scan_root, _audit_log_path = client

    fake_recommendation = {
        "path": str(scan_root / "old.zip"),
        "recommended_action": "review_recommended",
        "staleness_score": 0.75,
        "factors": [],
        "duplicate_of": None,
        "near_duplicate_of": None,
    }
    fake_generate_result = {
        "scanned_count": 1,
        "skipped_count": 0,
        "protected_count": 0,
        "recommendations": [fake_recommendation],
    }
    fake_search_result = [
        {"item": fake_recommendation, "rrf_score": 0.032, "sources": ["faiss", "bm25"]}
    ]

    monkeypatch.setattr(
        "backend.app.main.generate_recommendations", lambda *a, **k: fake_generate_result
    )
    # build_index would otherwise load the real SBERT model - mock it out
    # so this test stays fast; copilot_retrieval.py's own test suite
    # already covers build_index()/search() against the real models.
    monkeypatch.setattr("backend.app.main.build_index", lambda recommendations: {"fake": True})
    monkeypatch.setattr(
        "backend.app.main.search", lambda query, index, top_k: fake_search_result
    )

    response = test_client.get(
        "/api/copilot/search", params={"root": str(scan_root), "query": "old zip files"}
    )

    assert response.status_code == 200
    assert response.json() == fake_search_result


def test_copilot_search_empty_recommendations_returns_empty_list(client, monkeypatch):
    test_client, scan_root, _audit_log_path = client

    empty_result = {
        "scanned_count": 0,
        "skipped_count": 0,
        "protected_count": 0,
        "recommendations": [],
    }
    monkeypatch.setattr("backend.app.main.generate_recommendations", lambda *a, **k: empty_result)

    response = test_client.get(
        "/api/copilot/search", params={"root": str(scan_root), "query": "anything"}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_copilot_search_nonexistent_root_returns_400(client):
    test_client, scan_root, _audit_log_path = client
    missing_root = scan_root / "does_not_exist"

    response = test_client.get(
        "/api/copilot/search", params={"root": str(missing_root), "query": "anything"}
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_copilot_search_root_outside_scan_roots_returns_400(client, tmp_path):
    test_client, _scan_root, _audit_log_path = client
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    response = test_client.get(
        "/api/copilot/search", params={"root": str(outside_dir), "query": "anything"}
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_copilot_ask_valid_question_returns_expected_shape(client, monkeypatch):
    test_client, scan_root, _audit_log_path = client

    fake_recommendation = {
        "path": str(scan_root / "old.zip"),
        "recommended_action": "review_recommended",
        "staleness_score": 0.75,
        "factors": [{"name": "recency_factor", "contribution": 0.4, "explanation": "not accessed in 200 days"}],
        "duplicate_of": None,
        "near_duplicate_of": None,
    }
    fake_generate_result = {
        "scanned_count": 1,
        "skipped_count": 0,
        "protected_count": 0,
        "recommendations": [fake_recommendation],
    }
    fake_answer = {
        "answer_text": "Here's what appears to be using up your space: old.zip.",
        "cited_paths": [fake_recommendation["path"]],
        "intent": "why_full",
    }

    monkeypatch.setattr(
        "backend.app.main.generate_recommendations", lambda *a, **k: fake_generate_result
    )
    # build_index/answer_query would otherwise load real SBERT/cross-encoder
    # models - mocked out so this test stays fast; copilot_answer.py's own
    # test suite already covers answer_query() against the real models.
    monkeypatch.setattr("backend.app.main.build_index", lambda recommendations: {"fake": True})
    monkeypatch.setattr("backend.app.main.answer_query", lambda question, index: fake_answer)

    response = test_client.post(
        "/api/copilot/ask",
        json={"question": "why is my disk full", "root": str(scan_root)},
    )

    assert response.status_code == 200
    assert response.json() == fake_answer


def test_copilot_ask_empty_recommendations_returns_honest_no_results_answer(client, monkeypatch):
    test_client, scan_root, _audit_log_path = client

    empty_result = {
        "scanned_count": 0,
        "skipped_count": 0,
        "protected_count": 0,
        "recommendations": [],
    }
    monkeypatch.setattr("backend.app.main.generate_recommendations", lambda *a, **k: empty_result)

    response = test_client.post(
        "/api/copilot/ask", json={"question": "anything", "root": str(scan_root)}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cited_paths"] == []
    assert body["answer_text"]
    assert "intent" in body


def test_copilot_ask_nonexistent_root_returns_400(client):
    test_client, scan_root, _audit_log_path = client
    missing_root = scan_root / "does_not_exist"

    response = test_client.post(
        "/api/copilot/ask", json={"question": "anything", "root": str(missing_root)}
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_copilot_ask_root_outside_scan_roots_returns_400(client, tmp_path):
    test_client, _scan_root, _audit_log_path = client
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    response = test_client.post(
        "/api/copilot/ask", json={"question": "anything", "root": str(outside_dir)}
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_recommendation_audit_entries_are_visible_through_audit_log_endpoint(client, monkeypatch):
    """Regression test: generate_recommendations() must write its audit
    entries to the same log GET /api/audit-log reads from.

    Previously, generate_recommendations() (and the classify_path/
    is_protected calls it makes) always wrote to audit_log's hardcoded
    default log path, ignoring settings.audit_log_path entirely - so a
    real recommendation run would "succeed" and appear to log correctly,
    while the entries silently landed in a different file than the one
    every other endpoint (and the user) actually reads from. This test
    exercises the real endpoint plumbing end to end, undoing the module's
    autouse audit-log mock so entries genuinely hit disk, then confirms
    they show up through GET /api/audit-log - not just in some file.
    """
    test_client, scan_root, audit_log_path = client

    # The autouse `audit_calls` fixture above replaces audit_log.append_entry
    # with an in-memory fake for every test in this file. Undo that just for
    # this test: proving real entries are visible through the API requires
    # a real write to actually happen.
    monkeypatch.setattr("backend.app.audit_log.append_entry", real_append_entry)

    duplicate_content = "identical payload\n" * 20
    (scan_root / "dup_a.bin").write_text(duplicate_content)
    (scan_root / "dup_b.bin").write_text(duplicate_content)

    assert not audit_log_path.exists()

    response = test_client.get("/api/recommendations", params={"root": str(scan_root)})
    assert response.status_code == 200
    recommended_actions = {r["recommended_action"] for r in response.json()["recommendations"]}
    assert "auto_apply" in recommended_actions

    # The write must have actually happened, at the path Settings resolved.
    assert audit_log_path.exists()

    log_response = test_client.get("/api/audit-log")
    assert log_response.status_code == 200
    entries = log_response.json()

    assert len(entries) == 2
    assert {e["action_type"] for e in entries} == {"auto_apply", "recommend"}
    logged_paths = {p for e in entries for p in e["target_paths"]}
    assert logged_paths == {
        str((scan_root / "dup_a.bin").resolve()),
        str((scan_root / "dup_b.bin").resolve()),
    }

    # And it's genuinely the same file the endpoint read from, not a
    # separate one that happens to agree.
    assert read_log(audit_log_path) == entries


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


def test_quarantine_endpoint_moves_file_and_returns_manifest_entry(client):
    test_client, scan_root, _audit_log_path = client
    target = scan_root / "old_download.dmg"
    target.write_text("some bytes")

    response = test_client.post(
        "/api/quarantine",
        json={"path": str(target), "reason": "stale, not opened in 200 days"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "quarantined"
    assert body["original_path"] == str(target)
    assert body["reason"] == "stale, not opened in 200 days"

    assert not target.exists()
    assert Path(body["quarantined_path"]).exists()


def test_quarantine_endpoint_refuses_protected_path(client):
    test_client, scan_root, _audit_log_path = client
    git_dir = scan_root / ".git"
    git_dir.mkdir()
    protected_file = git_dir / "config"
    protected_file.write_text("git internals")

    response = test_client.post(
        "/api/quarantine",
        json={"path": str(protected_file), "reason": "attempted quarantine"},
    )

    assert response.status_code == 400
    assert "detail" in response.json()
    assert protected_file.exists()


def test_quarantine_endpoint_refuses_path_outside_scan_roots(client, tmp_path):
    test_client, _scan_root, _audit_log_path = client
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("not in scope")

    response = test_client.post(
        "/api/quarantine",
        json={"path": str(outside_file), "reason": "should not be allowed"},
    )

    assert response.status_code == 400
    assert outside_file.exists()


def test_restore_endpoint_moves_file_back_to_original_path(client):
    test_client, scan_root, _audit_log_path = client
    target = scan_root / "restore_me.txt"
    target.write_text("payload")

    quarantine_response = test_client.post(
        "/api/quarantine", json={"path": str(target), "reason": "test reason"}
    )
    quarantine_id = quarantine_response.json()["quarantine_id"]

    restore_response = test_client.post(f"/api/quarantine/{quarantine_id}/restore")

    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "restored"
    assert target.exists()
    assert target.read_text() == "payload"


def test_restore_endpoint_unknown_id_returns_400(client):
    test_client, _scan_root, _audit_log_path = client

    response = test_client.post(
        "/api/quarantine/00000000-0000-0000-0000-000000000000/restore"
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_forecast_endpoint_returns_insufficient_data_with_no_snapshots(client):
    test_client, scan_root, _audit_log_path = client

    response = test_client.get("/api/forecast", params={"path": str(scan_root)})

    assert response.status_code == 200
    body = response.json()
    # Live disk usage is always present, independent of snapshot history.
    assert body["total_bytes"] > 0
    assert 0 <= body["used_percent"] <= 100
    assert body["status"] == "insufficient_data"
    assert body["snapshots_available"] == 0
    assert body["snapshots_needed"] == 3


def test_forecast_endpoint_nonexistent_path_returns_400(client, tmp_path):
    test_client, _scan_root, _audit_log_path = client
    missing = tmp_path / "does_not_exist"

    response = test_client.get("/api/forecast", params={"path": str(missing)})

    assert response.status_code == 400
    assert "detail" in response.json()


def test_forecast_snapshot_endpoint_records_real_usage(client):
    test_client, scan_root, _audit_log_path = client

    response = test_client.post("/api/forecast/snapshot", json={"path": str(scan_root)})

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(scan_root)
    assert body["total_bytes"] > 0
    assert 0 <= body["used_percent"] <= 100
    assert "timestamp" in body

    # And it's genuinely visible to a subsequent forecast call.
    forecast = test_client.get("/api/forecast", params={"path": str(scan_root)}).json()
    assert forecast["snapshots_available"] == 1


def test_forecast_endpoint_returns_ok_once_enough_snapshots_recorded(client):
    test_client, scan_root, _audit_log_path = client

    for _ in range(3):
        response = test_client.post("/api/forecast/snapshot", json={"path": str(scan_root)})
        assert response.status_code == 200

    response = test_client.get("/api/forecast", params={"path": str(scan_root)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "trend_bytes_per_day" in body
    assert "current_used_percent" in body
    assert "days_until_full" in body


def test_get_quarantine_lists_only_currently_quarantined_items(client):
    test_client, scan_root, _audit_log_path = client
    target1 = scan_root / "one.txt"
    target2 = scan_root / "two.txt"
    target1.write_text("1")
    target2.write_text("2")

    entry1 = test_client.post(
        "/api/quarantine", json={"path": str(target1), "reason": "reason 1"}
    ).json()
    entry2 = test_client.post(
        "/api/quarantine", json={"path": str(target2), "reason": "reason 2"}
    ).json()

    test_client.post(f"/api/quarantine/{entry1['quarantine_id']}/restore")

    response = test_client.get("/api/quarantine")

    assert response.status_code == 200
    ids = {e["quarantine_id"] for e in response.json()}
    assert ids == {entry2["quarantine_id"]}
