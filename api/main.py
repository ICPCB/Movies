from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db import create_all
from api.routes_library import router as library_router
from api.routes_search import router as search_router


def _warm_models() -> None:
    from src.models import get_embedder, get_reranker

    get_embedder()
    get_reranker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    app.state.model_warm = False
    if os.getenv("CINEMATCH_WARM") == "1":
        async def warm() -> None:
            await asyncio.to_thread(_warm_models)
            app.state.model_warm = True

        asyncio.create_task(warm())
    yield


app = FastAPI(title="CineMatch API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(library_router)
app.include_router(search_router)
