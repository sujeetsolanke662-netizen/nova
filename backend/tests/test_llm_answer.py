"""Tests for the LLM-backed answer path.

These mock the Llama class entirely - the real model is ~800MB and slow to
load, and this suite needs to stay fast. Real end-to-end model behavior is
verified manually, separately (see task notes), not here.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from backend.app.llm_answer import (
    LLMGroundingError,
    LLMModelNotFoundError,
    LLMTimeoutError,
    _build_prompt,
    _check_grounding,
    _filter_results_for_intent,
    _trim_to_complete_sentence,
    generate_llm_answer,
    is_llm_available,
    load_llm,
)

ITEM_A = {
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

ITEM_B = {
    "path": "/home/user/Downloads/old_installer.dmg",
    "recommended_action": "auto_apply",
    "staleness_score": 0.85,
    "factors": [
        {"name": "duplicate_factor", "contribution": 0.3, "explanation": "duplicate of another file"},
    ],
    "duplicate_of": "/home/user/Downloads/installer_original.dmg",
    "near_duplicate_of": None,
}


ITEM_KEEP = {
    "path": "/home/user/Downloads/current_todo.txt",
    "recommended_action": "keep",
    "staleness_score": 0.05,
    "factors": [
        {"name": "recency_factor", "contribution": -0.5, "explanation": "accessed 2 days ago"},
    ],
    "duplicate_of": None,
    "near_duplicate_of": None,
}


def _reranked(item):
    return {"item": item, "rrf_score": 0.5, "sources": ["faiss"], "cross_encoder_score": 1.0}


RERANKED_RESULTS = [_reranked(ITEM_A), _reranked(ITEM_B)]


def _mock_llm(content: str, delay: float = 0.0):
    """Build a mock replacing load_llm() whose create_chat_completion
    returns `content`, optionally after sleeping `delay` seconds (to
    exercise the timeout path)."""

    class _FakeLlama:
        def create_chat_completion(self, messages, temperature, max_tokens):
            if delay:
                time.sleep(delay)
            return {"choices": [{"message": {"content": content}}]}

    return _FakeLlama()


# --- prompt construction -----------------------------------------------


def test_build_prompt_includes_real_facts_and_grounding_instructions():
    messages = _build_prompt("why is my disk full", RERANKED_RESULTS, "why_full")

    assert messages[0]["role"] == "system"
    system_text = messages[0]["content"].lower()
    assert "only" in system_text
    assert "never invent" in system_text or "invent" in system_text

    assert messages[1]["role"] == "user"
    user_text = messages[1]["content"]
    assert "why is my disk full" in user_text
    assert ITEM_A["path"] in user_text
    assert ITEM_B["path"] in user_text
    assert "not accessed in 400 days" in user_text
    assert "duplicate of another file" in user_text
    assert "why_full" in user_text


def test_build_prompt_does_not_leak_data_outside_the_given_results():
    messages = _build_prompt("why is my disk full", [_reranked(ITEM_A)], "why_full")
    user_text = messages[1]["content"]
    assert ITEM_B["path"] not in user_text


# --- grounding check ------------------------------------------------------


def test_check_grounding_passes_when_answer_only_mentions_real_paths():
    real_paths = [ITEM_A["path"], ITEM_B["path"]]
    answer = f"Your biggest space user is {ITEM_A['path']}, and {ITEM_B['path']} is a duplicate."
    _check_grounding(answer, real_paths)  # should not raise


def test_check_grounding_passes_for_bare_filenames_of_real_paths():
    real_paths = [ITEM_A["path"], ITEM_B["path"]]
    answer = "huge_video.mp4 is taking up the most space, and old_installer.dmg is a duplicate."
    _check_grounding(answer, real_paths)  # should not raise


def test_check_grounding_raises_when_answer_mentions_an_invented_path():
    real_paths = [ITEM_A["path"], ITEM_B["path"]]
    answer = "The biggest space user is /home/user/Downloads/fake_invented_file.iso."
    with pytest.raises(LLMGroundingError):
        _check_grounding(answer, real_paths)


def test_check_grounding_raises_for_invented_bare_filename():
    real_paths = [ITEM_A["path"], ITEM_B["path"]]
    answer = "You should delete totally_made_up.zip to free up space."
    with pytest.raises(LLMGroundingError):
        _check_grounding(answer, real_paths)


def test_check_grounding_ignores_non_path_tokens():
    real_paths = [ITEM_A["path"]]
    # "e.g." and a bare number shouldn't be mistaken for invented paths.
    answer = "You have several large files, e.g. one at 620.0 MB, worth reviewing."
    _check_grounding(answer, real_paths)  # should not raise


# --- intent-based fact filtering (whats_safe must never see "keep") -------


def test_filter_results_for_intent_excludes_keep_files_for_whats_safe():
    results = [_reranked(ITEM_A), _reranked(ITEM_B), _reranked(ITEM_KEEP)]

    filtered = _filter_results_for_intent(results, "whats_safe")

    filtered_paths = {r["item"]["path"] for r in filtered}
    assert filtered_paths == {ITEM_A["path"], ITEM_B["path"]}
    assert ITEM_KEEP["path"] not in filtered_paths


def test_filter_results_for_intent_is_a_noop_for_intents_without_a_filter():
    results = [_reranked(ITEM_A), _reranked(ITEM_KEEP)]

    filtered = _filter_results_for_intent(results, "why_full")

    assert filtered == results


def test_build_prompt_for_whats_safe_never_includes_a_keep_file():
    """The bug this guards against: the LLM was shown a "keep" file
    alongside real safe-to-delete candidates and described it as safe to
    delete anyway. The fix filters the facts before the prompt is even
    built - see generate_llm_answer(), which calls
    _filter_results_for_intent() before _build_prompt()."""
    results = [_reranked(ITEM_A), _reranked(ITEM_B), _reranked(ITEM_KEEP)]
    filtered = _filter_results_for_intent(results, "whats_safe")

    messages = _build_prompt("what's safe to delete", filtered, "whats_safe")
    user_text = messages[1]["content"]

    assert ITEM_A["path"] in user_text
    assert ITEM_B["path"] in user_text
    assert ITEM_KEEP["path"] not in user_text
    assert "current_todo" not in user_text


def test_generate_llm_answer_whats_safe_never_sends_keep_file_to_the_model():
    results = [_reranked(ITEM_A), _reranked(ITEM_B), _reranked(ITEM_KEEP)]
    grounded_answer = f"{ITEM_B['path']} looks safe to remove - it's an exact duplicate."

    captured_messages = {}

    class _CapturingFakeLlama:
        def create_chat_completion(self, messages, temperature, max_tokens):
            captured_messages["messages"] = messages
            return {"choices": [{"message": {"content": grounded_answer}}]}

    with patch("backend.app.llm_answer.load_llm", return_value=_CapturingFakeLlama()):
        result = generate_llm_answer("what's safe to delete", results, "whats_safe")

    assert result["source"] == "llm"
    user_text = captured_messages["messages"][1]["content"]
    assert ITEM_KEEP["path"] not in user_text
    assert "current_todo" not in user_text


def test_generate_llm_answer_whats_safe_treats_mention_of_filtered_keep_file_as_ungrounded():
    """Even if the model somehow still names the excluded "keep" file
    (e.g. from a prior turn or hallucination, since it was never in the
    facts it was given), that must be treated exactly like an invented
    path - the same LLMGroundingError fallback mechanism, not a special
    case."""
    results = [_reranked(ITEM_A), _reranked(ITEM_KEEP)]
    bad_answer = f"{ITEM_KEEP['path']} looks safe to delete."

    with patch("backend.app.llm_answer.load_llm", return_value=_mock_llm(bad_answer)):
        with pytest.raises(LLMGroundingError):
            generate_llm_answer("what's safe to delete", results, "whats_safe")


def test_generate_llm_answer_whats_safe_falls_back_to_templated_when_everything_is_keep():
    """If every candidate for a "whats_safe" question is actually a
    "keep" file, there's nothing legitimate for the LLM to say - this
    must defer to the templated path's own honest handling instead of
    calling the model at all."""
    results = [_reranked(ITEM_KEEP)]

    with patch("backend.app.llm_answer.load_llm") as mock_load:
        result = generate_llm_answer("what's safe to delete", results, "whats_safe")

    mock_load.assert_not_called()
    assert result["cited_paths"] == []
    assert result["intent"] == "whats_safe"
    assert set(result.keys()) == {"answer_text", "cited_paths", "intent"}
    assert "safe to remove" in result["answer_text"].lower()


# --- sentence-boundary trimming (never return a mid-word truncation) ------


def test_trim_to_complete_sentence_is_a_noop_when_already_complete():
    text = "This file is large and hasn't been opened in a year."
    assert _trim_to_complete_sentence(text) == text


@pytest.mark.parametrize("ending_punct", [".", "!", "?"])
def test_trim_to_complete_sentence_cuts_back_a_mid_word_truncation(ending_punct):
    text = f"First sentence is complete{ending_punct} Second one trails off mid-wo"
    trimmed = _trim_to_complete_sentence(text)

    assert trimmed == f"First sentence is complete{ending_punct}"
    assert trimmed[-1] in ".!?"


def test_trim_to_complete_sentence_leaves_text_unchanged_with_no_sentence_break():
    text = "no punctuation at all here just cut off mid-wo"
    assert _trim_to_complete_sentence(text) == text


def test_trim_to_complete_sentence_does_not_mistake_a_truncated_decimal_for_a_sentence_end():
    """Regression test: the facts block is full of sizes like "15.6 MB", so
    a naive "does the text already end in '.'?" check is fooled by
    max_tokens cutting generation right after the decimal point (e.g.
    "...(15." from a truncated "15.6 MB)") - that '.' is not a real
    sentence end, and must not short-circuit trimming as a no-op."""
    text = "First sentence is complete. The file is (15."
    trimmed = _trim_to_complete_sentence(text)

    assert trimmed == "First sentence is complete."
    assert not trimmed.endswith("(15.")


def test_trim_to_complete_sentence_ignores_periods_inside_file_extensions():
    """A '.' inside a filename (e.g. "Introduction.mp4") is immediately
    followed by more filename characters, never whitespace - unlike a
    real sentence end - so it must not be mistaken for one while scanning
    backward for the true last sentence boundary. With no genuine boundary
    and no newline to fall back to either, the untrimmed text is returned
    unchanged - still better than silently losing everything."""
    text = "The largest file is Introduction.mp4 and it hasn't been opened in a ye"
    trimmed = _trim_to_complete_sentence(text)

    assert trimmed == text


def test_trim_to_complete_sentence_falls_back_to_last_complete_line_with_no_periods_at_all():
    """This model's answers are often bulleted lists with no sentence
    periods anywhere (each line is just "- fact"). With no '.', '!' or
    '?' to find at all, trimming should still cut off the incomplete
    trailing bullet rather than returning it half-written."""
    text = (
        "Here is what I found:\n"
        "- huge_video.mp4 (620 MB) - not accessed in 400 days\n"
        "- old_installer.dmg (12 MB) - duplicate of another file\n"
        "- another_file.iso (8 MB) - not accessed in 90 da"
    )
    trimmed = _trim_to_complete_sentence(text)

    assert trimmed == (
        "Here is what I found:\n"
        "- huge_video.mp4 (620 MB) - not accessed in 400 days\n"
        "- old_installer.dmg (12 MB) - duplicate of another file"
    )
    assert "another_file.iso" not in trimmed


def test_generate_llm_answer_trims_a_mid_word_truncated_response():
    truncated = (
        f"{ITEM_A['path']} is your biggest space user, not accessed in 400 days. "
        "It also appears to be growing at an alarming ra"
    )
    with patch("backend.app.llm_answer.load_llm", return_value=_mock_llm(truncated)):
        result = generate_llm_answer("why is my disk full", RERANKED_RESULTS, "why_full")

    assert result["answer_text"][-1] in ".!?"
    assert not result["answer_text"].endswith("ra")
    assert "growing" not in result["answer_text"]


# --- generate_llm_answer: success, empty results -------------------------


def test_generate_llm_answer_returns_llm_sourced_answer_on_success():
    grounded_answer = f"{ITEM_A['path']} is your biggest space user, not accessed in 400 days."
    with patch("backend.app.llm_answer.load_llm", return_value=_mock_llm(grounded_answer)):
        result = generate_llm_answer("why is my disk full", RERANKED_RESULTS, "why_full")

    assert result["source"] == "llm"
    assert result["answer_text"] == grounded_answer
    assert result["intent"] == "why_full"
    assert ITEM_A["path"] in result["cited_paths"]


def test_generate_llm_answer_empty_results_skips_llm_entirely():
    with patch("backend.app.llm_answer.load_llm") as mock_load:
        result = generate_llm_answer("why is my disk full", [], "why_full")

    mock_load.assert_not_called()
    assert result["cited_paths"] == []
    assert result["intent"] == "why_full"
    assert "didn't find" in result["answer_text"].lower()


def test_generate_llm_answer_out_of_scope_skips_llm_entirely():
    with patch("backend.app.llm_answer.load_llm") as mock_load:
        result = generate_llm_answer("what's the weather today", RERANKED_RESULTS, "out_of_scope")

    mock_load.assert_not_called()
    assert result["source"] == "scoped_decline"
    assert result["cited_paths"] == []
    assert result["intent"] == "out_of_scope"


# --- generate_llm_answer: grounding failure -------------------------------


def test_generate_llm_answer_raises_grounding_error_for_invented_path():
    ungrounded_answer = "The biggest offender is /totally/made/up/path/nonexistent.iso."
    with patch("backend.app.llm_answer.load_llm", return_value=_mock_llm(ungrounded_answer)):
        with pytest.raises(LLMGroundingError):
            generate_llm_answer("why is my disk full", RERANKED_RESULTS, "why_full")


# --- generate_llm_answer: timeout ------------------------------------------


def test_generate_llm_answer_raises_timeout_error_when_model_is_slow():
    with patch("backend.app.llm_answer.load_llm", return_value=_mock_llm("irrelevant", delay=0.5)):
        with pytest.raises(LLMTimeoutError):
            generate_llm_answer("why is my disk full", RERANKED_RESULTS, "why_full", timeout_seconds=0.05)


# --- generate_llm_answer: concurrency lock ---------------------------------


def test_generate_llm_answer_never_runs_two_model_calls_concurrently():
    """Two overlapping calls (e.g. a second request arriving while a first
    is still running, possibly orphaned from a prior timeout) must never
    both be inside create_chat_completion() at once. The second must fail
    fast (LLMTimeoutError, same fallback-to-templated path a slow response
    already triggers) rather than run concurrently against the shared
    model instance or block until the first finishes."""
    state_lock = threading.Lock()
    active = {"count": 0, "max_concurrent": 0}

    class _SlowFakeLlama:
        def create_chat_completion(self, messages, temperature, max_tokens):
            with state_lock:
                active["count"] += 1
                active["max_concurrent"] = max(active["max_concurrent"], active["count"])
            time.sleep(1.0)  # well past _LOCK_ACQUIRE_TIMEOUT_SECONDS (0.5s)
            with state_lock:
                active["count"] -= 1
            grounded_answer = f"{ITEM_A['path']} is your biggest space user."
            return {"choices": [{"message": {"content": grounded_answer}}]}

    results: dict[str, object] = {}

    def _call(name: str) -> None:
        try:
            results[name] = generate_llm_answer(
                "why is my disk full", RERANKED_RESULTS, "why_full", timeout_seconds=2.0
            )
        except Exception as exc:  # noqa: BLE001 - capturing to assert on below
            results[name] = exc

    with patch("backend.app.llm_answer.load_llm", return_value=_SlowFakeLlama()):
        first = threading.Thread(target=_call, args=("first",))
        first.start()
        time.sleep(0.1)  # let the first call actually acquire the lock

        second_start = time.monotonic()
        second = threading.Thread(target=_call, args=("second",))
        second.start()
        second.join()
        second_elapsed = time.monotonic() - second_start

        first.join()

    # The core guarantee: create_chat_completion() was never entered twice
    # at the same time.
    assert active["max_concurrent"] == 1

    assert results["first"]["source"] == "llm"
    assert isinstance(results["second"], LLMTimeoutError)

    # Bounded, not blocked: the second caller failed fast off the lock's
    # own short timeout, not by waiting out the first call's full 1.0s
    # (and not the overall 2.0s timeout_seconds either).
    assert second_elapsed < 1.0


# --- load_llm(): missing model file -----------------------------------


def test_load_llm_raises_model_not_found_error_for_missing_path(tmp_path, monkeypatch):
    """A missing/misconfigured .gguf must raise this specific, catchable
    error type with the exact path it looked for - not a raw
    FileNotFoundError, and not whatever llama_cpp itself would raise
    trying to open a file that isn't there (load_llm() must never even
    get as far as importing/calling into llama_cpp for a missing path)."""
    monkeypatch.setattr("backend.app.llm_answer._llm_instance", None)
    missing_path = tmp_path / "does-not-exist.gguf"
    monkeypatch.setenv("NOVA_LLM_MODEL_PATH", str(missing_path))

    with pytest.raises(LLMModelNotFoundError) as exc_info:
        load_llm()

    assert str(missing_path) in str(exc_info.value)
    assert not is_llm_available()
