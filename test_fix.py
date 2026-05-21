#!/usr/bin/env python
"""Test the palindromic timeline query fix."""
import sys
sys.path.insert(0, '.')

from recommend_bgem3 import recommend

query = "A palindromic timeline where scenes and characters move forward and backward through time simultaneously"

print("Testing query on Advanced pipeline...")
print(f"Query: {query}")
print()

results = recommend(query, top_k=10, with_explanation=False)

print("Top 10 results:")
for i, m in enumerate(results[:10]):
    title = m.get('title', '')
    year = m.get('year', '')
    score = m.get('final_score', 0)
    print(f"{i+1}. {title} ({int(year) if year else '?'}) - Score: {score:.4f}")
    if 'Memento' in title or 'Tenet' in title:
        print(f"   ^^^ TARGET FOUND! ^^^")

print()
print("Checking if Memento or Tenet appear in results...")
found = False
for m in results:
    if 'Memento' in m.get('title', '') or 'Tenet' in m.get('title', ''):
        idx = results.index(m)
        print(f"FOUND: {m['title']} at position {idx + 1} with score {m.get('final_score', 0):.4f}")
        found = True

if not found:
    print("NOT FOUND in top 10 results")
