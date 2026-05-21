#!/usr/bin/env python
"""Quick smoke test on key benchmark cases to ensure no regressions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.pipelines import advanced
from src.config import FINAL_TOP_K

# Key benchmark cases that should NOT regress
test_cases = [
    {
        "query": "a dream heist movie where people enter dreams to steal secrets",
        "expected": "Inception",
        "name": "Inception (Dream Heist)"
    },
    {
        "query": "a robot cleaning Earth after humans left",
        "expected": "WALL-E",
        "name": "WALL-E (Robot Earth)"
    },
    {
        "query": "a stranded astronaut trying to survive on Mars",
        "expected": "The Martian",
        "name": "The Martian (Astronaut Mars)"
    },
    {
        "query": "a man ages backwards through the twentieth century",
        "expected": "Benjamin Button",
        "name": "The Curious Case of Benjamin Button (Aging Backwards)"
    },
]

print("="*100)
print("REGRESSION TEST - Key Benchmark Cases")
print("="*100)
print()

all_pass = True
for case in test_cases:
    query = case["query"]
    expected = case["expected"]
    name = case["name"]
    
    try:
        results = advanced.run(query, top_k=FINAL_TOP_K + 5, with_explanation=False)
        
        # Check if expected movie is in top 10
        found = False
        rank = None
        for i, m in enumerate(results[:10]):
            if expected.lower() in m.get("title", "").lower():
                found = True
                rank = i + 1
                break
        
        status = "PASS" if found else "FAIL"
        rank_str = f"#{rank}" if rank else "MISS"
        
        print(f"{status:>4} {name:<50} {rank_str}")
        
        if not found:
            all_pass = False
    except Exception as e:
        print(f"{'ERR':>4} {name:<50} {str(e)[:40]}")
        all_pass = False

print()
print("="*100)
print(f"Result: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED - CHECK REGRESSION'}")
print("="*100)
