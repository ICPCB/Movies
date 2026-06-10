from __future__ import annotations

from engine.intent_schema import validate_intent


def test_recommend_uses_stub_cache_and_page_slices(client):
    payload = {
        "free_text": "spy story",
        "mode": "content",
        "page": 1,
        "page_size": 2,
    }
    first = client.post("/api/recommend", json=payload)
    second = client.post("/api/recommend", json=payload)
    page_two = client.post("/api/recommend", json={**payload, "page": 2})

    assert first.status_code == 200
    assert first.json()["cache_hit"] is False
    assert len(first.json()["results"]) == 2
    assert all("match_reason" in movie for movie in first.json()["results"])

    assert second.json()["cache_hit"] is True
    assert page_two.json()["cache_hit"] is True
    assert [movie["tmdb_id"] for movie in page_two.json()["results"]] == [3, 4]


def test_random_is_seeded_and_movie_404s(client):
    first = client.get("/api/random?seed=17").json()
    second = client.get("/api/random?seed=17").json()
    assert first["tmdb_id"] == second["tmdb_id"]
    assert client.get("/api/movies/999").status_code == 404


def test_recommend_log_history_false_skips_history(client):
    payload = {
        "free_text": "spy story",
        "mode": "content",
        "page": 2,
        "page_size": 2,
        "log_history": False,
    }
    assert client.post("/api/recommend", json=payload).status_code == 200
    assert client.get("/api/history").json() == []


def test_explain_returns_async_explanation_from_cache(client):
    from api.main import app

    first = client.post(
        "/api/recommend",
        json={"free_text": "spy story", "mode": "content", "page_size": 2},
    ).json()
    cache_key = first["cache_key"]
    movie_key = first["results"][0]["movie_key"]

    seen = {}

    def stub_explainer(query: str, movie: dict) -> str:
        seen["query"] = query
        seen["title"] = movie["title"]
        return "stub explanation"

    app.state.explainer = stub_explainer
    try:
        response = client.get(f"/api/explain/{cache_key}/{movie_key}")
        assert response.status_code == 200
        assert response.json() == {
            "movie_key": movie_key,
            "explanation": "stub explanation",
        }
        assert seen == {"query": "spy story", "title": "Spy One"}
        assert client.get(f"/api/explain/{cache_key}/missing-key").status_code == 404
        assert client.get(f"/api/explain/nope/{movie_key}").status_code == 404
    finally:
        del app.state.explainer


def test_parse_intent_returns_valid_intent_and_query(client):
    response = client.post(
        "/api/parse-intent",
        json={"text": "something hopeful", "mode": "mood"},
    )
    assert response.status_code == 200
    body = response.json()
    assert validate_intent(body["intent"]) == (True, [])
    assert body["query"]["query_text"] == "something hopeful"
