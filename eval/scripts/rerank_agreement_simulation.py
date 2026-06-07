"""Dep #9 agreement-bonus simulation.

Recomputes snapshot rankings with fixed production vote/upstream weights and
candidate source-agreement bonuses. Also evaluates q05 against the DECOMP-01
full candidate pools, without model inference or production changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from math import log1p
from pathlib import Path
from typing import Any

CURRENT_WEIGHTS = {
    "rerank_vote_count_weight": 0.08,
    "rerank_upstream_weight": 0.12,
    "rerank_source_agreement_bonus": 0.10,
}
AGREEMENT_VALUES = [0.00, 0.02, 0.05, 0.08, 0.10]
RECOMMENDED_VALUE = 0.02
STRICT_HIT_GRADE_THRESHOLD = 3
Q05_TARGET_TMDB_ID = 144204


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_gold_labels(run_dir: Path) -> dict[tuple[str, int], dict]:
    gold: dict[tuple[str, int], dict] = {}
    for line in (run_dir / "gold_labels.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            gold[(row["qid"], row["tmdb_id"])] = row
    return gold


def source_agreement(movie: dict) -> float:
    return float(
        movie.get("semantic_rank") is not None
        and movie.get("bm25_rank") is not None
    )


def upstream_score(movie: dict) -> float:
    for key in ("rrf_score", "semantic_rrf", "semantic_score", "bm25_score"):
        try:
            value = float(movie.get(key) or 0.0)
        except (TypeError, ValueError):
            continue
        if value:
            return value
    return 0.0


def compute_final_score(
    rerank_score: float,
    quality_prior: float,
    upstream_prior: float,
    agreement: float,
) -> float:
    return (
        rerank_score
        + CURRENT_WEIGHTS["rerank_vote_count_weight"] * quality_prior
        + CURRENT_WEIGHTS["rerank_upstream_weight"] * upstream_prior
        + agreement * 1.0
    )


def recompute_final_scores(
    baseline_top: list[dict],
    pool: list[dict],
    agreement: float,
) -> list[dict]:
    """Re-rank baseline entries using normalization maxima from the full pool."""
    if not baseline_top or not pool:
        return []

    pool_lookup = {row["tmdb_id"]: row for row in pool}
    max_votes = max((int(row.get("vote_count", 0) or 0) for row in pool), default=0)
    max_vote_log = log1p(max_votes) or 1.0
    max_upstream = max((upstream_score(row) for row in pool), default=0.0) or 1.0

    ranked = []
    for entry in baseline_top:
        pool_row = pool_lookup.get(entry["tmdb_id"])
        if pool_row is None:
            continue
        quality_prior = log1p(int(pool_row.get("vote_count", 0) or 0)) / max_vote_log
        upstream_prior = upstream_score(pool_row) / max_upstream
        agreement_input = source_agreement(pool_row)
        final_score = compute_final_score(
            float(entry["rerank_score"]),
            quality_prior,
            upstream_prior,
            agreement * agreement_input,
        )
        ranked.append({
            **entry,
            "quality_prior": quality_prior,
            "upstream_prior": upstream_prior,
            "source_agreement": agreement_input,
            "new_final_score": final_score,
        })

    ranked.sort(key=lambda row: -row["new_final_score"])
    for rank, row in enumerate(ranked):
        row["new_rank"] = rank
    return ranked


def check_strict_hit_at_k(
    ranked_entries: list[dict],
    gold: dict[tuple[str, int], dict],
    qid: str,
    k: int = 5,
) -> bool:
    for entry in ranked_entries[:k]:
        label = gold.get((qid, entry["tmdb_id"]))
        if label is None:
            continue
        grade = label.get("gold_grade")
        if grade is None:
            grade = label.get("grade", 0)
        if grade is not None and grade >= STRICT_HIT_GRADE_THRESHOLD:
            return True
    return False


def classify_change(original_hit: bool, new_hit: bool) -> str:
    if original_hit and not new_hit:
        return "hit_to_miss"
    if not original_hit and new_hit:
        return "miss_to_hit"
    return "unchanged"


def simulate_agreement(
    snapshot: dict,
    gold: dict[tuple[str, int], dict],
    agreement: float,
) -> dict:
    per_query: dict[str, dict[str, Any]] = {}
    regressions: list[str] = []
    improvements: list[str] = []

    for query in snapshot["queries"]:
        qid = query["qid"]
        per_query[qid] = {}
        for mode in ("advanced", "hybrid"):
            mode_data = query["modes"].get(mode, {})
            baseline_top = mode_data.get("baseline_top") or []
            pool = mode_data.get("pool") or []
            if not baseline_top or not pool:
                per_query[qid][mode] = {"error": "missing_data"}
                continue

            current_ranked = recompute_final_scores(
                baseline_top,
                pool,
                CURRENT_WEIGHTS["rerank_source_agreement_bonus"],
            )
            candidate_ranked = recompute_final_scores(baseline_top, pool, agreement)
            original_hit = check_strict_hit_at_k(current_ranked, gold, qid)
            new_hit = check_strict_hit_at_k(candidate_ranked, gold, qid)
            change = classify_change(original_hit, new_hit)
            per_query[qid][mode] = {
                "original_hit": original_hit,
                "new_hit": new_hit,
                "change": change,
            }
            key = f"{qid}/{mode}"
            if change == "hit_to_miss":
                regressions.append(key)
            elif change == "miss_to_hit":
                improvements.append(key)

    return {
        "agreement": agreement,
        "regressions": regressions,
        "improvements": improvements,
        "regression_count": len(regressions),
        "improvement_count": len(improvements),
        "per_query": per_query,
    }


def parse_decomp_pool_row(row: dict, agreement: float) -> dict:
    inputs = row["final_blend"]["inputs"]
    quality_prior = float(inputs["quality_prior"])
    upstream_prior = float(inputs["upstream_prior"])
    agreement_input = float(inputs["source_agreement"])
    return {
        "tmdb_id": row["tmdb_id"],
        "is_target": bool(row.get("is_target")),
        "final_score": compute_final_score(
            float(row["rerank_score"]),
            quality_prior,
            upstream_prior,
            agreement * agreement_input,
        ),
        "quality_prior": quality_prior,
        "upstream_prior": upstream_prior,
        "source_agreement": agreement_input,
    }


def simulate_decomp_pool(rows: list[dict], agreement: float) -> dict:
    ranked = [parse_decomp_pool_row(row, agreement) for row in rows]
    ranked.sort(key=lambda row: -row["final_score"])
    target_rank = next(
        (
            rank
            for rank, row in enumerate(ranked)
            if row["is_target"] or row["tmdb_id"] == Q05_TARGET_TMDB_ID
        ),
        None,
    )
    return {
        "agreement": agreement,
        "target_rank": target_rank,
        "hit": target_rank is not None and target_rank < 5,
    }


def analyze_q05_decomp(decomp: dict) -> dict:
    q05 = next((row for row in decomp["per_qid"] if row["qid"] == "q05"), None)
    if q05 is None:
        raise ValueError("DECOMP data does not contain q05")

    arms: dict[str, dict[str, list[dict]]] = {}
    for arm in ("no_llm", "pinned"):
        arm_data = q05["arms"][arm]
        arms[arm] = {}
        for pool in ("standard", "extended"):
            rows = arm_data[f"{pool}_pool_rows"]
            arms[arm][f"{pool}_pool"] = [
                simulate_decomp_pool(rows, agreement)
                for agreement in AGREEMENT_VALUES
            ]
    return {"agreement_values": AGREEMENT_VALUES, "arms": arms}


def main() -> int:
    parser = argparse.ArgumentParser(description="Dep #9 agreement-bonus simulation")
    parser.add_argument("run_dir", help="Path to an eval run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"ERROR: run directory not found: {run_dir}", file=sys.stderr)
        return 1

    try:
        snapshot = load_json(
            run_dir / "analysis" / "rerank_regression" / "full_set_pool_snapshot.json"
        )
        gold = load_gold_labels(run_dir)
        decomp = load_json(
            run_dir / "analysis" / "decomp" / "q05_q10_pool_decomposition.json"
        )
        results = [simulate_agreement(snapshot, gold, value) for value in AGREEMENT_VALUES]
        q05_analysis = analyze_q05_decomp(decomp)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[dep9] BLOCKED: artifact structure mismatch: {exc}", file=sys.stderr)
        return 1

    recommended = next(row for row in results if row["agreement"] == RECOMMENDED_VALUE)
    output = {
        "schema_version": "dep9-agreement-simulation.v1",
        "run_id": snapshot.get("run_id", run_dir.name),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "current_weights": CURRENT_WEIGHTS,
        "agreement_values_tested": AGREEMENT_VALUES,
        "verdict": "pass" if recommended["regression_count"] == 0 else "fail",
        "recommended_value": RECOMMENDED_VALUE,
        "results": results,
        "q05_decomp_analysis": q05_analysis,
    }
    out_path = run_dir / "analysis" / "rerank_regression" / "agreement_simulation.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    print(f"[dep9] wrote {out_path}")
    print(
        f"[dep9] agreement={RECOMMENDED_VALUE:.2f}: "
        f"regressions={recommended['regression_count']} "
        f"improvements={recommended['improvement_count']}"
    )
    return 0 if output["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
