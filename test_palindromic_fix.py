#!/usr/bin/env python
"""Test the palindromic timeline query to verify fix."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Import pipelines
from src.pipelines import advanced, basic, hybrid
from src.config import FINAL_TOP_K

query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"

print("="*100)
print("PALINDROMIC TIMELINE QUERY TEST")
print("="*100)
print(f"Query: {query}\n")

def run_pipeline(name, pipeline_module, with_explanation=False):
    print(f"\n{name.upper()} PIPELINE")
    print("-" * 100)
    try:
        results = pipeline_module.run(query, top_k=FINAL_TOP_K + 5, with_explanation=with_explanation)
        
        print(f"{'Rank':<6} {'Title':<40} {'Year':<6} {'Final Score':<12} {'Found':<10}")
        print("-" * 100)
        
        memento_found = False
        tenet_found = False
        
        for i, movie in enumerate(results[:10], 1):
            title = movie.get('title', '')[:38]
            year = int(movie.get('year')) if movie.get('year') else '?'
            score = movie.get('final_score', 0)
            
            marker = ""
            if 'Memento' in movie.get('title', ''):
                marker = "✓ MEMENTO"
                memento_found = True
            elif 'Tenet' in movie.get('title', ''):
                marker = "✓ TENET"
                tenet_found = True
            
            print(f"{i:<6} {title:<40} {year:<6} {score:<12.4f} {marker:<10}")
        
        if memento_found or tenet_found:
            print(f"\n✓ SUCCESS: Target movie {'(Memento/Tenet)' if memento_found and tenet_found else '(Memento)' if memento_found else '(Tenet)'} found in top 10")
            return True
        else:
            print(f"\n✗ FAIL: Neither Memento nor Tenet found in top 10")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

# Run tests
results = {}
results['Basic'] = run_pipeline('Basic', basic)
results['Advanced'] = run_pipeline('Advanced', advanced)
results['Hybrid'] = run_pipeline('Hybrid', hybrid)

# Summary
print("\n" + "="*100)
print("SUMMARY")
print("="*100)
for name, success in results.items():
    status = "PASS" if success else "FAIL"
    print(f"  {name:<15} {status}")

all_pass = all(results.values())
print(f"\nOverall: {'PASS - Query expansion and ranking fix is working!' if all_pass else 'FAIL - Additional tuning needed'}")
