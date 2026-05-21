"""Analyze remaining HY-FIX mixed q05/q10 defects from existing artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from eval.scripts import _run_io


SCHEMA_VERSION = "hy-fix-04-mixed-q05-q10.v1"
LOCALIZATION_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_localize" / "localization.json"
)
STABILITY_TRACE_RELATIVE_PATH = (
    Path("analysis") / "hybrid_expansion_stability" / "stability_trace.jsonl"
)
ERROR_REPORT_RELATIVE_PATH = (
    Path("analysis") / "error_report" / "per_query_mode.gold.jsonl"
)
RRF_POLICY_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_rrf_pool" / "rrf_pool_policy_validation.json"
)
Q07_ANALYSIS_RELATIVE_PATH = (
    Path("analysis")
    / "hy_fix_reranker_scoring"
    / "q07_reranker_scoring_analysis.json"
)
OUTPUT_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_mixed" / "q05_q10_mixed_analysis.json"
)
QIDS = ("q05", "q10")
CONTROL_ARMS = ("pinned", "no_llm")
POLICY_IDS = (
    "global_cutoff_small",
    "final_blend_reweight_for_mixed",
    "reranker_scoring_adjustment",
    "query_or_label_review",
)


class HyFixMixedQ05Q10Error(ValueError):
    """Raised when HY-FIX-04 mixed analysis cannot proceed."""


def run(run_id: Optional[str] = None) -> tuple[str, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    inputs = _load_inputs(actual_run_id)
    data = build_analysis(actual_run_id, inputs)
    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_io._atomic_write_json(output_path, data)
    return actual_run_id, output_path, data


def build_analysis(run_id: str, inputs: Mapping[str, Any]) -> Dict[str, Any]:
    localization = inputs["localization"]
    stability_rows = inputs["stability_rows"]
    error_rows = inputs["error_rows"]
    rrf_policy = inputs["rrf_policy"]
    q07_analysis = inputs["q07_analysis"]

    per_qid = {
        qid: _qid_summary(
            qid=qid,
            localization=localization,
            stability_rows=stability_rows,
            error_rows=error_rows,
        )
        for qid in QIDS
    }
    prior_blockers = _prior_blockers(rrf_policy, q07_analysis)
    evidence = {
        "per_qid": per_qid,
        "prior_blockers": prior_blockers,
    }
    policies = [_policy(policy_id, evidence) for policy_id in POLICY_IDS]
    safe = [policy for policy in policies if policy["safe_enough_for_hy_fix_04"]]
    next_action = (
        "draft_hy_fix_04_implementation"
        if safe
        else "final_closeout_no_safe_localized_fixes_remaining"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "source_artifacts": {
            "localization": str(LOCALIZATION_RELATIVE_PATH).replace("\\", "/"),
            "stability_trace": str(STABILITY_TRACE_RELATIVE_PATH).replace("\\", "/"),
            "error_report": str(ERROR_REPORT_RELATIVE_PATH).replace("\\", "/"),
            "rrf_policy_validation": str(RRF_POLICY_RELATIVE_PATH).replace("\\", "/"),
            "q07_reranker_analysis": str(Q07_ANALYSIS_RELATIVE_PATH).replace("\\", "/"),
        },
        "qids": list(QIDS),
        "evidence": evidence,
        "policies": policies,
        "recommended_policy": safe[0]["policy_id"] if safe else None,
        "implementation_recommended": bool(safe),
        "implementation_allowed_files": safe[0]["exact_allowed_src_files"]
        if safe
        else [],
        "decision": {
            "status": "implementation_not_justified" if not safe else "implementation_ready",
            "reason": (
                "q05/q10 failures are mixed across recall depth, final blend, "
                "and reranker scoring; no single bounded src change is proven."
                if not safe
                else "A minimal bounded mixed-defect policy was identified."
            ),
            "next_action": next_action,
            "external_review": "optional_non_blocking",
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze HY-FIX-04 mixed q05/q10 evidence."
    )
    parser.add_argument("--run", default=None)
    args = parser.parse_args(argv)

    try:
        run_id, output_path, data = run(args.run)
    except (HyFixMixedQ05Q10Error, FileNotFoundError) as exc:
        print(f"hy_fix_mixed_q05_q10: {exc}", file=sys.stderr)
        return 1

    print(f"run_id={run_id}")
    print(f"output={output_path}")
    print(f"implementation_recommended={data['implementation_recommended']}")
    print(f"recommended_policy={data['recommended_policy']}")
    print(f"decision={data['decision']['status']}")
    print(f"next_action={data['decision']['next_action']}")
    return 0


def _load_inputs(run_id: str) -> Dict[str, Any]:
    run_path = _run_io.run_dir(run_id)
    paths = {
        "localization": run_path / LOCALIZATION_RELATIVE_PATH,
        "stability_trace": run_path / STABILITY_TRACE_RELATIVE_PATH,
        "error_report": run_path / ERROR_REPORT_RELATIVE_PATH,
        "rrf_policy": run_path / RRF_POLICY_RELATIVE_PATH,
        "q07_analysis": run_path / Q07_ANALYSIS_RELATIVE_PATH,
    }
    missing = [path for path in paths.values() if not path.exists()]
    if missing:
        raise HyFixMixedQ05Q10Error(
            "required input file missing: " + ", ".join(str(path) for path in missing)
        )
    return {
        "localization": _read_json_object(paths["localization"]),
        "stability_rows": _read_jsonl_objects(paths["stability_trace"]),
        "error_rows": _read_jsonl_objects(paths["error_report"]),
        "rrf_policy": _read_json_object(paths["rrf_policy"]),
        "q07_analysis": _read_json_object(paths["q07_analysis"]),
    }


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise HyFixMixedQ05Q10Error(f"{path}: JSON root must be an object")
    return data


def _read_jsonl_objects(path: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise HyFixMixedQ05Q10Error(
                    f"{path}:{line_number}: JSONL row must be an object"
                )
            rows.append(data)
    return rows


def _qid_summary(
    *,
    qid: str,
    localization: Mapping[str, Any],
    stability_rows: Sequence[Mapping[str, Any]],
    error_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    row = _localization_row(localization, qid)
    return {
        "tmdb_id": row.get("tmdb_id"),
        "title": row.get("title"),
        "consolidated_fix_category": row.get("consolidated_fix_category"),
        "arms_agree": row.get("arms_agree"),
        "deterministic_arms": _deterministic_arms(row),
        "trace_summary": _trace_summary(qid, stability_rows),
        "mode_comparison": _mode_comparison(qid, error_rows),
    }


def _localization_row(localization: Mapping[str, Any], qid: str) -> Mapping[str, Any]:
    rows = localization.get("per_target")
    if not isinstance(rows, list):
        raise HyFixMixedQ05Q10Error("localization missing per_target list")
    for row in rows:
        if isinstance(row, dict) and row.get("qid") == qid:
            return row
    raise HyFixMixedQ05Q10Error(f"localization missing {qid}")


def _deterministic_arms(row: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    arms = row.get("arms")
    if not isinstance(arms, dict):
        raise HyFixMixedQ05Q10Error(f"{row.get('qid')}: localization missing arms")
    result: Dict[str, Dict[str, Any]] = {}
    for arm in CONTROL_ARMS:
        arm_data = arms.get(arm)
        if not isinstance(arm_data, dict):
            raise HyFixMixedQ05Q10Error(f"{row.get('qid')}: missing {arm} arm")
        stage = arm_data.get("stage_table")
        if not isinstance(stage, dict):
            raise HyFixMixedQ05Q10Error(
                f"{row.get('qid')}: missing {arm}.stage_table"
            )
        rrf_rank = _nested(stage, "rrf", "rank")
        rerank_rank = _nested(stage, "rerank", "rerank_rank")
        final_rank = _nested(stage, "final", "final_rank")
        result[arm] = {
            "loss_stage": arm_data.get("loss_stage"),
            "fix_category": arm_data.get("fix_category"),
            "semantic_rank": _nested(stage, "semantic", "rank"),
            "bm25_rank": _nested(stage, "bm25", "rank"),
            "rrf_rank": rrf_rank,
            "minimum_rerank_top_k_needed_if_rrf_rank_zero_based": (
                rrf_rank + 1 if isinstance(rrf_rank, int) else None
            ),
            "target_in_rerank_pool": _nested(stage, "rerank", "in_pool"),
            "rerank_score": _nested(stage, "rerank", "rerank_score"),
            "rerank_rank": rerank_rank,
            "minimum_rerank_rank_top_k_needed_if_zero_based": (
                rerank_rank + 1 if isinstance(rerank_rank, int) else None
            ),
            "final_score": _nested(stage, "final", "final_score"),
            "final_rank": final_rank,
            "minimum_final_top_k_needed_if_zero_based": (
                final_rank + 1 if isinstance(final_rank, int) else None
            ),
            "in_top5": _nested(stage, "final", "in_top5"),
        }
    return result


def _nested(data: Mapping[str, Any], section: str, key: str) -> Any:
    value = data.get(section)
    if isinstance(value, dict):
        return value.get(key)
    return None


def _trace_summary(
    qid: str,
    rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    qid_rows = [row for row in rows if row.get("qid") == qid]
    if not qid_rows:
        raise HyFixMixedQ05Q10Error(f"stability trace missing {qid}")
    by_arm: Dict[str, Any] = {}
    for arm in ("live", "pinned", "no_llm"):
        arm_rows = [row for row in qid_rows if row.get("arm") == arm]
        if not arm_rows:
            continue
        by_arm[arm] = {
            "repeats": len(arm_rows),
            "loss_classification_counts": dict(
                Counter(str(row.get("loss_classification")) for row in arm_rows)
            ),
        }
    return {
        "rows_for_qid": len(qid_rows),
        "by_arm": by_arm,
    }


def _mode_comparison(
    qid: str,
    rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("qid") != qid:
            continue
        mode = row.get("mode")
        if not isinstance(mode, str):
            continue
        result[mode] = {
            "strict_hit_at_k": row.get("strict_hit_at_k"),
            "first_relevant_rank": row.get("first_relevant_rank"),
            "first_perfect_rank": row.get("first_perfect_rank"),
            "top_titles": [
                item.get("title")
                for item in row.get("top", [])
                if isinstance(item, dict)
            ],
        }
    if "basic" not in result or "hybrid" not in result:
        raise HyFixMixedQ05Q10Error(
            f"error report missing {qid} basic or hybrid rows"
        )
    return result


def _prior_blockers(
    rrf_policy: Mapping[str, Any],
    q07_analysis: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "hy_fix_02b_status": rrf_policy.get("decision", {}).get("status"),
        "hy_fix_02b_reason": rrf_policy.get("decision", {}).get("reason"),
        "hy_fix_03_q07_status": q07_analysis.get("decision", {}).get("status"),
        "hy_fix_03_q07_reason": q07_analysis.get("decision", {}).get("reason"),
    }


def _policy(policy_id: str, evidence: Mapping[str, Any]) -> Dict[str, Any]:
    per_qid = evidence["per_qid"]
    q05 = per_qid["q05"]["deterministic_arms"]
    q10 = per_qid["q10"]["deterministic_arms"]
    common = {
        "policy_id": policy_id,
        "q05_rescued_to_top5": False,
        "q10_rescued_to_top5": False,
        "minimal": False,
        "safe_enough_for_hy_fix_04": False,
        "exact_allowed_src_files": [],
    }

    if policy_id == "global_cutoff_small":
        common.update(
            {
                "estimated_risk": "medium",
                "q05_pinned_minimum_rerank_top_k": q05["pinned"][
                    "minimum_rerank_top_k_needed_if_rrf_rank_zero_based"
                ],
                "q10_pinned_minimum_rerank_top_k": q10["pinned"][
                    "minimum_rerank_top_k_needed_if_rrf_rank_zero_based"
                ],
                "stop_reason": (
                    "cutoff_addresses_only_pinned_recall_arm_and_contradicts_"
                    "hy_fix_02b_no_safe_global_cutoff"
                ),
                "rationale": (
                    "Small cutoff increases could admit q05/q10 pinned "
                    "targets, but the no_llm arms still need final-blend or "
                    "reranker changes and HY-FIX-02B already rejected a safe "
                    "global cutoff policy."
                ),
            }
        )
    elif policy_id == "final_blend_reweight_for_mixed":
        common.update(
            {
                "estimated_risk": "medium_high",
                "q05_no_llm_final_top_k_needed": q05["no_llm"][
                    "minimum_final_top_k_needed_if_zero_based"
                ],
                "q10_no_llm_final_top_k_needed": q10["no_llm"][
                    "minimum_final_top_k_needed_if_zero_based"
                ],
                "stop_reason": "needs_full_pool_decomposition_and_regression_validation",
                "rationale": (
                    "q05 no_llm is rerank rank 4 but final rank 9, and q10 "
                    "no_llm is rerank rank 6/final rank 7. This suggests "
                    "blend pressure, but the artifact lacks full-pool "
                    "decomposition to prove a safe global reweight."
                ),
            }
        )
    elif policy_id == "reranker_scoring_adjustment":
        common.update(
            {
                "estimated_risk": "high",
                "q10_no_llm_rerank_top_k_needed": q10["no_llm"][
                    "minimum_rerank_rank_top_k_needed_if_zero_based"
                ],
                "stop_reason": "mixed_failures_do_not_identify_one_reranker_scoring_change",
                "rationale": (
                    "q05 and q10 combine recall cutoff, final blend, and "
                    "reranker-rank misses. A scorer change would affect all "
                    "reranked results and is not localized by the current "
                    "evidence."
                ),
            }
        )
    elif policy_id == "query_or_label_review":
        common.update(
            {
                "estimated_risk": "external_review_required",
                "stop_reason": "requires_human_or_external_movie_label_judgment",
                "rationale": (
                    "Basic or advanced already finds the perfect target for "
                    "q05/q10, while hybrid misses. Deciding whether to change "
                    "query wording or labels is outside deterministic src "
                    "implementation."
                ),
            }
        )
    else:
        raise HyFixMixedQ05Q10Error(f"unknown policy id: {policy_id}")
    return common


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
