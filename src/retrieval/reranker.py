"""Cross-encoder reranking.

The reranker is the last quality-gate before LLM explanations, so two
things matter most here:

1. The document passed to the cross-encoder must be overview-rich, not
   title-only. A title-only pair like `("astronaut on mars", "Stranded")`
   lets the model fall back to surface lexical overlap and rewards
   exactly the kind of title-keyword movies we are trying to push down.
2. We deduplicate before AND after scoring so a movie cannot occupy two
   final slots through a metadata mismatch upstream.
"""
from __future__ import annotations
from math import log1p

from src.config import (
    FINAL_TOP_K,
    RERANK_TOP_K,
    RERANK_SOURCE_AGREEMENT_BONUS,
    RERANK_UPSTREAM_WEIGHT,
    RERANK_VOTE_COUNT_WEIGHT,
)
from src.models import get_reranker
from src.utils.dedup import deduplicate_movies, get_movie_key


def _year_str(m: dict) -> str:
    y = m.get("year")
    if y:
        try:
            return str(int(y))
        except (TypeError, ValueError):
            pass
    rd = str(m.get("release_date", "") or "")
    return rd[:4] if len(rd) >= 4 and rd[:4].isdigit() else ""


def build_movie_document(m: dict) -> str:
    """Render the candidate as a single text block for the cross-encoder.

    Order: title → year → genres → tagline → overview → keywords.
    Overview is given the largest character budget so that, after the
    cross-encoder's truncation, it dominates the attention budget. No
    ranking scores (rerank/rrf/vote_*) are included — those would leak
    upstream signals into the cross-encoder.
    """
    title = str(m.get("title", "") or "").strip()
    year = _year_str(m)
    genres = str(m.get("genres", "") or "").strip()
    tagline = str(m.get("tagline", "") or "").strip()
    overview = str(m.get("overview", "") or "").strip()
    keywords = str(m.get("keywords", "") or "").strip()

    parts = []
    if title:
        head = f"{title} ({year})" if year else title
        parts.append(f"Title: {head}.")
    if genres:
        parts.append(f"Genres: {genres}.")
    if tagline:
        parts.append(f"Tagline: {tagline[:200]}")
    if overview:
        parts.append(f"Overview: {overview[:600]}")
    if keywords:
        parts.append(f"Keywords: {keywords[:200]}")
    return " ".join(parts) if parts else (title or "")


def _float_value(movie: dict, key: str) -> float:
    try:
        return float(movie.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _upstream_score(movie: dict) -> float:
    for key in ("rrf_score", "semantic_rrf", "semantic_score", "bm25_score", "final_score"):
        score = _float_value(movie, key)
        if score:
            return score
    return 0.0


def _source_agreement(movie: dict) -> float:
    """Small binary prior when dense and sparse retrieval both found a movie."""
    if movie.get("semantic_rank") is not None and movie.get("bm25_rank") is not None:
        return 1.0
    return 0.0


def rerank(
    query: str,
    movies: list[dict],
    top_k: int = FINAL_TOP_K,
    rerank_pool: int = RERANK_TOP_K,
) -> list[dict]:
    if not movies:
        return []

    # Dedup BEFORE the cross-encoder so we never spend a slot on a
    # duplicate. prefer_score is set to final_score so the strongest
    # fused/RRF candidate survives.
    deduped = deduplicate_movies(movies, prefer_score="final_score")
    deduped.sort(key=lambda m: _float_value(m, "final_score"), reverse=True)
    pool = deduped[:rerank_pool]

    reranker = get_reranker()
    pairs = [[query, build_movie_document(m)] for m in pool]
    scores = reranker.predict(pairs, show_progress_bar=False)

    max_votes = max((int(m.get("vote_count", 0) or 0) for m in pool), default=0)
    max_vote_log = log1p(max_votes) or 1.0
    upstream_values = [_upstream_score(m) for m in pool]
    max_upstream = max(upstream_values, default=0.0) or 1.0

    for m, s, upstream_raw in zip(pool, scores, upstream_values):
        rerank_score = float(s)
        vote_prior = log1p(int(m.get("vote_count", 0) or 0)) / max_vote_log
        upstream_prior = upstream_raw / max_upstream
        source_agreement = _source_agreement(m)
        final_score = (
            rerank_score
            + RERANK_VOTE_COUNT_WEIGHT * vote_prior
            + RERANK_UPSTREAM_WEIGHT * upstream_prior
            + RERANK_SOURCE_AGREEMENT_BONUS * source_agreement
        )
        m["rerank_score"] = rerank_score
        m["quality_prior"] = vote_prior
        m["upstream_prior"] = upstream_prior
        m["source_agreement"] = source_agreement
        m["final_score"] = final_score
        debug = m.get("debug") or {}
        debug = dict(debug)
        debug["rerank_score"] = rerank_score
        debug["quality_prior"] = vote_prior
        debug["upstream_prior"] = upstream_prior
        debug["source_agreement"] = source_agreement
        debug["final_score"] = final_score
        m["debug"] = debug
        if not m.get("movie_key"):
            m["movie_key"] = get_movie_key(m)

    # Dedup AFTER too — if the rerank pool contained a duplicate we
    # missed (e.g. movie_key collision via title+year fallback), keep
    # the higher-scoring copy.
    pool = deduplicate_movies(pool, prefer_score="final_score")
    pool.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    return pool[:top_k]
