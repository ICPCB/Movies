"""Dump stored advanced/hybrid intermediate-stage scores for one qid."""

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


PRIMARY_K = 5
TRACE_MODES = ("advanced", "hybrid")
MODE_TRACE_KEYS = (
    "rank",
    "semantic_score",
    "bm25_score",
    "rrf_score",
    "rerank_score",
    "final_score",
)


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(data, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
            yield data


def _load_candidates(path: Path) -> list[Dict[str, Any]]:
    return [_schemas.validate_candidate_record(record) for record in _read_jsonl(path)]


def _load_silver_labels(path: Path) -> list[Dict[str, Any]]:
    return [_schemas.validate_silver_record(record) for record in _read_jsonl(path)]


def _silver_map(
    silver_labels: Iterable[Mapping[str, Any]],
) -> Dict[tuple[str, int], Mapping[str, Any]]:
    mapped: Dict[tuple[str, int], Mapping[str, Any]] = {}
    for label in silver_labels:
        mapped[(str(label["qid"]), int(label["tmdb_id"]))] = label
    return mapped


def _mode_trace(mode_data: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not mode_data:
        return None

    trace: Dict[str, Any] = {}
    for key in MODE_TRACE_KEYS:
        if key == "rank":
            trace[key] = int(mode_data[key]) if key in mode_data else None
        else:
            trace[key] = mode_data.get(key)
    return trace


def _in_top_5(mode_trace: Optional[Mapping[str, Any]]) -> bool:
    if mode_trace is None or mode_trace.get("rank") is None:
        return False
    return int(mode_trace["rank"]) < PRIMARY_K


def _rank_delta(
    hybrid: Optional[Mapping[str, Any]],
    advanced: Optional[Mapping[str, Any]],
) -> Optional[int]:
    if hybrid is None or advanced is None:
        return None
    if hybrid.get("rank") is None or advanced.get("rank") is None:
        return None
    return int(hybrid["rank"]) - int(advanced["rank"])


def _top_5_tmdb_ids(
    records: Sequence[Mapping[str, Any]],
    mode: str,
) -> list[int]:
    in_top_key = f"in_top_5_{mode}"
    rows = [
        record
        for record in records
        if record[in_top_key] and record[mode] is not None
    ]
    rows.sort(key=lambda record: (int(record[mode]["rank"]), int(record["tmdb_id"])))
    return [int(record["tmdb_id"]) for record in rows]


def build_trace(
    *,
    qid: str,
    candidates: Sequence[Mapping[str, Any]],
    silver_labels: Sequence[Mapping[str, Any]],
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    labels = _silver_map(silver_labels)
    records: list[Dict[str, Any]] = []

    for candidate in candidates:
        if str(candidate["qid"]) != qid:
            continue

        per_mode = candidate.get("per_mode", {})
        advanced = _mode_trace(per_mode.get("advanced"))
        hybrid = _mode_trace(per_mode.get("hybrid"))
        if advanced is None and hybrid is None:
            continue

        tmdb_id = int(candidate["tmdb_id"])
        label = labels.get((qid, tmdb_id), {})
        record: Dict[str, Any] = {
            "qid": qid,
            "tmdb_id": tmdb_id,
            "title": candidate["title"],
            "year": int(candidate["year"]),
            "silver_grade": label.get("grade"),
            "silver_confidence": label.get("confidence"),
            "advanced": advanced,
            "hybrid": hybrid,
            "rank_delta_hybrid_minus_advanced": _rank_delta(hybrid, advanced),
            "in_top_5_advanced": _in_top_5(advanced),
            "in_top_5_hybrid": _in_top_5(hybrid),
        }
        records.append(record)

    advanced_top_5 = _top_5_tmdb_ids(records, "advanced")
    hybrid_top_5 = _top_5_tmdb_ids(records, "hybrid")
    hybrid_top_5_set = set(hybrid_top_5)
    advanced_top_5_set = set(advanced_top_5)
    summary = {
        "qid": qid,
        "candidates_seen": len(records),
        "in_top_5_advanced_count": len(advanced_top_5),
        "in_top_5_hybrid_count": len(hybrid_top_5),
        "advanced_only_top_5_tmdb_ids": [
            tmdb_id for tmdb_id in advanced_top_5 if tmdb_id not in hybrid_top_5_set
        ],
        "hybrid_only_top_5_tmdb_ids": [
            tmdb_id for tmdb_id in hybrid_top_5 if tmdb_id not in advanced_top_5_set
        ],
        "advanced_top_5_tmdb_ids": advanced_top_5,
        "hybrid_top_5_tmdb_ids": hybrid_top_5,
    }
    return records, summary


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    text = "".join(json.dumps(row) + "\n" for row in rows)
    _run_io._atomic_write_text(path, text)


def run(
    *,
    qid: str,
    run_id: Optional[str] = None,
) -> tuple[str, Path, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    run_path = _run_io.run_dir(actual_run_id)
    candidates = _load_candidates(run_path / "candidates.jsonl")
    silver_labels = _load_silver_labels(run_path / "silver_labels.jsonl")

    qid_candidates = [
        candidate for candidate in candidates if str(candidate["qid"]) == qid
    ]
    if not qid_candidates:
        raise ValueError(f"qid {qid} not in run {actual_run_id}")

    records, summary = build_trace(
        qid=qid,
        candidates=qid_candidates,
        silver_labels=silver_labels,
    )

    output_dir = run_path / "analysis" / "hybrid_stage_trace"
    trace_path = output_dir / f"{qid}.jsonl"
    summary_path = output_dir / f"{qid}.summary.json"
    _write_jsonl(trace_path, records)
    _run_io._atomic_write_json(summary_path, summary)
    return actual_run_id, trace_path, summary_path, summary


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dump stored advanced/hybrid stage scores for one qid."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--qid", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, trace_path, summary_path, _summary = run(
            run_id=args.run,
            qid=args.qid,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"run_id={run_id}")
    print(f"trace={trace_path}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
