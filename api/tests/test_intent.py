from __future__ import annotations

import copy

import pytest

from engine.intent_query_builder import build_query
from engine.intent_schema import empty_intent, validate_intent


@pytest.mark.parametrize("mode", ["mood", "content", "hybrid", "category", "random"])
def test_schema_accepts_all_modes(mode):
    valid, errors = validate_intent(empty_intent("find a movie", mode))
    assert valid is True
    assert errors == []


def test_schema_rejects_bad_enum_extra_field_and_tone_range():
    bad_mode = empty_intent("x")
    bad_mode["mode"] = "invalid"
    assert validate_intent(bad_mode)[0] is False

    extra = empty_intent("x")
    extra["unexpected"] = True
    assert validate_intent(extra)[0] is False

    tone = empty_intent("x")
    tone["tone"]["darkness"] = 2
    tone["tone"]["intensity"] = -0.1
    valid, errors = validate_intent(tone)
    assert valid is False
    assert len(errors) == 2


def test_empty_intent_is_valid():
    intent = empty_intent("a detective mystery")
    assert validate_intent(intent) == (True, [])
    assert intent["free_text_query"] == "a detective mystery"


def test_build_query_is_deterministic_and_uses_plot_then_mood():
    intent = empty_intent("fallback", "mood")
    intent["plot_elements"] = ["betrayed spy", "clear his name"]
    intent["desired_film_moods"] = ["warm", "hopeful"]
    intent["avoid_film_moods"] = ["bleak"]
    intent["genres_include"] = ["Thriller"]
    intent["genres_exclude"] = ["Horror"]
    intent["era"] = {"min_year": 1990, "max_year": 2000}
    intent["constraints"] = {"min_rating": 7.0}
    intent["tone"] = {"darkness": -0.5, "intensity": 0.7}

    original = copy.deepcopy(intent)
    first = build_query(intent)
    second = build_query(intent)

    assert first == second
    assert intent == original
    assert first == {
        "query_text": "betrayed spy clear his name warm hopeful",
        "filters": {
            "min_year": 1990,
            "max_year": 2000,
            "min_rating": 7.0,
            "genres_include": ["Thriller"],
            "genres_exclude": ["Horror"],
        },
        "boosts": {
            "desired_film_moods": ["warm", "hopeful"],
            "avoid_film_moods": ["bleak"],
            "tone": {"darkness": -0.5, "intensity": 0.7},
        },
    }
