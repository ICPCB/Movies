#!/usr/bin/env python
"""Analyze ranking root cause for palindromic timeline query."""
import sys
sys.path.insert(0, '.')

from src.retrieval.query_processor import expand_retrieval_query, normalize_query
from src.retrieval.semantic import semantic_search
from src.retrieval.bm25 import bm25_search
from src.retrieval.fusion import fuse_results
from src.retrieval.reranker import rerank
from src.config import CANDIDATE_POOL, RERANK_POOL, RERANK_TOP_K, FINAL_TOP_K
import pandas as pd
import json

query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"

print("="*120)
print("RANKING ROOT CAUSE ANALYSIS")
print("="*120)

# Step 1: Load movies
df = pd.read_csv('data/movies_clean.csv')
memento = df[df['id'] == 77].iloc[0]
tenet = df[df['id'] == 577922].iloc[0]

print(f"\n[TARGET MOVIES]")
print(f"Memento ID: 77, vote_count: {memento['vote_count']}, vote_average: {memento['vote_average']}")
print(f"Memento keywords: {memento.get('keywords_clean', '')[:100]}")
print(f"\nTenet ID: 577922, vote_count: {tenet['vote_count']}, vote_average: {tenet['vote_average']}")
print(f"Tenet keywords: {tenet.get('keywords_clean', '')[:100]}")

# Step 2: Query expansion
normalized = normalize_query(query)
expanded = expand_retrieval_query(normalized)

print(f"\n{'='*120}")
print(f"[QUERY PROCESSING]")
print(f"{'='*120}")
print(f"Original: {query[:80]}...")
print(f"Normalized: {normalized}")
print(f"Expanded: {expanded[:150]}...")

# Step 3: Semantic search
print(f"\n{'='*120}")
print(f"[STEP 1: SEMANTIC SEARCH] (top_k={CANDIDATE_POOL})")
print(f"{'='*120}")
sem_results = semantic_search(expanded, top_k=CANDIDATE_POOL)

memento_sem = None
tenet_sem = None
for i, m in enumerate(sem_results):
    if m['id'] == 77:
        memento_sem = m
        print(f"  Memento: Rank {i+1}/{len(sem_results)}, semantic_score={m.get('semantic_score', 0):.6f}")
    elif m['id'] == 577922:
        tenet_sem = m
        print(f"  Tenet: Rank {i+1}/{len(sem_results)}, semantic_score={m.get('semantic_score', 0):.6f}")

if not memento_sem:
    print(f"  Memento NOT found in top {CANDIDATE_POOL} semantic results")
if not tenet_sem:
    print(f"  Tenet NOT found in top {CANDIDATE_POOL} semantic results")

# Step 4: BM25 search
print(f"\n{'='*120}")
print(f"[STEP 2: BM25 SEARCH] (top_k={CANDIDATE_POOL})")
print(f"{'='*120}")
bm25_results = bm25_search(expanded, top_k=CANDIDATE_POOL)

memento_bm25 = None
tenet_bm25 = None
for i, m in enumerate(bm25_results):
    if m['id'] == 77:
        memento_bm25 = m
        print(f"  Memento: Rank {i+1}/{len(bm25_results)}, bm25_score={m.get('bm25_score', 0):.6f}")
    elif m['id'] == 577922:
        tenet_bm25 = m
        print(f"  Tenet: Rank {i+1}/{len(bm25_results)}, bm25_score={m.get('bm25_score', 0):.6f}")

if not memento_bm25:
    print(f"  Memento NOT found in top {CANDIDATE_POOL} BM25 results")
if not tenet_bm25:
    print(f"  Tenet NOT found in top {CANDIDATE_POOL} BM25 results")

# Step 5: Fusion
print(f"\n{'='*120}")
print(f"[STEP 3: FUSION] (combines semantic + BM25)")
print(f"{'='*120}")
fused = fuse_results(sem_results, bm25_results, top_k=RERANK_TOP_K)

memento_fused = None
tenet_fused = None
for i, m in enumerate(fused):
    if m['id'] == 77:
        memento_fused = m
        print(f"  Memento: Rank {i+1}/{len(fused)}, final_score={m.get('final_score', 0):.6f}")
        print(f"    - rrf_score: {m.get('rrf_score', 'N/A')}")
        print(f"    - semantic_rank: {m.get('semantic_rank', 'N/A')}, bm25_rank: {m.get('bm25_rank', 'N/A')}")
    elif m['id'] == 577922:
        tenet_fused = m
        print(f"  Tenet: Rank {i+1}/{len(fused)}, final_score={m.get('final_score', 0):.6f}")
        print(f"    - rrf_score: {m.get('rrf_score', 'N/A')}")
        print(f"    - semantic_rank: {m.get('semantic_rank', 'N/A')}, bm25_rank: {m.get('bm25_rank', 'N/A')}")

if not memento_fused:
    print(f"  Memento NOT found in fused results (top {RERANK_TOP_K})")
if not tenet_fused:
    print(f"  Tenet NOT found in fused results (top {RERANK_TOP_K})")

# Step 6: Reranking
print(f"\n{'='*120}")
print(f"[STEP 4: RERANKING] (cross-encoder scoring, top_k={FINAL_TOP_K})")
print(f"{'='*120}")
reranked = rerank(query, fused, top_k=FINAL_TOP_K, rerank_pool=RERANK_POOL)

memento_final = None
tenet_final = None
for i, m in enumerate(reranked):
    if m['id'] == 77:
        memento_final = m
        print(f"  Memento: Rank {i+1}/{len(reranked)}")
        print(f"    - rerank_score: {m.get('rerank_score', 0):.6f}")
        print(f"    - quality_prior (vote_count): {m.get('quality_prior', 0):.6f}")
        print(f"    - upstream_prior: {m.get('upstream_prior', 0):.6f}")
        print(f"    - source_agreement: {m.get('source_agreement', 0):.6f}")
        print(f"    - final_score: {m.get('final_score', 0):.6f}")
        print(f"    - vote_count: {m.get('vote_count', 0)}, vote_average: {m.get('vote_average', 0):.2f}")
    elif m['id'] == 577922:
        tenet_final = m
        print(f"  Tenet: Rank {i+1}/{len(reranked)}")
        print(f"    - rerank_score: {m.get('rerank_score', 0):.6f}")
        print(f"    - quality_prior (vote_count): {m.get('quality_prior', 0):.6f}")
        print(f"    - upstream_prior: {m.get('upstream_prior', 0):.6f}")
        print(f"    - source_agreement: {m.get('source_agreement', 0):.6f}")
        print(f"    - final_score: {m.get('final_score', 0):.6f}")
        print(f"    - vote_count: {m.get('vote_count', 0)}, vote_average: {m.get('vote_average', 0):.2f}")

if not memento_final:
    print(f"  Memento NOT found in final results (top {FINAL_TOP_K})")
if not tenet_final:
    print(f"  Tenet NOT found in final results (top {FINAL_TOP_K})")

# Analysis
print(f"\n{'='*120}")
print(f"[ANALYSIS & DIAGNOSIS]")
print(f"{'='*120}")

print("\nMemento:")
print(f"  In semantic results: {'YES' if memento_sem else 'NO'}")
print(f"  In BM25 results: {'YES' if memento_bm25 else 'NO'}")
print(f"  In fused results: {'YES' if memento_fused else 'NO'}")
print(f"  In final results: {'YES' if memento_final else 'NO'}")

print("\nTenet:")
print(f"  In semantic results: {'YES' if tenet_sem else 'NO'}")
print(f"  In BM25 results: {'YES' if tenet_bm25 else 'NO'}")
print(f"  In fused results: {'YES' if tenet_fused else 'NO'}")
print(f"  In final results: {'YES' if tenet_final else 'NO'}")

print("\nFirst 5 Final Results:")
for i in range(min(5, len(reranked))):
    m = reranked[i]
    marker = ""
    if m['id'] == 77:
        marker = " <-- MEMENTO"
    elif m['id'] == 577922:
        marker = " <-- TENET"
    print(f"  {i+1}. {m['title']} (score: {m.get('final_score', 0):.6f}){marker}")

print("\n" + "="*120)
