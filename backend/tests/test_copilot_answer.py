import pytest

from backend.app.copilot_answer import (
    NO_RESULTS_TEXT,
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


@pytest.fixture(scope="module")
def fusion_index():
    return build_index(FUSION_CORPUS)


def test_answer_query_end_to_end_returns_well_formed_answer(fusion_index):
    result = answer_query(FUSION_QUERY, fusion_index, top_k_search=6, top_k_rerank=3)

    assert set(result.keys()) == {"answer_text", "cited_paths", "intent"}
    assert isinstance(result["answer_text"], str) and result["answer_text"]
    assert isinstance(result["cited_paths"], list)
    assert result["intent"] in {"why_full", "find_duplicates", "whats_safe", "general"}

    # Every cited path must correspond to an actual item in the corpus -
    # nothing invented.
    corpus_paths = {item["path"] for item in FUSION_CORPUS}
    assert set(result["cited_paths"]) <= corpus_paths
