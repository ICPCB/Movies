"""Post-rerank safety filter for mood-sensitive queries."""
from __future__ import annotations

import re

from src.retrieval.mood_preprocessor import MoodIntent


DARK_GENRE_KEYWORDS = frozenset({
    "horror",
    "thriller",
    "slasher",
    "gore",
    "torture",
    "serial killer",
    "psychological thriller",
    "disturbing",
    "violent",
    "brutal",
    "nightmare",
    "terror",
})


def _is_dark_candidate(movie: dict) -> bool:
    genres = (movie.get("genres") or "").lower()
    keywords = (movie.get("keywords") or "").lower()
    text = f"{genres} {keywords}"
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text)
        for kw in DARK_GENRE_KEYWORDS
    )


def apply_safety_filter(
    movies: list[dict],
    mood: MoodIntent,
) -> list[dict]:
    if mood.safety_sensitivity != "safe_hopeful":
        return movies

    safe_candidates: list[dict] = []
    dark_candidates: list[dict] = []
    for movie in movies:
        if _is_dark_candidate(movie):
            dark_candidates.append(movie)
        else:
            safe_candidates.append(movie)
    return safe_candidates + dark_candidates
