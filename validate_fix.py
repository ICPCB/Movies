#!/usr/bin/env python
"""Validation that the palindromic timeline fix works."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.retrieval.query_processor import expand_retrieval_query, normalize_query
from src.retrieval.semantic import semantic_search
from src.retrieval.bm25 import bm25_search
from src.config import CANDIDATE_POOL

def test_query_expansion():
    """Test that query expansion detects the palindromic timeline pattern."""
    query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"
    normalized = normalize_query(query)
    expanded = expand_retrieval_query(normalized)
    
    # The expanded query should contain timeline-related keywords
    expected_keywords = ["nonlinear", "reverse chronology", "time paradox", "palindromic"]
    success = all(kw in expanded for kw in expected_keywords)
    
    print("TEST 1: Query Expansion")
    print(f"  Original: {query[:60]}...")
    print(f"  Expanded contains target keywords: {success}")
    if not success:
        print(f"  Expanded: {expanded}")
    return success

def test_semantic_retrieval():
    """Test that Memento/Tenet appear in semantic search results."""
    query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"
    normalized = normalize_query(query)
    expanded = expand_retrieval_query(normalized)
    
    results = semantic_search(expanded, top_k=CANDIDATE_POOL)
    
    memento_rank = None
    tenet_rank = None
    for i, m in enumerate(results):
        if m['id'] == 77:  # Memento
            memento_rank = i + 1
        if m['id'] == 577922:  # Tenet
            tenet_rank = i + 1
    
    # Check if either appears in top 50
    in_top_50 = False
    if memento_rank and memento_rank <= 50:
        in_top_50 = True
        print(f"  Memento found at semantic rank {memento_rank}")
    if tenet_rank and tenet_rank <= 50:
        in_top_50 = True
        print(f"  Tenet found at semantic rank {tenet_rank}")
    
    print("TEST 2: Semantic Retrieval (top 50)")
    print(f"  Target movies in top 50: {in_top_50}")
    return in_top_50

def test_bm25_retrieval():
    """Test that Memento/Tenet appear in BM25 results."""
    query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"
    normalized = normalize_query(query)
    expanded = expand_retrieval_query(normalized)
    
    results = bm25_search(expanded, top_k=CANDIDATE_POOL)
    
    memento_rank = None
    tenet_rank = None
    for i, m in enumerate(results):
        if m['id'] == 77:  # Memento
            memento_rank = i + 1
        if m['id'] == 577922:  # Tenet
            tenet_rank = i + 1
    
    # Check if either appears in top 50
    in_top_50 = False
    if memento_rank and memento_rank <= 50:
        in_top_50 = True
        print(f"  Memento found at BM25 rank {memento_rank}")
    if tenet_rank and tenet_rank <= 50:
        in_top_50 = True
        print(f"  Tenet found at BM25 rank {tenet_rank}")
    
    print("TEST 3: BM25 Retrieval (top 50)")
    print(f"  Target movies in top 50: {in_top_50}")
    return in_top_50

def test_reranker():
    """Test that reranker produces meaningful scores."""
    from src.retrieval.reranker import rerank
    
    query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"
    normalized = normalize_query(query)
    expanded = expand_retrieval_query(normalized)
    
    # Get candidates from both retrievers
    from src.retrieval.fusion import rrf_fusion
    from src.utils.dedup import deduplicate_movies
    
    semantic_results = semantic_search(expanded, top_k=CANDIDATE_POOL)
    bm25_results = bm25_search(expanded, top_k=CANDIDATE_POOL)
    
    semantic_results = deduplicate_movies(semantic_results, prefer_score="semantic_score")
    bm25_results = deduplicate_movies(bm25_results, prefer_score="bm25_score")
    
    fused = rrf_fusion(semantic_results[:CANDIDATE_POOL], bm25_results[:CANDIDATE_POOL])
    reranked = rerank(normalized, fused, top_k=10, rerank_pool=80)
    
    # Check if Memento or Tenet made it to top 10 after reranking
    memento_rank = None
    tenet_rank = None
    for i, m in enumerate(reranked):
        if m['id'] == 77:  # Memento
            memento_rank = i + 1
        if m['id'] == 577922:  # Tenet
            tenet_rank = i + 1
    
    in_top_10 = memento_rank is not None or tenet_rank is not None
    if memento_rank:
        print(f"  Memento found at reranked position {memento_rank}")
    if tenet_rank:
        print(f"  Tenet found at reranked position {tenet_rank}")
    
    print("TEST 4: Full Pipeline Reranking (top 10)")
    print(f"  Target movies in top 10 after reranking: {in_top_10}")
    return in_top_10

if __name__ == "__main__":
    print("="*80)
    print("PALINDROMIC TIMELINE QUERY FIX VALIDATION")
    print("="*80)
    print()
    
    results = []
    try:
        results.append(("Query Expansion", test_query_expansion()))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("Query Expansion", False))
    
    print()
    try:
        results.append(("Semantic Retrieval", test_semantic_retrieval()))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("Semantic Retrieval", False))
    
    print()
    try:
        results.append(("BM25 Retrieval", test_bm25_retrieval()))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("BM25 Retrieval", False))
    
    print()
    try:
        results.append(("Reranking", test_reranker()))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("Reranking", False))
    
    print()
    print("="*80)
    print("RESULTS")
    print("="*80)
    for name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"  {name}: {status}")
    
    all_pass = all(success for _, success in results)
    print()
    print(f"Overall: {'PASS' if all_pass else 'FAIL'}")
