from unittest.mock import patch

import pytest

from backend.app.copilot_answer import (
    NO_RESULTS_TEXT,
    SCOPED_DECLINE_TEXT,
    answer_query,
    classify_query_intent,
    generate_answer,
)
from backend.app.copilot_retrieval import build_index
from backend.tests.test_copilot_retrieval import FUSION_CORPUS, FUSION_QUERY


def _reranked(item):
    return {"item": item, "rrf_score": 0.5, "sources": ["faiss"], "cross_encoder_score": 1.0}


@pytest.mark.parametrize(
    "query,expected_intent",
    [
        ("why is my disk full?", "why_full"),
        ("what's taking up all my space?", "why_full"),
        ("find duplicate photos", "find_duplicates"),
        ("are there any similar files?", "find_duplicates"),
        ("what's safe to delete?", "whats_safe"),
        ("what can I clean up?", "whats_safe"),
        ("tell me about my files", "general"),
        ("show me everything on this drive", "general"),
        ("what's using my space", "general"),
        ("do I have duplicates", "find_duplicates"),
        ("what's the weather today", "out_of_scope"),
        ("what's 2+2", "out_of_scope"),
        ("tell me a joke", "out_of_scope"),
    ],
)
def test_classify_query_intent(query, expected_intent):
    assert classify_query_intent(query) == expected_intent


def test_generate_answer_why_full_mentions_only_input_files_and_reasons():
    item_a = {
        "path": "/home/user/Downloads/huge_video.mp4",
        "recommended_action": "review_recommended",
        "staleness_score": 0.9,
        "factors": [
            {"name": "recency_factor", "contribution": 0.4, "explanation": "not accessed in 400 days"},
            {
                "name": "size_factor",
                "contribution": 0.1,
                "explanation": "620.0 MB - reclaiming it would free up meaningful space",
            },
        ],
        "duplicate_of": None,
        "near_duplicate_of": None,
    }
    item_b = {
        "path": "/home/user/Downloads/old_installer.dmg",
        "recommended_action": "auto_apply",
        "staleness_score": 0.85,
        "factors": [
            {"name": "duplicate_factor", "contribution": 0.3, "explanation": "duplicate of another file"},
        ],
        "duplicate_of": "/home/user/Downloads/installer_original.dmg",
        "near_duplicate_of": None,
    }

    reranked_results = [_reranked(item_a), _reranked(item_b)]

    result = generate_answer("why is my disk full", reranked_results, "why_full")

    assert result["intent"] == "why_full"
    assert set(result["cited_paths"]) == {item_a["path"], item_b["path"]}

    text = result["answer_text"]
    assert "huge_video.mp4" in text
    assert "not accessed in 400 days" in text
    assert "old_installer.dmg" in text
    assert "duplicate of another file" in text
    assert "620.0" in text  # total reclaimable space, computed from the input

    # Real grounding check: nothing outside the input should ever appear -
    # including item_b's own duplicate_of target, which isn't itself one
    # of the passed-in items and which this template never even prints.
    assert "secret_diary.txt" not in text
    assert "installer_original.dmg" not in text


def test_generate_answer_empty_results_returns_honest_no_results_message():
    result = generate_answer("why is my disk full", [], "why_full")

    assert result == {"answer_text": NO_RESULTS_TEXT, "cited_paths": [], "intent": "why_full"}


@pytest.mark.parametrize(
    "query",
    ["what's the weather today", "what's 2+2", "tell me a joke"],
)
def test_generate_answer_out_of_scope_returns_scoped_decline_without_results(query):
    result = generate_answer(query, [], "out_of_scope")

    assert result == {
        "answer_text": SCOPED_DECLINE_TEXT,
        "cited_paths": [],
        "intent": "out_of_scope",
        "source": "scoped_decline",
    }


@pytest.fixture(scope="module")
def fusion_index():
    return build_index(FUSION_CORPUS)


def test_answer_query_end_to_end_returns_well_formed_answer(fusion_index):
    # prefer_llm=False: this test exercises the templated pipeline glue,
    # not the (mocked-elsewhere, real-model-loading) LLM path - see
    # test_llm_answer.py for LLM-path coverage and answer_query's
    # fallback behavior.
    result = answer_query(FUSION_QUERY, fusion_index, top_k_search=6, top_k_rerank=3, prefer_llm=False)

    assert set(result.keys()) == {"answer_text", "cited_paths", "intent"}
    assert isinstance(result["answer_text"], str) and result["answer_text"]
    assert isinstance(result["cited_paths"], list)
    assert result["intent"] in {"why_full", "find_duplicates", "whats_safe", "general"}

    # Every cited path must correspond to an actual item in the corpus -
    # nothing invented.
    corpus_paths = {item["path"] for item in FUSION_CORPUS}
    assert set(result["cited_paths"]) <= corpus_paths


def test_answer_query_prefer_llm_false_never_touches_llm_path(fusion_index):
    with patch("backend.app.copilot_answer.generate_llm_answer") as mock_llm_answer:
        result = answer_query(FUSION_QUERY, fusion_index, top_k_search=6, top_k_rerank=3, prefer_llm=False)

    mock_llm_answer.assert_not_called()
    assert set(result.keys()) == {"answer_text", "cited_paths", "intent"}


def test_answer_query_prefer_llm_true_skips_llm_entirely_when_never_loaded(fusion_index, monkeypatch):
    """If the LLM was never successfully loaded (e.g. LLMModelNotFoundError
    at startup - see llm_answer.is_llm_available()), answer_query(
    prefer_llm=True) must skip straight to the templated path - not
    attempt the LLM call and catch its failure, just skip it entirely."""
    monkeypatch.setattr("backend.app.copilot_answer.is_llm_available", lambda: False)

    with patch("backend.app.copilot_answer.generate_llm_answer") as mock_llm_answer:
        result = answer_query(FUSION_QUERY, fusion_index, top_k_search=6, top_k_rerank=3, prefer_llm=True)

    mock_llm_answer.assert_not_called()

    templated_result = answer_query(FUSION_QUERY, fusion_index, top_k_search=6, top_k_rerank=3, prefer_llm=False)
    assert result == templated_result


@pytest.mark.parametrize(
    "query",
    ["what's the weather today", "what's 2+2", "tell me a joke"],
)
def test_answer_query_out_of_scope_short_circuits_before_search_rerank_or_llm(fusion_index, monkeypatch, query):
    """An out-of-scope question must never reach retrieval/reranking or the
    LLM path - classify_query_intent() already knows it's unrelated, so
    running any of that would be pure waste. Mirrors the existing
    prefer_llm=False short-circuit test above, but for this earlier
    short-circuit."""
    monkeypatch.setattr("backend.app.copilot_answer.is_llm_available", lambda: True)

    with (
        patch("backend.app.copilot_answer.search") as mock_search,
        patch("backend.app.copilot_answer.rerank") as mock_rerank,
        patch("backend.app.copilot_answer.generate_llm_answer") as mock_llm_answer,
    ):
        result = answer_query(query, fusion_index, prefer_llm=True)

    mock_search.assert_not_called()
    mock_rerank.assert_not_called()
    mock_llm_answer.assert_not_called()

    assert result == {
        "answer_text": SCOPED_DECLINE_TEXT,
        "cited_paths": [],
        "intent": "out_of_scope",
        "source": "scoped_decline",
    }


def test_answer_query_prefer_llm_true_falls_back_to_templated_on_any_llm_failure(fusion_index, monkeypatch):
    # Force the "LLM is available but this particular call fails" case
    # explicitly, so this test still exercises the exception-catching
    # fallback it's named for regardless of whether the real LLM happens
    # to be loaded in this test process - see the is_llm_available()
    # short-circuit test above for the "never loaded at all" case.
    monkeypatch.setattr("backend.app.copilot_answer.is_llm_available", lambda: True)

    with patch("backend.app.copilot_answer.generate_llm_answer", side_effect=RuntimeError("model exploded")):
        llm_result = answer_query(FUSION_QUERY, fusion_index, top_k_search=6, top_k_rerank=3, prefer_llm=True)

    templated_result = answer_query(FUSION_QUERY, fusion_index, top_k_search=6, top_k_rerank=3, prefer_llm=False)

    # Falls back to exactly what the templated path would have produced -
    # no partial/error text leaks through, no "source" field appended.
    assert llm_result == templated_result
    assert set(llm_result.keys()) == {"answer_text", "cited_paths", "intent"}
