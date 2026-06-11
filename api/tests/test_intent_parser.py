from __future__ import annotations

from engine import intent_parser
from engine.intent_schema import validate_intent


def test_tier1_mood_words_and_body_sensations():
    intent = intent_parser.parse_tier1("feeling heartbroken and drained")
    assert validate_intent(intent) == (True, [])
    assert intent["mode"] == "mood"
    assert intent["user_moods"] == ["despair_sad", "stressed_tense"]
    assert "warm" in intent["desired_film_moods"]
    assert "bleak" in intent["avoid_film_moods"]
    assert intent["confidence"] == 0.9


def test_tier1_multiword_phrase_and_hybrid_detection():
    intent = intent_parser.parse_tier1(
        "feeling on edge, want a quiet small town detective story"
    )
    assert intent["mode"] == "hybrid"
    assert intent["user_moods"] == ["angry_annoyed"]


def test_tier1_plain_content_query_has_no_moods():
    intent = intent_parser.parse_tier1("a trash robot in space")
    assert intent["mode"] == "content"
    assert intent["user_moods"] == []
    assert intent["desired_film_moods"] == []
    assert intent["confidence"] == 0.3


def test_tier1_era_genre_and_rating_extraction():
    intent = intent_parser.parse_tier1(
        "a 90s sci-fi thriller rated above 7 before 1999"
    )
    assert intent["era"] == {"min_year": 1990, "max_year": 1999}
    assert intent["genres_include"] == ["Science Fiction", "Thriller"]
    assert intent["constraints"] == {"min_rating": 7.0}


def test_tier2_merges_plot_and_genres_but_never_moods():
    def stub_llm(text: str, timeout: float) -> dict:
        return {
            "plot_elements": ["heist", "winter"],
            "genres_include": ["Thriller", "NotAGenre"],
            "genres_exclude": ["Horror"],
            "user_moods": ["should be ignored"],
        }

    intent = intent_parser.parse(
        "feeling weary, a heist in winter, no horror",
        use_llm=True,
        llm_call=stub_llm,
    )
    assert validate_intent(intent) == (True, [])
    assert intent["plot_elements"] == ["heist", "winter"]
    assert intent["genres_include"] == ["Horror", "Thriller"] or intent[
        "genres_include"
    ] == ["Thriller", "Horror"] or "Thriller" in intent["genres_include"]
    assert intent["genres_exclude"] == ["Horror"]
    # mood fields are tier-1 only
    assert intent["user_moods"] == ["despair_sad"]


def test_tier2_failure_falls_back_to_tier1():
    def broken_llm(text: str, timeout: float) -> dict:
        raise ConnectionError("ollama down")

    intent = intent_parser.parse(
        "feeling hopeless tonight", use_llm=True, llm_call=broken_llm
    )
    assert validate_intent(intent) == (True, [])
    assert intent["user_moods"] == ["despair_sad"]
    assert intent["plot_elements"] == []
