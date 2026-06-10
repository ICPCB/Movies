from __future__ import annotations

import ast
import math
import random
import re
from threading import Lock
from typing import Any

import pandas as pd

from src.config import MOVIES_CSV
from src.utils.dedup import get_movie_key


_LOCK = Lock()
_movies: pd.DataFrame | None = None
_SPLIT_RE = re.compile(r"[|,;]")


def load(df: pd.DataFrame | None = None) -> pd.DataFrame:
    global _movies
    with _LOCK:
        if df is not None:
            _movies = df.copy(deep=True).reset_index(drop=True)
        elif _movies is None:
            _movies = pd.read_csv(MOVIES_CSV, low_memory=False)
        return _movies


def _clean(value: Any, default: Any = "") -> Any:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return value


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(_clean(value, default))
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(_clean(value, default)))
    except (TypeError, ValueError):
        return default


def _list_value(value: Any) -> list[str]:
    value = _clean(value, "")
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple, set)):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (SyntaxError, ValueError):
            pass
    return [part.strip() for part in _SPLIT_RE.split(text) if part.strip()]


def _tmdb_id(row: pd.Series) -> int:
    for column in ("tmdb_id", "movie_id", "id"):
        if column in row.index and _clean(row.get(column), "") != "":
            return _integer(row.get(column))
    return _integer(row.name)


def _profile(row: pd.Series) -> dict[str, Any]:
    year = _integer(row.get("year"))
    if not year:
        release_date = str(_clean(row.get("release_date"), ""))
        if len(release_date) >= 4 and release_date[:4].isdigit():
            year = int(release_date[:4])
    raw_movie = {
        "movie_id": _tmdb_id(row),
        "title": str(_clean(row.get("title"), "")),
        "year": year,
    }
    return {
        "tmdb_id": raw_movie["movie_id"],
        "movie_key": get_movie_key(raw_movie),
        "title": raw_movie["title"],
        "year": year,
        "genres": _list_value(row.get("genres")),
        "overview": str(_clean(row.get("overview"), "")),
        "keywords": _list_value(row.get("keywords")),
        "tagline": str(_clean(row.get("tagline"), "")),
        "vote_average": _number(row.get("vote_average")),
        "vote_count": _integer(row.get("vote_count")),
        "popularity": _number(row.get("popularity")),
        "poster_path": str(_clean(row.get("poster_path"), "")),
        "backdrop_path": str(_clean(row.get("backdrop_path"), "")),
        "film_mood_tags": [],
        "tone_scores": {"darkness": 0.0, "intensity": 0.0},
    }


def get_movie(tmdb_id: int | str) -> dict[str, Any] | None:
    movies = load()
    target = str(tmdb_id)
    for _, row in movies.iterrows():
        if str(_tmdb_id(row)) == target:
            return _profile(row)
    return None


def list_genres() -> list[str]:
    genres: set[str] = set()
    for value in load().get("genres", pd.Series(dtype=object)):
        genres.update(_list_value(value))
    return sorted(genres, key=lambda value: value.casefold())


def browse(
    genre: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    sort: str = "popularity",
    page: int = 1,
    page_size: int = 24,
) -> list[dict[str, Any]]:
    if sort not in {"popularity", "rating", "year"}:
        raise ValueError(f"unsupported sort: {sort}")
    profiles = [_profile(row) for _, row in load().iterrows()]
    if genre:
        genre_key = genre.casefold()
        profiles = [
            movie
            for movie in profiles
            if genre_key in {value.casefold() for value in movie["genres"]}
        ]
    if min_year is not None:
        profiles = [movie for movie in profiles if movie["year"] >= min_year]
    if max_year is not None:
        profiles = [movie for movie in profiles if movie["year"] <= max_year]

    if sort == "popularity":
        key = lambda movie: (
            -movie["vote_count"],
            -movie["vote_average"],
            movie["title"].casefold(),
            movie["tmdb_id"],
        )
    elif sort == "rating":
        key = lambda movie: (
            -movie["vote_average"],
            -movie["vote_count"],
            movie["title"].casefold(),
            movie["tmdb_id"],
        )
    else:
        key = lambda movie: (
            -movie["year"],
            -movie["vote_count"],
            movie["title"].casefold(),
            movie["tmdb_id"],
        )
    profiles.sort(key=key)
    start = (max(page, 1) - 1) * max(page_size, 1)
    return profiles[start : start + max(page_size, 1)]


def random_pick(
    min_votes: int = 200,
    min_rating: float = 6.0,
    seed: int | None = None,
) -> dict[str, Any] | None:
    candidates = [
        _profile(row)
        for _, row in load().iterrows()
        if _integer(row.get("vote_count")) >= min_votes
        and _number(row.get("vote_average")) >= min_rating
    ]
    if not candidates:
        return None
    rng = random.Random(seed)
    return rng.choices(
        candidates,
        weights=[max(movie["vote_count"], 1) for movie in candidates],
        k=1,
    )[0]
