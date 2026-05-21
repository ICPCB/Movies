"""Ad-hoc benchmark for the 10 AGENTS.md expected-title cases.

Runs each query through Basic / Advanced / Hybrid (no LLM explanations
to keep it fast) and reports whether the expected title appears in the
top 3 / top 10. Intentionally lives outside scripts/quality_smoke_test.py
so the official smoke test stays unchanged for Phase 2.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipelines import basic as basic_pipeline
from src.pipelines import advanced as advanced_pipeline
from src.pipelines import hybrid as hybrid_pipeline


CASES = [
    ("a stranded astronaut trying to survive on Mars",
     ["the martian"]),
    ("a toy cowboy and a space ranger becoming friends",
     ["toy story", "toy story 2"]),
    ("a dream heist movie where people enter dreams to steal secrets",
     ["inception"]),
    ("a thief infiltrates the subconscious of targets to steal secrets and plant an idea",
     ["inception"]),
    ("a philosophical animated movie about lucid dreams and reality",
     ["waking life"]),
    ("a robot cleaning Earth after humans left",
     ["wall-e", "wall·e", "walle"]),
    ("a clown fish father searching for his lost son",
     ["finding nemo"]),
    ("a lonely hitman protects a young girl",
     ["leon: the professional", "léon: the professional", "the professional"]),
    ("a poor family infiltrates a rich household",
     ["parasite"]),
    ("a hacker discovers reality is a simulation",
     ["the matrix"]),
]


def normalize_title(t: str) -> str:
    return "".join(c for c in t.lower() if c.isalnum() or c.isspace()).strip()


def rank_of_expected(movies: list[dict], expected: list[str]) -> int | None:
    """1-indexed rank of any expected title in `movies`, or None."""
    norm_expected = {normalize_title(e) for e in expected}
    for i, m in enumerate(movies, 1):
        title_norm = normalize_title(str(m.get("title", "") or ""))
        for e in norm_expected:
            if e in title_norm or title_norm in e:
                return i
    return None


def run_case(query: str, expected: list[str], top_k: int = 10) -> dict:
    out = {"query": query, "expected": expected}
    for mode, pipe in (
        ("basic", lambda q: basic_pipeline.run(q, top_k=top_k)),
        ("advanced", lambda q: advanced_pipeline.run(q, top_k=top_k, with_explanation=False)),
        ("hybrid", lambda q: hybrid_pipeline.run(q, top_k=top_k, with_explanation=False)),
    ):
        t0 = time.time()
        try:
            movies = pipe(query)
            rank = rank_of_expected(movies, expected)
            top1 = str(movies[0].get("title", "")) if movies else ""
            top3 = [str(m.get("title", "")) for m in movies[:3]]
        except Exception as e:
            rank = None
            top1 = f"ERROR: {e}"
            top3 = []
        out[mode] = {
            "rank": rank,
            "in_top3": rank is not None and rank <= 3,
            "in_top10": rank is not None and rank <= 10,
            "top1": top1,
            "top3": top3,
            "elapsed_s": round(time.time() - t0, 2),
        }
    return out


def fmt_rank(r: int | None) -> str:
    return f"#{r}" if r is not None else "MISS"


def main() -> int:
    print("=" * 90)
    print(" AGENTS.md 10-case benchmark — expected-title accuracy (no LLM explanations)")
    print("=" * 90)
    results = []
    for query, expected in CASES:
        print(f"\n>>> {query}")
        print(f"    expected: {expected}")
        r = run_case(query, expected, top_k=10)
        results.append(r)
        for mode in ("basic", "advanced", "hybrid"):
            stats = r[mode]
            print(
                f"    {mode:<8} rank={fmt_rank(stats['rank']):>5}  "
                f"top1={stats['top1'][:60]!r}  ({stats['elapsed_s']}s)"
            )

    # Summary
    print("\n" + "=" * 90)
    print(" SUMMARY")
    print("=" * 90)
    print(f" {'mode':<10} {'top1':>6} {'top3':>6} {'top10':>6} {'miss':>6}")
    for mode in ("basic", "advanced", "hybrid"):
        top1 = sum(1 for r in results if r[mode]["rank"] == 1)
        top3 = sum(1 for r in results if r[mode]["in_top3"])
        top10 = sum(1 for r in results if r[mode]["in_top10"])
        miss = sum(1 for r in results if r[mode]["rank"] is None)
        print(f" {mode:<10} {top1:>6} {top3:>6} {top10:>6} {miss:>6}  / {len(results)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
