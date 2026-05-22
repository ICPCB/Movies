"""DECOMP-01 q05/q10 rerank-pool and final-blend decomposition."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import (  # noqa: E402
    _run_io,
    hy_fix_rrf_pool_trace,
    hybrid_expansion_stability,
    hybrid_live_trace,
)
from eval.scripts.hybrid_live_trace import StageRun, Target  # noqa: E402


SCHEMA_VERSION = "decomp-01-q05-q10.v1"
QIDS = ("q05", "q10")
CONTROL_ARMS = ("pinned", "no_llm")
LOCALIZATION_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_localize" / "localization.json"
)
STABILITY_TRACE_RELATIVE_PATH = (
    Path("analysis") / "hybrid_expansion_stability" / "stability_trace.jsonl"
)
STABILITY_DIAGNOSIS_RELATIVE_PATH = (
    Path("analysis") / "hybrid_expansion_stability" / "stability_diagnosis.json"
)
RRF_POOL_TRACE_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_rrf_pool" / "rrf_pool_trace.json"
)
CANDIDATES_RELATIVE_PATH = Path("candidates.jsonl")
OUTPUT_RELATIVE_PATH = (
    Path("analysis") / "decomp" / "q05_q10_pool_decomposition.json"
)
REPORT_PATH = (
    _run_io.PROJECT_ROOT / "docs" / "superpowers" / "reports" / "decomp-01-q05-q10.md"
)

EXPECTED_BUDGET = {
    "expected_cost_usd": 0.0,
    "expected_runtime_seconds": 900,
    "max_extended_pool_depth": 75,
    "max_total_rerank_pairs": 500,
    "max_vram_mib": 7800,
    "expected_ollama_setup": (
        "$env:CUDA_VISIBLE_DEVICES='-1'; "
        "Start-Process -WindowStyle Hidden -FilePath 'ollama' -ArgumentList 'serve'"
    ),
    "expected_python_command": (
        "./venv/Scripts/python.exe -m eval.scripts.decomp_pool_q05_q10 "
        "--run 2026-05-19-1846-nogit"
    ),
}
SAFE_COLLATERAL_LIMITS = {
    "max_non_target_rank_changes": 5,
    "max_non_target_rank_change_magnitude": 10,
    "max_top5_churn": 0,
}


class DecompPoolError(ValueError):
    """Raised when DECOMP-01 cannot safely produce gate evidence."""


def run(
    *,
    run_id: Optional[str] = None,
    dry_run: bool = False,
) -> tuple[str, Optional[Path], Optional[Path], Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    inputs = _load_inputs(actual_run_id)
    plan = _trace_plan(inputs)
    target_depth = _global_extended_depth(plan, inputs["config"])
    expected_pairs = _expected_rerank_pairs(target_depth, inputs["config"])
    _check_pool_budget(target_depth, expected_pairs)

    if dry_run:
        return (
            actual_run_id,
            None,
            None,
            _dry_run_summary(actual_run_id, plan, target_depth, expected_pairs),
        )

    start = time.monotonic()
    vram_observations: list[Dict[str, Any]] = []
    _record_vram(vram_observations, "before_run")
    per_qid = []
    for qid_row in plan:
        arms: Dict[str, Any] = {}
        for arm in CONTROL_ARMS:
            _check_runtime_budget(start)
            _record_vram(vram_observations, f"before_{qid_row['qid']}_{arm}")
            arms[arm] = _run_arm_decomposition(
                qid_row=qid_row,
                arm=arm,
                target_depth=target_depth,
                config=inputs["config"],
            )
            _record_vram(vram_observations, f"after_{qid_row['qid']}_{arm}")
            _check_runtime_budget(start)
        per_qid.append(
            {
                "qid": qid_row["qid"],
                "tmdb_id": qid_row["tmdb_id"],
                "title": qid_row["title"],
                "movie_key": qid_row["movie_key"],
                "arms": arms,
            }
        )

    actual_runtime = time.monotonic() - start
    policy_analysis = _evaluate_policies(per_qid, inputs["config"])
    decision = _decision(policy_analysis)
    data = _build_artifact(
        run_id=actual_run_id,
        inputs=inputs,
        per_qid=per_qid,
        target_depth=target_depth,
        expected_pairs=expected_pairs,
        vram_observations=vram_observations,
        actual_runtime=actual_runtime,
        policy_analysis=policy_analysis,
        decision=decision,
    )

    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_io._atomic_write_json(output_path, data)
    _write_report(REPORT_PATH, data)
    return actual_run_id, output_path, REPORT_PATH, data


def _load_inputs(run_id: str) -> Dict[str, Any]:
    run_path = _run_io.run_dir(run_id)
    paths = {
        "localization": run_path / LOCALIZATION_RELATIVE_PATH,
        "stability_trace": run_path / STABILITY_TRACE_RELATIVE_PATH,
        "stability_diagnosis": run_path / STABILITY_DIAGNOSIS_RELATIVE_PATH,
        "rrf_pool_trace": run_path / RRF_POOL_TRACE_RELATIVE_PATH,
        "candidates": run_path / CANDIDATES_RELATIVE_PATH,
        "queries": _run_io.EVAL_DIR / "queries" / "v1.jsonl",
    }
    missing = [path for path in paths.values() if not path.exists()]
    if missing:
        raise DecompPoolError(
            "required input file missing: " + ", ".join(str(path) for path in missing)
        )
    diagnosis = _read_json_object(paths["stability_diagnosis"])
    return {
        "run_path": run_path,
        "localization": _read_json_object(paths["localization"]),
        "stability_trace": _read_jsonl_objects(paths["stability_trace"]),
        "stability_diagnosis": diagnosis,
        "rrf_pool_trace_present": True,
        "candidates_present": True,
        "queries": _read_queries(paths["queries"]),
        "config": _config_from_diagnosis(diagnosis),
    }


def _trace_plan(inputs: Mapping[str, Any]) -> list[Dict[str, Any]]:
    localization_by_qid = _localization_by_qid(inputs["localization"])
    trace_rows = inputs["stability_trace"]
    queries = inputs["queries"]
    plan: list[Dict[str, Any]] = []

    for qid in QIDS:
        localized = localization_by_qid.get(qid)
        if localized is None:
            raise DecompPoolError(f"localization.json missing {qid}")
        tmdb_id = int(localized["tmdb_id"])
        if qid not in queries:
            raise DecompPoolError(f"queries file missing {qid}")
        arms: Dict[str, Any] = {}
        movie_key: Optional[str] = None
        for arm in CONTROL_ARMS:
            rows = hy_fix_rrf_pool_trace._trace_rows_for(trace_rows, qid, tmdb_id, arm)
            arm_plan = hy_fix_rrf_pool_trace._recorded_arm_queries(qid, arm, rows)
            arm_stage = localized.get("arms", {}).get(arm, {}).get("stage_table", {})
            arm_plan["recorded_loss_stage"] = localized.get("arms", {}).get(
                arm, {}
            ).get("loss_stage")
            arm_plan["recorded_stage_table"] = _json_clone(arm_stage)
            arms[arm] = arm_plan
            movie_key = movie_key or str(arm_plan["movie_key"])
        plan.append(
            {
                "qid": qid,
                "tmdb_id": tmdb_id,
                "title": str(localized["title"]),
                "movie_key": movie_key,
                "raw_query": queries[qid],
                "arms": arms,
            }
        )
    return plan


def _run_arm_decomposition(
    *,
    qid_row: Mapping[str, Any],
    arm: str,
    target_depth: int,
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    arm_plan = qid_row["arms"][arm]
    standard_stage = hybrid_expansion_stability.run_stages(
        raw_query=str(qid_row["raw_query"]),
        retrieval_query=str(arm_plan["retrieval_query"]),
        rerank_query=str(arm_plan["rerank_query"]),
    )
    target = _target_from_plan(qid_row)
    standard_table = _target_stage_table(standard_stage, target)
    _assert_reproduced(qid_row=qid_row, arm=arm, arm_plan=arm_plan, table=standard_table)

    extended_stage = _extended_stage_run(standard_stage, target_depth)
    extended_rows = build_pool_rows(
        stage_run=extended_stage,
        target=target,
        pool_depth=target_depth,
        formula_weights=_formula_weights(config),
    )
    standard_rows = build_pool_rows(
        stage_run=standard_stage,
        target=target,
        pool_depth=int(config["RERANK_TOP_K"]),
        formula_weights=_formula_weights(config),
    )
    decomposed = hybrid_expansion_stability._decompose_pool(
        scored_pool=extended_stage.scored_pool,
        target=target,
    )
    target_row = _row_by_key(extended_rows, str(qid_row["movie_key"]))
    cutoff_depth = int(config["RERANK_TOP_K"])
    target_rrf_rank = target_row["rrf_rank"] if target_row is not None else None
    return {
        "retrieval_query": arm_plan["retrieval_query"],
        "rerank_query": arm_plan["rerank_query"],
        "recorded_loss_stage": arm_plan["recorded_loss_stage"],
        "recorded_target_rrf_rank": arm_plan["recorded_rrf_rank"],
        "reproduced_standard_stage_table": standard_table,
        "reproduced_matches_recorded": True,
        "standard_rerank_top_k": cutoff_depth,
        "extended_rerank_top_k": target_depth,
        "target_captured_through_rrf_rank": (
            target_rrf_rank is not None and target_rrf_rank < target_depth
        ),
        "cutoff": {
            "standard_rerank_top_k": cutoff_depth,
            "extended_rerank_top_k": target_depth,
            "last_standard_pool_entry": _entry_at(extended_stage.rrf, cutoff_depth - 1),
            "first_extended_entry": _entry_at(extended_stage.rrf, cutoff_depth),
            "target_rrf_rank": target_rrf_rank,
            "target_ranks_below_standard_cutoff": (
                target_rrf_rank - (cutoff_depth - 1)
                if isinstance(target_rrf_rank, int)
                else None
            ),
        },
        "source_mix": {
            "standard_pool": hy_fix_rrf_pool_trace._source_mix(
                _rrf_entries(extended_stage.rrf[:cutoff_depth])
            ),
            "extended_pool": hy_fix_rrf_pool_trace._source_mix(
                _rrf_entries(extended_stage.rrf[:target_depth])
            ),
        },
        "target_decomposition": {
            "target_in_pool": decomposed["target_in_pool"],
            "target": decomposed["target"],
            "leapfrog_count": decomposed["leapfrog_count"],
            "leapfrog_competitors": decomposed["leapfrog_competitors"],
        },
        "standard_pool_rows": standard_rows,
        "extended_pool_rows": extended_rows,
    }


def _extended_stage_run(stage_run: StageRun, target_depth: int) -> StageRun:
    hybrid_expansion_stability._require_live_imports()
    scored = hybrid_live_trace.rerank(
        stage_run.rerank_query,
        list(stage_run.rrf),
        top_k=target_depth,
        rerank_pool=target_depth,
    )
    return StageRun(
        retrieval_query=stage_run.retrieval_query,
        rerank_query=stage_run.rerank_query,
        filters=stage_run.filters,
        semantic=stage_run.semantic,
        bm25=stage_run.bm25,
        rrf=stage_run.rrf,
        scored_pool=tuple(dict(movie) for movie in scored),
    )


def build_pool_rows(
    *,
    stage_run: StageRun,
    target: Target,
    pool_depth: int,
    formula_weights: Mapping[str, float],
) -> list[Dict[str, Any]]:
    """Build full score rows for every scored member of a rerank pool."""
    semantic = _stage_index(stage_run.semantic, "semantic_score")
    bm25 = _stage_index(stage_run.bm25, "bm25_score")
    rrf = _stage_index(stage_run.rrf, "rrf_score")
    scored_by_key = {
        _movie_key(movie): movie
        for movie in stage_run.scored_pool
    }
    rerank_ranks, final_ranks = hybrid_expansion_stability._rank_maps(
        stage_run.scored_pool
    )
    rerank_rank_by_key = {
        _movie_key(movie): rerank_ranks[index]
        for index, movie in enumerate(stage_run.scored_pool)
    }
    final_rank_by_key = {
        _movie_key(movie): final_ranks[index]
        for index, movie in enumerate(stage_run.scored_pool)
    }

    rows: list[Dict[str, Any]] = []
    for rrf_rank, rrf_movie in enumerate(stage_run.rrf[:pool_depth]):
        key = _movie_key(rrf_movie)
        scored = scored_by_key.get(key)
        if scored is None:
            raise DecompPoolError(
                f"{target.qid}: scored pool missing RRF member at rank {rrf_rank}: {key}"
            )
        inputs = {
            "rerank_score": _required_float(scored, "rerank_score"),
            "quality_prior": _required_float(scored, "quality_prior"),
            "upstream_prior": _required_float(scored, "upstream_prior"),
            "source_agreement": _required_float(scored, "source_agreement"),
        }
        contributions = {
            "rerank_score": inputs["rerank_score"],
            "quality_prior": (
                formula_weights["quality_prior"] * inputs["quality_prior"]
            ),
            "upstream_prior": (
                formula_weights["upstream_prior"] * inputs["upstream_prior"]
            ),
            "source_agreement": (
                formula_weights["source_agreement"] * inputs["source_agreement"]
            ),
        }
        final_score = _required_float(scored, "final_score")
        contribution_total = sum(contributions.values())
        if abs(contribution_total - final_score) > 1e-6:
            raise DecompPoolError(
                f"{target.qid}: final blend mismatch for {key}: "
                f"{contribution_total} != {final_score}"
            )
        sem = semantic.get(key, {})
        bm = bm25.get(key, {})
        rrf_data = rrf.get(key, {})
        rows.append(
            {
                "pool_rank": rrf_rank,
                "rrf_rank": rrf_rank,
                "movie_key": key,
                "tmdb_id": _coerce_int(scored.get("id")),
                "title": str(scored.get("title", "")),
                "year": scored.get("year"),
                "is_target": key == target.movie_key,
                "semantic_rank": sem.get("rank"),
                "semantic_score": sem.get("score"),
                "bm25_rank": bm.get("rank"),
                "bm25_score": bm.get("score"),
                "rrf_score": rrf_data.get("score"),
                "rerank_score": inputs["rerank_score"],
                "rerank_rank": rerank_rank_by_key[key],
                "final_score": final_score,
                "final_rank": final_rank_by_key[key],
                "final_blend": {
                    "formula": (
                        "final_score = rerank_score + "
                        "quality_prior_weight*quality_prior + "
                        "upstream_prior_weight*upstream_prior + "
                        "source_agreement_weight*source_agreement"
                    ),
                    "inputs": inputs,
                    "weights": dict(formula_weights),
                    "contributions": contributions,
                },
            }
        )
    return rows


def _evaluate_policies(
    per_qid: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    current = _formula_weights(config)
    blend_candidates = [
        {
            "id": "rerank_only",
            "weights": {
                "quality_prior": 0.0,
                "upstream_prior": 0.0,
                "source_agreement": 0.0,
            },
        },
        {
            "id": "half_priors",
            "weights": {
                "quality_prior": current["quality_prior"] / 2.0,
                "upstream_prior": current["upstream_prior"] / 2.0,
                "source_agreement": current["source_agreement"] / 2.0,
            },
        },
        {
            "id": "remove_quality_prior",
            "weights": {
                "quality_prior": 0.0,
                "upstream_prior": current["upstream_prior"],
                "source_agreement": current["source_agreement"],
            },
        },
        {
            "id": "remove_upstream_prior",
            "weights": {
                "quality_prior": current["quality_prior"],
                "upstream_prior": 0.0,
                "source_agreement": current["source_agreement"],
            },
        },
        {
            "id": "remove_source_agreement",
            "weights": {
                "quality_prior": current["quality_prior"],
                "upstream_prior": current["upstream_prior"],
                "source_agreement": 0.0,
            },
        },
    ]
    policies: list[Dict[str, Any]] = [
        _policy_result(
            policy_id="rerank_cutoff_67_current_blend",
            policy_type="rerank_cutoff_increase",
            per_qid=per_qid,
            use_extended_pool=True,
            weights=current,
        )
    ]
    for candidate in blend_candidates:
        weights = candidate["weights"]
        policies.append(
            _policy_result(
                policy_id=f"final_blend_{candidate['id']}_standard_cutoff",
                policy_type="final_blend_reweight",
                per_qid=per_qid,
                use_extended_pool=False,
                weights=weights,
            )
        )
        policies.append(
            _policy_result(
                policy_id=f"cutoff_67_plus_final_blend_{candidate['id']}",
                policy_type="rerank_cutoff_increase_plus_final_blend_reweight",
                per_qid=per_qid,
                use_extended_pool=True,
                weights=weights,
            )
        )

    all_rescuing = [
        policy for policy in policies if policy["all_targets_rescued"]
    ]
    safe = [
        policy for policy in all_rescuing if policy["collateral_within_limits"]
    ]
    return {
        "safe_collateral_limits": dict(SAFE_COLLATERAL_LIMITS),
        "policy_count": len(policies),
        "policies": policies,
        "all_targets_rescued_policy_ids": [
            policy["policy_id"] for policy in all_rescuing
        ],
        "safe_policy_ids": [policy["policy_id"] for policy in safe],
        "recommended_policy": safe[0]["policy_id"] if safe else None,
    }


def _policy_result(
    *,
    policy_id: str,
    policy_type: str,
    per_qid: Sequence[Mapping[str, Any]],
    use_extended_pool: bool,
    weights: Mapping[str, float],
) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    all_rescued = True
    max_changed = 0
    max_magnitude = 0
    max_top5_churn = 0
    for qid_row in per_qid:
        qid = str(qid_row["qid"])
        target_key = str(qid_row["movie_key"])
        results[qid] = {}
        for arm in CONTROL_ARMS:
            arm_data = qid_row["arms"][arm]
            baseline_rows = arm_data["standard_pool_rows"]
            policy_source_rows = (
                arm_data["extended_pool_rows"]
                if use_extended_pool
                else arm_data["standard_pool_rows"]
            )
            policy_rows = reweight_rows(policy_source_rows, weights)
            rescued = target_rescued(policy_rows, target_key)
            collateral = collateral_impact(
                rank_rows(baseline_rows),
                policy_rows,
                target_key=target_key,
            )
            all_rescued = all_rescued and rescued
            max_changed = max(
                max_changed,
                int(collateral["non_target_rank_changes_count"]),
            )
            max_magnitude = max(
                max_magnitude,
                int(collateral["non_target_rank_change_magnitude"]),
            )
            max_top5_churn = max(max_top5_churn, int(collateral["top5_churn_count"]))
            results[qid][arm] = {
                "target_rescued": rescued,
                "target_policy_rank": _rank_for(policy_rows, target_key),
                "target_baseline_rank": _rank_for(rank_rows(baseline_rows), target_key),
                "collateral": collateral,
            }

    within_limits = (
        max_changed <= SAFE_COLLATERAL_LIMITS["max_non_target_rank_changes"]
        and max_magnitude
        <= SAFE_COLLATERAL_LIMITS["max_non_target_rank_change_magnitude"]
        and max_top5_churn <= SAFE_COLLATERAL_LIMITS["max_top5_churn"]
    )
    return {
        "policy_id": policy_id,
        "policy_type": policy_type,
        "pool": "extended_67" if use_extended_pool else "standard_50",
        "weights": {
            "rerank_score": 1.0,
            "quality_prior": weights["quality_prior"],
            "upstream_prior": weights["upstream_prior"],
            "source_agreement": weights["source_agreement"],
        },
        "per_qid_arm": results,
        "all_targets_rescued": all_rescued,
        "max_non_target_rank_changes_count": max_changed,
        "max_non_target_rank_change_magnitude": max_magnitude,
        "max_top5_churn_count": max_top5_churn,
        "collateral_within_limits": within_limits,
        "safe_localized_fix_candidate": all_rescued and within_limits,
    }


def reweight_rows(
    rows: Sequence[Mapping[str, Any]],
    weights: Mapping[str, float],
) -> list[Dict[str, Any]]:
    ranked: list[Dict[str, Any]] = []
    for row in rows:
        inputs = row["final_blend"]["inputs"]
        policy_score = (
            float(inputs["rerank_score"])
            + float(weights["quality_prior"]) * float(inputs["quality_prior"])
            + float(weights["upstream_prior"]) * float(inputs["upstream_prior"])
            + float(weights["source_agreement"]) * float(inputs["source_agreement"])
        )
        ranked.append(
            {
                "movie_key": row["movie_key"],
                "title": row.get("title"),
                "is_target": row.get("is_target"),
                "policy_final_score": policy_score,
            }
        )
    ranked.sort(
        key=lambda row: (
            -float(row["policy_final_score"]),
            str(row["movie_key"]),
        )
    )
    for rank, row in enumerate(ranked):
        row["policy_final_rank"] = rank
    return ranked


def rank_rows(rows: Sequence[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    ranked = [
        {
            "movie_key": row["movie_key"],
            "title": row.get("title"),
            "is_target": row.get("is_target"),
            "policy_final_score": row["final_score"],
            "policy_final_rank": row["final_rank"],
        }
        for row in rows
    ]
    ranked.sort(key=lambda row: int(row["policy_final_rank"]))
    return ranked


def target_rescued(
    policy_rows: Sequence[Mapping[str, Any]],
    target_key: str,
    final_top_k: int = 5,
) -> bool:
    rank = _rank_for(policy_rows, target_key)
    return rank is not None and rank < final_top_k


def collateral_impact(
    baseline_rows: Sequence[Mapping[str, Any]],
    policy_rows: Sequence[Mapping[str, Any]],
    *,
    target_key: str,
    final_top_k: int = 5,
) -> Dict[str, Any]:
    baseline = _rank_map(baseline_rows)
    policy = _rank_map(policy_rows)
    common_non_targets = sorted((set(baseline) & set(policy)) - {target_key})
    changed: list[Dict[str, Any]] = []
    for key in common_non_targets:
        before = baseline[key]
        after = policy[key]
        if before != after:
            changed.append(
                {
                    "movie_key": key,
                    "baseline_rank": before,
                    "policy_rank": after,
                    "rank_delta": after - before,
                    "abs_rank_delta": abs(after - before),
                }
            )
    baseline_top5 = {key for key, rank in baseline.items() if rank < final_top_k}
    policy_top5 = {key for key, rank in policy.items() if rank < final_top_k}
    baseline_top5.discard(target_key)
    policy_top5.discard(target_key)
    top5_removed = sorted(baseline_top5 - policy_top5)
    top5_added = sorted(policy_top5 - baseline_top5)
    return {
        "rank_basis": "common non-target candidates in baseline vs policy pool",
        "common_non_target_count": len(common_non_targets),
        "non_target_rank_changes_count": len(changed),
        "non_target_rank_change_magnitude": sum(
            int(row["abs_rank_delta"]) for row in changed
        ),
        "max_abs_non_target_rank_change": max(
            (int(row["abs_rank_delta"]) for row in changed),
            default=0,
        ),
        "changed_non_targets": changed,
        "policy_only_non_target_count": len(set(policy) - set(baseline) - {target_key}),
        "baseline_only_non_target_count": len(
            set(baseline) - set(policy) - {target_key}
        ),
        "top5_removed_non_targets": top5_removed,
        "top5_added_non_targets": top5_added,
        "top5_churn_count": len(top5_removed) + len(top5_added),
    }


def _decision(policy_analysis: Mapping[str, Any]) -> Dict[str, Any]:
    recommended = policy_analysis.get("recommended_policy")
    if recommended:
        return {
            "status": "safe_localized_fix_proven",
            "exact_bounded_change": recommended,
            "exact_allowed_src_file": "src/config.py",
            "measured_collateral_impact": _recommended_collateral(
                policy_analysis, str(recommended)
            ),
            "phase5_gate": "may_consider_unblocking_after_DECOMP-01-review",
        }
    if policy_analysis.get("all_targets_rescued_policy_ids"):
        return {
            "status": "safe_localized_fix_ruled_out",
            "reason": (
                "Some evaluated policies rescued all q05/q10 deterministic arms, "
                "but their non-target rank collateral exceeded the recorded safe "
                "limits."
            ),
            "phase5_gate": "blocked",
        }
    return {
        "status": "safe_localized_fix_ruled_out",
        "reason": (
            "No evaluated bounded rerank-cutoff or final-blend reweight policy "
            "rescued q05 and q10 across both pinned and no_llm deterministic arms."
        ),
        "phase5_gate": "blocked",
    }


def _build_artifact(
    *,
    run_id: str,
    inputs: Mapping[str, Any],
    per_qid: Sequence[Mapping[str, Any]],
    target_depth: int,
    expected_pairs: int,
    vram_observations: Sequence[Mapping[str, Any]],
    actual_runtime: float,
    policy_analysis: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> Dict[str, Any]:
    trace_meta = inputs["stability_diagnosis"].get("trace_meta", {})
    max_vram = max(
        (
            int(row["used_mib"])
            for row in vram_observations
            if row.get("used_mib") is not None
        ),
        default=None,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "source_artifacts": {
            "localization": str(LOCALIZATION_RELATIVE_PATH).replace("\\", "/"),
            "stability_trace": str(STABILITY_TRACE_RELATIVE_PATH).replace("\\", "/"),
            "stability_diagnosis": str(STABILITY_DIAGNOSIS_RELATIVE_PATH).replace(
                "\\",
                "/",
            ),
            "rrf_pool_trace": str(RRF_POOL_TRACE_RELATIVE_PATH).replace("\\", "/"),
            "candidates": str(CANDIDATES_RELATIVE_PATH).replace("\\", "/"),
        },
        "run_accounting": {
            "expected": {
                **EXPECTED_BUDGET,
                "extended_pool_depth": target_depth,
                "expected_total_rerank_pairs": expected_pairs,
            },
            "actual": {
                "actual_cost_usd": 0.0,
                "actual_runtime_seconds": round(actual_runtime, 3),
                "actual_python_executable": sys.executable,
                "actual_python_argv": list(sys.argv),
                "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "max_observed_vram_mib": max_vram,
                "vram_observations": list(vram_observations),
            },
        },
        "trace_meta": {
            "embedding_model": trace_meta.get("embedding_model"),
            "reranker_model": trace_meta.get("reranker_model"),
            "llm_model": trace_meta.get("llm_model"),
            "config": _json_clone(inputs["config"]),
            "qids": list(QIDS),
            "arms": list(CONTROL_ARMS),
            "standard_rerank_top_k": int(inputs["config"]["RERANK_TOP_K"]),
            "extended_rerank_top_k": target_depth,
            "llm_call_note": (
                "Pinned and no_llm deterministic arm queries are reused from "
                "HY-STAB-01 trace rows; DECOMP-01 does not call expand_query."
            ),
        },
        "final_blend_formula": {
            "formula": (
                "final_score = rerank_score + "
                "RERANK_VOTE_COUNT_WEIGHT*quality_prior + "
                "RERANK_UPSTREAM_WEIGHT*upstream_prior + "
                "RERANK_SOURCE_AGREEMENT_BONUS*source_agreement"
            ),
            "weights": _formula_weights(inputs["config"]),
        },
        "per_qid": list(per_qid),
        "policy_analysis": _json_clone(policy_analysis),
        "decision": _json_clone(decision),
    }


def _write_report(path: Path, data: Mapping[str, Any]) -> None:
    decision = data["decision"]
    policies = data["policy_analysis"]["policies"]
    lines = [
        "# DECOMP-01 q05/q10 Pool Decomposition",
        "",
        f"Timestamp: {data['generated_at']}",
        f"Run: `{data['run_id']}`",
        "Ticket: DECOMP-01",
        "Scope: eval/report only; no `src/*` edits.",
        "",
        "## Method",
        "",
        (
            "The runner reused recorded HY-STAB deterministic arm queries for "
            "`pinned` and `no_llm`, reran the current 50-candidate baseline, "
            "then reran an extended 67-candidate rerank pool for q05 and q10."
        ),
        (
            "Each extended pool row records semantic, BM25, RRF, rerank, final "
            "scores, and the final-blend inputs, weights, and contributions."
        ),
        "",
        "## Cost And Time",
        "",
        f"- Expected cost: ${data['run_accounting']['expected']['expected_cost_usd']:.2f}.",
        (
            "- Expected runtime budget: "
            f"{data['run_accounting']['expected']['expected_runtime_seconds']}s; "
            "expected total rerank pairs: "
            f"{data['run_accounting']['expected']['expected_total_rerank_pairs']}."
        ),
        (
            "- Actual cost: "
            f"${data['run_accounting']['actual']['actual_cost_usd']:.2f}; "
            "actual runtime: "
            f"{data['run_accounting']['actual']['actual_runtime_seconds']}s."
        ),
        (
            "- Max observed VRAM: "
            f"{data['run_accounting']['actual']['max_observed_vram_mib']} MiB "
            f"(budget {data['run_accounting']['expected']['max_vram_mib']} MiB)."
        ),
        "",
        "## Policy Results",
        "",
        "| Policy | All Targets Rescued | Max Non-target Changes | Max Rank-change Magnitude | Safe |",
        "|---|---:|---:|---:|---:|",
    ]
    for policy in policies:
        lines.append(
            "| "
            f"`{policy['policy_id']}` | "
            f"{policy['all_targets_rescued']} | "
            f"{policy['max_non_target_rank_changes_count']} | "
            f"{policy['max_non_target_rank_change_magnitude']} | "
            f"{policy['safe_localized_fix_candidate']} |"
        )

    lines.extend(
        [
            "",
            "## Phase 5 Gate",
            "",
            (
                "Phase 5 remains blocked."
                if decision["phase5_gate"] == "blocked"
                else "Phase 5 may be considered for unblocking after DECOMP-01 review."
            ),
            decision.get("reason", ""),
            "",
            "## Decision",
            "",
            str(decision["status"]),
        ]
    )
    _run_io._atomic_write_text(path, "\n".join(lines).rstrip() + "\n")


def _target_stage_table(stage_run: StageRun, target: Target) -> Dict[str, Any]:
    rerank_data, final_data = hybrid_live_trace._rerank_capture(
        stage_run.scored_pool,
        target,
    )
    record = {
        "semantic": hybrid_live_trace._stage_presence(
            stage_run.semantic,
            target,
            "semantic_score",
        ),
        "bm25": hybrid_live_trace._stage_presence(
            stage_run.bm25,
            target,
            "bm25_score",
        ),
        "rrf": hybrid_live_trace._stage_presence(
            stage_run.rrf,
            target,
            "rrf_score",
        ),
        "rerank": rerank_data,
        "final": final_data,
    }
    classify_record = {
        **record,
        "loss_classification": None,
    }
    record["loss_classification"] = hybrid_live_trace.classify_loss(classify_record)
    return record


def _assert_reproduced(
    *,
    qid_row: Mapping[str, Any],
    arm: str,
    arm_plan: Mapping[str, Any],
    table: Mapping[str, Any],
) -> None:
    checks = (
        ("semantic", "rank"),
        ("bm25", "rank"),
        ("rrf", "rank"),
        ("rerank", "rerank_rank"),
        ("final", "final_rank"),
    )
    recorded = arm_plan["recorded_stage_table"]
    mismatches = []
    for section, field in checks:
        expected = _nested(recorded, section, field)
        actual = _nested(table, section, field)
        if expected != actual:
            mismatches.append(f"{section}.{field}: recorded={expected} actual={actual}")
    expected_loss = arm_plan.get("recorded_loss_stage")
    if expected_loss != table.get("loss_classification"):
        mismatches.append(
            "loss_classification: "
            f"recorded={expected_loss} actual={table.get('loss_classification')}"
        )
    if mismatches:
        raise DecompPoolError(
            f"{qid_row['qid']} {arm} deterministic arm diverged from HY-STAB: "
            + "; ".join(mismatches)
        )


def _stage_index(
    movies: Sequence[Mapping[str, Any]],
    score_key: str,
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for rank, movie in enumerate(movies):
        result[_movie_key(movie)] = {
            "rank": rank,
            "score": _coerce_float(movie.get(score_key)),
        }
    return result


def _global_extended_depth(
    plan: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> int:
    standard = int(config["RERANK_TOP_K"])
    target_depth = standard
    for qid_row in plan:
        for arm in CONTROL_ARMS:
            rank = qid_row["arms"][arm].get("recorded_rrf_rank")
            if isinstance(rank, int):
                target_depth = max(target_depth, rank + 1)
    return target_depth


def _expected_rerank_pairs(target_depth: int, config: Mapping[str, Any]) -> int:
    standard = int(config["RERANK_TOP_K"])
    return len(QIDS) * len(CONTROL_ARMS) * (standard + target_depth)


def _check_pool_budget(target_depth: int, expected_pairs: int) -> None:
    if target_depth > int(EXPECTED_BUDGET["max_extended_pool_depth"]):
        raise DecompPoolError(
            "extended pool depth exceeds recorded budget: "
            f"{target_depth} > {EXPECTED_BUDGET['max_extended_pool_depth']}"
        )
    if expected_pairs > int(EXPECTED_BUDGET["max_total_rerank_pairs"]):
        raise DecompPoolError(
            "rerank pair count exceeds recorded budget: "
            f"{expected_pairs} > {EXPECTED_BUDGET['max_total_rerank_pairs']}"
        )


def _check_runtime_budget(start: float) -> None:
    elapsed = time.monotonic() - start
    if elapsed > float(EXPECTED_BUDGET["expected_runtime_seconds"]):
        raise DecompPoolError(
            "runtime exceeded recorded budget: "
            f"{elapsed:.1f}s > {EXPECTED_BUDGET['expected_runtime_seconds']}s"
        )


def _record_vram(observations: list[Dict[str, Any]], label: str) -> None:
    observation = _query_vram()
    observation["label"] = label
    observation["observed_at"] = _utc_timestamp()
    observations.append(observation)
    used = observation.get("used_mib")
    if used is not None and int(used) > int(EXPECTED_BUDGET["max_vram_mib"]):
        raise DecompPoolError(
            "VRAM exceeded recorded budget: "
            f"{used} MiB > {EXPECTED_BUDGET['max_vram_mib']} MiB"
        )


def _query_vram() -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "total_mib": None,
            "used_mib": None,
            "error": str(exc),
        }
    first_line = completed.stdout.strip().splitlines()[0].strip()
    total_text, used_text = [part.strip() for part in first_line.split(",", 1)]
    return {
        "available": True,
        "total_mib": int(total_text),
        "used_mib": int(used_text),
        "error": None,
    }


def _config_from_diagnosis(diagnosis: Mapping[str, Any]) -> Dict[str, Any]:
    source = diagnosis.get("trace_meta", {}).get("config")
    if not isinstance(source, dict):
        raise DecompPoolError("stability_diagnosis missing trace_meta.config")
    required = (
        "CANDIDATE_POOL",
        "RERANK_POOL",
        "RERANK_TOP_K",
        "FINAL_TOP_K",
        "RRF_K",
        "SEMANTIC_WEIGHT",
        "BM25_WEIGHT",
        "RERANK_VOTE_COUNT_WEIGHT",
        "RERANK_UPSTREAM_WEIGHT",
        "RERANK_SOURCE_AGREEMENT_BONUS",
    )
    missing = [key for key in required if key not in source]
    if missing:
        raise DecompPoolError(
            "stability_diagnosis config missing: " + ", ".join(missing)
        )
    return {key: _json_clone(source[key]) for key in required}


def _formula_weights(config: Mapping[str, Any]) -> Dict[str, float]:
    return {
        "quality_prior": float(config["RERANK_VOTE_COUNT_WEIGHT"]),
        "upstream_prior": float(config["RERANK_UPSTREAM_WEIGHT"]),
        "source_agreement": float(config["RERANK_SOURCE_AGREEMENT_BONUS"]),
    }


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise DecompPoolError(f"{path}: JSON root must be an object")
    return data


def _read_jsonl_objects(path: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            data = json.loads(text)
            if not isinstance(data, dict):
                raise DecompPoolError(f"{path}:{line_number}: row must be object")
            rows.append(data)
    return rows


def _read_queries(path: Path) -> Dict[str, str]:
    queries: Dict[str, str] = {}
    for row in _read_jsonl_objects(path):
        if "qid" not in row or "query" not in row:
            raise DecompPoolError(f"{path}: query row missing qid or query")
        queries[str(row["qid"])] = str(row["query"])
    return queries


def _localization_by_qid(localization: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    rows = localization.get("per_target")
    if not isinstance(rows, list):
        raise DecompPoolError("localization.json missing per_target list")
    return {
        str(row["qid"]): row
        for row in rows
        if isinstance(row, dict) and row.get("qid") in QIDS
    }


def _target_from_plan(qid_row: Mapping[str, Any]) -> Target:
    return Target(
        qid=str(qid_row["qid"]),
        tmdb_id=int(qid_row["tmdb_id"]),
        title=str(qid_row["title"]),
        year="",
        release_date="",
        movie_key=str(qid_row["movie_key"]),
    )


def _entry_at(
    movies: Sequence[Mapping[str, Any]],
    rank: int,
) -> Optional[Dict[str, Any]]:
    if rank < 0 or rank >= len(movies):
        return None
    return hy_fix_rrf_pool_trace._fused_entry(movies[rank], rank)


def _rrf_entries(movies: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    return [
        hy_fix_rrf_pool_trace._fused_entry(movie, rank)
        for rank, movie in enumerate(movies)
    ]


def _row_by_key(
    rows: Sequence[Mapping[str, Any]],
    movie_key: str,
) -> Optional[Mapping[str, Any]]:
    for row in rows:
        if row.get("movie_key") == movie_key:
            return row
    return None


def _rank_map(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    return {
        str(row["movie_key"]): int(row["policy_final_rank"])
        for row in rows
    }


def _rank_for(
    rows: Sequence[Mapping[str, Any]],
    movie_key: str,
) -> Optional[int]:
    for row in rows:
        if row.get("movie_key") == movie_key:
            return int(row["policy_final_rank"])
    return None


def _recommended_collateral(
    policy_analysis: Mapping[str, Any],
    policy_id: str,
) -> Dict[str, Any]:
    for policy in policy_analysis["policies"]:
        if policy["policy_id"] == policy_id:
            return {
                "max_non_target_rank_changes_count": policy[
                    "max_non_target_rank_changes_count"
                ],
                "max_non_target_rank_change_magnitude": policy[
                    "max_non_target_rank_change_magnitude"
                ],
                "max_top5_churn_count": policy["max_top5_churn_count"],
            }
    raise DecompPoolError(f"recommended policy missing: {policy_id}")


def _nested(data: Mapping[str, Any], section: str, field: str) -> Any:
    value = data.get(section)
    if isinstance(value, dict):
        return value.get(field)
    return None


def _movie_key(movie: Mapping[str, Any]) -> str:
    value = movie.get("movie_key")
    if value:
        return str(value)
    return hybrid_live_trace.get_movie_key(dict(movie))


def _required_float(movie: Mapping[str, Any], key: str) -> float:
    if key not in movie:
        raise DecompPoolError(f"{movie.get('title', '<unknown>')}: missing {key}")
    try:
        return float(movie[key])
    except (TypeError, ValueError) as exc:
        raise DecompPoolError(
            f"{movie.get('title', '<unknown>')}: {key} must be numeric"
        ) from exc


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _dry_run_summary(
    run_id: str,
    plan: Sequence[Mapping[str, Any]],
    target_depth: int,
    expected_pairs: int,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "qids": list(QIDS),
        "arms": list(CONTROL_ARMS),
        "extended_pool_depth": target_depth,
        "expected_total_rerank_pairs": expected_pairs,
        "targets": [
            {
                "qid": row["qid"],
                "tmdb_id": row["tmdb_id"],
                "title": row["title"],
                "movie_key": row["movie_key"],
                "recorded_rrf_ranks": {
                    arm: row["arms"][arm]["recorded_rrf_rank"]
                    for arm in CONTROL_ARMS
                },
            }
            for row in plan
        ],
        "expected_budget": dict(EXPECTED_BUDGET),
    }


def _print_dry_run(summary: Mapping[str, Any]) -> None:
    print(f"run_id={summary['run_id']}")
    print("qids=" + ",".join(summary["qids"]))
    print("arms=" + ",".join(summary["arms"]))
    print(f"extended_pool_depth={summary['extended_pool_depth']}")
    print(f"expected_total_rerank_pairs={summary['expected_total_rerank_pairs']}")
    for target in summary["targets"]:
        ranks = ",".join(
            f"{arm}:{rank}"
            for arm, rank in target["recorded_rrf_ranks"].items()
        )
        print(f"{target['qid']} tmdb_id={target['tmdb_id']} rrf_ranks={ranks}")


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build DECOMP-01 q05/q10 full rerank-pool decomposition."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, output_path, report_path, data = run(
            run_id=args.run,
            dry_run=args.dry_run,
        )
    except (DecompPoolError, FileNotFoundError) as exc:
        print(f"decomp_pool_q05_q10: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(data)
        return 0

    print(f"run_id={run_id}")
    print(f"output={output_path}")
    print(f"report={report_path}")
    print(f"decision={data['decision']['status']}")
    print(f"phase5_gate={data['decision']['phase5_gate']}")
    print(
        "expected_runtime_seconds="
        f"{data['run_accounting']['expected']['expected_runtime_seconds']}"
    )
    print(
        "actual_runtime_seconds="
        f"{data['run_accounting']['actual']['actual_runtime_seconds']}"
    )
    print(
        "expected_cost_usd="
        f"{data['run_accounting']['expected']['expected_cost_usd']:.2f}"
    )
    print(
        "actual_cost_usd="
        f"{data['run_accounting']['actual']['actual_cost_usd']:.2f}"
    )
    print(
        "max_observed_vram_mib="
        f"{data['run_accounting']['actual']['max_observed_vram_mib']}"
    )
    print(f"policy_count={data['policy_analysis']['policy_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
