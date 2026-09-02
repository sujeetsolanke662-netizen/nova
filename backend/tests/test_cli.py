from backend.cli import main


def _fake_generate_result(path):
    return {
        "scanned_count": 1,
        "skipped_count": 0,
        "protected_count": 0,
        "recommendations": [
            {
                "path": path,
                "recommended_action": "review_recommended",
                "staleness_score": 0.8,
                "factors": [],
                "duplicate_of": None,
                "near_duplicate_of": None,
            }
        ],
    }


def test_ask_prints_answer_text_and_cited_files(tmp_path, monkeypatch, capsys):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    monkeypatch.setenv("NOVA_SCAN_ROOTS", str(scan_root))
    monkeypatch.setenv("NOVA_AUDIT_LOG_PATH", str(tmp_path / "audit_log.jsonl"))

    cited_path = str(scan_root / "old.zip")
    fake_generate_result = _fake_generate_result(cited_path)
    fake_answer = {
        "answer_text": "You have one old zip file taking up space.",
        "cited_paths": [cited_path],
        "intent": "why_full",
    }

    monkeypatch.setattr(
        "backend.cli.generate_recommendations", lambda *a, **k: fake_generate_result
    )
    monkeypatch.setattr("backend.cli.build_index", lambda recommendations: {"fake": True})
    monkeypatch.setattr("backend.cli.answer_query", lambda query, index: fake_answer)

    exit_code = main(["ask", "why is my disk full"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Scanning..." in captured.out
    assert "You have one old zip file taking up space." in captured.out
    assert "Files referenced:" in captured.out
    assert f"  - {cited_path}" in captured.out
    assert captured.err == ""


def test_ask_root_override_is_passed_through_to_generate_recommendations(tmp_path, monkeypatch):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    monkeypatch.setenv("NOVA_SCAN_ROOTS", str(scan_root))
    monkeypatch.setenv("NOVA_AUDIT_LOG_PATH", str(tmp_path / "audit_log.jsonl"))

    other_root = tmp_path / "other_root"
    other_root.mkdir()

    captured_args = {}

    def fake_generate_recommendations(root, scan_roots, patterns, audit_log_path=None):
        captured_args["root"] = root
        captured_args["scan_roots"] = scan_roots
        return {"scanned_count": 0, "skipped_count": 0, "protected_count": 0, "recommendations": []}

    monkeypatch.setattr("backend.cli.generate_recommendations", fake_generate_recommendations)

    exit_code = main(["ask", "anything", "--root", str(other_root)])

    assert exit_code == 0
    # The override root must be used verbatim, not silently ignored in
    # favor of settings.scan_roots (which points at scan_root, not
    # other_root).
    assert captured_args["root"] == str(other_root)
    assert captured_args["scan_roots"] == [str(other_root)]


def test_ask_empty_recommendations_prints_sensible_message_not_traceback(tmp_path, monkeypatch, capsys):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    monkeypatch.setenv("NOVA_SCAN_ROOTS", str(scan_root))
    monkeypatch.setenv("NOVA_AUDIT_LOG_PATH", str(tmp_path / "audit_log.jsonl"))

    monkeypatch.setattr(
        "backend.cli.generate_recommendations",
        lambda *a, **k: {
            "scanned_count": 0,
            "skipped_count": 0,
            "protected_count": 0,
            "recommendations": [],
        },
    )

    exit_code = main(["ask", "anything"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Scanning..." in captured.out
    assert "Nothing to search" in captured.out
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err


def test_ask_nonexistent_root_prints_error_not_traceback(tmp_path, monkeypatch, capsys):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    monkeypatch.setenv("NOVA_SCAN_ROOTS", str(scan_root))
    monkeypatch.setenv("NOVA_AUDIT_LOG_PATH", str(tmp_path / "audit_log.jsonl"))

    missing_root = tmp_path / "does_not_exist"

    exit_code = main(["ask", "anything", "--root", str(missing_root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "not an existing directory" in captured.err
    assert "Traceback" not in captured.err
