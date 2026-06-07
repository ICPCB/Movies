"""Build targeted silver-label audit review sheets for an eval run."""

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

from eval.scripts import _run_io, _schemas


ERROR_REPORT_MISSING_MESSAGE = (
    "error_report not found — run eval.scripts.error_report first"
)
MODE_ORDER = ("basic", "advanced", "hybrid")
RULES = (
    "silver_confidence_low",
    "silver_grade_1_in_top_5",
    "silver_grade_null",
)
REVIEW_KEYS = (
    "qid",
    "tmdb_id",
    "query",
    "title",
    "year",
    "overview",
    "genres",
    "silver_grade",
    "silver_confidence",
    "silver_reason",
    "in_top_5_of",
    "flag_reasons",
    "gold_grade",
    "gold_notes",
)


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
            yield value


def _load_candidates(path: Path) -> list[Dict[str, Any]]:
    return [_schemas.validate_candidate_record(record) for record in _read_jsonl(path)]


def _load_silver_labels(path: Path) -> list[Dict[str, Any]]:
    return [_schemas.validate_silver_record(record) for record in _read_jsonl(path)]


def _load_queries(path: Path) -> Dict[str, Dict[str, Any]]:
    queries: Dict[str, Dict[str, Any]] = {}
    for record in _read_jsonl(path):
        try:
            query = _schemas.validate_query_record(record)
        except ValueError:
            query = _schemas.validate_query_record_v2(record)
        queries[str(query["qid"])] = query
    return queries


def _parse_qids(value: str) -> list[str]:
    qids: list[str] = []
    seen: set[str] = set()
    for raw_qid in value.split(","):
        qid = raw_qid.strip()
        if not qid:
            continue
        if qid not in seen:
            qids.append(qid)
            seen.add(qid)
    if not qids:
        raise argparse.ArgumentTypeError("--qids must include at least one qid")
    return qids


def _require_error_report(run_path: Path) -> tuple[Path, Path]:
    error_report_dir = run_path / "analysis" / "error_report"
    per_query_path = error_report_dir / "per_query_mode.jsonl"
    summary_path = error_report_dir / "summary.json"
    if (
        not error_report_dir.exists()
        or not per_query_path.exists()
        or not summary_path.exists()
    ):
        raise FileNotFoundError(ERROR_REPORT_MISSING_MESSAGE)

    with summary_path.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    if not isinstance(summary, dict):
        raise ValueError("error_report summary.json must contain an object")
    return per_query_path, summary_path


def _top_5_modes(per_query_path: Path) -> Dict[tuple[str, int], set[str]]:
    modes_by_key: Dict[tuple[str, int], set[str]] = {}
    for record in _read_jsonl(per_query_path):
        qid = str(record["qid"])
        mode = str(record["mode"])
        if mode not in MODE_ORDER:
            raise ValueError(f"error_report mode must be one of: {', '.join(MODE_ORDER)}")
        top_rows = record.get("top")
        if not isinstance(top_rows, list):
            raise ValueError("error_report top must be a list")
        for top_row in top_rows:
            if not isinstance(top_row, dict):
                raise ValueError("error_report top rows must be objects")
            rank = int(top_row["rank"])
            if rank <= 5:
                key = (qid, int(top_row["tmdb_id"]))
                modes_by_key.setdefault(key, set()).add(mode)
    return modes_by_key


def _candidate_map(
    candidates: Iterable[Mapping[str, Any]],
) -> Dict[tuple[str, int], Mapping[str, Any]]:
    mapped: Dict[tuple[str, int], Mapping[str, Any]] = {}
    for candidate in candidates:
        mapped[(str(candidate["qid"]), int(candidate["tmdb_id"]))] = candidate
    return mapped


def _ordered_modes(modes: Iterable[str]) -> list[str]:
    mode_set = set(modes)
    return [mode for mode in MODE_ORDER if mode in mode_set]


def _flag_reasons(
    *,
    silver: Mapping[str, Any],
    audit_qids: set[str],
    include_rules: bool,
    top_5_modes: Mapping[tuple[str, int], set[str]],
) -> list[str]:
    qid = str(silver["qid"])
    tmdb_id = int(silver["tmdb_id"])
    key = (qid, tmdb_id)
    reasons: list[str] = []
    if qid in audit_qids:
        reasons.append("qid_in_audit_list")
    if include_rules:
        if silver["confidence"] == "low":
            reasons.append("silver_confidence_low")
        if silver["grade"] == 1 and key in top_5_modes:
            reasons.append("silver_grade_1_in_top_5")
        if silver["grade"] is None:
            reasons.append("silver_grade_null")
    return reasons


def build_review_sheet(
    *,
    run_id: str,
    qids: Sequence[str],
    include_rules: bool,
    candidates: Sequence[Mapping[str, Any]],
    silver_labels: Sequence[Mapping[str, Any]],
    queries: Mapping[str, Mapping[str, Any]],
    top_5_modes: Mapping[tuple[str, int], set[str]],
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    audit_qids = set(qids)
    candidates_by_key = _candidate_map(candidates)
    rows: list[Dict[str, Any]] = []

    for silver in silver_labels:
        qid = str(silver["qid"])
        tmdb_id = int(silver["tmdb_id"])
        key = (qid, tmdb_id)
        flag_reasons = _flag_reasons(
            silver=silver,
            audit_qids=audit_qids,
            include_rules=include_rules,
            top_5_modes=top_5_modes,
        )
        if not flag_reasons:
            continue

        if key not in candidates_by_key:
            raise ValueError(f"missing candidate for {qid}/{tmdb_id}")
        if qid not in queries:
            raise ValueError(f"missing query text for {qid}")

        candidate = candidates_by_key[key]
        record: Dict[str, Any] = {
            "qid": qid,
            "tmdb_id": tmdb_id,
            "query": queries[qid]["query"],
            "title": candidate["title"],
            "year": candidate["year"],
            "overview": candidate["overview"],
            "genres": candidate["genres"],
            "silver_grade": silver["grade"],
            "silver_confidence": silver["confidence"],
            "silver_reason": silver["reason"],
            "in_top_5_of": _ordered_modes(top_5_modes.get(key, set())),
            "flag_reasons": flag_reasons,
            "gold_grade": None,
            "gold_notes": None,
        }
        rows.append({key_name: record[key_name] for key_name in REVIEW_KEYS})

    rows.sort(key=lambda row: (row["qid"], row["tmdb_id"]))
    rows_by_qid = {qid: 0 for qid in qids}
    for row in rows:
        rows_by_qid.setdefault(str(row["qid"]), 0)
        rows_by_qid[str(row["qid"])] += 1
    ordered_rows_by_qid = {
        qid: rows_by_qid[qid]
        for qid in sorted(rows_by_qid)
    }
    summary = {
        "run_id": run_id,
        "qids_in_audit": list(qids),
        "rules_applied": list(RULES) if include_rules else [],
        "rows_total": len(rows),
        "rows_by_qid": ordered_rows_by_qid,
    }
    return rows, summary


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def run(
    *,
    run_id: Optional[str] = None,
    queries_path: Optional[Path] = None,
    qids: Optional[Sequence[str]] = None,
    include_rules: bool = False,
) -> tuple[str, Path, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    audit_qids = list(qids) if qids is not None else ["q12", "q13"]
    run_path = _run_io.run_dir(actual_run_id)
    per_query_path, _summary_path = _require_error_report(run_path)

    candidates = _load_candidates(run_path / "candidates.jsonl")
    silver_labels = _load_silver_labels(run_path / "silver_labels.jsonl")
    queries = _load_queries(queries_path or (_run_io.EVAL_DIR / "queries" / "v1.jsonl"))
    top_5_modes = _top_5_modes(per_query_path)
    rows, summary = build_review_sheet(
        run_id=actual_run_id,
        qids=audit_qids,
        include_rules=include_rules,
        candidates=candidates,
        silver_labels=silver_labels,
        queries=queries,
        top_5_modes=top_5_modes,
    )

    output_dir = run_path / "analysis" / "audit_silver_labels"
    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = output_dir / "review_sheet.jsonl"
    output_summary_path = output_dir / "summary.json"
    _write_jsonl(review_path, rows)
    _run_io._atomic_write_json(output_summary_path, summary)
    return actual_run_id, review_path, output_summary_path, summary


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a targeted CineMatch silver-label audit sheet."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--queries", default=None, type=Path)
    parser.add_argument("--qids", default=["q12", "q13"], type=_parse_qids)
    parser.add_argument("--include-rules", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, review_path, summary_path, _summary = run(
            run_id=args.run,
            queries_path=args.queries,
            qids=args.qids,
            include_rules=args.include_rules,
        )
    except FileNotFoundError as exc:
        if str(exc) == ERROR_REPORT_MISSING_MESSAGE:
            print(str(exc), file=sys.stderr)
            return 1
        raise

    print(f"run_id={run_id}")
    print(f"review_sheet={review_path}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
