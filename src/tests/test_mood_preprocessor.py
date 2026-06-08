from src.retrieval.mood_preprocessor import extract_mood_intent


def test_exhausted_user_wants_cozy_movie():
    intent = extract_mood_intent("I'm exhausted and want something cozy")

    assert intent.current_emotion == "exhausted"
    assert intent.emotion_source == "free_text"
    assert intent.desired_movie_tone == ["cozy"]
    assert intent.safety_sensitivity == "safe_hopeful"
    assert intent.allow_dark_content is False
    assert "cozy" in intent.cleaned_query
    assert "exhausted" not in intent.cleaned_query


def test_warm_energy_is_desired_movie_tone_not_user_state():
    intent = extract_mood_intent("I want a movie with warm energy")

    assert intent.current_emotion is None
    assert intent.emotion_source == "none"
    assert intent.desired_movie_tone == ["warm"]
    assert intent.safety_sensitivity == "neutral"
    assert intent.allow_dark_content is None


def test_explicit_dark_disturbing_movie_intent():
    intent = extract_mood_intent("I want a dark psychologically disturbing movie")

    assert intent.current_emotion is None
    assert intent.desired_movie_tone == ["dark", "disturbing"]
    assert intent.safety_sensitivity == "dark_intended"
    assert intent.allow_dark_content is True


def test_disturbed_user_wants_gentle_movie():
    intent = extract_mood_intent("I feel disturbed and want something gentle")

    assert intent.current_emotion == "disturbed"
    assert intent.desired_movie_tone == ["gentle"]
    assert intent.safety_sensitivity == "safe_hopeful"
    assert intent.allow_dark_content is False


def test_devastating_raw_war_film_is_explicit_heavy_content():
    intent = extract_mood_intent("I want a devastating raw war film")

    assert intent.current_emotion is None
    assert intent.safety_sensitivity == "dark_intended"
    assert intent.allow_dark_content is True


def test_no_mood_query_remains_unchanged():
    query = "animated spider hero"

    intent = extract_mood_intent(query)

    assert intent.current_emotion is None
    assert intent.emotion_source == "none"
    assert intent.safety_sensitivity == "neutral"
    assert intent.allow_dark_content is None
    assert intent.cleaned_query == query


def test_anxious_user_explicit_horror_request_stays_neutral():
    intent = extract_mood_intent("I feel anxious but want a horror movie")

    assert intent.current_emotion == "anxious"
    assert intent.desired_movie_tone == ["horror"]
    assert intent.safety_sensitivity == "neutral"
    assert intent.allow_dark_content is True
