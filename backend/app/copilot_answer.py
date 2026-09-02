"""Answer generation for NOVA Copilot.

Turns search/rerank results into a plain-English answer using
intent-specific templates - zero LLM calls, by design: NOVA is fully
offline, so every sentence here is templated string composition over the
actual result data, never a generative model call. Every fact the
generated text states must trace back to the input results; nothing here
invents a file count, size, or reason that isn't already present in the
data passed in.
"""

from __future__ import annotations

import re
from pathlib import Path

from .copilot_retrieval import rerank, search

WHY_FULL = "why_full"
FIND_DUPLICATES = "find_duplicates"
WHATS_SAFE = "whats_safe"
GENERAL = "general"

NO_RESULTS_TEXT = "I didn't find anything matching that."

# Simple, honest keyword matching - no ML. This only needs to pick a
# reasonable template family, not truly understand the question. Order
# matters: checked top to bottom, first match wins. The more specific
# intents (explicitly about duplicates, or explicitly about safety/
# deletion) are checked before the broad "why is my space used" wording,
# since a query like "why do I have so many duplicate files" is really
# asking about duplicates, not a general space-usage question.
_INTENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        FIND_DUPLICATES,
        ("duplicate", "duplicates", "similar file", "similar files", "copies", "copy of", "same file"),
    ),
    (
        WHATS_SAFE,
        (
            "safe to delete",
            "safe to remove",
            "can i delete",
            "should i delete",
            "what can i delete",
            "what should i delete",
            "what's safe",
            "whats safe",
            "clean up",
            "cleanup",
            "ok to delete",
        ),
    ),
    (
        WHY_FULL,
        (
            "why",
            "full",
            "taking up",
            "using up",
            "using the most",
            "most space",
            "biggest",
            "largest",
            "out of space",
            "running out",
            "so much space",
            "disk usage",
            "storage usage",
        ),
    ),
]


def classify_query_intent(query: str) -> str:
    """Classify a query into one of the template families above.

    Deliberately simple substring matching, not a model - see the module
    docstring for why. Falls back to "general" when nothing matches.
    """
    query_lower = query.lower()
    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword in query_lower for keyword in keywords):
            return intent
    return GENERAL


def _filename(path: str) -> str:
    return Path(path).name


def _positive_explanations(item: dict) -> list[str]:
    """Explanations for this item's factors that actually contributed to
    its score, most-contributing first - the same "what actually mattered"
    filter used elsewhere (e.g. recommendation.py's _build_reason)."""
    positive = [f for f in item.get("factors", []) if f.get("contribution", 0) > 0]
    positive.sort(key=lambda f: f["contribution"], reverse=True)
    return [f["explanation"] for f in positive]


_SIZE_MB_RE = re.compile(r"([\d.]+)\s*MB")


def _extract_size_mb(item: dict) -> float | None:
    """Pull a size in MB out of this item's factor explanations, if any
    mention one (staleness.py's size_factor explanation includes one for
    files >= 1 MB). Returns None rather than guessing when it can't - see
    generate_answer()'s "only state what's computable" rule."""
    for factor in item.get("factors", []):
        match = _SIZE_MB_RE.search(factor.get("explanation", ""))
        if match:
            return float(match.group(1))
    return None


def _answer_why_full(results: list[dict], intent: str) -> dict:
    items = [r["item"] for r in results]

    known_sizes_mb = [size for size in (_extract_size_mb(item) for item in items) if size is not None]
    if known_sizes_mb:
        lead = (
            f"Here's what appears to be using up your space - together, these "
            f"account for at least {sum(known_sizes_mb):.1f} MB you could reclaim:"
        )
    else:
        lead = "Here's what appears to be using up your space:"

    sentences = [lead]
    cited_paths = []
    for item in items[:4]:
        explanations = _positive_explanations(item)
        reason = explanations[0] if explanations else "flagged by the staleness scan"
        sentences.append(f"- {_filename(item['path'])}: {reason}.")
        cited_paths.append(item["path"])

    return {"answer_text": "\n".join(sentences), "cited_paths": cited_paths, "intent": intent}


def _answer_find_duplicates(results: list[dict], intent: str) -> dict:
    items = [r["item"] for r in results]

    exact_dupes = [item for item in items if item.get("duplicate_of")]
    near_dupes = [item for item in items if item.get("near_duplicate_of")]

    if not exact_dupes and not near_dupes:
        return {
            "answer_text": "I didn't find any duplicate or similar files among the matches for that.",
            "cited_paths": [],
            "intent": intent,
        }

    sentences = []
    cited_paths = []

    if exact_dupes:
        sentences.append(f"Found {len(exact_dupes)} exact duplicate file(s):")
        for item in exact_dupes[:4]:
            sentences.append(
                f"- {_filename(item['path'])} is an exact copy of {_filename(item['duplicate_of'])}."
            )
            cited_paths.append(item["path"])

    if near_dupes:
        sentences.append(f"Found {len(near_dupes)} near-duplicate/similar file(s):")
        for item in near_dupes[:4]:
            others = ", ".join(_filename(p) for p in item["near_duplicate_of"])
            sentences.append(f"- {_filename(item['path'])} is similar to {others}.")
            cited_paths.append(item["path"])

    return {"answer_text": "\n".join(sentences), "cited_paths": cited_paths, "intent": intent}


def _answer_whats_safe(results: list[dict], intent: str) -> dict:
    items = [r["item"] for r in results]

    auto_apply = [item for item in items if item["recommended_action"] == "auto_apply"]
    review = [item for item in items if item["recommended_action"] == "review_recommended"]

    sentences = []
    cited_paths = []

    if auto_apply:
        sentences.append(f"{len(auto_apply)} file(s) look safe to remove with high confidence:")
        for item in auto_apply[:4]:
            explanations = _positive_explanations(item)
            reason = explanations[0] if explanations else "flagged as safe to auto-apply"
            sentences.append(f"- {_filename(item['path'])}: {reason}.")
            cited_paths.append(item["path"])

    if review:
        sentences.append(f"{len(review)} more file(s) are worth a quick look before deleting:")
        for item in review[:4]:
            explanations = _positive_explanations(item)
            reason = explanations[0] if explanations else "flagged for review"
            sentences.append(f"- {_filename(item['path'])}: {reason}.")
            cited_paths.append(item["path"])

    if not sentences:
        sentences.append(
            "None of the matching files look safe to remove right now - they all "
            "appear to still be in active use."
        )

    return {"answer_text": "\n".join(sentences), "cited_paths": cited_paths, "intent": intent}


def _answer_general(results: list[dict], intent: str) -> dict:
    items = [r["item"] for r in results]

    sentences = [f"Here's what I found ({len(items)} matching file(s)):"]
    cited_paths = []
    for item in items[:4]:
        explanations = _positive_explanations(item)
        line = f"- {_filename(item['path'])} ({item['recommended_action']})"
        if explanations:
            line += f": {explanations[0]}"
        sentences.append(line + ".")
        cited_paths.append(item["path"])

    return {"answer_text": "\n".join(sentences), "cited_paths": cited_paths, "intent": intent}


_TEMPLATES = {
    WHY_FULL: _answer_why_full,
    FIND_DUPLICATES: _answer_find_duplicates,
    WHATS_SAFE: _answer_whats_safe,
}


def generate_answer(query: str, reranked_results: list[dict], intent: str) -> dict:
    """Build a natural-language answer from reranked results and a
    classified intent.

    Returns {"answer_text", "cited_paths", "intent"}. "cited_paths" lists
    exactly which files answer_text actually references, so a frontend
    can highlight/link them later. Every fact stated comes straight from
    the items in reranked_results - if there's nothing to work with, this
    says so honestly rather than fabricating an answer.
    """
    if not reranked_results:
        return {"answer_text": NO_RESULTS_TEXT, "cited_paths": [], "intent": intent}

    template = _TEMPLATES.get(intent, _answer_general)
    return template(reranked_results, intent)


def answer_query(
    query: str,
    index: dict,
    top_k_search: int = 10,
    top_k_rerank: int = 5,
) -> dict:
    """Full pipeline glue: classify intent, search, rerank, then generate
    the final answer from the reranked candidates."""
    intent = classify_query_intent(query)
    search_results = search(query, index, top_k=top_k_search)
    reranked_results = rerank(query, search_results, top_k=top_k_rerank)
    return generate_answer(query, reranked_results, intent)
