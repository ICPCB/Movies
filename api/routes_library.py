from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.db import get_session
from api.db_models import Favorite, SearchHistory, Watchlist
from api.schemas import LibraryMovie, WatchlistPatch


router = APIRouter(prefix="/api", tags=["library"])


def _favorite_dict(item: Favorite) -> dict:
    return {
        "id": item.id,
        "movie_key": item.movie_key,
        "tmdb_id": item.tmdb_id,
        "title": item.title,
        "poster_path": item.poster_path,
        "added_at": item.added_at,
    }


def _watchlist_dict(item: Watchlist) -> dict:
    return {
        "id": item.id,
        "movie_key": item.movie_key,
        "tmdb_id": item.tmdb_id,
        "title": item.title,
        "poster_path": item.poster_path,
        "watched": item.watched,
        "added_at": item.added_at,
        "watched_at": item.watched_at,
    }


@router.get("/favorites")
def list_favorites(session: Session = Depends(get_session)) -> list[dict]:
    items = session.scalars(
        select(Favorite).order_by(Favorite.added_at.desc(), Favorite.id.desc())
    ).all()
    return [_favorite_dict(item) for item in items]


@router.post("/favorites")
def add_favorite(
    payload: LibraryMovie,
    session: Session = Depends(get_session),
) -> dict:
    item = session.scalar(select(Favorite).where(Favorite.movie_key == payload.movie_key))
    values = payload.model_dump()
    if item is None:
        item = Favorite(**values)
        session.add(item)
    else:
        for field, value in values.items():
            setattr(item, field, value)
    session.commit()
    session.refresh(item)
    return _favorite_dict(item)


@router.delete("/favorites/{movie_key}")
def remove_favorite(
    movie_key: str,
    session: Session = Depends(get_session),
) -> Response:
    session.execute(delete(Favorite).where(Favorite.movie_key == movie_key))
    session.commit()
    return Response(status_code=204)


@router.get("/watchlist")
def list_watchlist(session: Session = Depends(get_session)) -> list[dict]:
    items = session.scalars(
        select(Watchlist).order_by(Watchlist.added_at.desc(), Watchlist.id.desc())
    ).all()
    return [_watchlist_dict(item) for item in items]


@router.post("/watchlist")
def add_watchlist(
    payload: LibraryMovie,
    session: Session = Depends(get_session),
) -> dict:
    item = session.scalar(
        select(Watchlist).where(Watchlist.movie_key == payload.movie_key)
    )
    values = payload.model_dump()
    if item is None:
        item = Watchlist(**values)
        session.add(item)
    else:
        for field, value in values.items():
            setattr(item, field, value)
    session.commit()
    session.refresh(item)
    return _watchlist_dict(item)


@router.patch("/watchlist/{movie_key}")
def update_watchlist(
    movie_key: str,
    payload: WatchlistPatch,
    session: Session = Depends(get_session),
) -> dict:
    item = session.scalar(select(Watchlist).where(Watchlist.movie_key == movie_key))
    if item is None:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    watched = not item.watched if payload.watched is None else payload.watched
    item.watched = watched
    item.watched_at = datetime.now() if watched else None
    session.commit()
    session.refresh(item)
    return _watchlist_dict(item)


@router.delete("/watchlist/{movie_key}")
def remove_watchlist(
    movie_key: str,
    session: Session = Depends(get_session),
) -> Response:
    session.execute(delete(Watchlist).where(Watchlist.movie_key == movie_key))
    session.commit()
    return Response(status_code=204)


@router.get("/history")
def list_history(session: Session = Depends(get_session)) -> list[dict]:
    items = session.scalars(
        select(SearchHistory)
        .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc())
        .limit(50)
    ).all()
    return [
        {
            "id": item.id,
            "mode": item.mode,
            "query_text": item.query_text,
            "intent_json": item.intent_json,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.delete("/history")
def clear_history(session: Session = Depends(get_session)) -> Response:
    session.execute(delete(SearchHistory))
    session.commit()
    return Response(status_code=204)
