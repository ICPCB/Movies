"""Reciprocal Rank Fusion (RRF) for hybrid search.

Fusion is keyed on the stable `movie_key` produced by `src.utils.dedup` —
NOT on list position. That way a movie that hits in both the semantic
list and the BM25 list is counted exactly once, and its evidence from
both sources is summed via 1/(k+rank).
"""
from __future__ import annotations
from src.config import RERANK_POOL, RRF_K, SEMANTIC_WEIGHT, BM25_WEIGHT
from src.utils.dedup import get_movie_key, deduplicate_movies


def _rank_of(movie: dict, fallback_rank: int, source: str) -> int:
    """Pull the source-side rank if a retriever already stamped one,
    otherwise fall back to the position the candidate appears in here."""
    key = "semantic_rank" if source == "semantic" else "bm25_rank"
    r = movie.get(key)
    if r is None:
        return fallback_rank
    try:
        return int(r)
    except (TypeError, ValueError):
        return fallback_rank


def rrf_fusion(
    semantic_results: list[dict],
    bm25_results: list[dict],
    top_k: int = RERANK_POOL,
) -> list[dict]:
    """Fuse two ranked lists by stable movie key with standard RRF.

    Returns deduplicated candidates sorted by rrf_score descending. Each
    fused candidate preserves both source scores/ranks so the reranker,
    the UI, and the smoke test can all inspect why a movie was promoted.
    """
    fused: dict[str, dict] = {}
    rrf_score: dict[str, float] = {}

    # --- semantic side ---
    for i, m in enumerate(semantic_results or []):
        key = m.get("movie_key") or get_movie_key(m)
        rank = _rank_of(m, i, "semantic")
        contribution = SEMANTIC_WEIGHT / (RRF_K + rank + 1)
        rrf_score[key] = rrf_score.get(key, 0.0) + contribution

        if key in fused:
            entry = fused[key]
        else:
            entry = dict(m)
            entry["movie_key"] = key
            fused[key] = entry
        if entry.get("semantic_score") is None:
            entry["semantic_score"] = m.get("semantic_score")
        if entry.get("semantic_rank") is None:
            entry["semantic_rank"] = rank

    # --- BM25 side ---
    for i, m in enumerate(bm25_results or []):
        key = m.get("movie_key") or get_movie_key(m)
        rank = _rank_of(m, i, "bm25")
        contribution = BM25_WEIGHT / (RRF_K + rank + 1)
        rrf_score[key] = rrf_score.get(key, 0.0) + contribution

        if key in fused:
            entry = fused[key]
            # Fill in any metadata the semantic side didn't carry —
            # keywords and tagline live on the BM25 row, for example.
            for k, v in m.items():
                if k in {"semantic_score", "semantic_rank", "final_score", "debug"}:
                    continue
                if entry.get(k) in (None, "", 0, 0.0) and v not in (None, "", 0, 0.0):
                    entry[k] = v
        else:
            entry = dict(m)
            entry["movie_key"] = key
            fused[key] = entry
        if entry.get("bm25_score") is None:
            entry["bm25_score"] = m.get("bm25_score")
        if entry.get("bm25_rank") is None:
            entry["bm25_rank"] = rank

    # --- stamp scores + clean up per-source `final_score` taints ---
    results: list[dict] = []
    for key, entry in fused.items():
        s = rrf_score[key]
        entry["rrf_score"] = s
        entry["final_score"] = s
        debug = entry.get("debug") or {}
        debug = dict(debug)
        debug.update({
            "semantic_rank": entry.get("semantic_rank"),
            "semantic_score": entry.get("semantic_score"),
            "bm25_rank": entry.get("bm25_rank"),
            "bm25_score": entry.get("bm25_score"),
            "rrf_score": s,
        })
        entry["debug"] = debug
        results.append(entry)

    # Defence-in-depth: dedup once more on the fused output. Fusion is
    # already keyed by movie_key so this is normally a no-op, but it
    # guarantees the contract even if a caller passed pre-merged input.
    results = deduplicate_movies(results, prefer_score="rrf_score")
    results.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    return results[:top_k]
