from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any

from src.utils.dedup import get_movie_key

from engine import mood_labels
from engine.intent_query_builder import build_query


Pipeline = Callable[..., list[dict[str, Any]]]

# ChromaDB/model singletons in src are not safe to initialize from two requests
# at once; serialize only the first (cold) pipeline call.
_COLD_START_LOCK = Lock()
_warmed = False


def _default_pipeline(
    query: str,
    *,
    top_k: int,
    with_explanation: bool,
) -> list[dict[str, Any]]:
    global _warmed
    from src.pipelines.hybrid import run

    if not _warmed:
        with _COLD_START_LOCK:
            result = run(query, top_k=top_k, with_explanation=with_explanation)
            _warmed = True
            return result
    return run(query, top_k=top_k, with_explanation=with_explanation)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _year(movie: dict[str, Any]) -> int:
    value = movie.get("year")
    if value not in (None, ""):
        return int(_as_float(value))
    release_date = str(movie.get("release_date") or "")
    return int(release_date[:4]) if release_date[:4].isdigit() else 0


def _genres(movie: dict[str, Any]) -> list[str]:
    value = movie.get("genres") or []
    if isinstance(value, str):
        value = value.replace("|", ",").split(",")
    return [str(item).strip() for item in value if str(item).strip()]


def _matches_filters(movie: dict[str, Any], filters: dict[str, Any]) -> bool:
    year = _year(movie)
    if filters["min_year"] is not None and year < filters["min_year"]:
        return False
    if filters["max_year"] is not None and year > filters["max_year"]:
        return False
    if (
        filters["min_rating"] is not None
        and _as_float(movie.get("vote_average")) < filters["min_rating"]
    ):
        return False
    movie_genres = {genre.casefold() for genre in _genres(movie)}
    included = {genre.casefold() for genre in filters["genres_include"]}
    excluded = {genre.casefold() for genre in filters["genres_exclude"]}
    if included and not included.intersection(movie_genres):
        return False
    return not excluded.intersection(movie_genres)


def _match_reason(movie: dict[str, Any], intent: dict[str, Any]) -> str:
    haystack = " ".join(
        str(movie.get(field) or "")
        for field in ("title", "overview", "keywords", "genres")
    ).casefold()
    signals: list[str] = []
    for term in intent.get("plot_elements", []):
        text = str(term).strip()
        if text and text.casefold() in haystack:
            signals.append(text)
    movie_genres = {genre.casefold() for genre in _genres(movie)}
    for genre in intent.get("genres_include", []):
        text = str(genre).strip()
        if text and text.casefold() in movie_genres and text not in signals:
            signals.append(text)
    mood_hits = sorted(
        set(movie.get("film_mood_tags", []))
        & set(intent.get("desired_film_moods", []))
    )
    parts = []
    if signals:
        parts.append(", ".join(signals))
    if mood_hits:
        parts.append(" · ".join(mood_hits))
    return f"matches: {' · '.join(parts)}" if parts else "matches: content relevance"


# Post-rerank mood adjustment (plan section 10): rank-unit nudges are
# scale-free, so we never have to guess what score field the pipeline used.
_DESIRED_RANK_BONUS = 5
_AVOID_RANK_PENALTY = 8
_MAX_COUNTED_HITS = 2


def _mood_adjusted_order(
    movies: list[dict[str, Any]],
    desired: set[str],
    avoid: set[str],
) -> list[dict[str, Any]]:
    if not desired and not avoid:
        return movies

    def adjusted_rank(item: tuple[int, dict[str, Any]]) -> int:
        index, movie = item
        tags = set(movie.get("film_mood_tags", []))
        desired_hits = min(len(tags & desired), _MAX_COUNTED_HITS)
        avoid_hits = min(len(tags & avoid), _MAX_COUNTED_HITS)
        return (
            index
            - desired_hits * _DESIRED_RANK_BONUS
            + avoid_hits * _AVOID_RANK_PENALTY
        )

    indexed = sorted(enumerate(movies), key=adjusted_rank)
    return [movie for _, movie in indexed]


def recommend(
    intent: dict[str, Any],
    pool_size: int = 100,
    pipeline: Pipeline | None = None,
) -> list[dict[str, Any]]:
    built = build_query(intent)
    runner = pipeline or _default_pipeline
    movies = runner(
        built["query_text"],
        top_k=pool_size,
        with_explanation=False,
    )
    desired = set(built["boosts"]["desired_film_moods"])
    avoid = set(built["boosts"]["avoid_film_moods"])
    output = []
    for candidate in movies:
        movie = dict(candidate)
        if not _matches_filters(movie, built["filters"]):
            continue
        movie.setdefault("movie_key", get_movie_key(movie))
        if not movie.get("film_mood_tags"):
            movie["film_mood_tags"] = mood_labels.tags_for(movie["movie_key"])
        movie["match_reason"] = _match_reason(movie, intent)
        output.append(movie)
        if len(output) >= pool_size:
            break
    return _mood_adjusted_order(output, desired, avoid)
