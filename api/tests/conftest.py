from __future__ import annotations

import os

import pandas as pd
import pytest


os.environ["CINEMATCH_DB_URL"] = "sqlite+pysqlite:///:memory:"
os.environ.pop("CINEMATCH_WARM", None)

from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.db import SessionLocal, create_all
from api.db_models import Base
from api.main import app
from engine import mood_labels, movie_store


MOVIES = [
    {
        "tmdb_id": 1,
        "title": "Spy One",
        "overview": "A betrayed spy must clear his name.",
        "genres": "Action, Thriller",
        "keywords": "spy, betrayal",
        "tagline": "Trust no one",
        "year": 1998,
        "vote_average": 7.5,
        "vote_count": 900,
        "popularity": 10.0,
        "poster_path": "/spy.jpg",
        "backdrop_path": "/spy-bg.jpg",
    },
    {
        "tmdb_id": 2,
        "title": "Warm Home",
        "overview": "Friends find a warm home together.",
        "genres": "Drama",
        "keywords": "friendship, warm",
        "tagline": "",
        "year": 2005,
        "vote_average": 8.0,
        "vote_count": 700,
        "popularity": 9.0,
        "poster_path": "/warm.jpg",
        "backdrop_path": "",
    },
    {
        "tmdb_id": 3,
        "title": "Space Case",
        "overview": "An astronaut investigates a mystery.",
        "genres": "Science Fiction",
        "keywords": "space, mystery",
        "tagline": "",
        "year": 2015,
        "vote_average": 7.0,
        "vote_count": 500,
        "popularity": 8.0,
        "poster_path": "",
        "backdrop_path": "",
    },
    {
        "tmdb_id": 4,
        "title": "Quiet Comedy",
        "overview": "A quiet small-town comedy.",
        "genres": "Comedy",
        "keywords": "small town",
        "tagline": "",
        "year": 2022,
        "vote_average": 6.5,
        "vote_count": 300,
        "popularity": 7.0,
        "poster_path": "",
        "backdrop_path": "",
    },
]


def stub_pipeline(query: str, *, top_k: int, with_explanation: bool) -> list[dict]:
    assert query
    assert with_explanation is False
    return [dict(movie) for movie in MOVIES[:top_k]]


@pytest.fixture
def client():
    movie_store.load(df=pd.DataFrame(MOVIES))
    mood_labels.load(labels={})  # hermetic: no real label file in tests
    create_all()
    with SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(delete(table))
        session.commit()
    app.state.recommend_pipeline = stub_pipeline
    with TestClient(app) as test_client:
        yield test_client
    if hasattr(app.state, "recommend_pipeline"):
        del app.state.recommend_pipeline
