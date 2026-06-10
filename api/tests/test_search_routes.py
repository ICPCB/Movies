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


def test_parse_intent_returns_valid_intent_and_query(client):
    response = client.post(
        "/api/parse-intent",
        json={"text": "something hopeful", "mode": "mood"},
    )
    assert response.status_code == 200
    body = response.json()
    assert validate_intent(body["intent"]) == (True, [])
    assert body["query"]["query_text"] == "something hopeful"
