"""Quality smoke test / benchmark for the recommendation pipelines.

Implements AGENTS.md Task 8: a small English-query benchmark with named
expected titles. Each case lists the query, the title(s) we'd expect a
good recommender to return, and we report whether any expected title
landed in top-3 and top-10 for each pipeline (Basic / Advanced / Hybrid).

Important: expected-title *measurement* is not the same as
expected-title *coercion*. AGENTS.md Task 3 forbids hardcoding answers
into the recommender (e.g. forcing 'Inception' into query expansion).
This file only inspects pipeline OUTPUT — the pipelines never see the
expected list.

Run from the project root:

    python scripts/quality_smoke_test.py
    python scripts/quality_smoke_test.py --modes Basic Hybrid
    python scripts/quality_smoke_test.py --top-k 5 --no-llm
    python scripts/quality_smoke_test.py --no-llm --stress
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
import unicodedata
from pathlib import Path

# Make `src` importable when the script is run directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.dedup import find_duplicate_keys, get_movie_key  # noqa: E402


# AGENTS.md Task 8 benchmark cases. Each case lists the query, the set
# of acceptable expected titles, and an optional note. CineMatch uses an
# English query/UI scope, but the cleaned index can include global films
# when TMDB provides English metadata.
BENCHMARK_CASES: list[dict] = [
    {
        "query": "a stranded astronaut trying to survive on Mars",
        "expected": ["The Martian"],
        "note": "Advanced/Hybrid: top 1-3; Basic: top 10.",
    },
    {
        "query": "a toy cowboy and a space ranger becoming friends",
        "expected": ["Toy Story", "Toy Story 2"],
        "note": "At least one expected title in top 10.",
    },
    {
        "query": "a dream heist movie where people enter dreams to steal secrets",
        "expected": ["Inception"],
        "note": "Advanced: top 1-3; Hybrid: no literal-keyword false positive.",
    },
    {
        "query": "a thief infiltrates the subconscious of targets to steal secrets and plant an idea",
        "expected": ["Inception"],
        "note": "All modes should rank Inception high; Advanced/Hybrid top 1.",
    },
    {
        "query": "a philosophical animated movie about lucid dreams and reality",
        "expected": ["Waking Life"],
        "note": "Advanced/Hybrid: top 1.",
    },
    {
        "query": "a robot cleaning Earth after humans left",
        "expected": ["WALL-E", "WALL·E", "WALLE", "Wall-E"],
        "note": "Expected title in top 1-3.",
    },
    {
        "query": "a clown fish father searching for his lost son",
        "expected": ["Finding Nemo"],
        "note": "Expected title in top 1-3.",
    },
    {
        "query": "a lonely hitman protects a young girl",
        "expected": ["Léon: The Professional", "Leon: The Professional", "The Professional"],
        "note": "Expected title in top 1-3.",
    },
    {
        "query": "a poor family infiltrates a rich household",
        "expected": ["Parasite"],
        "note": "Expected title in top 1-3.",
    },
    {
        "query": "a hacker discovers reality is a simulation",
        "expected": ["The Matrix"],
        "note": "Expected title in top 1-3.",
    },
]

STRESS_CASES: list[dict] = [
    {"query": "an archaeologist searches for the lost ark before the nazis", "expected": ["Raiders of the Lost Ark"]},
    {"query": "a great white shark terrorizes a beach town", "expected": ["Jaws"]},
    {"query": "a teenager travels through time in a DeLorean", "expected": ["Back to the Future"]},
    {"query": "a mafia family crime epic about the Corleones", "expected": ["The Godfather"]},
    {"query": "a masked billionaire vigilante fights crime in Gotham", "expected": ["Batman Begins", "The Dark Knight", "Batman"]},
    {"query": "a hobbit must destroy a ring in a volcano", "expected": ["The Lord of the Rings: The Return of the King", "The Lord of the Rings: The Fellowship of the Ring"]},
    {"query": "a theme park with cloned dinosaurs goes wrong", "expected": ["Jurassic Park"]},
    {"query": "a young wizard attends a magical school", "expected": ["Harry Potter and the Philosopher's Stone", "Harry Potter and the Sorcerer's Stone"]},
    {"query": "a boxer from Philadelphia gets a chance at the heavyweight title", "expected": ["Rocky"]},
    {"query": "a cyborg assassin is sent back in time to kill Sarah Connor", "expected": ["The Terminator"]},
    {"query": "two detectives investigate murders based on the seven deadly sins", "expected": ["Se7en", "Seven"]},
    {"query": "a woman is trapped in space after debris destroys her shuttle", "expected": ["Gravity"]},
    {"query": "a pianist survives the Holocaust in Warsaw", "expected": ["The Pianist"]},
    {"query": "a math genius janitor at MIT goes to therapy", "expected": ["Good Will Hunting"]},
    {"query": "a rat secretly becomes a chef in Paris", "expected": ["Ratatouille"]},
    {"query": "a computer hacker named Neo learns about the matrix", "expected": ["The Matrix"]},
    {"query": "a boxer trains in a meat locker and runs up steps", "expected": ["Rocky"]},
    {"query": "a man ages backwards through the twentieth century", "expected": ["The Curious Case of Benjamin Button"]},
    {"query": "a cursed videotape kills viewers after seven days", "expected": ["The Ring", "Ringu"]},
    {"query": "a former roman general becomes a gladiator", "expected": ["Gladiator"]},
    {"query": "a girl enters a spirit world after her parents become pigs", "expected": ["Spirited Away"]},
    {"query": "a bus will explode if it goes below fifty miles per hour", "expected": ["Speed"]},
    {"query": "a young lion prince flees after his father is killed", "expected": ["The Lion King"]},
    {"query": "a man relives the same day again and again", "expected": ["Groundhog Day"]},
]

# Generic "could apply to almost any movie" phrases. We flag explanations
# made of nothing but these as suspicious. NOT used to silently reject
# explanations — only to warn the human reading the smoke test output.
_GENERIC_PHRASES = (
    "great movie", "amazing film", "must watch", "must-watch",
    "critically acclaimed", "highly recommended", "iconic",
    "masterpiece", "won an oscar", "audiences love", "fans agree",
    "fans will love", "groundbreaking", "perfectly matches",
)


def _fmt_score(v):
    if v is None:
        return "—"
    try:
        return f"{float(v):.4f}"
    except (TypeError, ValueError):
        return "—"


def _year_str(m: dict) -> str:
    y = m.get("year")
    if y:
        try:
            return str(int(y))
        except (TypeError, ValueError):
            pass
    rd = str(m.get("release_date", "") or "")
    return rd[:4] if len(rd) >= 4 and rd[:4].isdigit() else "????"


def _normalize_title(t: str) -> str:
    """Lowercased, punctuation-stripped title for fuzzy matching."""
    text = unicodedata.normalize("NFKD", str(t or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return "".join(c for c in text if c.isalnum() or c.isspace()).strip()


def _rank_of_expected(movies: list[dict], expected: list[str]) -> int | None:
    """1-indexed rank of the first movie whose normalized title contains
    (or is contained in) any expected title. None if no expected title
    appears in the list."""
    norm_expected = {_normalize_title(e) for e in expected if e}
    for i, m in enumerate(movies, 1):
        title_norm = _normalize_title(str(m.get("title", "") or ""))
        if not title_norm:
            continue
        for e in norm_expected:
            if e and (e in title_norm or title_norm in e):
                return i
    return None


def _looks_unsupported(explanation: str, movie: dict) -> bool:
    """Return True if the explanation seems to invent facts."""
    if not explanation:
        return False
    text = explanation.lower()
    overview = str(movie.get("overview", "") or "").lower()
    # Generic praise with no overview reference.
    generic_hits = sum(1 for p in _GENERIC_PHRASES if p in text)
    if generic_hits >= 1 and not any(w in text for w in overview.split()[:30] if len(w) > 4):
        return True
    # "Same title, different plot" disclaimer — flag unless the overview
    # actually says something contradictory to the query.
    if "same title" in text or "different plot" in text:
        return True
    return False


def _print_row(rank: int, m: dict, explanation_present: bool) -> None:
    key = m.get("movie_key") or get_movie_key(m)
    title = str(m.get("title", "") or "").strip() or "?"
    year = _year_str(m)
    genres = str(m.get("genres", "") or "").strip()

    print(f"  #{rank:>2}  key={key}  {title} ({year})")
    if genres:
        print(f"        genres: {genres[:120]}")
    print(
        "        "
        f"sem={_fmt_score(m.get('semantic_score'))}  "
        f"bm25={_fmt_score(m.get('bm25_score'))}  "
        f"rrf={_fmt_score(m.get('rrf_score'))}  "
        f"rerank={_fmt_score(m.get('rerank_score'))}  "
        f"final={_fmt_score(m.get('final_score'))}"
    )
    if explanation_present:
        expl = str(m.get("explanation", "") or "").strip()
        if expl:
            print(f"        why: {expl[:240]}")


def _check_warnings(query: str, mode: str, movies: list[dict], top_k: int) -> list[str]:
    warnings: list[str] = []

    if len(movies) < min(top_k, 3):
        warnings.append(f"only {len(movies)} results returned (expected at least {min(top_k, 3)})")

    dup_keys = find_duplicate_keys(movies)
    if dup_keys:
        warnings.append(f"duplicate movie_key in final list: {dup_keys}")

    title_year_seen: dict[tuple[str, str], int] = {}
    for m in movies:
        t = str(m.get("title", "") or "").strip().lower()
        y = _year_str(m)
        title_year_seen[(t, y)] = title_year_seen.get((t, y), 0) + 1
    dup_ty = [k for k, n in title_year_seen.items() if n > 1]
    if dup_ty:
        warnings.append(f"duplicate title+year in final list: {dup_ty}")

    for i, m in enumerate(movies, 1):
        if m.get("final_score") is None:
            warnings.append(f"#{i} missing final_score")
            break

    if mode == "Hybrid":
        if not any(m.get("rrf_score") is not None for m in movies):
            warnings.append("Hybrid mode produced no rrf_score on any movie")

    if mode in ("Advanced", "Hybrid"):
        if not any(m.get("rerank_score") is not None for m in movies):
            warnings.append(f"{mode} mode produced no rerank_score on any movie")

    for i, m in enumerate(movies, 1):
        expl = m.get("explanation")
        if expl and _looks_unsupported(expl, m):
            warnings.append(f"#{i} explanation looks unsupported/generic: {expl[:120]!r}")

    return warnings


def run_case(
    case: dict,
    modes: list[str],
    top_k: int,
    with_llm: bool,
    results: dict[str, list[dict]],
) -> None:
    """Run one benchmark case through every mode and record results."""
    from src.pipelines import basic as basic_pipeline
    from src.pipelines import advanced as advanced_pipeline
    from src.pipelines import hybrid as hybrid_pipeline

    query = case["query"]
    expected = case.get("expected", [])
    note = case.get("note", "")
    is_expected_miss = bool(case.get("expected_miss"))

    print()
    print("=" * 78)
    print(f"QUERY: {query}")
    print(f"  expected:  {expected}")
    if note:
        print(f"  note:      {note}")
    if is_expected_miss:
        print("  status:    EXPECTED MISS in this benchmark scope")
    print("=" * 78)

    for mode in modes:
        print(f"\n--- {mode} ---")
        t0 = time.time()
        try:
            if mode == "Basic":
                movies = basic_pipeline.run(query, top_k=top_k)
            elif mode == "Advanced":
                movies = advanced_pipeline.run(query, top_k=top_k, with_explanation=with_llm)
            elif mode == "Hybrid":
                movies = hybrid_pipeline.run(query, top_k=top_k, with_explanation=with_llm)
            else:
                print(f"  unknown mode: {mode}")
                continue
        except Exception:
            print(f"  ERROR running {mode}:")
            traceback.print_exc()
            results.setdefault(mode, []).append({
                "query": query, "expected": expected, "rank": None,
                "in_top3": False, "in_top10": False,
                "is_expected_miss": is_expected_miss, "error": True,
            })
            continue
        elapsed = time.time() - t0

        explanation_present = mode in ("Advanced", "Hybrid") and with_llm
        for i, m in enumerate(movies, 1):
            _print_row(i, m, explanation_present)

        rank = _rank_of_expected(movies, expected)
        in_top3 = rank is not None and rank <= 3
        in_top10 = rank is not None and rank <= 10
        rank_str = f"#{rank}" if rank is not None else "MISS"
        verdict = (
            "(expected miss — OK)" if rank is None and is_expected_miss
            else "(MISS — regression?)" if rank is None
            else ""
        )
        print(
            f"  [{mode} done in {elapsed:.2f}s — {len(movies)} results "
            f"— expected rank={rank_str} top3={in_top3} top10={in_top10} {verdict}]"
        )
        for w in _check_warnings(query, mode, movies, top_k):
            print(f"  WARN  {w}")

        results.setdefault(mode, []).append({
            "query": query, "expected": expected, "rank": rank,
            "in_top3": in_top3, "in_top10": in_top10,
            "is_expected_miss": is_expected_miss, "error": False,
        })


def _print_summary(results: dict[str, list[dict]], modes: list[str]) -> None:
    """Final pass/fail table by mode."""
    print()
    print("=" * 78)
    print("BENCHMARK SUMMARY (English query / global metadata build)")
    print("=" * 78)
    header = f"  {'mode':<10} {'top1':>5} {'top3':>5} {'top10':>5} {'miss':>5} {'exp_miss':>9}  / total"
    print(header)
    for mode in modes:
        rs = results.get(mode, [])
        total = len(rs)
        top1 = sum(1 for r in rs if r["rank"] == 1)
        top3 = sum(1 for r in rs if r["in_top3"])
        top10 = sum(1 for r in rs if r["in_top10"])
        miss = sum(1 for r in rs if r["rank"] is None and not r["is_expected_miss"])
        exp_miss = sum(1 for r in rs if r["rank"] is None and r["is_expected_miss"])
        print(f"  {mode:<10} {top1:>5} {top3:>5} {top10:>5} {miss:>5} {exp_miss:>9}  / {total}")
    print(
        "\n  Columns:\n"
        "    top1/top3/top10 — expected title appeared in top-1 / top-3 / top-10\n"
        "    miss            — expected title absent\n"
        "    exp_miss        — expected title absent but explicitly marked expected-miss"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["Basic", "Advanced", "Hybrid"],
        choices=["Basic", "Advanced", "Hybrid"],
    )
    parser.add_argument(
        "--top-k", type=int, default=10,
        help="Number of results per pipeline (default 10 so top-10 checks have data).",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip all LLM calls: retrieval expansion, HyDE, and explanations.",
    )
    parser.add_argument(
        "--no-llm-retrieval",
        action="store_true",
        help="Skip retrieval-side LLM expansion/HyDE but keep explanation behavior unchanged.",
    )
    parser.add_argument(
        "--stress",
        action="store_true",
        help="Run the broader 24-case paraphrase stress set instead of the default 10-case benchmark.",
    )
    parser.add_argument(
        "--queries",
        nargs="*",
        default=None,
        help=(
            "Override benchmark queries. Each query runs WITHOUT an expected-title "
            "check (rank reported as MISS in the summary). Defaults to the AGENTS.md set."
        ),
    )
    args = parser.parse_args()

    from src import config as runtime_config

    if args.no_llm or args.no_llm_retrieval:
        runtime_config.LLM_RETRIEVAL_ENABLED = False

    if args.queries:
        cases = [{"query": q, "expected": [], "note": "ad-hoc override"} for q in args.queries]
    elif args.stress:
        cases = STRESS_CASES
    else:
        cases = BENCHMARK_CASES

    with_llm = not args.no_llm
    retrieval_llm = runtime_config.LLM_RETRIEVAL_ENABLED

    print("Running quality smoke test")
    print(f"  modes:  {args.modes}")
    print(f"  top_k:  {args.top_k}")
    print(f"  llm explanations: {'on' if with_llm else 'off'}")
    print(f"  llm retrieval:    {'on' if retrieval_llm else 'off'}")
    print(f"  cwd:    {os.getcwd()}")
    print(f"  root:   {ROOT}")
    print(f"  cases:  {len(cases)}")

    results: dict[str, list[dict]] = {}
    for case in cases:
        run_case(case, args.modes, args.top_k, with_llm, results)

    _print_summary(results, args.modes)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
