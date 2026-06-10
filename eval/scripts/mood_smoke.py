"""Smoke-check mood_v1 queries against the running API (ULTRAPLAN phase 6).

For a deterministic sample of mood_v1 queries, POST the full intent to
/api/recommend (log_history=false) and report, per query: result count and
how many of the top 10 carry at least one desired film-mood tag. This is a
sanity check that the mood layer attaches tags and surfaces mood-relevant
movies — NOT a graded relevance eval (mood_v1 has no gold labels yet).
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
QUERIES = ROOT / "eval" / "queries" / "mood_v1.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--every", type=int, default=7, help="sample every Nth query")
    args = parser.parse_args()

    rows = [json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
    sample = rows[:: args.every]
    failures = 0
    for row in sample:
        tags = row["tags"]
        intent = {
            "mode": tags["mode"],
            "user_moods": tags["user_mood_categories"],
            "desired_film_moods": tags["desired_film_moods"],
            "avoid_film_moods": tags["avoid_film_moods"],
            "plot_elements": [],
            "genres_include": [],
            "genres_exclude": [],
            "era": {"min_year": None, "max_year": None},
            "tone": {"darkness": 0.0, "intensity": 0.0},
            "constraints": {"min_rating": None},
            "free_text_query": row["query"],
            "confidence": 1.0,
        }
        body = json.dumps(
            {"intent": intent, "page_size": 10, "log_history": False}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{args.base_url}/api/recommend",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = data["results"]
        desired = set(tags["desired_film_moods"])
        tagged = sum(
            1 for movie in results if set(movie.get("film_mood_tags", [])) & desired
        )
        ok = bool(results) and tagged > 0
        if not ok:
            failures += 1
        print(
            f"{row['qid']} [{tags['mode']:>6}] results={len(results):2d} "
            f"desired-mood-tagged-in-top10={tagged:2d} {'OK' if ok else 'FAIL'} "
            f"{row['query']!r}"
        )
    print(f"\nsampled={len(sample)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
