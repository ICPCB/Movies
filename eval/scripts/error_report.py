"""Write per-query, per-mode error reports for an eval run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io
from eval.scripts import merge_labels
from eval.scripts.compute_metrics import (
    MODE_ORDER,
    PRIMARY_K,
    RELEVANCE,
    TOP_KS,
    _group_candidates_by_qid,
    _label_map,
    _load_candidates,
    _load_silver_labels,
    _query_mode_metrics,
    _top_for_mode,
)

# Gold-mode reports use merged gold-over-silver grades, while confidence stays
# the original silver pre-grader confidence for the same (qid, tmdb_id).

_REPORT_KEYS = (
    "qid",
    "mode",
    "k",
    "top",
    "hit_at_k",
    "strict_hit_at_k",
    "first_relevant_rank",
    "first_perfect_rank",
    "null_grades_in_top_k",
)


class ErrorReportError(ValueError):
    """Raised when an error report precondition fails before writing."""


def _metric_value(value: Optional[float]) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _is_relevant_grade(grade: Optional[int]) -> bool:
    return grade is not None and RELEVANCE[grade] >= RELEVANCE[2]


def _is_perfect_grade(grade: Optional[int]) -> bool:
    return grade is not None and RELEVANCE[grade] == RELEVANCE[3]


def _first_rank(
    rows: Iterable[Mapping[str, Any]],
    predicate,
) -> Optional[int]:
    for row in sorted(rows, key=lambda item: int(item["rank"])):
        if predicate(row["grade"]):
            return int(row["rank"])
    return None


def _silver_confidence_map(
    silver_records: Iterable[Mapping[str, Any]],
) -> Dict[tuple[str, int], Optional[str]]:
    confidences: Dict[tuple[str, int], Optional[str]] = {}
    for record in silver_records:
        confidences[(str(record["qid"]), int(record["tmdb_id"]))] = record.get(
            "confidence"
        )
    return confidences


def _load_gold_labels(path: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    expected_keys = set(merge_labels.GOLD_LABEL_KEYS)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ErrorReportError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ErrorReportError(f"{path}:{line_number}: row must be an object")
            if set(value) != expected_keys:
                raise ErrorReportError(
                    f"{path}:{line_number}: unexpected gold label keys"
                )
            grade = value["grade"]
            if (
                grade is not None
                and (
                    not isinstance(grade, int)
                    or isinstance(grade, bool)
                    or grade not in merge_labels.GRADE_VALUES
                )
            ):
                raise ErrorReportError(
                    f"{path}:{line_number}: grade must be one of 0, 1, 2, 3, or null"
                )
            rows.append(value)
    return rows


def _candidate_map(
    candidates: Iterable[Mapping[str, Any]],
) -> Dict[tuple[str, int], Mapping[str, Any]]:
    mapped: Dict[tuple[str, int], Mapping[str, Any]] = {}
    for candidate in candidates:
        mapped[(str(candidate["qid"]), int(candidate["tmdb_id"]))] = candidate
    return mapped


def _top_rows(
    *,
    top_for_mode: Sequence[Mapping[str, Any]],
    candidates_by_key: Mapping[tuple[str, int], Mapping[str, Any]],
    confidences: Mapping[tuple[str, int], Optional[str]],
) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for row in top_for_mode:
        key = (str(row["qid"]), int(row["tmdb_id"]))
        candidate = candidates_by_key[key]
        rows.append(
            {
                "rank": int(row["rank"]),
                "tmdb_id": int(row["tmdb_id"]),
                "title": candidate["title"],
                "year": candidate["year"],
                "grade": row["grade"],
                "confidence": confidences.get(key),
            }
        )
    return rows


def _query_mode_record(
    *,
    qid: str,
    mode: str,
    k: int,
    candidates_for_query: Sequence[Mapping[str, Any]],
    labels: Mapping[tuple[str, int], Optional[int]],
    candidates_by_key: Mapping[tuple[str, int], Mapping[str, Any]],
    confidences: Mapping[tuple[str, int], Optional[str]],
) -> Dict[str, Any]:
    ranked_rows = _top_for_mode(candidates_for_query, mode, labels, k)
    metrics = _query_mode_metrics(
        candidates_for_query,
        mode,
        labels,
        {top_k: 1.0 for top_k in TOP_KS},
    )
    top = _top_rows(
        top_for_mode=ranked_rows,
        candidates_by_key=candidates_by_key,
        confidences=confidences,
    )
    record: Dict[str, Any] = {
        "qid": qid,
        "mode": mode,
        "k": k,
        "top": top,
        "hit_at_k": _metric_value(metrics[f"hit_at_{k}"]),
        "strict_hit_at_k": _metric_value(metrics[f"strict_hit_at_{k}"]),
        "first_relevant_rank": _first_rank(ranked_rows, _is_relevant_grade),
        "first_perfect_rank": _first_rank(ranked_rows, _is_perfect_grade),
        "null_grades_in_top_k": sum(1 for row in ranked_rows if row["grade"] is None),
    }
    return {key: record[key] for key in _REPORT_KEYS}


def _summary(
    *,
    run_id: str,
    k: int,
    qids: Sequence[str],
    records_by_qid_mode: Mapping[tuple[str, str], Mapping[str, Any]],
    label_source: str,
    labels_file: str,
) -> Dict[str, Any]:
    by_mode: Dict[str, Dict[str, list[str]]] = {}
    for mode in MODE_ORDER:
        by_mode[mode] = {
            "miss_qids": [
                qid
                for qid in qids
                if records_by_qid_mode[(qid, mode)]["hit_at_k"] == 0
            ],
            "strict_miss_qids": [
                qid
                for qid in qids
                if records_by_qid_mode[(qid, mode)]["strict_hit_at_k"] == 0
            ],
        }

    any_mode_miss_qids = [
        qid
        for qid in qids
        if any(
            records_by_qid_mode[(qid, mode)]["hit_at_k"] == 0
            for mode in MODE_ORDER
        )
    ]
    all_modes_miss_qids = [
        qid
        for qid in qids
        if all(
            records_by_qid_mode[(qid, mode)]["hit_at_k"] == 0
            for mode in MODE_ORDER
        )
    ]
    hybrid_only_miss_qids = [
        qid
        for qid in qids
        if records_by_qid_mode[(qid, "hybrid")]["hit_at_k"] == 0
        and records_by_qid_mode[(qid, "basic")]["hit_at_k"] == 1
        and records_by_qid_mode[(qid, "advanced")]["hit_at_k"] == 1
    ]

    return {
        "run_id": run_id,
        "k": k,
        "by_mode": by_mode,
        "any_mode_miss_qids": any_mode_miss_qids,
        "all_modes_miss_qids": all_modes_miss_qids,
        "hybrid_only_miss_qids": hybrid_only_miss_qids,
        "label_source": label_source,
        "labels_file": labels_file,
    }


def build_report(
    *,
    run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    grade_labels: Sequence[Mapping[str, Any]],
    confidence_labels: Sequence[Mapping[str, Any]],
    k: int = PRIMARY_K,
    label_source: str,
    labels_file: str,
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    if k not in TOP_KS:
        allowed = ", ".join(str(value) for value in TOP_KS)
        raise ValueError(f"k must be one of: {allowed}")

    labels = _label_map(grade_labels)
    confidences = _silver_confidence_map(confidence_labels)
    grouped = _group_candidates_by_qid(candidates)
    candidates_by_key = _candidate_map(candidates)

    records: list[Dict[str, Any]] = []
    records_by_qid_mode: Dict[tuple[str, str], Dict[str, Any]] = {}
    qids = sorted(grouped)
    for qid in qids:
        candidates_for_query = list(grouped[qid])
        for mode in MODE_ORDER:
            record = _query_mode_record(
                qid=qid,
                mode=mode,
                k=k,
                candidates_for_query=candidates_for_query,
                labels=labels,
                candidates_by_key=candidates_by_key,
                confidences=confidences,
            )
            records.append(record)
            records_by_qid_mode[(qid, mode)] = record

    return records, _summary(
        run_id=run_id,
        k=k,
        qids=qids,
        records_by_qid_mode=records_by_qid_mode,
        label_source=label_source,
        labels_file=labels_file,
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def run(
    *,
    run_id: Optional[str] = None,
    k: int = PRIMARY_K,
    labels: str = "silver",
) -> tuple[str, Path, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    run_path = _run_io.run_dir(actual_run_id)
    candidates = _load_candidates(run_path / "candidates.jsonl")
    silver_labels = _load_silver_labels(run_path / "silver_labels.jsonl")

    if labels == "silver":
        grade_labels = silver_labels
        confidence_labels = silver_labels
        label_source = "silver"
        labels_file = "silver_labels.jsonl"
        per_query_name = "per_query_mode.jsonl"
        summary_name = "summary.json"
    elif labels == "gold":
        gold_path = run_path / "gold_labels.jsonl"
        if not gold_path.exists():
            raise ErrorReportError(
                "gold_labels.jsonl not found in run "
                f"{actual_run_id} \u2014 run eval.scripts.merge_labels first"
            )
        grade_labels = _load_gold_labels(gold_path)
        confidence_labels = silver_labels
        label_source = "merged_gold_over_silver"
        labels_file = "gold_labels.jsonl"
        per_query_name = "per_query_mode.gold.jsonl"
        summary_name = "summary.gold.json"
    else:
        raise ValueError("labels must be one of: silver, gold")

    records, summary = build_report(
        run_id=actual_run_id,
        candidates=candidates,
        grade_labels=grade_labels,
        confidence_labels=confidence_labels,
        k=k,
        label_source=label_source,
        labels_file=labels_file,
    )

    output_dir = run_path / "analysis" / "error_report"
    output_dir.mkdir(parents=True, exist_ok=True)
    per_query_path = output_dir / per_query_name
    summary_path = output_dir / summary_name
    _write_jsonl(per_query_path, records)
    _run_io._atomic_write_json(summary_path, summary)
    return actual_run_id, per_query_path, summary_path, summary


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write CineMatch per-query, per-mode error reports."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--k", default=PRIMARY_K, choices=TOP_KS, type=int)
    parser.add_argument("--labels", default="silver", choices=("silver", "gold"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, per_query_path, summary_path, summary = run(
            run_id=args.run,
            k=args.k,
            labels=args.labels,
        )
    except ErrorReportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"run_id={run_id}")
    print(f"per_query_mode={per_query_path}")
    print(f"summary={summary_path}")
    print(f"label_source={summary['label_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
