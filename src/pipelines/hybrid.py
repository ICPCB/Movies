"""Hybrid pipeline:
    normalize -> optional LLM expand -> deterministic expand -> semantic + BM25
        -> dedup each source -> RRF fuse -> dedup
        -> user-intent rerank -> dedup -> final top_k
        -> batched LLM explanations for top EXPLAIN_TOP_K

Important:
- Retrieval may use LLM expansion plus deterministic metadata terms.
- Reranking uses the deterministic, title-free intent query.
- Final ordering uses final_score, not raw rerank_score.
"""
from __future__ import annotations

from src import config as runtime_config
from src.config import (
    FINAL_TOP_K,
    CANDIDATE_POOL,
    RERANK_POOL,
    RERANK_TOP_K,
    EXPLAIN_TOP_K,
)
from src.retrieval.query_processor import normalize_query, expand_retrieval_query
from src.retrieval.filters import parse_filters
from src.retrieval.semantic import semantic_search
from src.retrieval.bm25 import bm25_search
from src.retrieval.fusion import rrf_fusion
from src.retrieval.reranker import rerank
from src.retrieval.mood_preprocessor import extract_mood_intent
from src.retrieval.safety_filter import apply_safety_filter
from src.utils.dedup import deduplicate_movies
from src.utils.debug import timed
from src.llm.langchain_ollama import (
    expand_query,
    explain_movies_batch,
    _fallback_explanation,
)


def _score(m: dict, key: str, fallback: str = "final_score") -> float:
    try:
        return float(m.get(key, m.get(fallback, 0.0)) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _expand_query(query: str, *, mood_aware: bool) -> str:
    try:
        return expand_query(query, mood_aware=mood_aware)
    except TypeError as exc:
        if "mood_aware" not in str(exc):
            raise
        return expand_query(query)


def run(
    query: str,
    top_k: int = FINAL_TOP_K,
    with_explanation: bool = True,
) -> list[dict]:
    if not query or not query.strip():
        return []

    with timed("extract_mood_intent", "hybrid"):
        mood = extract_mood_intent(query)
    mood_detected = mood.current_emotion is not None
    retrieval_input = mood.cleaned_query if mood_detected else query

    with timed("normalize_query", "hybrid"):
        processed = normalize_query(retrieval_input)

    if not processed:
        return []

    deterministic_query = expand_retrieval_query(processed)
    if runtime_config.HYBRID_USE_LLM_EXPANSION and runtime_config.LLM_RETRIEVAL_ENABLED:
        with timed("expand_query", "hybrid"):
            retrieval_query = expand_retrieval_query(
                _expand_query(processed, mood_aware=mood_detected) or processed
            )
    else:
        retrieval_query = deterministic_query
    rerank_query = deterministic_query

    with timed("parse_filters", "hybrid"):
        filters = parse_filters(query) or None

    with timed("semantic_search", "hybrid"):
        sem = semantic_search(retrieval_query, top_k=CANDIDATE_POOL, filters=filters)

    with timed("bm25_search", "hybrid"):
        bm = bm25_search(retrieval_query, top_k=CANDIDATE_POOL, filters=filters)

    sem = deduplicate_movies(sem, prefer_score="semantic_score")
    bm = deduplicate_movies(bm, prefer_score="bm25_score")

    with timed("rrf_fusion", "hybrid"):
        fused = rrf_fusion(sem, bm, top_k=RERANK_POOL)

    fused = deduplicate_movies(fused, prefer_score="rrf_score")
    fused.sort(key=lambda x: _score(x, "final_score", "rrf_score"), reverse=True)

    with timed("rerank", "hybrid"):
        final = rerank(
            query=rerank_query,
            movies=fused,
            top_k=top_k,
            rerank_pool=RERANK_TOP_K,
        )

    # Important:
    # Use final_score after reranking because reranker may blend:
    # raw rerank score + upstream hybrid score + quality boost + penalties.
    final = deduplicate_movies(final, prefer_score="final_score")
    final.sort(
        key=lambda x: _score(x, "final_score", "rerank_score"),
        reverse=True,
    )

    with timed("safety_filter", "hybrid"):
        final = apply_safety_filter(final, mood)

    final = final[:top_k]

    _attach_explanations(query, final, with_explanation)
    return final


def _attach_explanations(
    query: str,
    final: list[dict],
    with_explanation: bool,
) -> None:
    if not final:
        return

    if not with_explanation:
        for m in final:
            m["explanation"] = ""
        return

    explain_n = min(EXPLAIN_TOP_K, len(final))

    with timed("explain_movies_batch", "hybrid"):
        explanations = explain_movies_batch(query, final[:explain_n])

    for m, text in zip(final[:explain_n], explanations):
        m["explanation"] = text or _fallback_explanation(query, m)

    for m in final[explain_n:]:
        m["explanation"] = ""
