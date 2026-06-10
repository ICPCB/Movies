from __future__ import annotations


MOVIE = {
    "movie_key": "movie_id:1",
    "tmdb_id": 1,
    "title": "Spy One",
    "poster_path": "/spy.jpg",
}


def test_favorites_add_list_delete_is_idempotent(client):
    first = client.post("/api/favorites", json=MOVIE)
    second = client.post("/api/favorites", json={**MOVIE, "title": "Spy One Updated"})
    assert first.status_code == 200
    assert second.status_code == 200

    items = client.get("/api/favorites").json()
    assert len(items) == 1
    assert items[0]["title"] == "Spy One Updated"

    assert client.delete("/api/favorites/movie_id:1").status_code == 204
    assert client.get("/api/favorites").json() == []


def test_watchlist_add_and_patch_toggle_sets_watched_at(client):
    added = client.post("/api/watchlist", json=MOVIE)
    assert added.status_code == 200
    assert added.json()["watched"] is False

    toggled = client.patch("/api/watchlist/movie_id:1", json={})
    assert toggled.status_code == 200
    assert toggled.json()["watched"] is True
    assert toggled.json()["watched_at"] is not None

    cleared = client.patch("/api/watchlist/movie_id:1", json={"watched": False})
    assert cleared.json()["watched"] is False
    assert cleared.json()["watched_at"] is None


def test_history_records_and_clears(client):
    response = client.post(
        "/api/recommend",
        json={"free_text": "spy story", "mode": "content", "page_size": 2},
    )
    assert response.status_code == 200

    history = client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["query_text"] == "spy story"

    assert client.delete("/api/history").status_code == 204
    assert client.get("/api/history").json() == []
