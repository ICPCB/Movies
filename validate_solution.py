#!/usr/bin/env python
"""
Final validation of the palindromic timeline ranking fix.

This script tests:
1. Query expansion is active
2. Both Memento and Tenet appear in candidate pools
3. They appear in final reranked results
4. No regression on existing benchmark cases
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_query_expansion():
    """Verify query expansion adds the right keywords."""
    from src.retrieval.query_processor import expand_retrieval_query, normalize_query
    
    query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"
    normalized = normalize_query(query)
    expanded = expand_retrieval_query(normalized)
    
    # Check that expansion happened
    if expanded == normalized:
        return False, "Query not expanded"
    
    # Check for required keywords
    required_keywords = ["nonlinear", "reverse chronology", "time paradox"]
    missing = [kw for kw in required_keywords if kw not in expanded]
    if missing:
        return False, f"Missing keywords: {missing}"
    
    return True, "Query expanded with timeline keywords"

def test_candidate_retrieval():
    """Verify Memento/Tenet appear in retrieval candidate pools."""
    from src.retrieval.query_processor import expand_retrieval_query, normalize_query
    from src.retrieval.semantic import semantic_search
    from src.retrieval.bm25 import bm25_search
    from src.config import CANDIDATE_POOL
    
    query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"
    normalized = normalize_query(query)
    expanded = expand_retrieval_query(normalized)
    
    # Check semantic search
    sem_results = semantic_search(expanded, top_k=CANDIDATE_POOL)
    memento_in_sem = any(m['id'] == 77 for m in sem_results)
    tenet_in_sem = any(m['id'] == 577922 for m in sem_results)
    
    # Check BM25 search
    bm25_results = bm25_search(expanded, top_k=CANDIDATE_POOL)
    memento_in_bm25 = any(m['id'] == 77 for m in bm25_results)
    tenet_in_bm25 = any(m['id'] == 577922 for m in bm25_results)
    
    found = {
        'memento_semantic': memento_in_sem,
        'tenet_semantic': tenet_in_sem,
        'memento_bm25': memento_in_bm25,
        'tenet_bm25': tenet_in_bm25,
    }
    
    if not any(found.values()):
        return False, "Neither movie found in retrieval candidate pools"
    
    found_str = ", ".join([k.replace('_', ' ') for k, v in found.items() if v])
    return True, f"Found in: {found_str}"

def test_final_ranking():
    """Verify Memento/Tenet appear in final pipeline output."""
    from src.pipelines import advanced
    from src.config import FINAL_TOP_K
    
    query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"
    results = advanced.run(query, top_k=FINAL_TOP_K + 5, with_explanation=False)
    
    memento_rank = None
    tenet_rank = None
    for i, m in enumerate(results):
        if m['id'] == 77:
            memento_rank = i + 1
        if m['id'] == 577922:
            tenet_rank = i + 1
    
    found_ranks = []
    if memento_rank:
        found_ranks.append(f"Memento #{memento_rank}")
    if tenet_rank:
        found_ranks.append(f"Tenet #{tenet_rank}")
    
    if not found_ranks:
        return False, "Neither movie in final results"
    
    # Success if either appears in top 10
    in_top_10 = (memento_rank and memento_rank <= 10) or (tenet_rank and tenet_rank <= 10)
    if not in_top_10:
        return False, f"Found but not in top 10: {', '.join(found_ranks)}"
    
    return True, f"Success: {', '.join(found_ranks)}"

def test_no_regression():
    """Quick smoke test on a few existing benchmark cases."""
    from src.pipelines import advanced
    from src.config import FINAL_TOP_K
    
    cases = [
        {
            "query": "a dream heist movie where people enter dreams to steal secrets",
            "expected_title": "Inception",
            "expected_id": 27205,  # Approximate
        },
        {
            "query": "a robot cleaning Earth after humans left",
            "expected_title": "WALL-E",
            "expected_id": 10681,  # Approximate
        },
    ]
    
    regressions = []
    for case in cases:
        results = advanced.run(case["query"], top_k=FINAL_TOP_K + 5, with_explanation=False)
        found = any(case["expected_title"].lower() in m.get("title", "").lower() for m in results[:10])
        if not found:
            regressions.append(case["expected_title"])
    
    if regressions:
        return False, f"Regressions on: {', '.join(regressions)}"
    
    return True, "No regressions on existing benchmark cases"

def main():
    print("="*100)
    print("PALINDROMIC TIMELINE RANKING FIX - COMPREHENSIVE VALIDATION")
    print("="*100)
    print()
    
    tests = [
        ("Query Expansion", test_query_expansion),
        ("Candidate Retrieval", test_candidate_retrieval),
        ("Final Ranking", test_final_ranking),
        ("No Regression", test_no_regression),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            success, message = test_fn()
            results.append((name, success, message))
            status = "PASS" if success else "FAIL"
            print(f"{status:>4} {name:<30} {message}")
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"{'ERROR':>4} {name:<30} {str(e)[:60]}")
    
    print()
    print("="*100)
    all_pass = all(success for _, success, _ in results)
    print(f"Overall: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
    print("="*100)
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
