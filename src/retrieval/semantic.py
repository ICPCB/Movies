"""BGE-M3 semantic search against ChromaDB."""
from __future__ import annotations
import chromadb
from src.config import CHROMA_DIR, COLLECTION_NAME, CANDIDATE_POOL
from src.models import get_embedder
from src.utils.dedup import deduplicate_movies, get_movie_key

_client: chromadb.PersistentClient | None = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_collection(COLLECTION_NAME)
    return _collection


def _derive_year(meta: dict) -> int:
    y = meta.get("year")
    if y not in (None, "", 0, 0.0):
        try:
            return int(float(y))
        except (TypeError, ValueError):
            pass
    rd = str(meta.get("release_date", "") or "")
    if len(rd) >= 4 and rd[:4].isdigit():
        return int(rd[:4])
    return 0


def _to_chroma_where(filters: dict | None) -> dict | None:
    if not filters:
        return None

    clauses: list[dict] = []
    for field, condition in filters.items():
        if isinstance(condition, dict):
            for op, value in condition.items():
                clauses.append({field: {op: value}})
        else:
            clauses.append({field: condition})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def semantic_search(
    query: str,
    top_k: int = CANDIDATE_POOL,
    filters: dict | None = None,
) -> list[dict]:
    embedder = get_embedder()
    collection = _get_collection()

    embedding = embedder.encode(query, normalize_embeddings=True).tolist()

    query_args: dict = {
        "query_embeddings": [embedding],
        "n_results": top_k,
        "include": ["metadatas", "distances"],
    }
    where = _to_chroma_where(filters)
    if where:
        query_args["where"] = where

    results = collection.query(**query_args)

    movies: list[dict] = []
    for i, (id_, meta, dist) in enumerate(zip(
        results["ids"][0], results["metadatas"][0], results["distances"][0]
    )):
        # Chroma IDs may be either the legacy positional `movie_{i}` or
        # the new stable `tmdb_{tmdb_id}`. Pull the trailing integer.
        suffix = str(id_).rsplit("_", 1)[-1]
        movie_id = int(suffix) if suffix.isdigit() else 0
        # Cosine distance in Chroma ranges roughly 0..2 for normalized
        # embeddings; clamp so the displayed score stays in [0, 1].
        sem_score = float(1 - dist)
        if sem_score < 0.0:
            sem_score = 0.0
        elif sem_score > 1.0:
            sem_score = 1.0

        movie = {
            "id": movie_id,
            "title": meta.get("title", ""),
            "release_date": str(meta.get("release_date", "")),
            "year": _derive_year(meta),
            "genres": meta.get("genres", ""),
            "overview": meta.get("overview", ""),
            "poster_path": meta.get("poster_path", ""),
            "vote_average": float(meta.get("vote_average", 0)),
            "vote_count": int(meta.get("vote_count", 0) or 0),
            "popularity": float(meta.get("popularity", 0.0) or 0.0),
            "keywords": meta.get("keywords", ""),
            "tagline": meta.get("tagline", ""),
            "semantic_score": sem_score,
            "semantic_rank": i,
            "final_score": sem_score,
            "debug": {"semantic_rank": i, "semantic_score": sem_score},
        }
        movie["movie_key"] = get_movie_key(movie)
        movies.append(movie)

    return deduplicate_movies(movies, prefer_score="semantic_score")
