"""LLM-based answer generation for NOVA Copilot.

An optional, higher-quality answer path layered on top of
copilot_answer.py's templated system. Instead of composing a sentence from
a fixed template, this hands the same grounding data (paths, recommended
actions, staleness factor explanations) to a small local model and asks it
to phrase the answer.

This path is never trusted blindly: it runs under a hard timeout and every
generated answer is checked post-hoc to confirm it didn't invent a file
path that isn't actually in the input data. Either failure mode raises, and
copilot_answer.answer_query() catches that and falls back to the templated
path - see its module docstring. Nothing here should ever be the only way
to get an answer.
"""

from __future__ import annotations

import concurrent.futures
import re
import threading
from pathlib import Path

from ..config.settings import get_settings

_llm_instance = None  # module-level cache, populated by load_llm() on first use

# Guards every real inference call against _llm_instance. llama.cpp's
# context isn't safe for concurrent use from two threads - without this,
# a request that times out (see generate_llm_answer) leaves its background
# thread running, and a *later* request calling create_chat_completion()
# on the same shared instance while that orphaned thread is still inside
# its own call crashes the process (a native segfault, not a catchable
# Python exception). Only one generation may be in flight, ever.
_llm_lock = threading.Lock()

# How long a call will wait for _llm_lock before giving up. Short and
# bounded on purpose: if the lock is already held (a previous, possibly
# orphaned, call is still running), a caller must never block indefinitely
# waiting for it - it should fail fast into the same LLMTimeoutError/
# fallback-to-templated path a slow model response already triggers.
_LOCK_ACQUIRE_TIMEOUT_SECONDS = 0.5

# Matches filename-or-path-like tokens ending in a plausible file extension
# (letters only, 2-5 chars), so we can pull out anything the model's answer
# claims is a file and check it against the real data. Requires a 2+
# char name before the extension so short abbreviations like "e.g." don't
# false-trigger a grounding failure, and a letters-only extension so a
# number like "620.0" (a size, not a path) doesn't match either.
_PATH_TOKEN_RE = re.compile(r"[\w\-./]{2,}\.[A-Za-z]{2,5}\b")

# Which recommended_action values are consistent with a given intent's
# question - used by _filter_results_for_intent() to keep contradictory
# facts out of the prompt entirely, rather than just asking the model
# nicely to ignore them. Value must match the corresponding intent
# constant in copilot_answer.py (e.g. "whats_safe" == WHATS_SAFE). Intents
# not listed here get no filtering - not every intent has a notion of
# "matches vs. contradicts". Easy to extend with more intents later.
_INTENT_ALLOWED_ACTIONS: dict[str, tuple[str, ...]] = {
    "whats_safe": ("auto_apply", "review_recommended"),
}

# Sentence-ending punctuation used by _trim_to_complete_sentence() to cut
# a max_tokens-truncated answer back to its last complete thought.
_SENTENCE_END_CHARS = ".!?"


class LLMTimeoutError(Exception):
    """Raised when the LLM does not respond within the allotted time."""


class LLMGroundingError(Exception):
    """Raised when the LLM's answer references a file path that doesn't
    appear anywhere in the reranked_results it was given - i.e. it
    invented something instead of only using the supplied facts."""


class LLMModelNotFoundError(Exception):
    """Raised when the configured GGUF model file doesn't exist on disk -
    e.g. a demo machine the .gguf wasn't copied onto, or a misconfigured
    NOVA_LLM_MODEL_PATH. Distinct from a raw FileNotFoundError (or letting
    llama_cpp fail on its own) so callers - specifically main.py's
    lifespan handler - can catch exactly this and keep booting in
    templated-only mode, instead of either crashing the whole server or
    accidentally swallowing some other, unrelated error."""


def load_llm():
    """Lazily load and cache the local GGUF model.

    Loading is expensive (hundreds of MB, real disk + init time), so this
    only happens once per process, on first use, not at import time -
    importing this module must stay cheap and side-effect free.

    Raises LLMModelNotFoundError if the configured model file doesn't
    exist - checked explicitly before ever touching llama_cpp, so the
    failure is this specific, catchable type with the exact path in its
    message, not a raw FileNotFoundError or whatever llama_cpp itself
    would raise trying to open a missing file.
    """
    global _llm_instance
    if _llm_instance is None:
        settings = get_settings()
        model_path = Path(settings.llm_model_path)
        if not model_path.exists():
            raise LLMModelNotFoundError(f"LLM model file not found at '{model_path}'")

        from llama_cpp import Llama

        _llm_instance = Llama(
            model_path=str(model_path),
            n_ctx=2048,
            verbose=False,
        )
    return _llm_instance


def is_llm_available() -> bool:
    """Whether the LLM has already been successfully loaded in this
    process - False both when loading was never attempted and when the
    last attempt failed (e.g. LLMModelNotFoundError at startup); either
    way there's no usable instance to call. Never attempts a load itself -
    see load_llm() for that - so this is safe to call from a hot path
    (e.g. answer_query()'s prefer_llm check, or /health) without risking
    the cost or side effects of a real load attempt."""
    return _llm_instance is not None


def _filename(path: str) -> str:
    return Path(path).name


def _positive_explanations(item: dict) -> list[str]:
    positive = [f for f in item.get("factors", []) if f.get("contribution", 0) > 0]
    positive.sort(key=lambda f: f["contribution"], reverse=True)
    return [f["explanation"] for f in positive]


def _facts_block(reranked_results: list[dict]) -> str:
    """Render reranked_results as a plain-text facts list for the prompt -
    the same underlying data copilot_answer.py's templates draw from, just
    handed to the model instead of being spliced into a template string."""
    items = [r["item"] for r in reranked_results]
    blocks = []
    for item in items:
        lines = [f"- path: {item['path']}", f"  recommended_action: {item['recommended_action']}"]
        for explanation in _positive_explanations(item):
            lines.append(f"  reason: {explanation}")
        if item.get("duplicate_of"):
            lines.append(f"  exact duplicate of: {item['duplicate_of']}")
        if item.get("near_duplicate_of"):
            lines.append(f"  similar to: {', '.join(item['near_duplicate_of'])}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _filter_results_for_intent(reranked_results: list[dict], intent: str) -> list[dict]:
    """Restrict what the model is even shown to facts consistent with this
    intent's question, per _INTENT_ALLOWED_ACTIONS - e.g. a "whats_safe"
    question should never have a "keep" file in its facts section at all,
    so the model has no way to describe one as safe to delete. Physically
    excluding the fact is the fix; the system prompt's "use only the
    facts" instruction alone isn't enough, since a real file's presence in
    the facts doesn't tell the model whether it actually answers the
    question being asked. The narrower list this returns also becomes the
    grounding truth in generate_llm_answer() - see its docstring - so any
    mention of an excluded file is caught as a grounding failure too."""
    allowed_actions = _INTENT_ALLOWED_ACTIONS.get(intent)
    if allowed_actions is None:
        return reranked_results
    return [r for r in reranked_results if r["item"]["recommended_action"] in allowed_actions]


def _is_genuine_sentence_end(text: str, i: int) -> bool:
    """Whether text[i] (one of _SENTENCE_END_CHARS) is a real sentence
    boundary rather than punctuation that just happens to appear there -
    the facts block is full of paths and sizes, both of which contain
    '.', so a naive "is this char '.', '!' or '?'" check false-positives
    constantly:

    - A decimal number cut off mid-generation (e.g. "...(15." from a
      truncated "15.6 MB") ends in '.', but that '.' is preceded by a
      digit - real sentences don't end "...word5." with no space before
      the digit run either, so this is a strong tell it's a number, not a
      sentence end.
    - A file extension's '.' (e.g. "Introduction.mp4") is immediately
      followed by more non-space filename characters, never whitespace or
      end-of-string - unlike a real sentence-ending '.', which is always
      followed by a space/newline or is the last character of the text.
    """
    if text[i] not in _SENTENCE_END_CHARS:
        return False
    if i > 0 and text[i - 1].isdigit():
        return False
    if i == len(text) - 1:
        return True
    return text[i + 1].isspace()


def _trim_to_complete_sentence(text: str) -> str:
    """Cut text back to its last complete sentence instead of returning a
    mid-word (or mid-number, or mid-filename) truncation - hitting
    max_tokens can end generation anywhere, and a shorter answer that
    ends cleanly reads far better than one that trails off. No-op if text
    already ends on a genuine sentence boundary (_is_genuine_sentence_end).
    If no real sentence boundary exists anywhere (this answer style is
    often a '\\n'-separated bullet list with no periods at all), falls
    back to cutting the last, incomplete bullet/line off entirely rather
    than returning a bare '.', '!' or '?' scan result. Only if there's no
    earlier boundary of any kind does this give up and return the
    untrimmed text - a mid-word cutoff still beats returning nothing."""
    if not text:
        return text
    if _is_genuine_sentence_end(text, len(text) - 1):
        return text
    for i in range(len(text) - 1, -1, -1):
        if text[i] in _SENTENCE_END_CHARS and _is_genuine_sentence_end(text, i):
            return text[: i + 1]
    last_newline = text.rstrip().rfind("\n")
    if last_newline != -1:
        return text[:last_newline].rstrip()
    return text


def _build_prompt(query: str, reranked_results: list[dict], intent: str) -> list[dict]:
    system_prompt = (
        "You are NOVA Copilot, a disk-cleanup assistant. Answer the user's "
        "question using ONLY the facts listed below - they are the "
        "complete result of a real scan. Never invent file names, paths, "
        "sizes, or reasons that are not explicitly present in the facts. "
        "If the facts don't fully answer the question, say only what the "
        "facts support. Keep the answer concise: 2-4 sentences, plain "
        "text, no markdown formatting."
    )
    user_prompt = f"User question (intent: {intent}): {query}\n\nFacts:\n{_facts_block(reranked_results)}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _check_grounding(answer_text: str, real_paths: list[str]) -> None:
    """Raise LLMGroundingError if answer_text mentions any file path/name
    that isn't actually one of real_paths (or a suffix/basename of one).
    Never return partially-grounded text - see module docstring."""
    for token in _PATH_TOKEN_RE.findall(answer_text):
        grounded = any(
            token == real_path or real_path.endswith(token) or _filename(real_path) == token
            for real_path in real_paths
        )
        if not grounded:
            raise LLMGroundingError(f"LLM answer mentions a path not present in the input data: {token!r}")


def _cited_paths(answer_text: str, real_paths: list[str]) -> list[str]:
    return [path for path in real_paths if path in answer_text or _filename(path) in answer_text]


def _call_llm(messages: list[dict]) -> str:
    """Run one real inference call, serialized through _llm_lock.

    If another call (possibly an orphaned one left running past a prior
    timeout) already holds the lock, this waits at most
    _LOCK_ACQUIRE_TIMEOUT_SECONDS for it, then raises LLMTimeoutError
    rather than either blocking indefinitely or running concurrently
    against the same shared model instance - see _llm_lock's docstring.
    """
    if not _llm_lock.acquire(timeout=_LOCK_ACQUIRE_TIMEOUT_SECONDS):
        raise LLMTimeoutError(
            f"LLM is busy with another request (lock not free within "
            f"{_LOCK_ACQUIRE_TIMEOUT_SECONDS}s)"
        )
    try:
        llm = load_llm()
        response = llm.create_chat_completion(messages=messages, temperature=0.3, max_tokens=200)
        return response["choices"][0]["message"]["content"]
    finally:
        _llm_lock.release()


def generate_llm_answer(
    query: str,
    reranked_results: list[dict],
    intent: str,
    timeout_seconds: float | None = None,
) -> dict:
    """LLM-backed counterpart to copilot_answer.generate_answer().

    Returns the same {"answer_text", "cited_paths", "intent"} shape, plus
    "source": "llm" on success so callers can tell which path answered.
    Raises LLMTimeoutError if the model doesn't respond in time, or
    LLMGroundingError if it mentions a file that isn't actually in the
    facts it was given - callers (see copilot_answer.answer_query) should
    catch both and fall back to the templated path. Note "facts it was
    given" may be a strict subset of reranked_results: intents listed in
    _INTENT_ALLOWED_ACTIONS (e.g. "whats_safe") have contradictory results
    (e.g. a "keep" file) filtered out before the prompt is even built, and
    that same narrowed set is what the post-generation grounding check
    validates against - so a mention of a filtered-out file is treated
    exactly like an invented one.

    timeout_seconds defaults to Settings.llm_timeout_seconds (resolved at
    call time, same as load_llm()'s model path) rather than a fixed
    literal, so NOVA_LLM_TIMEOUT_SECONDS can tune it per-machine without a
    code change.

    intent == "out_of_scope" is handled first, before anything else in
    this function runs: copilot_answer.answer_query() already short-
    circuits this case before it ever reaches here, but this path handles
    it too so a direct caller gets the same fast, no-LLM-call decline
    (source: "scoped_decline") instead of the model trying to force an
    answer to an unrelated question.
    """
    from .copilot_answer import OUT_OF_SCOPE, SCOPED_DECLINE_TEXT

    if intent == OUT_OF_SCOPE:
        return {
            "answer_text": SCOPED_DECLINE_TEXT,
            "cited_paths": [],
            "intent": intent,
            "source": "scoped_decline",
        }

    if timeout_seconds is None:
        timeout_seconds = get_settings().llm_timeout_seconds

    if not reranked_results:
        # Same honest "nothing found" response the templated path gives -
        # no reason to spend a model call on facts that don't exist.
        from .copilot_answer import NO_RESULTS_TEXT

        return {"answer_text": NO_RESULTS_TEXT, "cited_paths": [], "intent": intent}

    filtered_results = _filter_results_for_intent(reranked_results, intent)
    if not filtered_results:
        # Everything got filtered out for this intent (e.g. a "whats_safe"
        # question where every candidate is actually a "keep") - there are
        # no legitimate facts left for the LLM to answer from. Defer to
        # the templated path's own honest handling of this case (it knows
        # how to say "nothing looks safe to remove") rather than either
        # forcing the LLM to answer anyway or fabricating a response here.
        from .copilot_answer import generate_answer

        return generate_answer(query, reranked_results, intent)

    messages = _build_prompt(query, filtered_results, intent)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_call_llm, messages)
    try:
        raw_answer = future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError as exc:
        raise LLMTimeoutError(f"LLM did not respond within {timeout_seconds}s") from exc
    finally:
        # Don't block the caller waiting for a hung model call to finish -
        # let it run itself out in the background thread (or, if it's
        # stuck on _llm_lock, until that lock's own bounded wait expires).
        # Always runs, on both the success and timeout paths, so the
        # executor is never leaked.
        executor.shutdown(wait=False)

    answer_text = _trim_to_complete_sentence(raw_answer.strip())
    real_paths = [r["item"]["path"] for r in filtered_results]
    _check_grounding(answer_text, real_paths)

    return {
        "answer_text": answer_text,
        "cited_paths": _cited_paths(answer_text, real_paths),
        "intent": intent,
        "source": "llm",
    }
