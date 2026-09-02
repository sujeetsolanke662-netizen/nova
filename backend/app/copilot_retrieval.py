"""Retrieval pipeline for NOVA Copilot.

Indexes recommendation data (the "recommendations" list from
generate_recommendations()'s output) so natural-language questions can find
relevant files by meaning, not just exact keyword match.

Three-stage retrieval, each stage narrower and more expensive than the
last:

1. build_index() embeds a short, genuinely descriptive text
   representation of every item (filename, parent folder, recommended
   action, and its positive staleness factors) with an SBERT bi-encoder
   into a FAISS index, and separately indexes the same text with BM25.
2. search() queries both indexes and fuses their rankings with Reciprocal
   Rank Fusion (RRF), so an item only one method would surface (an exact
   keyword hit BM25 catches but is semantically unremarkable, or a
   semantic match that shares no literal words) still comes through.
3. rerank() takes that narrowed candidate list and re-scores it with a
   cross-encoder, which is far more accurate at judging query-vs-document
   relevance than the bi-encoder/BM25 fusion, but far too expensive to run
   against every indexed item - hence only running it here, on the
   already-narrowed list.
"""

from __future__ import annotations

import re
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

SBERT_MODEL_NAME = "all-MiniLM-L6-v2"
CROSS_ENCODER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Standard Reciprocal Rank Fusion constant.
RRF_K = 60

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Both models are loaded lazily and cached at module level rather than
# stored in the index dict: they're process-wide singletons (loading them
# is the slow part), not per-index state, and every index built in this
# process shares the same two models anyway.
_sbert_model: SentenceTransformer | None = None
_cross_encoder_model: CrossEncoder | None = None


def _get_sbert_model() -> SentenceTransformer:
    global _sbert_model
    if _sbert_model is None:
        _sbert_model = SentenceTransformer(SBERT_MODEL_NAME)
    return _sbert_model


def _get_cross_encoder_model() -> CrossEncoder:
    global _cross_encoder_model
    if _cross_encoder_model is None:
        _cross_encoder_model = CrossEncoder(CROSS_ENCODER_MODEL_NAME)
    return _cross_encoder_model


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on any non-alphanumeric run - same tokenization
    for indexing and querying, so BM25 term matching is consistent."""
    return _TOKEN_RE.findall(text.lower())


def _build_text_representation(item: dict) -> str:
    """A short, descriptive string for one recommendation item - what
    actually gets embedded and indexed, not the raw path.

    e.g. "app_2.log in .storageai_quarantine, review_recommended, not
    accessed in 214 days, duplicate of another file"
    """
    path = Path(item["path"])
    parts = [f"{path.name} in {path.parent.name}", item["recommended_action"]]
    parts.extend(
        factor["explanation"]
        for factor in item.get("factors", [])
        if factor.get("contribution", 0) > 0
    )
    return ", ".join(parts)


def build_index(recommendations: list[dict]) -> dict:
    """Build a searchable index over a list of recommendation items.

    Returns a dict bundling everything search()/rerank() need: the FAISS
    index (cosine similarity via normalized embeddings + inner product),
    the BM25 index, and the original recommendation items (so results map
    back to full data, not just the text that was searched). The SBERT
    model itself isn't stored here - see _get_sbert_model()'s docstring.
    """
    texts = [_build_text_representation(item) for item in recommendations]

    model = _get_sbert_model()
    embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype="float32")

    faiss_index = faiss.IndexFlatIP(embeddings.shape[1])
    faiss_index.add(embeddings)

    bm25_index = BM25Okapi([_tokenize(text) for text in texts])

    return {
        "faiss_index": faiss_index,
        "bm25_index": bm25_index,
        "items": recommendations,
    }


def _rrf_merge(rankings: list[list[int]]) -> tuple[dict[int, float], dict[int, set[str]]]:
    """Reciprocal Rank Fusion over several (name, ranked-index-list) pairs.

    score(item) = sum, over every ranking it appears in, of 1/(RRF_K + rank)
    with rank 1-indexed (the top result in a ranking contributes
    1/(RRF_K + 1)). An item missing from a ranking simply contributes
    nothing from it - it isn't penalized beyond not getting that credit.
    """
    scores: dict[int, float] = {}
    sources: dict[int, set[str]] = {}

    for name, ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (RRF_K + rank)
            sources.setdefault(idx, set()).add(name)

    return scores, sources


def search(query: str, index: dict, top_k: int = 10) -> list[dict]:
    """Search both the FAISS (semantic) and BM25 (keyword) indexes and
    fuse their rankings with RRF.

    Returns up to top_k results, each {"item": <recommendation dict>,
    "rrf_score": float, "sources": [...]} where "sources" lists which
    ranking(s) ("faiss", "bm25") this item appeared in - kept around for
    explainability/debugging, not just the final score.
    """
    items = index["items"]
    n = len(items)
    if n == 0:
        return []

    top_k_effective = min(top_k, n)

    model = _get_sbert_model()
    query_embedding = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    query_embedding = np.asarray(query_embedding, dtype="float32")

    _scores, faiss_indices = index["faiss_index"].search(query_embedding, top_k_effective)
    faiss_ranking = [int(idx) for idx in faiss_indices[0] if idx != -1]

    bm25_scores = index["bm25_index"].get_scores(_tokenize(query))
    bm25_ranking = [int(idx) for idx in np.argsort(bm25_scores)[::-1][:top_k_effective]]

    rrf_scores, sources = _rrf_merge([("faiss", faiss_ranking), ("bm25", bm25_ranking)])

    ranked_indices = sorted(rrf_scores, key=lambda idx: rrf_scores[idx], reverse=True)

    return [
        {
            "item": items[idx],
            "rrf_score": rrf_scores[idx],
            "sources": sorted(sources[idx]),
        }
        for idx in ranked_indices[:top_k]
    ]


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Re-score search()'s narrowed candidate list with a cross-encoder.

    `candidates` is search()'s output (each with an "item" key). Far more
    accurate at judging query-vs-document relevance than the bi-encoder/
    BM25 fusion above, but too slow to run over every indexed item - which
    is exactly why it only runs here, on the already-narrowed list.

    Returns the top_k candidates, sorted by cross-encoder score
    descending, with a "cross_encoder_score" added to each.
    """
    if not candidates:
        return []

    cross_encoder = _get_cross_encoder_model()
    pairs = [(query, _build_text_representation(c["item"])) for c in candidates]
    scores = cross_encoder.predict(pairs)

    rescored = [
        {**candidate, "cross_encoder_score": float(score)}
        for candidate, score in zip(candidates, scores)
    ]
    rescored.sort(key=lambda c: c["cross_encoder_score"], reverse=True)

    return rescored[:top_k]
