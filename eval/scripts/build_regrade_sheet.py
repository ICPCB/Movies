"""Build a frozen human re-grade sheet from existing eval artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from eval.scripts import _run_io


REVIEW_ROW_KEYS = [
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
]
ROW_KEYS = REVIEW_ROW_KEYS + ["batch", "batch_purpose"]
REVIEW_QIDS = ("q12", "q13")
RETRIEVAL_MISS_QIDS = ("q03", "q08")
Q07_FOLLOWUP_QIDS = ("q07",)
OVERWRITE_MESSAGE = (
    "regrade_sheet.jsonl already exists — delete it manually to rebuild"
)
SHEET_NOT_FOUND_MESSAGE = (
    "regrade_sheet.jsonl not found — run the base build before adding q07 batch 3"
)
Q07_BATCH_PRESENT_MESSAGE = (
    "regrade_sheet.jsonl already includes q07 batch 3 — nothing to add"
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    tmdb_id = row.get("tmdb_id")
    if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool):
        raise ValueError("tmdb_id must be an integer")
    qid = row.get("qid")
    if not isinstance(qid, str):
        raise ValueError("qid must be a string")
    return qid, tmdb_id


def _load_queries(path: Path) -> dict[str, str]:
    queries: dict[str, str] = {}
    for row in _load_jsonl(path):
        qid = row.get("qid")
        query = row.get("query")
        if isinstance(qid, str) and isinstance(query, str):
            queries[qid] = query
    return queries


def _load_candidates(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    candidates: dict[tuple[str, int], dict[str, Any]] = {}
    for row in _load_jsonl(path):
        candidates[_row_key(row)] = row
    return candidates


def _load_silver_reasons(path: Path) -> dict[tuple[str, int], Any]:
    reasons: dict[tuple[str, int], Any] = {}
    for row in _load_jsonl(path):
        reasons[_row_key(row)] = row.get("reason")
    return reasons


def _build_batch1(review_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected_keys = set(REVIEW_ROW_KEYS)
    for index, source in enumerate(review_rows, start=1):
        if set(source) != expected_keys:
            raise ValueError(
                "review sheet row "
                f"{index} has unexpected keys: {sorted(set(source) ^ expected_keys)}"
            )
        row = dict(source)
        row["batch"] = 1
        row["batch_purpose"] = "label_artifact_audit"
        rows.append(row)
    return rows


def _collect_top5_union(
    per_query_rows: list[dict[str, Any]],
    qids: tuple[str, ...] = RETRIEVAL_MISS_QIDS,
) -> dict[tuple[str, int], dict[str, Any]]:
    collected: dict[tuple[str, int], dict[str, Any]] = {}
    modes_by_pair: dict[tuple[str, int], set[str]] = defaultdict(set)

    for mode_row in per_query_rows:
        qid = mode_row.get("qid")
        if qid not in qids:
            continue
        mode = mode_row.get("mode")
        if not isinstance(mode, str):
            raise ValueError(f"{qid} per-query row has missing mode")
        top = mode_row.get("top")
        if not isinstance(top, list):
            raise ValueError(f"{qid}/{mode} top must be a list")
        for top_row in top[:5]:
            if not isinstance(top_row, dict):
                raise ValueError(f"{qid}/{mode} top rows must be objects")
            tmdb_id = top_row.get("tmdb_id")
            if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool):
                raise ValueError(f"{qid}/{mode} top row tmdb_id must be an integer")
            key = (qid, tmdb_id)
            modes_by_pair[key].add(mode)
            collected.setdefault(
                key,
                {
                    "title": top_row.get("title"),
                    "year": top_row.get("year"),
                    "silver_grade": top_row.get("grade"),
                    "silver_confidence": top_row.get("confidence"),
                },
            )

    for key, modes in modes_by_pair.items():
        collected[key]["in_top_5_of"] = sorted(modes)
    return collected


def _build_union_batch(
    per_query_rows: list[dict[str, Any]],
    *,
    qids: tuple[str, ...],
    queries: dict[str, str],
    candidates: dict[tuple[str, int], dict[str, Any]],
    silver_reasons: dict[tuple[str, int], Any],
    batch: int,
    batch_purpose: str,
    flag_reason: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, top_fields in _collect_top5_union(per_query_rows, qids).items():
        qid, tmdb_id = key
        if qid not in queries:
            raise ValueError(f"missing query text for {qid}")
        if key not in candidates:
            raise ValueError(f"missing candidate metadata for {qid}:{tmdb_id}")

        candidate = candidates[key]
        in_top_5_of = top_fields["in_top_5_of"]
        row = {
            "qid": qid,
            "tmdb_id": tmdb_id,
            "query": queries[qid],
            "title": top_fields["title"],
            "year": top_fields["year"],
            "overview": candidate.get("overview"),
            "genres": candidate.get("genres"),
            "silver_grade": top_fields["silver_grade"],
            "silver_confidence": top_fields["silver_confidence"],
            "silver_reason": silver_reasons.get(key),
            "in_top_5_of": in_top_5_of,
            "flag_reasons": [flag_reason]
            + [f"top_5_{mode}" for mode in in_top_5_of],
            "gold_grade": None,
            "gold_notes": None,
            "batch": batch,
            "batch_purpose": batch_purpose,
        }
        rows.append(row)
    return rows


def _build_batch2(
    per_query_rows: list[dict[str, Any]],
    *,
    queries: dict[str, str],
    candidates: dict[tuple[str, int], dict[str, Any]],
    silver_reasons: dict[tuple[str, int], Any],
) -> list[dict[str, Any]]:
    return _build_union_batch(
        per_query_rows,
        qids=RETRIEVAL_MISS_QIDS,
        queries=queries,
        candidates=candidates,
        silver_reasons=silver_reasons,
        batch=2,
        batch_purpose="retrieval_miss_audit",
        flag_reason="regrade_q03_q08",
    )


def _build_batch3(
    per_query_rows: list[dict[str, Any]],
    *,
    queries: dict[str, str],
    candidates: dict[tuple[str, int], dict[str, Any]],
    silver_reasons: dict[tuple[str, int], Any],
) -> list[dict[str, Any]]:
    return _build_union_batch(
        per_query_rows,
        qids=Q07_FOLLOWUP_QIDS,
        queries=queries,
        candidates=candidates,
        silver_reasons=silver_reasons,
        batch=3,
        batch_purpose="ql_01_label_followup",
        flag_reason="regrade_q07",
    )


def _build_manifest(run_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows_by_batch = Counter(str(row["batch"]) for row in rows)
    rows_by_qid = Counter(str(row["qid"]) for row in rows)
    snapshot: dict[str, Any] = {}

    for row in rows:
        key = f"{row['qid']}:{row['tmdb_id']}"
        if key in snapshot:
            raise ValueError(f"duplicate row for {key}")
        snapshot[key] = row.get("silver_grade")

    return {
        "run_id": run_id,
        "built_from": {
            "q12_q13_sheet": "analysis/audit_silver_labels/review_sheet.jsonl",
            "q03_q08_source": "analysis/error_report/per_query_mode.jsonl",
        },
        "rows_total": len(rows),
        "rows_by_batch": dict(sorted(rows_by_batch.items())),
        "rows_by_qid": dict(sorted(rows_by_qid.items())),
        "silver_grade_snapshot": snapshot,
    }


def build_regrade_sheet(run_id: str) -> tuple[Path, Path]:
    run_dir = _run_io.run_dir(run_id)
    regrade_dir = run_dir / "analysis" / "regrade"
    sheet_path = regrade_dir / "regrade_sheet.jsonl"
    manifest_path = regrade_dir / "regrade_manifest.json"

    if sheet_path.exists():
        raise FileExistsError(OVERWRITE_MESSAGE)

    review_rows = _load_jsonl(
        run_dir / "analysis" / "audit_silver_labels" / "review_sheet.jsonl"
    )
    per_query_rows = _load_jsonl(
        run_dir / "analysis" / "error_report" / "per_query_mode.jsonl"
    )
    queries = _load_queries(_run_io.EVAL_DIR / "queries" / "v1.jsonl")
    candidates = _load_candidates(run_dir / "candidates.jsonl")
    silver_reasons = _load_silver_reasons(run_dir / "silver_labels.jsonl")

    rows = _build_batch1(review_rows)
    rows.extend(
        _build_batch2(
            per_query_rows,
            queries=queries,
            candidates=candidates,
            silver_reasons=silver_reasons,
        )
    )
    rows.sort(key=lambda row: (row["batch"], row["qid"], row["tmdb_id"]))

    for index, row in enumerate(rows, start=1):
        if set(row) != set(ROW_KEYS):
            raise ValueError(f"output row {index} has unexpected keys")

    manifest = _build_manifest(run_id, rows)
    regrade_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(sheet_path, rows)
    _run_io._atomic_write_json(manifest_path, manifest)
    return sheet_path, manifest_path


def add_q07_batch(run_id: str) -> tuple[Path, Path]:
    run_dir = _run_io.run_dir(run_id)
    regrade_dir = run_dir / "analysis" / "regrade"
    sheet_path = regrade_dir / "regrade_sheet.jsonl"
    manifest_path = regrade_dir / "regrade_manifest.json"

    if not sheet_path.exists():
        raise FileNotFoundError(SHEET_NOT_FOUND_MESSAGE)

    existing_rows = _load_jsonl(sheet_path)
    if any(row.get("batch") == 3 for row in existing_rows):
        raise FileExistsError(Q07_BATCH_PRESENT_MESSAGE)

    with open(sheet_path, "rb") as handle:
        handle.seek(-1, 2)
        last_byte = handle.read(1)
    needs_newline = last_byte != b"\n"

    per_query_rows = _load_jsonl(
        run_dir / "analysis" / "error_report" / "per_query_mode.jsonl"
    )
    queries = _load_queries(_run_io.EVAL_DIR / "queries" / "v1.jsonl")
    candidates = _load_candidates(run_dir / "candidates.jsonl")
    silver_reasons = _load_silver_reasons(run_dir / "silver_labels.jsonl")

    batch3_rows = _build_batch3(
        per_query_rows,
        queries=queries,
        candidates=candidates,
        silver_reasons=silver_reasons,
    )
    batch3_rows.sort(key=lambda row: (row["qid"], row["tmdb_id"]))

    with open(sheet_path, "a", encoding="utf-8", newline="\n") as handle:
        if needs_newline:
            handle.write("\n")
        for row in batch3_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    all_rows = existing_rows + batch3_rows
    manifest = _build_manifest(run_id, all_rows)
    _run_io._atomic_write_json(manifest_path, manifest)
    return sheet_path, manifest_path


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a frozen human re-grade sheet from existing artifacts."
    )
    parser.add_argument(
        "--run",
        default=None,
        help="Eval run id. Defaults to eval.scripts._run_io.latest_run().",
    )
    parser.add_argument(
        "--add-q07-batch",
        action="store_true",
        help="Add q07 batch 3 to existing regrade sheet (RG-03 A1).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id = args.run or _run_io.latest_run()
    try:
        if args.add_q07_batch:
            sheet_path, manifest_path = add_q07_batch(run_id)
        else:
            sheet_path, manifest_path = build_regrade_sheet(run_id)
    except (FileExistsError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"wrote {sheet_path}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
