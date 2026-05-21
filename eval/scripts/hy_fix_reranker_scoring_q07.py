"""Analyze HY-FIX-03 q07 reranker-scoring evidence from existing artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from eval.scripts import _run_io


SCHEMA_VERSION = "hy-fix-03-reranker-q07.v1"
LOCALIZATION_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_localize" / "localization.json"
)
STABILITY_TRACE_RELATIVE_PATH = (
    Path("analysis") / "hybrid_expansion_stability" / "stability_trace.jsonl"
)
CANDIDATES_RELATIVE_PATH = Path("candidates.jsonl")
ERROR_REPORT_RELATIVE_PATH = (
    Path("analysis") / "error_report" / "per_query_mode.gold.jsonl"
)
OUTPUT_RELATIVE_PATH = (
    Path("analysis")
    / "hy_fix_reranker_scoring"
    / "q07_reranker_scoring_analysis.json"
)
QID = "q07"
TARGET_TMDB_ID = 63700
CONTROL_ARMS = ("pinned", "no_llm")
POLICY_IDS = (
    "final_blend_reweight_only",
    "reranker_document_text_change",
    "rerank_query_change",
    "final_top_k_expand_only",
)


class HyFixRerankerScoringQ07Error(ValueError):
    """Raised when HY-FIX-03 q07 analysis cannot proceed."""


def run(run_id: Optional[str] = None) -> tuple[str, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    inputs = _load_inputs(actual_run_id)
    data = build_analysis(actual_run_id, inputs)
    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_io._atomic_write_json(output_path, data)
    return actual_run_id, output_path, data


def build_analysis(
    run_id: str,
    inputs: Mapping[str, Any],
) -> Dict[str, Any]:
    localization = inputs["localization"]
    stability_rows = inputs["stability_rows"]
    candidate_rows = inputs["candidate_rows"]
    error_rows = inputs["error_rows"]

    q07_localization = _localization_row(localization)
    deterministic_arms = _deterministic_arm_summary(q07_localization)
    trace_summary = _stability_trace_summary(stability_rows)
    mode_comparison = _mode_comparison(error_rows)
    candidate_summary = _candidate_summary(candidate_rows)
    evidence = {
        "deterministic_arms": deterministic_arms,
        "trace_summary": trace_summary,
        "mode_comparison": mode_comparison,
        "candidate_summary": candidate_summary,
    }
    policies = [_policy(policy_id, evidence) for policy_id in POLICY_IDS]
    safe = [policy for policy in policies if policy["safe_enough_for_hy_fix_03"]]
    next_action = (
        "draft_hy_fix_03_implementation"
        if safe
        else "continue_to_mixed_q05_q10_analysis"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "source_artifacts": {
            "localization": str(LOCALIZATION_RELATIVE_PATH).replace("\\", "/"),
            "stability_trace": str(STABILITY_TRACE_RELATIVE_PATH).replace("\\", "/"),
            "candidates": str(CANDIDATES_RELATIVE_PATH).replace("\\", "/"),
            "error_report": str(ERROR_REPORT_RELATIVE_PATH).replace("\\", "/"),
        },
        "qid": QID,
        "tmdb_id": TARGET_TMDB_ID,
        "title": q07_localization.get("title"),
        "consolidated_fix_category": q07_localization.get(
            "consolidated_fix_category"
        ),
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
                "q07 is a true reranker-scoring defect, but existing artifacts "
                "do not prove a minimal bounded-risk scorer or reranker change."
                if not safe
                else "A minimal bounded q07 policy was identified."
            ),
            "next_action": next_action,
            "external_review": "optional_non_blocking",
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze HY-FIX-03 q07 reranker-scoring evidence."
    )
    parser.add_argument("--run", default=None)
    args = parser.parse_args(argv)

    try:
        run_id, output_path, data = run(args.run)
    except (HyFixRerankerScoringQ07Error, FileNotFoundError) as exc:
        print(f"hy_fix_reranker_scoring_q07: {exc}", file=sys.stderr)
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
        "candidates": run_path / CANDIDATES_RELATIVE_PATH,
        "error_report": run_path / ERROR_REPORT_RELATIVE_PATH,
    }
    missing = [path for path in paths.values() if not path.exists()]
    if missing:
        raise HyFixRerankerScoringQ07Error(
            "required input file missing: " + ", ".join(str(path) for path in missing)
        )
    return {
        "localization": _read_json_object(paths["localization"]),
        "stability_rows": _read_jsonl_objects(paths["stability_trace"]),
        "candidate_rows": _read_jsonl_objects(paths["candidates"]),
        "error_rows": _read_jsonl_objects(paths["error_report"]),
    }


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise HyFixRerankerScoringQ07Error(f"{path}: JSON root must be an object")
    return data


def _read_jsonl_objects(path: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise HyFixRerankerScoringQ07Error(
                    f"{path}:{line_number}: JSONL row must be an object"
                )
            rows.append(data)
    return rows


def _localization_row(localization: Mapping[str, Any]) -> Mapping[str, Any]:
    rows = localization.get("per_target")
    if not isinstance(rows, list):
        raise HyFixRerankerScoringQ07Error("localization missing per_target list")
    for row in rows:
        if isinstance(row, dict) and row.get("qid") == QID:
            return row
    raise HyFixRerankerScoringQ07Error("localization missing q07")


def _deterministic_arm_summary(
    q07_localization: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    arms = q07_localization.get("arms")
    if not isinstance(arms, dict):
        raise HyFixRerankerScoringQ07Error("q07 localization missing arms")

    result: Dict[str, Dict[str, Any]] = {}
    for arm in CONTROL_ARMS:
        arm_data = arms.get(arm)
        if not isinstance(arm_data, dict):
            raise HyFixRerankerScoringQ07Error(f"q07 localization missing {arm}")
        stage = arm_data.get("stage_table")
        if not isinstance(stage, dict):
            raise HyFixRerankerScoringQ07Error(
                f"q07 localization missing {arm}.stage_table"
            )
        result[arm] = {
            "loss_stage": arm_data.get("loss_stage"),
            "fix_category": arm_data.get("fix_category"),
            "semantic_rank": _nested(stage, "semantic", "rank"),
            "rrf_rank": _nested(stage, "rrf", "rank"),
            "target_in_rerank_pool": _nested(stage, "rerank", "in_pool"),
            "rerank_score": _nested(stage, "rerank", "rerank_score"),
            "rerank_rank": _nested(stage, "rerank", "rerank_rank"),
            "final_score": _nested(stage, "final", "final_score"),
            "final_rank": _nested(stage, "final", "final_rank"),
            "in_top5": _nested(stage, "final", "in_top5"),
        }
    return result


def _nested(data: Mapping[str, Any], section: str, key: str) -> Any:
    value = data.get(section)
    if isinstance(value, dict):
        return value.get(key)
    return None


def _stability_trace_summary(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    q07_rows = [row for row in rows if row.get("qid") == QID]
    if not q07_rows:
        raise HyFixRerankerScoringQ07Error("stability trace missing q07")
    by_arm: Dict[str, Any] = {}
    for arm in ("live", "pinned", "no_llm"):
        arm_rows = [row for row in q07_rows if row.get("arm") == arm]
        if not arm_rows:
            continue
        by_arm[arm] = {
            "repeats": len(arm_rows),
            "loss_classification_counts": dict(
                Counter(str(row.get("loss_classification")) for row in arm_rows)
            ),
            "rerank_ranks": [
                row.get("rerank", {}).get("rerank_rank")
                for row in arm_rows
                if isinstance(row.get("rerank"), dict)
                and row.get("rerank", {}).get("rerank_rank") is not None
            ],
            "final_ranks": [
                row.get("final", {}).get("final_rank")
                for row in arm_rows
                if isinstance(row.get("final"), dict)
                and row.get("final", {}).get("final_rank") is not None
            ],
        }
    return {
        "rows_for_q07": len(q07_rows),
        "by_arm": by_arm,
    }


def _mode_comparison(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("qid") != QID:
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
        raise HyFixRerankerScoringQ07Error(
            "error report missing q07 basic or hybrid rows"
        )
    return result


def _candidate_summary(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    q07_rows = [row for row in rows if row.get("qid") == QID]
    if not q07_rows:
        raise HyFixRerankerScoringQ07Error("candidates missing q07")
    target_rows = [row for row in q07_rows if row.get("tmdb_id") == TARGET_TMDB_ID]
    hybrid_top = []
    for row in q07_rows:
        per_mode = row.get("per_mode")
        if not isinstance(per_mode, dict):
            continue
        hybrid = per_mode.get("hybrid")
        if not isinstance(hybrid, dict):
            continue
        rank = hybrid.get("rank")
        if isinstance(rank, int) and rank < 5:
            hybrid_top.append(
                {
                    "rank": rank,
                    "tmdb_id": row.get("tmdb_id"),
                    "title": row.get("title"),
                    "rerank_score": hybrid.get("rerank_score"),
                    "rrf_score": hybrid.get("rrf_score"),
                    "final_score": hybrid.get("final_score"),
                }
            )
    hybrid_top.sort(key=lambda item: int(item["rank"]))
    return {
        "candidate_rows_for_q07": len(q07_rows),
        "target_present_in_candidate_union": bool(target_rows),
        "target_candidate_modes": _target_modes(target_rows),
        "target_has_hybrid_candidate_row": any(
            isinstance(row.get("per_mode"), dict)
            and "hybrid" in row.get("per_mode", {})
            for row in target_rows
        ),
        "hybrid_top5_from_candidates": hybrid_top,
    }


def _target_modes(target_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    modes = set()
    for row in target_rows:
        per_mode = row.get("per_mode")
        if isinstance(per_mode, dict):
            modes.update(str(mode) for mode in per_mode)
    return sorted(modes)


def _policy(policy_id: str, evidence: Mapping[str, Any]) -> Dict[str, Any]:
    arms = evidence["deterministic_arms"]
    mode_comparison = evidence["mode_comparison"]
    max_final_top_k_needed = max(
        int(arm["final_rank"]) + 1
        for arm in arms.values()
        if isinstance(arm.get("final_rank"), int)
    )

    common = {
        "policy_id": policy_id,
        "q07_pinned_rescued_to_top5": False,
        "q07_no_llm_rescued_to_top5": False,
        "basic_first_perfect_rank": mode_comparison["basic"].get(
            "first_perfect_rank"
        ),
        "hybrid_first_perfect_rank": mode_comparison["hybrid"].get(
            "first_perfect_rank"
        ),
        "minimal": False,
        "safe_enough_for_hy_fix_03": False,
        "exact_allowed_src_files": [],
    }

    if policy_id == "final_blend_reweight_only":
        common.update(
            {
                "estimated_risk": "medium_high",
                "stop_reason": (
                    "target_cross_encoder_rank_is_17_to_20_and_full_q07_pool_"
                    "score_decomposition_is_missing"
                ),
                "rationale": (
                    "The target enters the rerank pool but is already below "
                    "top 5 by rerank score; changing blend weights is not "
                    "proven to rescue q07 and could broadly reorder results."
                ),
            }
        )
    elif policy_id == "reranker_document_text_change":
        common.update(
            {
                "estimated_risk": "high",
                "stop_reason": "requires_model_scoring_validation_and_src_reranker_behavior_change",
                "rationale": (
                    "Changing the candidate document text may affect all "
                    "reranked results and needs model-backed validation not "
                    "available in this analysis-only ticket."
                ),
            }
        )
    elif policy_id == "rerank_query_change":
        common.update(
            {
                "estimated_risk": "high",
                "stop_reason": "requires_query_or_movie_label_judgment_not_deterministic_src_fix",
                "rationale": (
                    "q07 basic already places the target at top 5 while "
                    "hybrid's intent query prefers different vampire "
                    "mockumentary results; altering the query is an eval-data "
                    "or label judgment, not a localized product fix."
                ),
            }
        )
    elif policy_id == "final_top_k_expand_only":
        common.update(
            {
                "estimated_risk": "medium",
                "minimum_final_top_k_needed_if_rank_is_zero_based": (
                    max_final_top_k_needed
                ),
                "stop_reason": "does_not_rescue_top5_metric_or_strict_hit_at_5",
                "rationale": (
                    "Returning more final results would only surface q07 near "
                    f"rank {max_final_top_k_needed}; it does not fix top-5 "
                    "accuracy."
                ),
            }
        )
    else:
        raise HyFixRerankerScoringQ07Error(f"unknown policy id: {policy_id}")
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
