from __future__ import annotations

from src.utils.dedup import get_movie_key

from engine import mood_labels
from engine.intent_schema import empty_intent
from engine.recommender import recommend


def _key(title: str, year: int) -> str:
    return get_movie_key({"title": title, "year": year})


def stub_pipeline(query: str, *, top_k: int, with_explanation: bool) -> list[dict]:
    return [
        {"title": "Grim Streets", "year": 2001, "vote_average": 7.0},
        {"title": "Quiet Sunrise", "year": 2002, "vote_average": 7.0},
        {"title": "Plain Story", "year": 2003, "vote_average": 7.0},
    ][:top_k]


def test_mood_layer_attaches_tags_reorders_and_explains(client):
    mood_labels.load(
        labels={
            _key("Grim Streets", 2001): ["bleak", "dark"],
            _key("Quiet Sunrise", 2002): ["warm", "hopeful"],
        }
    )
    try:
        intent = empty_intent("something gentle", "mood")
        intent["desired_film_moods"] = ["warm", "hopeful"]
        intent["avoid_film_moods"] = ["bleak"]

        results = recommend(intent, pool_size=3, pipeline=stub_pipeline)

        titles = [movie["title"] for movie in results]
        # Desired-mood match rises to the top; avoid-mood match sinks below
        # the untagged movie.
        assert titles == ["Quiet Sunrise", "Plain Story", "Grim Streets"]
        by_title = {movie["title"]: movie for movie in results}
        assert by_title["Quiet Sunrise"]["film_mood_tags"] == ["warm", "hopeful"]
        assert by_title["Plain Story"]["film_mood_tags"] == []
        assert by_title["Quiet Sunrise"]["match_reason"] == "matches: hopeful · warm"
        assert by_title["Plain Story"]["match_reason"] == "matches: content relevance"
    finally:
        mood_labels.load(labels={})


def test_mood_layer_no_moods_preserves_pipeline_order(client):
    intent = empty_intent("anything", "content")
    results = recommend(intent, pool_size=3, pipeline=stub_pipeline)
    assert [movie["title"] for movie in results] == [
        "Grim Streets",
        "Quiet Sunrise",
        "Plain Story",
    ]
