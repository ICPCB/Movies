"""Basic pipeline: query normalization → semantic search → top K."""
from __future__ import annotations
from src.config import FINAL_TOP_K
from src.retrieval.query_processor import normalize_query, expand_retrieval_query
from src.retrieval.filters import parse_filters
from src.retrieval.semantic import semantic_search
from src.utils.dedup import deduplicate_movies
from src.utils.debug import timed


def run(query: str, top_k: int = FINAL_TOP_K) -> list[dict]:
    with timed("normalize_query", "basic"):
        processed = normalize_query(query)
    with timed("parse_filters", "basic"):
        filters = parse_filters(query) or None
    retrieval_query = expand_retrieval_query(processed)

    with timed("semantic_search", "basic"):
        movies = semantic_search(retrieval_query, top_k=max(top_k * 4, top_k), filters=filters)
    movies = deduplicate_movies(movies, prefer_score="semantic_score")

    # Basic mode: final_score IS semantic_score. No reranker, no RRF.
    for m in movies:
        m["final_score"] = m.get("semantic_score", 0.0)
        m["explanation"] = ""
    movies.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    return movies[:top_k]
