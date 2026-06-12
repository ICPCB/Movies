from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db import create_all
from api.routes_library import router as library_router
from api.routes_search import router as search_router
from engine import lora

# Interactive hot-path overrides (plan section 10). The API process trims the
# cross-encoder pool from the eval default of 800 to 100, and keeps LLM query
# expansion off the render path (a down Ollama costs ~2.7s of connection
# retries per search; an up Ollama costs an LLM round-trip — neither fits the
# <800ms budget, which has no expansion stage). Must run before
# src.pipelines.hybrid is first imported (the engine imports it lazily);
# eval runs in its own process and keeps the src defaults.
from src import config as engine_config

engine_config.RERANK_POOL = int(os.getenv("CINEMATCH_RERANK_POOL", "100"))
engine_config.HYBRID_USE_LLM_EXPANSION = os.getenv("CINEMATCH_LLM_EXPANSION") == "1"


def _warm_models() -> None:
    from src.models import get_embedder, get_reranker

    get_embedder()
    get_reranker()
    # One tiny end-to-end query also builds the BM25 index, ChromaDB client,
    # and CSV caches, so the first real user search is hot-path only.
    from engine import recommender
    from engine.intent_schema import empty_intent

    recommender.recommend(empty_intent("warm up", "content"), pool_size=1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    app.state.model_warm = False
    app.state.intent_lora_process = lora.start_local_sidecar()
    app.state.intent_lora_ready = await asyncio.to_thread(lora.wait_until_ready)
    if os.getenv("CINEMATCH_WARM") == "1":
        async def warm() -> None:
            await asyncio.to_thread(_warm_models)
            app.state.model_warm = True

        asyncio.create_task(warm())
    yield
    intent_lora_process = app.state.intent_lora_process
    await asyncio.to_thread(lora.stop_local_sidecar, intent_lora_process)


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
