from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import get_session
from api.db_models import RecCache, SearchHistory
from api.schemas import ParseIntentRequest, RecommendRequest
from engine import intent_parser, lora, movie_store, recommender
from engine.intent_query_builder import build_query
from engine.intent_schema import validate_intent


router = APIRouter(prefix="/api", tags=["search"])
ERA_BUCKETS = [
    {"label": "Before 1980", "min_year": None, "max_year": 1979},
    {"label": "1980s", "min_year": 1980, "max_year": 1989},
    {"label": "1990s", "min_year": 1990, "max_year": 1999},
    {"label": "2000s", "min_year": 2000, "max_year": 2009},
    {"label": "2010s", "min_year": 2010, "max_year": 2019},
    {"label": "2020s", "min_year": 2020, "max_year": 2029},
]
CACHE_TTL_SECONDS = 3600


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _cache_key(intent: dict, page_size: int) -> str:
    payload = {"intent": intent, "page_size": page_size}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _cached_envelope(cached: RecCache) -> tuple[str, list[dict]]:
    loaded = json.loads(cached.results_json)
    if isinstance(loaded, list):  # legacy cache rows stored the bare pool
        return "", loaded
    return loaded.get("query_text", ""), loaded.get("results", [])


def _cached_results(cached: RecCache) -> list[dict]:
    return _cached_envelope(cached)[1]


def _default_explainer(query: str, movie: dict) -> str:
    from src.llm.langchain_ollama import explain_movie

    return explain_movie(query, movie)


@router.post("/parse-intent")
def parse_intent(payload: ParseIntentRequest) -> dict:
    parser = "tier1"
    intent = None
    if payload.use_lora:
        try:
            intent = lora.parse(payload.text)
            parser = "lora_v6_e4"
        except Exception:
            pass
    if intent is None:
        intent = intent_parser.parse(payload.text, payload.mode, use_llm=payload.use_llm)
        if payload.use_llm:
            parser = "tier2_or_tier1_fallback"
    valid, errors = validate_intent(intent)
    if not valid:
        raise HTTPException(status_code=500, detail={"intent_errors": errors})
    return {"intent": intent, "query": build_query(intent), "parser": parser}


@router.post("/recommend")
def recommend_movies(
    payload: RecommendRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    intent = payload.intent
    if intent is None:
        text = payload.free_text or ""
        try:
            intent = lora.parse(text)
        except Exception:
            intent = intent_parser.parse_tier1(text, payload.mode)
    valid, _ = validate_intent(intent)
    if not valid:
        intent = intent_parser.parse_tier1(payload.free_text or "", payload.mode)

    query = build_query(intent)
    if payload.log_history:
        session.add(
            SearchHistory(
                mode=intent["mode"],
                query_text=query["query_text"],
                intent_json=_canonical_json(intent),
            )
        )

    key = _cache_key(intent, payload.page_size)
    cached = session.get(RecCache, key)
    now = datetime.now()
    cache_hit = bool(
        cached
        and cached.created_at + timedelta(seconds=cached.ttl_seconds) > now
    )
    if cache_hit:
        pool = _cached_results(cached)
    else:
        pipeline = getattr(request.app.state, "recommend_pipeline", None)
        pool_size = max(100, payload.page * payload.page_size)
        pool = recommender.recommend(intent, pool_size=pool_size, pipeline=pipeline)
        envelope = _canonical_json(
            {"query_text": query["query_text"], "results": pool}
        )
        if cached is None:
            cached = RecCache(
                intent_hash=key,
                results_json=envelope,
                ttl_seconds=CACHE_TTL_SECONDS,
            )
            session.add(cached)
        else:
            cached.results_json = envelope
            cached.created_at = now
            cached.ttl_seconds = CACHE_TTL_SECONDS
    session.commit()

    start = (payload.page - 1) * payload.page_size
    return {
        "results": pool[start : start + payload.page_size],
        "page": payload.page,
        "total_pool": len(pool),
        "cache_hit": cache_hit,
        "cache_key": key,
    }


@router.get("/explain/{cache_key}/{movie_key:path}")
def explain_cached_movie(
    cache_key: str,
    movie_key: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    cached = session.get(RecCache, cache_key)
    if cached is None:
        raise HTTPException(status_code=404, detail="cache entry not found")
    query_text, results = _cached_envelope(cached)
    movie = next(
        (item for item in results if item.get("movie_key") == movie_key), None
    )
    if movie is None:
        raise HTTPException(status_code=404, detail="movie not in cached results")
    explainer = getattr(request.app.state, "explainer", None) or _default_explainer
    # Sync route: FastAPI runs it in a worker thread, so the Ollama call
    # (or its deterministic fallback) never blocks the event loop.
    return {
        "movie_key": movie_key,
        "explanation": explainer(query_text, movie),
    }


@router.get("/categories")
def categories() -> dict:
    return {"genres": movie_store.list_genres(), "eras": ERA_BUCKETS}


@router.get("/random")
def random_movie(
    min_votes: int = Query(default=200, ge=0),
    min_rating: float = Query(default=6.0, ge=0, le=10),
    seed: int | None = None,
) -> dict:
    movie = movie_store.random_pick(
        min_votes=min_votes,
        min_rating=min_rating,
        seed=seed,
    )
    if movie is None:
        raise HTTPException(status_code=404, detail="no movie matches quality floor")
    return movie


@router.get("/movies/{tmdb_id}")
def movie_detail(tmdb_id: int) -> dict:
    movie = movie_store.get_movie(tmdb_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="movie not found")
    return movie


@router.get("/health")
def health(request: Request) -> dict:
    return {
        "status": "ok",
        "model_warm": bool(getattr(request.app.state, "model_warm", False)),
        "intent_lora_ready": lora.is_ready(),
    }
