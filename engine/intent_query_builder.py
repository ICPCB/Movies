from __future__ import annotations

from typing import Any


def build_query(intent: dict[str, Any]) -> dict[str, Any]:
    plot_elements = [str(value).strip() for value in intent.get("plot_elements", [])]
    plot_elements = [value for value in plot_elements if value]
    query_text = " ".join(plot_elements) if plot_elements else str(
        intent.get("free_text_query", "")
    ).strip()

    desired = list(intent.get("desired_film_moods", []))
    if intent.get("mode") == "mood" and desired:
        query_text = " ".join(part for part in [query_text, *desired] if part).strip()

    era = intent.get("era") or {}
    constraints = intent.get("constraints") or {}
    return {
        "query_text": query_text,
        "filters": {
            "min_year": era.get("min_year"),
            "max_year": era.get("max_year"),
            "min_rating": constraints.get("min_rating"),
            "genres_include": list(intent.get("genres_include", [])),
            "genres_exclude": list(intent.get("genres_exclude", [])),
        },
        "boosts": {
            "desired_film_moods": desired,
            "avoid_film_moods": list(intent.get("avoid_film_moods", [])),
            "tone": dict(intent.get("tone") or {}),
        },
    }
