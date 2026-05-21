#!/usr/bin/env python
"""
FINAL VALIDATION TEST
Tests the palindromic timeline ranking fix on all three pipelines.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.pipelines import basic, advanced, hybrid
from src.config import FINAL_TOP_K

query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"

print("="*100)
print("FINAL VALIDATION: Palindromic Timeline Query Fix")
print("="*100)
print(f"\nQuery: {query}\n")

def test_pipeline(name, pipeline_module):
    """Test one pipeline and check for Memento/Tenet in top results."""
    try:
        results = pipeline_module.run(query, top_k=FINAL_TOP_K + 5, with_explanation=False)
        
        # Look for target movies
        memento_rank = None
        tenet_rank = None
        for i, m in enumerate(results[:10], 1):
            if m['id'] == 77:  # Memento ID
                memento_rank = i
            if m['id'] == 577922:  # Tenet ID
                tenet_rank = i
        
        # Report first 5 results
        print(f"{name.upper()} PIPELINE:")
        for i in range(min(5, len(results))):
            m = results[i]
            title = m.get('title', '')
            marker = ""
            if m['id'] == 77:
                marker = " <-- MEMENTO"
            elif m['id'] == 577922:
                marker = " <-- TENET"
            print(f"  {i+1}. {title}{marker}")
        
        # Check success
        if memento_rank or tenet_rank:
            positions = []
            if memento_rank:
                positions.append(f"Memento #{memento_rank}")
            if tenet_rank:
                positions.append(f"Tenet #{tenet_rank}")
            print(f"  ✓ SUCCESS: {', '.join(positions)}\n")
            return True
        else:
            print(f"  ✗ FAIL: Neither Memento nor Tenet found in top 10\n")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}\n")
        return False

# Test all pipelines
results = {
    "Basic": test_pipeline("Basic", basic),
    "Advanced": test_pipeline("Advanced", advanced),
    "Hybrid": test_pipeline("Hybrid", hybrid),
}

# Summary
print("="*100)
print("SUMMARY")
print("="*100)
for name, success in results.items():
    status = "PASS" if success else "FAIL"
    print(f"  {name:<15} {status}")

all_pass = all(results.values())
print()
if all_pass:
    print("✓ ALL TESTS PASSED - Fix is working across all pipelines!")
else:
    print("✗ Some tests failed - Further investigation needed")

print("="*100)
