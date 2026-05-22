"""Aggregate query/label review evidence for the q05/q07/q10 cluster (QL-01).

QL-01 is review/eval-only. This script reads existing run artifacts, builds one
structured evidence record per query, and emits a coarse ``rule_based_lean``.
It assigns no final classification - that judgment belongs to the QL-01 report.
It must not import ``src`` and must make no model or network calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from eval.scripts import _run_io


SCHEMA_VERSION = "ql-01-query-label-review.v1"
QIDS = ("q05", "q07", "q10")
CONTROL_ARMS = ("pinned", "no_llm")
MODES = ("basic", "advanced", "hybrid")
RERANK_DEMOTION_STAGES = ("rerank_demoted", "rerank_recovered_final_demoted")

LEAN_RERANKER_BLEND = "reranker_blend_issue_later_eval"
LEAN_NEEDS_REVIEW = "needs_analyst_review"
LEAN_INCONCLUSIVE = "inconclusive"

QUERIES_RELATIVE_PATH = Path("queries") / "v1.jsonl"
GOLD_RELATIVE_PATH = Path("gold_labels.jsonl")
SILVER_RELATIVE_PATH = Path("silver_labels.jsonl")
CANDIDATES_RELATIVE_PATH = Path("candidates.jsonl")
LOCALIZATION_RELATIVE_PATH = Path("analysis") / "hy_fix_localize" / "localization.json"
ERROR_REPORT_RELATIVE_PATH = (
    Path("analysis") / "error_report" / "per_query_mode.gold.jsonl"
)
STABILITY_TRACE_RELATIVE_PATH = (
    Path("analysis") / "hybrid_expansion_stability" / "stability_trace.jsonl"
)
OUTPUT_RELATIVE_PATH = (
    Path("analysis") / "query_label_review" / "q05_q07_q10_review.json"
)

LABEL_PROVENANCE_NOTE = (
    "q05/q07/q10 eval grades are silver/LLM-pregrade labels "
    "(label_source=silver, gold_grade=null); the merged gold_labels.jsonl "
    "carries human-gold rows only for q03/q08/q12/q13. A silver_label_issue "
    "finding is a recommendation to run an RG-style human regrade, not a "
    "dispute of an existing human gold grade."
)


class QueryLabelReviewError(ValueError):
    """Raised when QL-01 query/label review cannot proceed."""


def run(run_id: Optional[str] = None) -> Tuple[str, Path, Dict[str, Any]]:
    """Load inputs, build the review artifact, and write it to the run dir."""
    actual_run_id = run_id or _run_io.latest_run()
    inputs = _load_inputs(actual_run_id)
    data = build_review(actual_run_id, inputs)
    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_io._atomic_write_json(output_path, data)
    return actual_run_id, output_path, data


def build_review(run_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Build the QL-01 evidence artifact from already-loaded inputs."""
    queries = [_build_query(qid, inputs) for qid in QIDS]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "source_artifacts": {
            "queries": "queries/v1.jsonl",
            "gold_labels": "gold_labels.jsonl",
            "silver_labels": "silver_labels.jsonl",
            "candidates": "candidates.jsonl",
            "localization": _rel(LOCALIZATION_RELATIVE_PATH),
            "error_report": _rel(ERROR_REPORT_RELATIVE_PATH),
            "stability_trace": _rel(STABILITY_TRACE_RELATIVE_PATH),
        },
        "label_provenance_note": LABEL_PROVENANCE_NOTE,
        "queries": queries,
        "decision": {
            "status": "analyst_classification_required",
            "next_action": "complete_ql_01_report_classification",
            "external_review": (
                "optional_non_blocking_for_ql_01; "
                "required_for_any_label_or_query_change_followup"
            ),
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate QL-01 query/label review evidence for q05/q07/q10."
    )
    parser.add_argument("--run", default=None)
    args = parser.parse_args(argv)

    try:
        run_id, output_path, data = run(args.run)
    except (QueryLabelReviewError, FileNotFoundError) as exc:
        print(f"ql_query_label_review: {exc}", file=sys.stderr)
        return 1

    print(f"run_id={run_id}")
    print(f"output={output_path}")
    for query in data["queries"]:
        print(f"{query['qid']}_lean={query['rule_based_lean']}")
    print(f"decision={data['decision']['status']}")
    return 0


def _load_inputs(run_id: str) -> Dict[str, Any]:
    run_path = _run_io.run_dir(run_id)
    paths = {
        "queries": _run_io.EVAL_DIR / QUERIES_RELATIVE_PATH,
        "gold": run_path / GOLD_RELATIVE_PATH,
        "silver": run_path / SILVER_RELATIVE_PATH,
        "candidates": run_path / CANDIDATES_RELATIVE_PATH,
        "localization": run_path / LOCALIZATION_RELATIVE_PATH,
        "error_report": run_path / ERROR_REPORT_RELATIVE_PATH,
        "stability_trace": run_path / STABILITY_TRACE_RELATIVE_PATH,
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise QueryLabelReviewError(
            "required input file missing: " + ", ".join(missing)
        )
    return {
        "queries": _read_jsonl_objects(paths["queries"]),
        "gold": _read_jsonl_objects(paths["gold"]),
        "silver": _read_jsonl_objects(paths["silver"]),
        "candidates": _read_jsonl_objects(paths["candidates"]),
        "localization": _read_json_object(paths["localization"]),
        "error_rows": _read_jsonl_objects(paths["error_report"]),
        "stability_rows": _read_jsonl_objects(paths["stability_trace"]),
    }


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise QueryLabelReviewError(f"{path}: JSON root must be an object")
    return data


def _read_jsonl_objects(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise QueryLabelReviewError(
                    f"{path}:{line_number}: JSONL row must be an object"
                )
            rows.append(obj)
    return rows


def _build_query(qid: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    loc_row = _localization_row(inputs["localization"], qid)
    target_gold = _target_gold_row(inputs["gold"], qid)
    tmdb_id = target_gold.get("tmdb_id")
    if loc_row.get("tmdb_id") != tmdb_id:
        raise QueryLabelReviewError(
            f"{qid}: localization tmdb_id {loc_row.get('tmdb_id')} does not "
            f"match grade-3 gold tmdb_id {tmdb_id}"
        )
    query_record = _query_record(inputs["queries"], qid)
    arms = _deterministic_arms(loc_row)
    lean, trace = _rule_based_lean(arms)
    expansion_text, expansion_source = _hybrid_expansion(qid, inputs["stability_rows"])

    return {
        "qid": qid,
        "query_text": query_record.get("query"),
        "tags": query_record.get("tags"),
        "target": {
            "tmdb_id": tmdb_id,
            "title": loc_row.get("title"),
            "grade_used_for_eval": target_gold.get("grade"),
            "label_source": target_gold.get("label_source"),
            "gold_grade": target_gold.get("gold_grade"),
            "silver_grade": target_gold.get("silver_grade"),
            "silver_pregrade": _silver_pregrade(inputs["silver"], qid, tmdb_id),
        },
        "evidence": {
            "consolidated_fix_category": loc_row.get("consolidated_fix_category"),
            "arms_agree": loc_row.get("arms_agree"),
            "deterministic_arms": arms,
            "mode_comparison": _mode_comparison(qid, inputs["error_rows"]),
            "target_retrieved_by_mode": _target_retrieved_by_mode(
                qid, tmdb_id, inputs["candidates"]
            ),
            "hybrid_top5": _hybrid_top5(qid, inputs["error_rows"], inputs["gold"]),
            "hybrid_expansion_text": expansion_text,
            "hybrid_expansion_source": expansion_source,
        },
        "rule_based_lean": lean,
        "rule_trace": trace,
    }


def _localization_row(localization: Dict[str, Any], qid: str) -> Dict[str, Any]:
    rows = localization.get("per_target")
    if not isinstance(rows, list):
        raise QueryLabelReviewError("localization missing per_target list")
    for row in rows:
        if isinstance(row, dict) and row.get("qid") == qid:
            return row
    raise QueryLabelReviewError(f"localization missing {qid}")


def _target_gold_row(gold_rows: Sequence[Dict[str, Any]], qid: str) -> Dict[str, Any]:
    matches = [
        row for row in gold_rows if row.get("qid") == qid and row.get("grade") == 3
    ]
    if len(matches) != 1:
        raise QueryLabelReviewError(
            f"{qid}: expected exactly one grade-3 gold row, found {len(matches)}"
        )
    return matches[0]


def _query_record(queries: Sequence[Dict[str, Any]], qid: str) -> Dict[str, Any]:
    for record in queries:
        if record.get("qid") == qid:
            return record
    raise QueryLabelReviewError(f"queries/v1.jsonl missing {qid}")


def _silver_pregrade(
    silver_rows: Sequence[Dict[str, Any]],
    qid: str,
    tmdb_id: Any,
) -> Dict[str, Any]:
    for row in silver_rows:
        if row.get("qid") == qid and row.get("tmdb_id") == tmdb_id:
            return {
                "model": row.get("model"),
                "confidence": row.get("confidence"),
                "reason": row.get("reason"),
                "ts": row.get("ts"),
                "silver_grade": row.get("grade"),
            }
    return {
        "model": None,
        "confidence": None,
        "reason": None,
        "ts": None,
        "silver_grade": None,
    }


def _deterministic_arms(loc_row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    arms = loc_row.get("arms")
    if not isinstance(arms, dict):
        raise QueryLabelReviewError(f"{loc_row.get('qid')}: localization missing arms")
    result: Dict[str, Dict[str, Any]] = {}
    for arm in CONTROL_ARMS:
        arm_data = arms.get(arm)
        if not isinstance(arm_data, dict):
            raise QueryLabelReviewError(
                f"{loc_row.get('qid')}: localization missing {arm} arm"
            )
        stage = arm_data.get("stage_table")
        stage = stage if isinstance(stage, dict) else {}
        result[arm] = {
            "loss_stage": arm_data.get("loss_stage"),
            "fix_category": arm_data.get("fix_category"),
            "semantic_rank": _nested(stage, "semantic", "rank"),
            "rrf_rank": _nested(stage, "rrf", "rank"),
            "target_in_rerank_pool": _nested(stage, "rerank", "in_pool"),
            "rerank_rank": _nested(stage, "rerank", "rerank_rank"),
            "final_rank": _nested(stage, "final", "final_rank"),
            "in_top5": _nested(stage, "final", "in_top5"),
        }
    return result


def _nested(data: Dict[str, Any], section: str, key: str) -> Any:
    value = data.get(section)
    if isinstance(value, dict):
        return value.get(key)
    return None


def _rule_based_lean(
    deterministic_arms: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """Return a coarse lean plus a trace of which rule fired.

    R1 -> reranker_blend_issue_later_eval: both control arms show a rerank or
          final-blend demotion (retrieval succeeded, ranking demoted it).
    R2 -> needs_analyst_review: not R1, but the loss-stage evidence is present;
          wording vs label vs expansion judgment belongs to the report.
    R3 -> inconclusive: deterministic-arm loss-stage evidence is missing.
    """
    trace: List[str] = []
    stages: Dict[str, Any] = {}
    for arm in CONTROL_ARMS:
        arm_data = deterministic_arms.get(arm)
        stages[arm] = arm_data.get("loss_stage") if isinstance(arm_data, dict) else None

    if any(stages[arm] is None for arm in CONTROL_ARMS):
        trace.append(
            "R3 inconclusive: deterministic-arm loss_stage evidence missing "
            f"(pinned={stages['pinned']}, no_llm={stages['no_llm']})"
        )
        return LEAN_INCONCLUSIVE, trace

    if all(stages[arm] in RERANK_DEMOTION_STAGES for arm in CONTROL_ARMS):
        trace.append(
            "R1 reranker_blend: both control arms show a rerank/blend demotion "
            f"(pinned={stages['pinned']}, no_llm={stages['no_llm']})"
        )
        return LEAN_RERANKER_BLEND, trace

    trace.append(
        "R2 needs_analyst_review: control arms are not both rerank/blend "
        f"demotions (pinned={stages['pinned']}, no_llm={stages['no_llm']}); "
        "wording vs label vs expansion judgment required"
    )
    return LEAN_NEEDS_REVIEW, trace


def _mode_comparison(
    qid: str,
    error_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for row in error_rows:
        if row.get("qid") != qid:
            continue
        mode = row.get("mode")
        if mode not in MODES:
            continue
        top = row.get("top") or []
        result[mode] = {
            "strict_hit_at_k": row.get("strict_hit_at_k"),
            "first_relevant_rank": row.get("first_relevant_rank"),
            "first_perfect_rank": row.get("first_perfect_rank"),
            "top5": [
                {
                    "rank": item.get("rank"),
                    "tmdb_id": item.get("tmdb_id"),
                    "title": item.get("title"),
                    "grade": item.get("grade"),
                }
                for item in top[:5]
                if isinstance(item, dict)
            ],
        }
    return result


def _target_retrieved_by_mode(
    qid: str,
    tmdb_id: Any,
    candidate_rows: Sequence[Dict[str, Any]],
) -> Dict[str, bool]:
    retrieved = {mode: False for mode in MODES}
    for row in candidate_rows:
        if row.get("qid") != qid or row.get("tmdb_id") != tmdb_id:
            continue
        per_mode = row.get("per_mode")
        if isinstance(per_mode, dict):
            for mode in MODES:
                if mode in per_mode:
                    retrieved[mode] = True
    return retrieved


def _hybrid_top5(
    qid: str,
    error_rows: Sequence[Dict[str, Any]],
    gold_rows: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    label_source_by_tmdb = {
        row.get("tmdb_id"): row.get("label_source")
        for row in gold_rows
        if row.get("qid") == qid
    }
    for row in error_rows:
        if row.get("qid") == qid and row.get("mode") == "hybrid":
            top = row.get("top") or []
            return [
                {
                    "rank": item.get("rank"),
                    "tmdb_id": item.get("tmdb_id"),
                    "title": item.get("title"),
                    "grade": item.get("grade"),
                    "label_source": label_source_by_tmdb.get(item.get("tmdb_id")),
                }
                for item in top[:5]
                if isinstance(item, dict)
            ]
    return []


def _hybrid_expansion(
    qid: str,
    stability_rows: Sequence[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str]]:
    qid_rows = [row for row in stability_rows if row.get("qid") == qid]
    for preferred_arm in ("live", "pinned", "no_llm"):
        for row in qid_rows:
            if row.get("arm") != preferred_arm:
                continue
            resolved = row.get("resolved")
            if isinstance(resolved, dict):
                text = resolved.get("retrieval_query")
                if isinstance(text, str) and text:
                    return text, _rel(STABILITY_TRACE_RELATIVE_PATH)
    return None, None


def _rel(path: Path) -> str:
    return str(path).replace("\\", "/")


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
