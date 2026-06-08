from src.retrieval.mood_preprocessor import MoodIntent
from src.retrieval.safety_filter import apply_safety_filter


def _mood(safety: str = "neutral") -> MoodIntent:
    return MoodIntent(
        current_emotion=None,
        emotion_source="none",
        desired_direction=None,
        desired_movie_tone=[],
        energy_level=None,
        safety_sensitivity=safety,
        allow_dark_content=None,
        cleaned_query="test",
    )


def _movie(title: str, genres: str = "Drama", score: float = 1.0) -> dict:
    return {"title": title, "genres": genres, "final_score": score, "overview": ""}


def test_safe_hopeful_demotes_horror():
    movies = [
        _movie("A Quiet Place", "Horror, Thriller", 0.9),
        _movie("Paddington", "Comedy, Family", 0.8),
    ]
    result = apply_safety_filter(movies, _mood("safe_hopeful"))
    assert result[0]["title"] == "Paddington"
    assert result[1]["title"] == "A Quiet Place"


def test_neutral_does_not_demote():
    movies = [_movie("A Quiet Place", "Horror, Thriller", 0.9)]
    result = apply_safety_filter(movies, _mood("neutral"))
    assert result[0]["final_score"] == 0.9
    assert "safety_demoted" not in result[0]


def test_dark_intended_does_not_demote():
    movies = [_movie("A Quiet Place", "Horror, Thriller", 0.9)]
    result = apply_safety_filter(movies, _mood("dark_intended"))
    assert result[0]["final_score"] == 0.9


def test_non_dark_movie_not_demoted():
    movies = [_movie("Paddington", "Comedy, Family", 0.9)]
    result = apply_safety_filter(movies, _mood("safe_hopeful"))
    assert result[0]["final_score"] == 0.9


def test_safe_hopeful_mixed_list_moves_only_dark_candidates_down():
    movies = [
        _movie("A Quiet Place", "Horror, Thriller", 0.9),
        _movie("Paddington", "Comedy, Family", 0.8),
        _movie("Brutal Night", "Drama", 0.7),
    ]
    movies[2]["keywords"] = "violent brutal terror"

    result = apply_safety_filter(movies, _mood("safe_hopeful"))

    assert [m["title"] for m in result] == [
        "Paddington",
        "A Quiet Place",
        "Brutal Night",
    ]
    assert len(result) == len(movies)


def test_empty_candidate_list_no_crash():
    assert apply_safety_filter([], _mood("safe_hopeful")) == []
