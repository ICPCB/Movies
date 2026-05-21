"""Stable movie key + deduplication helpers.

Every retrieval stage (semantic, BM25, fusion, reranker, final) MUST run
results through these helpers so the same movie cannot appear twice in
the output the user sees.

Stable key priority:
    1. movie_id                          — a real external id like TMDB
    2. normalized title + release year   — the canonical identity in this
                                           dataset (movies_clean.csv has
                                           NO id column; the `id` field
                                           we currently expose is just
                                           the CSV row index, and the
                                           dataset legitimately contains
                                           the same movie under multiple
                                           rows. We therefore key on
                                           title+year so those merge.)
    3. id                                — last-resort fallback when
                                           title is missing.

This ordering is intentional: dedup correctness in *this* dataset comes
from collapsing the same (title, year) regardless of which CSV row a
given retriever happened to surface.
"""
from __future__ import annotations
import re
from typing import Iterable

# Score fields ordered weakest → strongest. When duplicates collide, the
# candidate with the highest `final_score` wins; ties fall through to
# rerank_score, then rrf_score, then bm25_score, then semantic_score.
_SCORE_PREFERENCE = (
    "final_score",
    "rerank_score",
    "rrf_score",
    "bm25_score",
    "semantic_score",
)

# Score keys we deliberately preserve when merging duplicate candidates
# from different retrieval sources (e.g. one hit from semantic + same
# movie hit from BM25). We keep both source scores side by side.
_PRESERVED_SCORE_KEYS = (
    "semantic_score", "semantic_rank",
    "bm25_score", "bm25_rank",
    "rrf_score",
    "rerank_score",
    "final_score",
)

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def _normalize_title(title: object) -> str:
    s = str(title or "").lower()
    s = _NON_ALNUM_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _extract_year(movie: dict) -> str:
    year = movie.get("year")
    if year not in (None, "", 0, 0.0):
        try:
            return str(int(float(year)))
        except (TypeError, ValueError):
            pass
    rd = str(movie.get("release_date", "") or "")
    if len(rd) >= 4 and rd[:4].isdigit():
        return rd[:4]
    return ""


def get_movie_key(movie: dict) -> str:
    """Return a stable string key identifying this movie across stages.

    See module docstring for why title+year beats `id` in this dataset.
    """
    # 1. Real external id (e.g. TMDB) if it ever shows up in the data.
    v = movie.get("movie_id")
    if v is not None and v != "":
        return f"movie_id:{v}"

    # 2. Canonical identity: normalized title + year.
    title = _normalize_title(movie.get("title"))
    year = _extract_year(movie)
    if title:
        return f"title:{title}|year:{year}"

    # 3. Last-resort: the synthetic id (CSV row index). Only reachable
    # when the title is genuinely missing — at that point there is
    # nothing better to key on.
    v = movie.get("id")
    if v is not None and v != "":
        return f"id:{v}"
    return "title:|year:"


def _candidate_score(movie: dict) -> float:
    for k in _SCORE_PREFERENCE:
        v = movie.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return float("-inf")


def _merge_into(keeper: dict, other: dict) -> None:
    """Merge `other` into `keeper` in place.

    Keeper's own values win for non-score fields (it's the stronger
    candidate). For preserved score fields we fill in any value that is
    missing on the keeper but present on `other` — this is how a movie
    that hit in both semantic and BM25 ends up carrying both source
    scores after dedup.
    """
    for k in _PRESERVED_SCORE_KEYS:
        if keeper.get(k) is None and other.get(k) is not None:
            keeper[k] = other[k]
    for k, v in other.items():
        if k in _PRESERVED_SCORE_KEYS:
            continue
        cur = keeper.get(k)
        if cur in (None, "", 0, 0.0) and v not in (None, "", 0, 0.0):
            keeper[k] = v


def deduplicate_movies(
    movies: Iterable[dict],
    prefer_score: str = "final_score",
) -> list[dict]:
    """Remove duplicate movies, keeping the strongest candidate per key.

    `prefer_score` lets callers bias the keeper choice toward a specific
    score field (e.g. "rerank_score" after reranking) — we still fall
    back to the general score preference if that field is missing.
    """
    best: dict[str, dict] = {}
    order: list[str] = []

    for m in movies:
        if not isinstance(m, dict):
            continue
        key = get_movie_key(m)
        if key not in best:
            best[key] = dict(m)
            best[key]["movie_key"] = key
            order.append(key)
            continue

        keeper = best[key]
        a = m.get(prefer_score)
        b = keeper.get(prefer_score)
        try:
            a_f = float(a) if a is not None else None
            b_f = float(b) if b is not None else None
        except (TypeError, ValueError):
            a_f = b_f = None

        if a_f is not None and b_f is not None:
            challenger_wins = a_f > b_f
        elif a_f is not None and b_f is None:
            challenger_wins = True
        elif a_f is None and b_f is not None:
            challenger_wins = False
        else:
            challenger_wins = _candidate_score(m) > _candidate_score(keeper)

        if challenger_wins:
            old = keeper
            new = dict(m)
            new["movie_key"] = key
            best[key] = new
            _merge_into(new, old)
        else:
            _merge_into(keeper, m)

    return [best[k] for k in order]


def attach_movie_keys(movies: Iterable[dict]) -> list[dict]:
    """Ensure every movie in the list carries a `movie_key` field."""
    out: list[dict] = []
    for m in movies:
        if not isinstance(m, dict):
            continue
        m["movie_key"] = get_movie_key(m)
        out.append(m)
    return out


def find_duplicate_keys(movies: Iterable[dict]) -> list[str]:
    """Return movie keys that appear more than once. Useful for smoke tests."""
    seen: dict[str, int] = {}
    for m in movies:
        if not isinstance(m, dict):
            continue
        k = get_movie_key(m)
        seen[k] = seen.get(k, 0) + 1
    return [k for k, n in seen.items() if n > 1]
