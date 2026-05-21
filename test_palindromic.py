#!/usr/bin/env python
"""Diagnostic test for palindromic timeline query."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.retrieval.query_processor import normalize_query, expand_retrieval_query
from src.retrieval.semantic import semantic_search
from src.retrieval.bm25 import bm25_search
from src.retrieval.fusion import rrf_fusion
from src.retrieval.reranker import rerank
from src.config import CANDIDATE_POOL, RERANK_TOP_K, FINAL_TOP_K

# Test query
query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"

print("=" * 80)
print("PHASE 1: QUERY PROCESSING")
print("=" * 80)

normalized = normalize_query(query)
print(f"Normalized: {normalized}")

expanded = expand_retrieval_query(normalized)
print(f"Expanded: {expanded}")
print()

# Test semantic search
print("=" * 80)
print("PHASE 2: SEMANTIC SEARCH")
print("=" * 80)
semantic_results = semantic_search(expanded, top_k=CANDIDATE_POOL)
print(f"Total semantic results: {len(semantic_results)}")

# Find Memento and Tenet in semantic results
for i, m in enumerate(semantic_results[:50]):
    if "Memento" in m.get("title", "") or "Tenet" in m.get("title", ""):
        print(f"  FOUND: {m['title']} at rank {i+1}, score={m.get('semantic_score', 0):.4f}")

if not any("Memento" in m.get("title", "") or "Tenet" in m.get("title", "") for m in semantic_results[:50]):
    print("  WARNING: Neither Memento nor Tenet found in top 50 semantic results")
    # Find them in full results
    for i, m in enumerate(semantic_results):
        if "Memento" in m.get("title", ""):
            print(f"  Memento found at rank {i+1}, score={m.get('semantic_score', 0):.4f}")
        if "Tenet" in m.get("title", ""):
            print(f"  Tenet found at rank {i+1}, score={m.get('semantic_score', 0):.4f}")

print("\nTop 5 semantic results:")
for i, m in enumerate(semantic_results[:5]):
    print(f"  {i+1}. {m['title']} ({m.get('year')}) - {m.get('semantic_score', 0):.4f}")
print()

# Test BM25 search
print("=" * 80)
print("PHASE 3: BM25 SEARCH")
print("=" * 80)
bm25_results = bm25_search(expanded, top_k=CANDIDATE_POOL)
print(f"Total BM25 results: {len(bm25_results)}")

# Find Memento and Tenet in BM25 results
for i, m in enumerate(bm25_results[:50]):
    if "Memento" in m.get("title", "") or "Tenet" in m.get("title", ""):
        print(f"  FOUND: {m['title']} at rank {i+1}, score={m.get('bm25_score', 0):.4f}")

if not any("Memento" in m.get("title", "") or "Tenet" in m.get("title", "") for m in bm25_results[:50]):
    print("  WARNING: Neither Memento nor Tenet found in top 50 BM25 results")
    # Find them in full results
    for i, m in enumerate(bm25_results):
        if "Memento" in m.get("title", ""):
            print(f"  Memento found at rank {i+1}, score={m.get('bm25_score', 0):.4f}")
        if "Tenet" in m.get("title", ""):
            print(f"  Tenet found at rank {i+1}, score={m.get('bm25_score', 0):.4f}")

print("\nTop 5 BM25 results:")
for i, m in enumerate(bm25_results[:5]):
    print(f"  {i+1}. {m['title']} ({m.get('year')}) - {m.get('bm25_score', 0):.4f}")
print()

# Test RRF fusion
print("=" * 80)
print("PHASE 4: RRF FUSION")
print("=" * 80)
from src.utils.dedup import deduplicate_movies
semantic_dedup = deduplicate_movies(semantic_results, prefer_score="semantic_score")
bm25_dedup = deduplicate_movies(bm25_results, prefer_score="bm25_score")

fused = rrf_fusion(semantic_dedup[:CANDIDATE_POOL], bm25_dedup[:CANDIDATE_POOL])
print(f"Total fused results: {len(fused)}")

print("\nTop 5 fused results:")
for i, m in enumerate(fused[:5]):
    print(f"  {i+1}. {m['title']} ({m.get('year')}) - Final: {m.get('final_score', 0):.4f}")

# Find Memento and Tenet in fused results
for i, m in enumerate(fused[:50]):
    if "Memento" in m.get("title", "") or "Tenet" in m.get("title", ""):
        print(f"  FOUND: {m['title']} at rank {i+1}, score={m.get('final_score', 0):.4f}")
print()

# Test reranker
print("=" * 80)
print("PHASE 5: RERANKING")
print("=" * 80)
reranked = rerank(normalized, fused, top_k=FINAL_TOP_K, rerank_pool=RERANK_TOP_K)
print(f"Total reranked results: {len(reranked)}")

print("\nFinal top 5 reranked results:")
for i, m in enumerate(reranked[:5]):
    print(f"  {i+1}. {m['title']} ({m.get('year')}) - Final: {m.get('final_score', 0):.4f}, Rerank: {m.get('rerank_score', 0):.4f}")

# Find Memento and Tenet in reranked results
print("\nSearching for Memento and Tenet in reranked results:")
found = False
for m in reranked:
    if "Memento" in m.get("title", "") or "Tenet" in m.get("title", ""):
        print(f"  FOUND: {m['title']}")
        found = True
if not found:
    print("  NOT FOUND in final results")
    print("\nSearching in full fused list before reranking:")
    for i, m in enumerate(fused[:50]):
        if "Memento" in m.get("title", "") or "Tenet" in m.get("title", ""):
            print(f"  {m['title']} at rank {i+1}")
