"""Ad-hoc check: do post-rebuild LLM explanations stay grounded in metadata,
and does the deterministic fallback kick in when the LLM is unavailable?

Tests:
  A) Live LLM path — run advanced pipeline on an Inception query, ask
     explain_movies_batch for the top-3, then for each explanation print:
       - the visible explanation
       - whether any 6+ word substring of the explanation appears verbatim
         in the metadata (proxy for "the model cited real evidence")
       - whether the explanation starts with "Title:" (signal that the
         deterministic fallback fired because the LLM reply was rejected)
  B) Fallback path — call _fallback_explanation directly with a movie that
     has rich metadata to confirm it never crashes and produces grounded text.
  C) Simulated LLM outage — monkey-patch _invoke_with_timeout to raise, then
     re-run explain_movies_batch to confirm we get fallbacks (not a crash).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipelines import advanced as advanced_pipeline
from src.llm import langchain_ollama as llm_mod


QUERY = "a thief infiltrates the subconscious of targets to steal secrets and plant an idea"


def metadata_blob(m: dict) -> str:
    parts = [
        str(m.get("title", "") or ""),
        str(m.get("genres", "") or ""),
        str(m.get("overview", "") or ""),
        str(m.get("keywords", "") or ""),
        str(m.get("tagline", "") or ""),
    ]
    return " ".join(parts).lower()


def cited_phrase(explanation: str, m: dict) -> str | None:
    """Return the longest 4+ word phrase from `explanation` that appears
    verbatim in the metadata, or None. A real grounded explanation should
    contain at least one such phrase."""
    blob = metadata_blob(m)
    words = explanation.lower().split()
    # Try long phrases first.
    for size in range(min(10, len(words)), 3, -1):
        for i in range(0, len(words) - size + 1):
            phrase = " ".join(words[i : i + size]).strip(".,;:!?\"'()[]")
            if len(phrase) > 8 and phrase in blob:
                return phrase
    return None


def report(label: str, movies: list[dict], explanations: list[str]) -> None:
    print(f"\n--- {label} ---")
    for m, expl in zip(movies, explanations):
        title = str(m.get("title", "") or "")
        cited = cited_phrase(expl, m)
        looks_like_fallback = expl.startswith(f"{title}:")
        print(f"\n  Movie: {title}")
        print(f"  Tagline:  {str(m.get('tagline', '') or '')[:120]}")
        print(f"  Overview: {str(m.get('overview', '') or '')[:160]}")
        print(f"  Explanation: {expl}")
        if looks_like_fallback:
            print("  -> deterministic fallback (LLM reply rejected or unavailable)")
        elif cited:
            print(f"  -> LLM cited verbatim phrase: '{cited}'")
        else:
            print("  -> WARN: no obvious verbatim citation in explanation")


def main() -> int:
    print("=" * 90)
    print(f" Query: {QUERY!r}")
    print("=" * 90)

    # ------------------------------------------------------------------
    # A) Live LLM path: run the advanced pipeline (no explanations) and
    #    then call explain_movies_batch on the top-3 results.
    # ------------------------------------------------------------------
    movies = advanced_pipeline.run(QUERY, top_k=3, with_explanation=False)
    print(f"\nTop-3 from advanced pipeline:")
    for i, m in enumerate(movies, 1):
        print(f"  {i}. {m.get('title', '')}  (tmdb_id={m.get('tmdb_id', '?')})")

    print("\n[A] LIVE LLM EXPLANATIONS")
    live = llm_mod.explain_movies_batch(QUERY, movies)
    report("live LLM", movies, live)

    # ------------------------------------------------------------------
    # B) Direct deterministic fallback on a known-rich movie (Inception).
    # ------------------------------------------------------------------
    print("\n[B] DETERMINISTIC FALLBACK (direct call on top-1)")
    if movies:
        det = llm_mod._fallback_explanation(QUERY, movies[0])
        print(f"  {det}")

    # ------------------------------------------------------------------
    # C) Simulated outage: force the LLM call to raise and confirm
    #    explain_movies_batch still returns one explanation per movie.
    # ------------------------------------------------------------------
    print("\n[C] SIMULATED LLM OUTAGE (monkey-patched _invoke_with_timeout)")
    orig = llm_mod._invoke_with_timeout

    def boom(*a, **kw):
        raise RuntimeError("simulated-outage")

    llm_mod._invoke_with_timeout = boom
    try:
        outage = llm_mod.explain_movies_batch(QUERY, movies)
        report("outage", movies, outage)
        all_fallback = all(
            e.startswith(f"{m.get('title','')}:")
            for m, e in zip(movies, outage)
        )
        print(
            f"\n  outage produced {len(outage)} explanations for {len(movies)} movies; "
            f"all-fallback={all_fallback}"
        )
    finally:
        llm_mod._invoke_with_timeout = orig

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
