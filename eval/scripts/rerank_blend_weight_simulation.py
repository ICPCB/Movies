"""Dep #7 — Rerank blend-weight simulation.

Reads the Dep #4 pool snapshot and recomputes final_score using candidate
blend-weight sets. Determines whether any weight set fixes q10 strict_hit@5
without regressing other queries.

No model inference, no src/* changes, no new labels.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from math import log1p
from pathlib import Path
from typing import Any

CURRENT_WEIGHTS = {
    "rerank_vote_count_weight": 0.08,
    "rerank_upstream_weight": 0.20,
    "rerank_source_agreement_bonus": 0.10,
}

CANDIDATE_UPSTREAM_WEIGHTS = [0.08, 0.10, 0.12, 0.15, 0.20]
CANDIDATE_AGREEMENT_BONUSES = [0.02, 0.05, 0.08, 0.10]
CANDIDATE_VOTE_WEIGHTS = [0.05, 0.08]

STRICT_HIT_GRADE_THRESHOLD = 3


def load_snapshot(run_dir: str) -> dict:
    path = Path(run_dir) / "analysis" / "rerank_regression" / "full_set_pool_snapshot.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_gold_labels(run_dir: str) -> dict[tuple[str, int], dict]:
    path = Path(run_dir) / "gold_labels.jsonl"
    gold: dict[tuple[str, int], dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            gold[(row["qid"], row["tmdb_id"])] = row
    return gold


def build_pool_lookup(pool: list[dict]) -> dict[int, dict]:
    return {p["tmdb_id"]: p for p in pool}


def source_agreement(movie: dict) -> float:
    if movie.get("semantic_rank") is not None and movie.get("bm25_rank") is not None:
        return 1.0
    return 0.0


def upstream_score(movie: dict) -> float:
    for key in ("rrf_score", "semantic_rrf", "semantic_score", "bm25_score"):
        try:
            v = float(movie.get(key) or 0.0)
            if v:
                return v
        except (TypeError, ValueError):
            pass
    return 0.0


def recompute_final_scores(
    baseline_top: list[dict],
    pool_lookup: dict[int, dict],
    pool_all: list[dict],
    weights: dict[str, float],
) -> list[dict]:
    """Recompute final_score for baseline_top entries using given weights.

    Normalization uses the full pool (matching production behavior in
    src/retrieval/reranker.py), not just the baseline_top subset.
    """
    entries = []
    for bt in baseline_top:
        tid = bt["tmdb_id"]
        pool_entry = pool_lookup.get(tid)
        if pool_entry is None:
            continue

        rerank_score = bt["rerank_score"]
        vote_count = int(pool_entry.get("vote_count", 0) or 0)
        upstream_raw = upstream_score(pool_entry)
        agreement = source_agreement(pool_entry)

        entries.append({
            "tmdb_id": tid,
            "movie_key": bt.get("movie_key", ""),
            "title": bt.get("title", ""),
            "rerank_score": rerank_score,
            "vote_count": vote_count,
            "upstream_raw": upstream_raw,
            "source_agreement": agreement,
            "original_rank": bt.get("rank", 999),
            "original_final_score": bt.get("final_score", 0.0),
        })

    if not entries:
        return entries

    max_votes = max(
        (int(p.get("vote_count", 0) or 0) for p in pool_all),
        default=0,
    ) or 1
    max_vote_log = log1p(max_votes) or 1.0
    max_upstream = max(
        (upstream_score(p) for p in pool_all),
        default=0.0,
    ) or 1.0

    for e in entries:
        vote_prior = log1p(e["vote_count"]) / max_vote_log
        upstream_prior = e["upstream_raw"] / max_upstream

        new_final = (
            e["rerank_score"]
            + weights["rerank_vote_count_weight"] * vote_prior
            + weights["rerank_upstream_weight"] * upstream_prior
            + weights["rerank_source_agreement_bonus"] * e["source_agreement"]
        )
        e["vote_prior"] = vote_prior
        e["upstream_prior"] = upstream_prior
        e["new_final_score"] = new_final

    entries.sort(key=lambda x: -x["new_final_score"])
    for i, e in enumerate(entries):
        e["new_rank"] = i

    return entries


def check_strict_hit_at_k(
    ranked_entries: list[dict],
    gold: dict[tuple[str, int], dict],
    qid: str,
    k: int = 5,
) -> bool:
    """Check if any grade>=2 target is in the top-k."""
    for e in ranked_entries[:k]:
        label = gold.get((qid, e["tmdb_id"]))
        if label:
            g = label.get("gold_grade") or label.get("grade", 0)
            if g is not None and g >= STRICT_HIT_GRADE_THRESHOLD:
                return True
    return False


def generate_weight_sets() -> list[dict[str, float]]:
    """Generate all candidate weight combinations."""
    sets = []
    for uw, ab, vw in product(
        CANDIDATE_UPSTREAM_WEIGHTS,
        CANDIDATE_AGREEMENT_BONUSES,
        CANDIDATE_VOTE_WEIGHTS,
    ):
        sets.append({
            "rerank_upstream_weight": uw,
            "rerank_source_agreement_bonus": ab,
            "rerank_vote_count_weight": vw,
        })
    return sets


def simulate_weight_set(
    snapshot: dict,
    gold: dict[tuple[str, int], dict],
    weights: dict[str, float],
) -> dict:
    """Simulate one weight set across all queries and modes."""
    per_query: dict[str, dict[str, Any]] = {}
    modes_with_rerank = ["advanced", "hybrid"]

    for q in snapshot["queries"]:
        qid = q["qid"]
        per_query[qid] = {}

        for mode in modes_with_rerank:
            mode_data = q["modes"].get(mode, {})
            baseline_top = mode_data.get("baseline_top", [])
            pool = mode_data.get("pool", [])

            if not baseline_top or not pool:
                per_query[qid][mode] = {"error": "missing_data"}
                continue

            pool_lookup = build_pool_lookup(pool)

            original_hit = check_strict_hit_at_k(
                sorted(baseline_top, key=lambda x: x.get("rank", 999)),
                gold, qid, k=5,
            )

            recomputed = recompute_final_scores(baseline_top, pool_lookup, pool, weights)
            new_hit = check_strict_hit_at_k(recomputed, gold, qid, k=5)

            per_query[qid][mode] = {
                "original_hit": original_hit,
                "new_hit": new_hit,
                "change": (
                    "miss_to_hit" if not original_hit and new_hit
                    else "hit_to_miss" if original_hit and not new_hit
                    else "unchanged"
                ),
            }

    regressions = []
    improvements = []
    for qid, modes in per_query.items():
        for mode, data in modes.items():
            if isinstance(data, dict) and data.get("change") == "hit_to_miss":
                regressions.append(f"{qid}/{mode}")
            elif isinstance(data, dict) and data.get("change") == "miss_to_hit":
                improvements.append(f"{qid}/{mode}")

    q10_adv = per_query.get("q10", {}).get("advanced", {})
    q10_hyb = per_query.get("q10", {}).get("hybrid", {})
    q10_fixed = (
        q10_adv.get("new_hit", False) and q10_hyb.get("new_hit", False)
    )

    viable = q10_fixed and len(regressions) == 0

    return {
        "weights": weights,
        "q10_fixed": q10_fixed,
        "regressions": regressions,
        "improvements": improvements,
        "regression_count": len(regressions),
        "improvement_count": len(improvements),
        "viable": viable,
        "per_query": per_query,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dep #7 blend-weight simulation")
    parser.add_argument("--run", required=True, help="Run directory name")
    args = parser.parse_args()

    run_dir = Path("eval/runs") / args.run
    if not run_dir.is_dir():
        print(f"ERROR: run directory not found: {run_dir}", file=sys.stderr)
        return 1

    print(f"[dep7] loading artifacts from {run_dir}")
    snapshot = load_snapshot(str(run_dir))
    gold = load_gold_labels(str(run_dir))

    pool_entry = snapshot["queries"][0]["modes"]["advanced"]["pool"][0]
    required_keys = {"vote_count", "rrf_score", "semantic_rank", "bm25_rank"}
    missing = required_keys - set(pool_entry.keys())
    if missing:
        print(f"[dep7] BLOCKED: missing score components in pool: {missing}")
        output = {
            "schema_version": "dep7-blend-weight-simulation.v1",
            "verdict": "blocked_missing_score_components",
            "missing_keys": sorted(missing),
        }
        out_path = run_dir / "analysis" / "rerank_regression" / "blend_weight_simulation.json"
        out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        return 1

    bt_entry = snapshot["queries"][0]["modes"]["advanced"]["baseline_top"][0]
    if "rerank_score" not in bt_entry:
        print("[dep7] BLOCKED: rerank_score missing from baseline_top entries")
        return 1

    weight_sets = generate_weight_sets()
    print(f"[dep7] testing {len(weight_sets)} weight combinations")

    print(f"[dep7] current weights: {CURRENT_WEIGHTS}")
    current_result = simulate_weight_set(snapshot, gold, CURRENT_WEIGHTS)
    print(f"  current: q10_fixed={current_result['q10_fixed']} regressions={current_result['regression_count']} improvements={current_result['improvement_count']}")

    results = []
    viable_results = []
    for ws in weight_sets:
        r = simulate_weight_set(snapshot, gold, ws)
        results.append(r)
        if r["viable"]:
            viable_results.append(r)

    print(f"[dep7] viable weight sets: {len(viable_results)}/{len(results)}")

    best = None
    if viable_results:
        viable_results.sort(key=lambda r: (-r["improvement_count"], r["weights"]["rerank_upstream_weight"]))
        best = viable_results[0]
        print(f"[dep7] best viable: {best['weights']}")
        print(f"  improvements: {best['improvements']}")
        print(f"  regressions: {best['regressions']}")

    q10_fixable_count = sum(1 for r in results if r["q10_fixed"])
    print(f"[dep7] weight sets that fix q10: {q10_fixable_count}/{len(results)}")

    if not viable_results:
        near_viable = [r for r in results if r["q10_fixed"] and r["regression_count"] <= 2]
        if near_viable:
            near_viable.sort(key=lambda r: r["regression_count"])
            nv = near_viable[0]
            print(f"[dep7] nearest near-viable: regressions={nv['regressions']}")
            print(f"  weights: {nv['weights']}")

    verdict = "gate_candidate_pass" if viable_results else "gate_fail"
    print(f"[dep7] verdict: {verdict}")

    output = {
        "schema_version": "dep7-blend-weight-simulation.v1",
        "run_id": args.run,
        "verdict": verdict,
        "current_weights": CURRENT_WEIGHTS,
        "weight_sets_tested": len(results),
        "q10_fixable_count": q10_fixable_count,
        "viable_count": len(viable_results),
        "best_viable": {
            "weights": best["weights"],
            "improvements": best["improvements"],
            "regressions": best["regressions"],
            "q10_fixed": best["q10_fixed"],
            "per_query": best["per_query"],
        } if best else None,
        "current_baseline": {
            "q10_fixed": current_result["q10_fixed"],
            "regressions": current_result["regressions"],
            "improvements": current_result["improvements"],
        },
        "all_viable_weights": [
            {"weights": r["weights"], "improvements": r["improvements"]}
            for r in viable_results
        ],
        "phase5_gate": "blocked",
        "phase5_note": "A gate_candidate_pass authorizes authoring a Phase 5 ticket for Human review. It does NOT unblock Phase 5 or authorize any src/* edit.",
    }

    out_path = run_dir / "analysis" / "rerank_regression" / "blend_weight_simulation.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[dep7] wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
