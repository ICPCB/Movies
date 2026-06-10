from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Mode = Literal["mood", "content", "hybrid", "category", "random"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LibraryMovie(StrictModel):
    movie_key: str
    tmdb_id: int | None = None
    title: str
    poster_path: str = ""


class WatchlistPatch(StrictModel):
    watched: bool | None = None


class ParseIntentRequest(StrictModel):
    text: str
    mode: Mode = "content"


class RecommendRequest(StrictModel):
    free_text: str | None = None
    intent: dict[str, Any] | None = None
    mode: Mode = "content"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    # Pagination/reroll and benchmarks re-run the same intent; only log it once.
    log_history: bool = True
