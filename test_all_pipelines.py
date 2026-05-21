#!/usr/bin/env python
"""Comprehensive test of palindromic timeline query across all pipelines."""
import sys
sys.path.insert(0, '.')

from src.pipelines import basic, advanced, hybrid
from src.config import FINAL_TOP_K

query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"

def test_pipeline(name, pipeline_fn):
    print(f"\n{'='*80}")
    print(f"{name.upper()}")
    print('='*80)
    try:
        results = pipeline_fn.run(query, top_k=FINAL_TOP_K)
        
        print(f"Top 5 results:")
        for i, m in enumerate(results[:5]):
            title = m.get('title', '')
            year = int(m.get('year')) if m.get('year') else '?'
            score = m.get('final_score', 0)
            print(f"  {i+1}. {title} ({year}) - Score: {score:.4f}")
        
        # Check for target movies
        memento_pos = None
        tenet_pos = None
        for i, m in enumerate(results):
            if 'Memento' in m.get('title', ''):
                memento_pos = i + 1
            if 'Tenet' in m.get('title', ''):
                tenet_pos = i + 1
        
        print(f"\nTarget movie positions:")
        print(f"  Memento: {'Position ' + str(memento_pos) if memento_pos else 'NOT IN TOP 5'}")
        print(f"  Tenet:   {'Position ' + str(tenet_pos) if tenet_pos else 'NOT IN TOP 5'}")
        
        if memento_pos or tenet_pos:
            print(f"  SUCCESS! Found target movie(s) in top results")
            return True
        else:
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

print("Query:", query)
print()

# Test all pipelines
results = []
results.append(("Basic", test_pipeline("Basic Pipeline", basic)))
results.append(("Advanced", test_pipeline("Advanced Pipeline", advanced)))
results.append(("Hybrid", test_pipeline("Hybrid Pipeline", hybrid)))

print(f"\n{'='*80}")
print("SUMMARY")
print('='*80)
for name, success in results:
    status = "PASS" if success else "FAIL"
    print(f"  {name}: {status}")
