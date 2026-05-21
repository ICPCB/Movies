"""Lazy singleton loaders — models are loaded once and reused."""
from __future__ import annotations
import torch
from sentence_transformers import SentenceTransformer, CrossEncoder
from src.config import EMBEDDING_MODEL, RERANKER_MODEL

_device = "cuda" if torch.cuda.is_available() else "cpu"
_embedder: SentenceTransformer | None = None
_reranker: CrossEncoder | None = None


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        print(f"[models] Loading embedder {EMBEDDING_MODEL} on {_device}...")
        _embedder = SentenceTransformer(EMBEDDING_MODEL, device=_device)
    return _embedder


def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        print(f"[models] Loading reranker {RERANKER_MODEL} on {_device}...")
        _reranker = CrossEncoder(RERANKER_MODEL, device=_device)
    return _reranker
