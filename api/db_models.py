from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now()


class Base(DeclarativeBase):
    pass


class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String)
    poster_path: Mapped[str] = mapped_column(String, default="")
    added_at: Mapped[datetime] = mapped_column(default=utcnow)


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String)
    poster_path: Mapped[str] = mapped_column(String, default="")
    watched: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(default=utcnow)
    watched_at: Mapped[datetime | None] = mapped_column(nullable=True)


class SearchHistory(Base):
    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String)
    query_text: Mapped[str] = mapped_column(Text)
    intent_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class RecCache(Base):
    __tablename__ = "rec_cache"

    intent_hash: Mapped[str] = mapped_column(String, primary_key=True)
    results_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    ttl_seconds: Mapped[int] = mapped_column(Integer)


class MoodLabel(Base):
    __tablename__ = "mood_labels"

    movie_key: Mapped[str] = mapped_column(String, primary_key=True)
    film_mood_tags_json: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(String)
