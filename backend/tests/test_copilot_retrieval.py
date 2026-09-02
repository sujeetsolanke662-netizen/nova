import pytest

from backend.app.copilot_retrieval import _tokenize, build_index, rerank, search


def _item(path, recommended_action, factors, staleness_score=0.5):
    return {
        "path": path,
        "recommended_action": recommended_action,
        "staleness_score": staleness_score,
        "factors": factors,
        "duplicate_of": None,
        "near_duplicate_of": None,
    }


def _factor(explanation, contribution=0.3):
    return {"name": "test_factor", "contribution": contribution, "explanation": explanation}


# --- Corpus for the basic-index / basic-match tests: two clearly
# different topics (old log files, duplicate photos), per the requirement
# to cover a couple of distinct topics. ---

LOG_ITEM_A = _item(
    "/var/log/app/server_error.log",
    "review_recommended",
    [_factor("not accessed in 214 days")],
)
LOG_ITEM_B = _item(
    "/var/log/app/worker_debug.log",
    "auto_apply",
    [_factor("duplicate of another file"), _factor("not accessed in 300 days")],
)
PHOTO_ITEM_A = _item(
    "/home/user/Photos/vacation_beach.jpg",
    "review_recommended",
    [_factor("duplicate of another file")],
)
PHOTO_ITEM_B = _item(
    "/home/user/Photos/vacation_beach_copy.jpg",
    "auto_apply",
    [_factor("duplicate of another file")],
)
FRESH_ITEM = _item(
    "/home/user/project/notes.txt",
    "keep",
    [_factor("recently modified", contribution=0.0)],
)

BASIC_CORPUS = [LOG_ITEM_A, LOG_ITEM_B, PHOTO_ITEM_A, PHOTO_ITEM_B, FRESH_ITEM]


@pytest.fixture(scope="module")
def basic_index():
    return build_index(BASIC_CORPUS)


def test_build_index_succeeds_and_returns_non_empty_index(basic_index):
    assert basic_index["faiss_index"].ntotal == len(BASIC_CORPUS)
    assert basic_index["items"] == BASIC_CORPUS
    assert basic_index["bm25_index"] is not None


def test_search_returns_closely_matching_item_in_top_results(basic_index):
    results = search("duplicate vacation photo taking up space", basic_index, top_k=3)

    assert len(results) > 0
    top_paths = {r["item"]["path"] for r in results}
    assert PHOTO_ITEM_A["path"] in top_paths or PHOTO_ITEM_B["path"] in top_paths


# --- Corpus for the RRF fusion test: one item shares a rare exact keyword
# with the query (BM25 should find it); a different item is semantically
# close to the query's meaning but shares no literal tokens with it at all
# (FAISS should find it). Filler items are built to share zero tokens with
# the query, so they can't accidentally contaminate the BM25 signal. ---

KEYWORD_ITEM = _item(
    "/home/user/Documents/invoice_2023.pdf",
    "review_recommended",
    [_factor("not accessed in 180 days")],
)
SEMANTIC_ITEM = _item(
    "/home/user/Scans/receipt_scan_042.jpg",
    "auto_apply",
    [_factor("outdated billing record, hasn't been opened in over a year")],
)
FILLER_ITEMS = [
    _item("/home/user/Pictures/sunset_beach.jpg", "keep", [_factor("recently accessed")]),
    _item("/home/user/Work/quarterly_slides.pptx", "keep", [_factor("accessed yesterday")]),
    _item("/home/user/Clips/funny_clip.mp4", "keep", [_factor("recently accessed")]),
    _item("/home/user/Desktop/todo_list.txt", "keep", [_factor("actively edited today")]),
]

FUSION_CORPUS = [KEYWORD_ITEM, SEMANTIC_ITEM, *FILLER_ITEMS]
FUSION_QUERY = "old invoice documents I should probably delete"


@pytest.fixture(scope="module")
def fusion_index():
    return build_index(FUSION_CORPUS)


def test_search_fusion_surfaces_both_keyword_and_semantic_matches(fusion_index):
    # Sanity check the test's own premise: BM25 must score the semantic
    # item at exactly zero for this query (no shared tokens at all), so
    # any credit it gets in the fused results can only have come from
    # FAISS - proving fusion, not BM25, is what surfaces it.
    bm25_scores = fusion_index["bm25_index"].get_scores(_tokenize(FUSION_QUERY))
    semantic_idx = FUSION_CORPUS.index(SEMANTIC_ITEM)
    assert bm25_scores[semantic_idx] == 0.0

    results = search(FUSION_QUERY, fusion_index, top_k=4)
    by_path = {r["item"]["path"]: r for r in results}

    assert KEYWORD_ITEM["path"] in by_path
    assert SEMANTIC_ITEM["path"] in by_path

    assert "bm25" in by_path[KEYWORD_ITEM["path"]]["sources"]
    assert "faiss" in by_path[SEMANTIC_ITEM["path"]]["sources"]
    # The semantic item's only source of credit must be FAISS - it has no
    # keyword overlap with the query at all.
    assert "bm25" not in by_path[SEMANTIC_ITEM["path"]]["sources"]


def test_rerank_puts_a_defensible_best_match_on_top(fusion_index):
    candidates = search(FUSION_QUERY, fusion_index, top_k=6)

    results = rerank(FUSION_QUERY, candidates, top_k=3)

    assert len(results) == 3
    scores = [r["cross_encoder_score"] for r in results]
    assert scores == sorted(scores, reverse=True)

    # Loose check, not a fixed ordering: the top result should be one of
    # the two genuinely relevant items, not an unrelated filler file.
    top_path = results[0]["item"]["path"]
    assert top_path in {KEYWORD_ITEM["path"], SEMANTIC_ITEM["path"]}
