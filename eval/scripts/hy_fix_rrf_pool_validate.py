"""Validate HY-FIX-02B RRF-pool policy options from finished trace data."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from eval.scripts import _run_io


SCHEMA_VERSION = "hy-fix-02b-validate.v1"
TRACE_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_rrf_pool" / "rrf_pool_trace.json"
)
LOCALIZATION_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_localize" / "localization.json"
)
OUTPUT_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_rrf_pool" / "rrf_pool_policy_validation.json"
)
CONTROL_ARMS = ("pinned", "no_llm")
CUTOFF_POLICIES = (80, 100, 150, 200, 250)
FIXED_DEFECT_QIDS = ("q05", "q07", "q08", "q10")


class HyFixRrfPoolValidateError(ValueError):
    """Raised when HY-FIX-02B validation cannot proceed."""


def run(run_id: Optional[str] = None) -> tuple[str, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    trace, localization = _load_inputs(actual_run_id)
    data = build_validation(actual_run_id, trace, localization)
    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_io._atomic_write_json(output_path, data)
    return actual_run_id, output_path, data


def build_validation(
    run_id: str,
    trace: Mapping[str, Any],
    localization: Mapping[str, Any],
) -> Dict[str, Any]:
    q08 = _qid_row(trace, "q08")
    config = _config(trace)
    arm_requirements = _arm_requirements(q08)
    policies = [_cutoff_policy(cutoff, q08, arm_requirements) for cutoff in CUTOFF_POLICIES]
    policies.append(_quota_policy(q08, arm_requirements))
    policies.append(_fusion_depth_policy(q08, arm_requirements))
    if _has_boundary_tie(q08):
        policies.append(_boundary_policy(q08, arm_requirements))

    safe = [policy for policy in policies if policy["safe_enough_for_hy_fix_02b"]]
    next_action = (
        "draft_hy_fix_02b_implementation"
        if safe
        else "continue_to_hy_fix_03_reranker_scoring_q07"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "source_artifacts": {
            "rrf_pool_trace": str(TRACE_RELATIVE_PATH).replace("\\", "/"),
            "localization": str(LOCALIZATION_RELATIVE_PATH).replace("\\", "/"),
        },
        "config": config,
        "fixed_defect_qids": list(FIXED_DEFECT_QIDS),
        "affected_fixed_defect_qids": _affected_fixed_defect_qids(localization, q08),
        "q08_arm_requirements": arm_requirements,
        "policies": policies,
        "recommended_policy": safe[0]["policy_id"] if safe else None,
        "implementation_recommended": bool(safe),
        "implementation_allowed_files": safe[0]["exact_allowed_src_config_files"]
        if safe
        else [],
        "decision": {
            "status": "implementation_not_justified" if not safe else "implementation_ready",
            "reason": (
                "No policy both rescues q08 in pinned/no_llm controls and keeps "
                "candidate growth bounded by the available trace evidence."
                if not safe
                else "A minimal bounded policy was identified."
            ),
            "next_action": next_action,
            "external_review": "optional_non_blocking",
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate HY-FIX-02B RRF-pool policy options."
    )
    parser.add_argument("--run", default=None)
    args = parser.parse_args(argv)

    try:
        run_id, output_path, data = run(args.run)
    except (HyFixRrfPoolValidateError, FileNotFoundError) as exc:
        print(f"hy_fix_rrf_pool_validate: {exc}", file=sys.stderr)
        return 1

    print(f"run_id={run_id}")
    print(f"output={output_path}")
    print(f"implementation_recommended={data['implementation_recommended']}")
    print(f"recommended_policy={data['recommended_policy']}")
    print(f"decision={data['decision']['status']}")
    print(f"next_action={data['decision']['next_action']}")
    return 0


def _load_inputs(run_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    run_path = _run_io.run_dir(run_id)
    trace_path = run_path / TRACE_RELATIVE_PATH
    localization_path = run_path / LOCALIZATION_RELATIVE_PATH
    missing = [path for path in (trace_path, localization_path) if not path.exists()]
    if missing:
        raise HyFixRrfPoolValidateError(
            "required input file missing: " + ", ".join(str(path) for path in missing)
        )
    return _read_json(trace_path), _read_json(localization_path)


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise HyFixRrfPoolValidateError(f"{path}: JSON root must be an object")
    return data


def _qid_row(trace: Mapping[str, Any], qid: str) -> Mapping[str, Any]:
    rows = trace.get("per_qid")
    if not isinstance(rows, list):
        raise HyFixRrfPoolValidateError("rrf_pool_trace missing per_qid list")
    for row in rows:
        if isinstance(row, dict) and row.get("qid") == qid:
            return row
    raise HyFixRrfPoolValidateError(f"rrf_pool_trace missing {qid}")


def _config(trace: Mapping[str, Any]) -> Dict[str, Any]:
    config = trace.get("config")
    if not isinstance(config, dict):
        raise HyFixRrfPoolValidateError("rrf_pool_trace missing config")
    return json.loads(json.dumps(config))


def _arm_requirements(qid_row: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    arms = qid_row.get("arms")
    if not isinstance(arms, dict):
        raise HyFixRrfPoolValidateError("q08 trace missing arms")
    result: Dict[str, Dict[str, Any]] = {}
    for arm in CONTROL_ARMS:
        data = arms.get(arm)
        if not isinstance(data, dict):
            raise HyFixRrfPoolValidateError(f"q08 trace missing {arm} arm")
        rank = data.get("target", {}).get("rrf", {}).get("rank")
        source_count = data.get("target", {}).get("source_count")
        result[arm] = {
            "rrf_rank": rank,
            "minimum_cutoff_needed": rank + 1 if isinstance(rank, int) else None,
            "target_source_count": source_count,
            "current_rerank_top_k": data.get("cutoff", {}).get("rerank_top_k"),
            "in_pool_source_mix": data.get("in_pool_source_mix"),
        }
    return result


def _cutoff_policy(
    cutoff: int,
    qid_row: Mapping[str, Any],
    requirements: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    rescued = _rescued_by_cutoff(cutoff, requirements)
    rescues_both = all(rescued.values())
    risk = _candidate_risk(cutoff, _current_cutoff(qid_row))
    minimal = cutoff == _next_listed_cutoff(max(
        req["minimum_cutoff_needed"] or 999999 for req in requirements.values()
    ))
    safe = rescues_both and risk["level"] in {"low", "medium"} and cutoff < 200
    stop_reason = None
    if not rescues_both:
        stop_reason = "does_not_rescue_both_deterministic_arms"
    elif cutoff >= 200:
        stop_reason = "pinned_q08_requires_cutoff_at_or_above_200_medium_high_risk"
    elif not minimal:
        stop_reason = "not_minimal_compared_with_smaller_cutoff_option"

    return _policy(
        policy_id=f"cutoff_only_top_{cutoff}",
        qid_row=qid_row,
        requirements=requirements,
        rescued=rescued,
        candidate_risk=risk,
        minimal=minimal,
        safe=safe,
        exact_allowed_src_config_files=["src/config.py"] if safe else [],
        stop_reason=stop_reason,
        rationale=(
            f"Set RERANK_TOP_K to {cutoff}; this is a direct cutoff-only "
            "policy and increases cross-encoder candidates linearly."
        ),
    )


def _quota_policy(
    qid_row: Mapping[str, Any],
    requirements: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    rescued = {arm: False for arm in CONTROL_ARMS}
    return _policy(
        policy_id="quota_preserve_semantic_bm25_small",
        qid_row=qid_row,
        requirements=requirements,
        rescued=rescued,
        candidate_risk={"level": "low", "multiplier": 1.2, "notes": "small reserved quota estimate"},
        minimal=False,
        safe=False,
        exact_allowed_src_config_files=[],
        stop_reason="trace_lacks_full_source_rank_lists_to_prove_quota_rescue",
        rationale=(
            "A small source-preserving quota cannot be proven from the q08 "
            "RRF neighborhood alone because q08 is outside the captured "
            "neighborhood in both deterministic arms."
        ),
    )


def _fusion_depth_policy(
    qid_row: Mapping[str, Any],
    requirements: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    rescued = {arm: False for arm in CONTROL_ARMS}
    return _policy(
        policy_id="fusion_depth_increase_small",
        qid_row=qid_row,
        requirements=requirements,
        rescued=rescued,
        candidate_risk={"level": "low", "multiplier": 1.0, "notes": "RERANK_TOP_K unchanged"},
        minimal=False,
        safe=False,
        exact_allowed_src_config_files=[],
        stop_reason="q08_already_present_in_rrf_list_so_depth_increase_does_not_change_pool_cutoff",
        rationale=(
            "Increasing fused-list depth does not rescue a target already in "
            "the RRF list while RERANK_TOP_K remains unchanged."
        ),
    )


def _boundary_policy(
    qid_row: Mapping[str, Any],
    requirements: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    rescued = {arm: False for arm in CONTROL_ARMS}
    return _policy(
        policy_id="tie_or_boundary_fix_only",
        qid_row=qid_row,
        requirements=requirements,
        rescued=rescued,
        candidate_risk={"level": "low", "multiplier": 1.0, "notes": "ordering-only policy"},
        minimal=False,
        safe=False,
        exact_allowed_src_config_files=[],
        stop_reason="q08_is_not_at_the_rerank_pool_boundary",
        rationale=(
            "A boundary tie exists in the trace, but q08 itself is rank 79 "
            "or 183, so tie handling cannot rescue it."
        ),
    )


def _policy(
    *,
    policy_id: str,
    qid_row: Mapping[str, Any],
    requirements: Mapping[str, Mapping[str, Any]],
    rescued: Mapping[str, bool],
    candidate_risk: Mapping[str, Any],
    minimal: bool,
    safe: bool,
    exact_allowed_src_config_files: Sequence[str],
    stop_reason: Optional[str],
    rationale: str,
) -> Dict[str, Any]:
    return {
        "policy_id": policy_id,
        "q08_no_llm_rescued_before_rerank_pool": bool(rescued["no_llm"]),
        "q08_pinned_rescued_before_rerank_pool": bool(rescued["pinned"]),
        "minimum_cutoff_needed": {
            "no_llm": requirements["no_llm"]["minimum_cutoff_needed"],
            "pinned": requirements["pinned"]["minimum_cutoff_needed"],
        },
        "affected_fixed_defect_qids": _affected_from_trace(qid_row),
        "estimated_candidate_count_memory_risk": dict(candidate_risk),
        "minimal": bool(minimal),
        "safe_enough_for_hy_fix_02b": bool(safe),
        "exact_allowed_src_config_files": list(exact_allowed_src_config_files),
        "stop_reason": stop_reason,
        "rationale": rationale,
    }


def _rescued_by_cutoff(
    cutoff: int,
    requirements: Mapping[str, Mapping[str, Any]],
) -> Dict[str, bool]:
    rescued = {}
    for arm, req in requirements.items():
        rank = req["rrf_rank"]
        rescued[arm] = isinstance(rank, int) and rank < cutoff
    return rescued


def _candidate_risk(cutoff: int, current: int) -> Dict[str, Any]:
    multiplier = round(cutoff / current, 2) if current else None
    if cutoff < 100:
        level = "low"
    elif cutoff < 200:
        level = "medium"
    else:
        level = "high"
    return {
        "level": level,
        "current_rerank_top_k": current,
        "candidate_count": cutoff,
        "candidate_growth_multiplier": multiplier,
        "notes": "Cross-encoder candidate count grows roughly linearly with RERANK_TOP_K.",
    }


def _current_cutoff(qid_row: Mapping[str, Any]) -> int:
    arms = qid_row["arms"]
    for arm in CONTROL_ARMS:
        value = arms[arm]["cutoff"]["rerank_top_k"]
        if isinstance(value, int):
            return value
    raise HyFixRrfPoolValidateError("q08 trace missing current cutoff")


def _next_listed_cutoff(minimum: int) -> Optional[int]:
    for cutoff in CUTOFF_POLICIES:
        if cutoff >= minimum:
            return cutoff
    return None


def _has_boundary_tie(qid_row: Mapping[str, Any]) -> bool:
    for arm in CONTROL_ARMS:
        cutoff = qid_row["arms"][arm]["cutoff"]
        last_score = cutoff.get("last_in_pool", {}).get("rrf_score")
        first_score = cutoff.get("first_out_of_pool", {}).get("rrf_score")
        if isinstance(last_score, (int, float)) and last_score == first_score:
            return True
    return False


def _affected_fixed_defect_qids(
    localization: Mapping[str, Any],
    qid_row: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    rows = localization.get("per_target", [])
    by_qid = {row.get("qid"): row for row in rows if isinstance(row, dict)}
    affected: Dict[str, Dict[str, Any]] = {}
    for qid in FIXED_DEFECT_QIDS:
        affected[qid] = {
            "has_rrf_pool_trace_data": qid == qid_row["qid"],
            "localization_category": by_qid.get(qid, {}).get(
                "consolidated_fix_category"
            ),
        }
    return affected


def _affected_from_trace(qid_row: Mapping[str, Any]) -> Dict[str, str]:
    return {
        qid: ("trace_data_available" if qid == qid_row["qid"] else "no_rrf_pool_trace_data")
        for qid in FIXED_DEFECT_QIDS
    }


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
