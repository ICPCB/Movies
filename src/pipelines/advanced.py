"""Advanced pipeline:
    normalize -> optional LLM expand -> deterministic expand -> semantic + BM25
        -> RRF fuse -> dedup -> user-intent rerank -> dedup -> final top_k
        -> single batched LLM explain for top EXPLAIN_TOP_K (fallback otherwise)

Phase 6a note: when USE_HYDE_IN_ADVANCED is True we ask the LLM to write
a short synthetic TMDB-style overview and embed that for semantic
retrieval. The reranker uses the deterministic, title-free intent query
(never the LLM rewrite), so LLM expansion cannot drift the final
relevance check.
If HyDE returns "" (timeout, outage, or rejected reply) we fall back to
the expanded query, which itself falls back to the normalized query.
"""
from __future__ import annotations
from src import config as runtime_config
from src.config import (
    FINAL_TOP_K, CANDIDATE_POOL, RERANK_TOP_K, EXPLAIN_TOP_K, RRF_K,
    RERANK_POOL,
)
from src.retrieval.query_processor import normalize_query, expand_retrieval_query
from src.retrieval.filters import parse_filters
from src.retrieval.semantic import semantic_search
from src.retrieval.bm25 import bm25_search
from src.retrieval.fusion import rrf_fusion
from src.retrieval.reranker import rerank
from src.retrieval.mood_preprocessor import extract_mood_intent
from src.retrieval.safety_filter import apply_safety_filter
from src.utils.dedup import deduplicate_movies, get_movie_key
from src.utils.debug import timed
from src.llm.langchain_ollama import (
    expand_query, hyde_generate, explain_movies_batch, _fallback_explanation,
)


def _rrf_two_semantic(list_a: list[dict], list_b: list[dict]) -> list[dict]:
    """Rank-based fusion of two semantic-search results.

    Why this exists: when we run two semantic queries (one against the
    user's expanded keyword query, one against a HyDE-style synthetic
    overview) the raw `semantic_score` values are not comparable —
    they were computed against different query embeddings. Sorting by
    `final_score` would let whichever query produced higher absolute
    similarities dominate the candidate pool, dropping movies that
    only the OTHER query found. RRF cares only about each candidate's
    *rank* inside its source list, so a movie that ranks well in
    either retrieval is preserved for the reranker to arbitrate.
    """
    rrf_score: dict[str, float] = {}
    keep: dict[str, dict] = {}
    for source in (list_a, list_b):
        for rank, m in enumerate(source):
            key = m.get("movie_key") or get_movie_key(m)
            rrf_score[key] = rrf_score.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            existing = keep.get(key)
            # Keep the entry with the higher original semantic_score so
            # downstream debug output still reflects the better hit.
            if (existing is None
                    or (m.get("semantic_score", 0.0) or 0.0)
                    > (existing.get("semantic_score", 0.0) or 0.0)):
                keep[key] = m

    fused: list[dict] = []
    for rank, (key, m) in enumerate(sorted(
        keep.items(),
        key=lambda item: rrf_score[item[0]],
        reverse=True,
    )):
        m["semantic_rrf"] = rrf_score[key]
        m["semantic_rank"] = rank
        debug = dict(m.get("debug") or {})
        debug["semantic_rrf"] = rrf_score[key]
        debug["semantic_rank"] = rank
        m["debug"] = debug
        # Stamp final_score so the reranker's pool truncation (which
        # sorts by final_score) selects by RRF rather than by an
        # incommensurable raw similarity.
        m["final_score"] = rrf_score[key]
        fused.append(m)
    return fused


def run(query: str, top_k: int = FINAL_TOP_K, with_explanation: bool = True) -> list[dict]:
    with timed("extract_mood_intent", "advanced"):
        mood = extract_mood_intent(query)
    retrieval_input = mood.cleaned_query if mood.current_emotion else query

    with timed("normalize_query", "advanced"):
        processed = normalize_query(retrieval_input)
    deterministic_query = expand_retrieval_query(processed)
    if runtime_config.LLM_RETRIEVAL_ENABLED:
        with timed("expand_query", "advanced"):
            expanded = expand_retrieval_query(expand_query(processed) or processed)
    else:
        expanded = deterministic_query
    rerank_query = deterministic_query

    if runtime_config.USE_HYDE_IN_ADVANCED and runtime_config.LLM_RETRIEVAL_ENABLED:
        with timed("hyde_generate", "advanced"):
            hyde = hyde_generate(processed)
    else:
        hyde = ""

    with timed("parse_filters", "advanced"):
        filters = parse_filters(query) or None

    # Always retrieve with the expanded query — that keeps the candidates
    # the user's keyword intent points at. When HyDE is on AND returned
    # a synthetic overview, we run a second semantic pass against the
    # synthetic overview and rank-fuse the two retrievals via RRF. The
    # reranker then arbitrates. RRF (not union-by-score) is the right
    # merge here because the two semantic queries are embedded against
    # different reference strings — their raw similarity scores are not
    # commensurable, so rank order is the only fair signal.
    with timed("semantic_search", "advanced"):
        candidates_exp = semantic_search(expanded, top_k=CANDIDATE_POOL, filters=filters)
        if hyde:
            candidates_hyde = semantic_search(hyde, top_k=CANDIDATE_POOL, filters=filters)
            semantic_candidates = _rrf_two_semantic(candidates_exp, candidates_hyde)
        else:
            semantic_candidates = candidates_exp

    with timed("bm25_search", "advanced"):
        bm25_candidates = bm25_search(expanded, top_k=CANDIDATE_POOL, filters=filters)

    semantic_candidates = deduplicate_movies(semantic_candidates, prefer_score="final_score")
    bm25_candidates = deduplicate_movies(bm25_candidates, prefer_score="bm25_score")

    with timed("rrf_fusion", "advanced"):
        candidates = rrf_fusion(semantic_candidates, bm25_candidates, top_k=RERANK_POOL)

    candidates = deduplicate_movies(candidates, prefer_score="rrf_score")

    with timed("rerank", "advanced"):
        final = rerank(rerank_query, candidates, top_k=top_k, rerank_pool=RERANK_TOP_K)
    final = deduplicate_movies(final, prefer_score="final_score")
    final.sort(key=lambda x: x.get("final_score", x.get("rerank_score", 0.0)), reverse=True)

    with timed("safety_filter", "advanced"):
        final = apply_safety_filter(final, mood)

    final = final[:top_k]

    _attach_explanations(query, final, with_explanation)
    return final


def _attach_explanations(query: str, final: list[dict], with_explanation: bool) -> None:
    if not final:
        return
    if not with_explanation:
        for m in final:
            m["explanation"] = ""
        return

    explain_n = min(EXPLAIN_TOP_K, len(final))
    with timed("explain_movies_batch", "advanced"):
        explanations = explain_movies_batch(query, final[:explain_n])
    for m, text in zip(final[:explain_n], explanations):
        m["explanation"] = text or _fallback_explanation(query, m)
    for m in final[explain_n:]:
        m["explanation"] = ""
