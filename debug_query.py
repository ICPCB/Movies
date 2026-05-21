#!/usr/bin/env python
"""Debug: Show what query expansion does and trace scoring."""
import sys
sys.path.insert(0, '.')

from src.retrieval.query_processor import expand_retrieval_query, normalize_query
from src.retrieval.semantic import semantic_search
from src.retrieval.bm25 import bm25_search
from src.config import CANDIDATE_POOL
import pandas as pd

query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"

print("="*100)
print("QUERY EXPANSION DEBUG")
print("="*100)

normalized = normalize_query(query)
expanded = expand_retrieval_query(normalized)

print(f"\nOriginal Query:")
print(f"  {query}")
print(f"\nNormalized:")
print(f"  {normalized}")
print(f"\nExpanded (with metadata hints):")
print(f"  {expanded}")
print(f"\nAdded terms: {expanded[len(normalized):].strip() if len(expanded) > len(normalized) else 'NONE'}")

# Load movie data
df = pd.read_csv('data/movies_clean.csv')
memento = df[df['id'] == 77].iloc[0]
tenet = df[df['id'] == 577922].iloc[0]

print(f"\n{'='*100}")
print("MEMENTO METADATA")
print("="*100)
print(f"Keywords: {memento['keywords_clean']}")

print(f"\n{'='*100}")
print("TENET METADATA")
print("="*100)
print(f"Keywords: {tenet['keywords_clean']}")

# Semantic search
print(f"\n{'='*100}")
print("SEMANTIC SEARCH RESULTS (Top 50)")
print("="*100)
sem_results = semantic_search(expanded, top_k=CANDIDATE_POOL)

memento_sem_rank = None
tenet_sem_rank = None
print(f"\n{'Rank':<6} {'Movie':<40} {'Score':<10}")
print("-"*100)

for i, m in enumerate(sem_results[:50]):
    if m['id'] == 77:
        memento_sem_rank = i + 1
        print(f"{i+1:<6} {m['title']:<40} {m.get('semantic_score', 0):<10.4f} <-- MEMENTO")
    elif m['id'] == 577922:
        tenet_sem_rank = i + 1
        print(f"{i+1:<6} {m['title']:<40} {m.get('semantic_score', 0):<10.4f} <-- TENET")
    elif i < 5:
        print(f"{i+1:<6} {m['title']:<40} {m.get('semantic_score', 0):<10.4f}")

if not memento_sem_rank:
    print("\nMemento NOT in top 50 semantic results")
if not tenet_sem_rank:
    print("\nTenet NOT in top 50 semantic results")

# BM25 search
print(f"\n{'='*100}")
print("BM25 SEARCH RESULTS (Top 50)")
print("="*100)
bm25_results = bm25_search(expanded, top_k=CANDIDATE_POOL)

memento_bm25_rank = None
tenet_bm25_rank = None
print(f"\n{'Rank':<6} {'Movie':<40} {'Score':<10}")
print("-"*100)

for i, m in enumerate(bm25_results[:50]):
    if m['id'] == 77:
        memento_bm25_rank = i + 1
        print(f"{i+1:<6} {m['title']:<40} {m.get('bm25_score', 0):<10.4f} <-- MEMENTO")
    elif m['id'] == 577922:
        tenet_bm25_rank = i + 1
        print(f"{i+1:<6} {m['title']:<40} {m.get('bm25_score', 0):<10.4f} <-- TENET")
    elif i < 5:
        print(f"{i+1:<6} {m['title']:<40} {m.get('bm25_score', 0):<10.4f}")

if not memento_bm25_rank:
    print("\nMemento NOT in top 50 BM25 results")
if not tenet_bm25_rank:
    print("\nTenet NOT in top 50 BM25 results")

print(f"\n{'='*100}")
print("SUMMARY")
print("="*100)
print(f"Memento - Semantic Rank: {memento_sem_rank or 'MISS'}, BM25 Rank: {memento_bm25_rank or 'MISS'}")
print(f"Tenet   - Semantic Rank: {tenet_sem_rank or 'MISS'}, BM25 Rank: {tenet_bm25_rank or 'MISS'}")
