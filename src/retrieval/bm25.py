"""Field-aware BM25 search with per-field boost weights.

Why fields are weighted the way they are: the previous configuration let
title BM25 dominate, so any movie whose title shared a query token would
float to the top even when its overview was unrelated. Overview is now
the strongest field — that is the text the user is actually describing.
"""
from __future__ import annotations
import re
import unicodedata
import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi
from src.config import (
    MOVIES_CSV, CANDIDATE_POOL,
    BM25_TITLE_BOOST, BM25_KEYWORDS_BOOST,
    BM25_GENRES_BOOST, BM25_TAGLINE_BOOST, BM25_OVERVIEW_BOOST,
)
from src.utils.dedup import deduplicate_movies, get_movie_key

_df: pd.DataFrame | None = None
_indices: dict[str, BM25Okapi] = {}

# Match word characters; strips punctuation that would otherwise glue
# tokens like "mars," or "Mars." to their neighbours and prevent BM25
# from scoring them.
_TOKEN_RE = re.compile(r"[a-z0-9]+")

_SYNONYM_GROUPS = (
    (1, {"astronaut", "space", "mars", "planet", "nasa", "cosmos"}),
    (1, {"stranded", "survive", "survival", "marooned", "alone", "trapped"}),
    (1, {"dream", "dreams", "subconscious", "lucid", "mind"}),
    (1, {"heist", "thief", "steal", "espionage", "robbery"}),
    (1, {"robot", "android", "machine", "automation"}),
    (1, {"girl", "child", "kid", "daughter", "teenager", "12", "young"}),
    (1, {"protect", "protects", "guardian", "guard", "custodian", "defend"}),
    (1, {"hitman", "assassin", "killer", "cleaner", "contract"}),
    (2, {"family", "household", "poor", "rich", "wealthy", "working"}),
    (2, {"simulation", "reality", "virtual", "computer", "hacker"}),
)

_STEM_SUFFIXES = ("ing", "ers", "ies", "ied", "ed", "es", "s")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _stem(token: str) -> str:
    for suffix in _STEM_SUFFIXES:
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            if suffix in {"ies", "ied"}:
                return token[: -len(suffix)] + "y"
            return token[: -len(suffix)]
    return token


def _tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN_RE.findall(_ascii(str(text or "")).lower())]


def _expand_query_tokens(tokens: list[str]) -> list[str]:
    expanded = list(tokens)
    token_set = set(tokens)
    for min_overlap, group in _SYNONYM_GROUPS:
        stems = {_stem(t) for t in group}
        if len(token_set & stems) >= min_overlap:
            expanded.extend(sorted(stems - token_set))
    return expanded


def _load() -> None:
    global _df
    if _df is not None:
        return
    print("[bm25] Building field-aware BM25 index...")
    _df = pd.read_csv(MOVIES_CSV)

    def tok_col(col: str) -> list[list[str]]:
        if col not in _df.columns:
            return [[] for _ in range(len(_df))]
        return [_tokenize(str(v) if pd.notna(v) else "") for v in _df[col]]

    _indices["title"] = BM25Okapi(tok_col("title"))
    _indices["keywords"] = BM25Okapi(tok_col("keywords_clean"))
    _indices["genres"] = BM25Okapi(tok_col("genres_clean"))
    _indices["tagline"] = BM25Okapi(tok_col("tagline"))
    _indices["overview"] = BM25Okapi(tok_col("overview"))
    print(f"[bm25] Ready — {len(_df):,} movies")


def _derive_year(row) -> int:
    y = row.get("year")
    if pd.notna(y):
        try:
            return int(float(y))
        except (TypeError, ValueError):
            pass
    rd = row.get("release_date")
    if isinstance(rd, str) and len(rd) >= 4 and rd[:4].isdigit():
        return int(rd[:4])
    return 0


def _filter_mask(filters: dict | None) -> np.ndarray:
    assert _df is not None
    mask = np.ones(len(_df), dtype=bool)
    if not filters:
        return mask

    for field, condition in filters.items():
        if field not in _df.columns:
            continue
        series = pd.to_numeric(_df[field], errors="coerce")
        if isinstance(condition, dict):
            if "$gte" in condition:
                mask &= (series >= float(condition["$gte"])).fillna(False).to_numpy()
            if "$lte" in condition:
                mask &= (series <= float(condition["$lte"])).fillna(False).to_numpy()
            if "$gt" in condition:
                mask &= (series > float(condition["$gt"])).fillna(False).to_numpy()
            if "$lt" in condition:
                mask &= (series < float(condition["$lt"])).fillna(False).to_numpy()
            if "$eq" in condition:
                mask &= (_df[field] == condition["$eq"]).to_numpy()
        else:
            mask &= (_df[field] == condition).to_numpy()
    return mask


def bm25_search(
    query: str,
    top_k: int = CANDIDATE_POOL,
    filters: dict | None = None,
) -> list[dict]:
    _load()
    assert _df is not None

    tokens = _expand_query_tokens(_tokenize(query))
    if not tokens:
        return []

    scores = (
        BM25_TITLE_BOOST    * np.array(_indices["title"].get_scores(tokens))
        + BM25_KEYWORDS_BOOST * np.array(_indices["keywords"].get_scores(tokens))
        + BM25_GENRES_BOOST   * np.array(_indices["genres"].get_scores(tokens))
        + BM25_TAGLINE_BOOST  * np.array(_indices["tagline"].get_scores(tokens))
        + BM25_OVERVIEW_BOOST * np.array(_indices["overview"].get_scores(tokens))
    )

    mask = _filter_mask(filters)
    scores = np.where(mask, scores, float("-inf"))

    # Pull a wider slice than top_k so dedup leaves us enough survivors.
    pool_size = max(top_k * 2, top_k + 20)
    finite_count = int(np.isfinite(scores).sum())
    if finite_count == 0:
        return []
    pool_size = min(pool_size, finite_count)
    top_indices = np.argpartition(-scores, min(pool_size - 1, len(scores) - 1))[:pool_size]
    top_indices = top_indices[np.argsort(-scores[top_indices])]

    movies: list[dict] = []
    for rank, idx in enumerate(top_indices):
        s = float(scores[idx])
        if s <= 0:
            continue
        row = _df.iloc[idx]
        movie = {
            "id": int(idx),
            "title": str(row["title"]),
            "release_date": str(row.get("release_date", "")),
            "year": _derive_year(row),
            "genres": str(row.get("genres_clean", row.get("genres", ""))),
            "overview": str(row.get("overview", ""))[:500],
            "poster_path": str(row["poster_path"]) if pd.notna(row.get("poster_path")) else "",
            "vote_average": float(row["vote_average"]) if pd.notna(row.get("vote_average")) else 0.0,
            "vote_count": int(row["vote_count"]) if pd.notna(row.get("vote_count")) else 0,
            "keywords": str(row.get("keywords_clean", "") or ""),
            "tagline": str(row.get("tagline", "") or ""),
            "bm25_score": s,
            "bm25_rank": rank,
            "final_score": s,
            "debug": {"bm25_rank": rank, "bm25_score": s},
        }
        movie["movie_key"] = get_movie_key(movie)
        movies.append(movie)

    # Dedup BEFORE truncation so duplicates can't push real candidates out.
    deduped = deduplicate_movies(movies, prefer_score="bm25_score")

    # Re-rank by bm25_score and re-stamp bm25_rank so callers can rely on
    # it as a contiguous 0..N-1 ordering after dedup.
    deduped.sort(key=lambda m: m.get("bm25_score", 0.0), reverse=True)
    for new_rank, m in enumerate(deduped[:top_k]):
        m["bm25_rank"] = new_rank
        m["debug"]["bm25_rank"] = new_rank

    return deduped[:top_k]
