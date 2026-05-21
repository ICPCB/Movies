#!/usr/bin/env python
"""Minimal diagnostic for palindromic timeline query."""
import pandas as pd
from src.retrieval.query_processor import normalize_query, expand_retrieval_query
from src.retrieval.semantic import semantic_search
from src.retrieval.bm25 import bm25_search
from src.config import CANDIDATE_POOL

# Load dataset
df = pd.read_csv('data/movies_clean.csv')
memento = df[df['id'] == 77].iloc[0]
tenet = df[df['id'] == 577922].iloc[0]

print("MEMENTO keywords:", memento['keywords_clean'][:100])
print("TENET keywords:", tenet['keywords_clean'][:100])
print()

query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"
normalized = normalize_query(query)
expanded = expand_retrieval_query(normalized)

print(f"Query: {query}")
print(f"Normalized: {normalized}")
print(f"Expanded: {expanded}")
print()

# Semantic
print("SEMANTIC SEARCH:")
sem = semantic_search(expanded, top_k=CANDIDATE_POOL)
for i, m in enumerate(sem):
    if m['id'] in [77, 577922]:
        print(f"  {'MEMENTO' if m['id'] == 77 else 'TENET'} at rank {i+1}, score={m.get('semantic_score', 0):.4f}")

# BM25
print("\nBM25 SEARCH:")
bm = bm25_search(expanded, top_k=CANDIDATE_POOL)
for i, m in enumerate(bm):
    if m['id'] in [77, 577922]:
        print(f"  {'MEMENTO' if m['id'] == 77 else 'TENET'} at rank {i+1}, score={m.get('bm25_score', 0):.4f}")

# Top results
print("\nTop 5 semantic:")
for i in range(5):
    if i < len(sem):
        print(f"  {i+1}. {sem[i]['title']}: {sem[i].get('semantic_score', 0):.4f}")

print("\nTop 5 BM25:")
for i in range(5):
    if i < len(bm):
        print(f"  {i+1}. {bm[i]['title']}: {bm[i].get('bm25_score', 0):.4f}")
