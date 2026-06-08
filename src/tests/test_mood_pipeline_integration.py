from types import SimpleNamespace

from src.llm import langchain_ollama
from src.llm import prompts
from src.pipelines import advanced, hybrid
from src.retrieval.mood_preprocessor import MoodIntent
from src.retrieval.safety_filter import apply_safety_filter


NO_MOOD_QUERIES = [
    "animated toys fear being replaced",
    "brilliant janitor hides from his own genius",
    "a fairy tale with sword fights, miracles, pirates, and true love read by a grandfather to his sick grandson",
]


def _neutral_mood(query: str) -> MoodIntent:
    return MoodIntent(
        current_emotion=None,
        emotion_source="none",
        desired_direction=None,
        desired_movie_tone=[],
        energy_level=None,
        safety_sensitivity="neutral",
        allow_dark_content=None,
        cleaned_query=query,
    )


def _mood_query() -> MoodIntent:
    return MoodIntent(
        current_emotion="sad",
        emotion_source="free_text",
        desired_direction=None,
        desired_movie_tone=["cozy"],
        energy_level=None,
        safety_sensitivity="safe_hopeful",
        allow_dark_content=False,
        cleaned_query="cozy comedy",
    )


def _movie(title: str = "Safe Movie") -> dict:
    return {
        "title": title,
        "movie_key": title.lower().replace(" ", "-"),
        "genres": "Comedy",
        "keywords": "gentle",
        "overview": "",
        "final_score": 1.0,
    }


def _patch_common_pipeline(monkeypatch, module, calls, *, include_hyde=False):
    monkeypatch.setattr(module.runtime_config, "LLM_RETRIEVAL_ENABLED", True)
    if module is advanced:
        monkeypatch.setattr(module.runtime_config, "USE_HYDE_IN_ADVANCED", include_hyde)
    if module is hybrid:
        monkeypatch.setattr(module.runtime_config, "HYBRID_USE_LLM_EXPANSION", True)
    monkeypatch.setattr(module, "parse_filters", lambda query: None)
    monkeypatch.setattr(module, "deduplicate_movies", lambda movies, prefer_score: list(movies))
    monkeypatch.setattr(module, "semantic_search", lambda query, top_k, filters: [_movie("Semantic")])
    monkeypatch.setattr(module, "bm25_search", lambda query, top_k, filters: [])
    monkeypatch.setattr(module, "rrf_fusion", lambda sem, bm, top_k: list(sem))
    monkeypatch.setattr(module, "rerank", lambda *args, **kwargs: list(args[1] if len(args) > 1 else kwargs["movies"]))
    monkeypatch.setattr(module, "explain_movies_batch", lambda query, movies: ["explanation"] * len(movies))

    def normalize(query):
        calls.setdefault("normalize", []).append(query)
        return query

    def deterministic(query):
        calls.setdefault("deterministic_expand", []).append(query)
        return query

    def llm_expand(query, *, mood_aware=False):
        calls.setdefault("llm_expand", []).append((query, mood_aware))
        return query

    monkeypatch.setattr(module, "normalize_query", normalize)
    monkeypatch.setattr(module, "expand_retrieval_query", deterministic)
    monkeypatch.setattr(module, "expand_query", llm_expand)

    if include_hyde:
        def hyde(query, *, mood_aware=False):
            calls.setdefault("hyde", []).append((query, mood_aware))
            return ""

        monkeypatch.setattr(module, "hyde_generate", hyde)


def test_no_mood_advanced_uses_original_query_and_non_mood_llm_flags(monkeypatch):
    for query in NO_MOOD_QUERIES:
        calls = {}
        _patch_common_pipeline(monkeypatch, advanced, calls, include_hyde=True)
        monkeypatch.setattr(advanced, "extract_mood_intent", lambda _query: _neutral_mood(_query))

        advanced.run(query, top_k=1, with_explanation=False)

        assert calls["normalize"] == [query]
        assert calls["llm_expand"] == [(query, False)]
        assert calls["hyde"] == [(query, False)]


def test_no_mood_hybrid_uses_original_query_and_non_mood_llm_flags(monkeypatch):
    for query in NO_MOOD_QUERIES:
        calls = {}
        _patch_common_pipeline(monkeypatch, hybrid, calls)
        monkeypatch.setattr(hybrid, "extract_mood_intent", lambda _query: _neutral_mood(_query))

        hybrid.run(query, top_k=1, with_explanation=False)

        assert calls["normalize"] == [query]
        assert calls["llm_expand"] == [(query, False)]


def test_mood_query_uses_cleaned_query_and_mood_aware_llm(monkeypatch):
    calls = {}
    _patch_common_pipeline(monkeypatch, advanced, calls, include_hyde=True)
    monkeypatch.setattr(advanced, "extract_mood_intent", lambda _query: _mood_query())

    advanced.run("I feel sad and want something cozy", top_k=1, with_explanation=False)

    assert calls["normalize"] == ["cozy comedy"]
    assert calls["llm_expand"] == [("cozy comedy", True)]
    assert calls["hyde"] == [("cozy comedy", True)]


def test_llm_api_uses_base_prompts_by_default_and_mood_prompts_when_requested(monkeypatch):
    messages_seen = []

    def fake_message(content):
        return SimpleNamespace(content=content)

    def fake_invoke(messages):
        messages_seen.append(messages)
        return SimpleNamespace(content='{"query": "expanded"}')

    monkeypatch.setattr(langchain_ollama, "SystemMessage", fake_message, raising=False)
    monkeypatch.setattr(langchain_ollama, "HumanMessage", fake_message, raising=False)
    monkeypatch.setattr(langchain_ollama, "_invoke_with_timeout", fake_invoke)

    langchain_ollama.expand_query("plain query")
    langchain_ollama.expand_query("sad query", mood_aware=True)

    assert messages_seen[0][0].content == prompts.EXPAND_SYSTEM_BASE
    assert messages_seen[1][0].content == prompts.EXPAND_SYSTEM_MOOD
    assert prompts.EXPAND_SYSTEM == prompts.EXPAND_SYSTEM_BASE


def test_safety_filter_is_stable_noop_for_neutral_intent():
    movies = [
        {"title": "Horror Film", "genres": "Horror", "keywords": "terror", "final_score": 1.0},
        {"title": "Comedy Film", "genres": "Comedy", "keywords": "gentle", "final_score": 0.9},
    ]

    result = apply_safety_filter(movies, _neutral_mood("anything"))

    assert result == movies
