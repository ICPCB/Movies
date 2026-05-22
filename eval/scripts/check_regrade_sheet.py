"""Validate a human-filled re-grade sheet and report silver/gold agreement."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from eval.scripts import _run_io, build_regrade_sheet


GOLD_KEYS = {"gold_grade", "gold_notes"}
GRADE_VALUES = {0, 1, 2, 3}
PREFERRED_QID_ORDER = ("q12", "q13", "q03", "q08", "q07")


class CheckError(ValueError):
    """Raised when the re-grade sheet fails structural validation."""


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise CheckError(f"{path} must contain a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CheckError(f"row {line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise CheckError(f"row {line_number}: JSONL row must be an object")
            rows.append(value)
    return rows


def _row_key(row: dict[str, Any], index: int) -> str:
    qid = row.get("qid")
    tmdb_id = row.get("tmdb_id")
    if not isinstance(qid, str):
        raise CheckError(f"row {index}: qid must be a string")
    if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool):
        raise CheckError(f"row {index}: tmdb_id must be an integer")
    return f"{qid}:{tmdb_id}"


def _expected_rows(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    built_from = manifest.get("built_from")
    if not isinstance(built_from, dict):
        raise CheckError("regrade_manifest.json built_from must be an object")

    review_rel = built_from.get(
        "q12_q13_sheet",
        "analysis/audit_silver_labels/review_sheet.jsonl",
    )
    per_query_rel = built_from.get(
        "q03_q08_source",
        "analysis/error_report/per_query_mode.jsonl",
    )
    if not isinstance(review_rel, str) or not isinstance(per_query_rel, str):
        raise CheckError("regrade_manifest.json built_from paths must be strings")

    review_rows = build_regrade_sheet._load_jsonl(run_dir / review_rel)
    per_query_rows = build_regrade_sheet._load_jsonl(run_dir / per_query_rel)
    queries = build_regrade_sheet._load_queries(_run_io.EVAL_DIR / "queries" / "v1.jsonl")
    candidates = build_regrade_sheet._load_candidates(run_dir / "candidates.jsonl")
    silver_reasons = build_regrade_sheet._load_silver_reasons(
        run_dir / "silver_labels.jsonl"
    )

    rows = build_regrade_sheet._build_batch1(review_rows)
    rows.extend(
        build_regrade_sheet._build_batch2(
            per_query_rows,
            queries=queries,
            candidates=candidates,
            silver_reasons=silver_reasons,
        )
    )

    rows_by_batch = manifest.get("rows_by_batch", {})
    if "3" in rows_by_batch:
        rows.extend(
            build_regrade_sheet._build_batch3(
                per_query_rows,
                queries=queries,
                candidates=candidates,
                silver_reasons=silver_reasons,
            )
        )

    rows.sort(key=lambda row: (row["batch"], row["qid"], row["tmdb_id"]))
    return rows


def _validate_manifest(manifest: dict[str, Any], run_id: str) -> dict[str, Any]:
    if manifest.get("run_id") != run_id:
        raise CheckError("regrade_manifest.json run_id does not match requested run")
    snapshot = manifest.get("silver_grade_snapshot")
    if not isinstance(snapshot, dict):
        raise CheckError(
            "regrade_manifest.json silver_grade_snapshot must be an object"
        )
    rows_total = manifest.get("rows_total")
    if not isinstance(rows_total, int) or isinstance(rows_total, bool):
        raise CheckError("regrade_manifest.json rows_total must be an integer")
    if rows_total != len(snapshot):
        raise CheckError(
            "regrade_manifest.json rows_total does not match "
            "silver_grade_snapshot"
        )
    rows_by_batch = manifest.get("rows_by_batch")
    if not isinstance(rows_by_batch, dict):
        raise CheckError("regrade_manifest.json rows_by_batch must be an object")
    rows_by_qid = manifest.get("rows_by_qid")
    if not isinstance(rows_by_qid, dict):
        raise CheckError("regrade_manifest.json rows_by_qid must be an object")
    return snapshot


def _compare_structure(
    *,
    rows: list[dict[str, Any]],
    expected_rows: list[dict[str, Any]],
    snapshot: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    expected_keys = list(snapshot)
    if len(rows) != len(expected_keys):
        if len(rows) < len(expected_keys):
            missing_index = len(rows) + 1
            raise CheckError(
                "row count differs from manifest: "
                f"missing row {missing_index} ({expected_keys[len(rows)]})"
            )
        raise CheckError(
            "row count differs from manifest: "
            f"added row {len(expected_keys) + 1}"
        )
    if len(expected_rows) != len(expected_keys):
        raise CheckError(
            "reconstructed RG-01 row count differs from regrade_manifest.json"
        )

    manifest_batch_counts = {
        str(key): value for key, value in manifest["rows_by_batch"].items()
    }
    actual_batch_counts = Counter(str(row.get("batch")) for row in rows)
    batch_keys = set(manifest_batch_counts) | set(actual_batch_counts)
    if any(
        actual_batch_counts.get(key, 0) != manifest_batch_counts.get(key, 0)
        for key in batch_keys
    ):
        raise CheckError("row count differs from manifest rows_by_batch")

    manifest_qid_counts = {
        str(key): value for key, value in manifest["rows_by_qid"].items()
    }
    actual_qid_counts = Counter(str(row.get("qid")) for row in rows)
    qid_keys = set(manifest_qid_counts) | set(actual_qid_counts)
    if any(
        actual_qid_counts.get(key, 0) != manifest_qid_counts.get(key, 0)
        for key in qid_keys
    ):
        raise CheckError("row count differs from manifest rows_by_qid")

    required_keys = set(build_regrade_sheet.ROW_KEYS)
    for index, (row, expected_row, expected_key) in enumerate(
        zip(rows, expected_rows, expected_keys),
        start=1,
    ):
        row_key = _row_key(row, index)
        if row_key != expected_key:
            raise CheckError(
                f"row {index}: expected {expected_key} from manifest, got {row_key}"
            )
        if set(row) != required_keys:
            unexpected = sorted(set(row) ^ required_keys)
            raise CheckError(f"row {index}: unexpected keys: {unexpected}")
        if row.get("silver_grade") != snapshot[expected_key]:
            raise CheckError(
                f"row {index} ({row_key}): silver_grade differs from manifest"
            )
        expected_non_gold = {
            key: value for key, value in expected_row.items() if key not in GOLD_KEYS
        }
        actual_non_gold = {
            key: value for key, value in row.items() if key not in GOLD_KEYS
        }
        if actual_non_gold != expected_non_gold:
            for key in sorted(expected_non_gold):
                if actual_non_gold.get(key) != expected_non_gold[key]:
                    raise CheckError(
                        f"row {index} ({row_key}): non-gold field {key} "
                        "differs from RG-01 output"
                    )
            raise CheckError(f"row {index} ({row_key}): non-gold fields differ")


def _validate_gold_fields(rows: Iterable[dict[str, Any]]) -> None:
    for index, row in enumerate(rows, start=1):
        row_key = _row_key(row, index)
        gold_grade = row.get("gold_grade")
        silver_grade = row.get("silver_grade")
        if gold_grade is not None:
            if (
                not isinstance(gold_grade, int)
                or isinstance(gold_grade, bool)
                or gold_grade not in GRADE_VALUES
            ):
                raise CheckError(
                    f"row {index} ({row_key}): gold_grade must be one of 0, 1, 2, 3"
                )
            if gold_grade != silver_grade:
                gold_notes = row.get("gold_notes")
                if not isinstance(gold_notes, str) or not gold_notes.strip():
                    raise CheckError(
                        f"row {index} ({row_key}): gold_notes must be a "
                        "non-empty string when gold_grade differs from silver_grade"
                    )


def _qid_order(manifest: dict[str, Any]) -> list[str]:
    manifest_qids = [str(qid) for qid in manifest["rows_by_qid"]]
    ordered = [qid for qid in PREFERRED_QID_ORDER if qid in manifest_qids]
    ordered.extend(qid for qid in manifest_qids if qid not in ordered)
    return ordered


def _grade_for_diff(silver_grade: Any) -> int:
    if silver_grade is None:
        return -1
    return int(silver_grade)


def _threshold_crossing(row: dict[str, Any]) -> str | None:
    silver_grade = row.get("silver_grade")
    gold_grade = row.get("gold_grade")
    if gold_grade is None:
        return None

    silver_hit = silver_grade is not None and silver_grade >= 2
    gold_hit = gold_grade >= 2
    silver_strict = silver_grade == 3
    gold_strict = gold_grade == 3

    crossings: list[str] = []
    if silver_hit != gold_hit:
        if gold_hit:
            crossings.append("silver<2->gold>=2")
        else:
            crossings.append("silver>=2->gold<2")
    if silver_strict != gold_strict:
        if gold_strict:
            crossings.append("silver<3->gold==3")
        else:
            crossings.append("silver==3->gold<3")
    if not crossings:
        return None
    return "; ".join(crossings)


def _build_report(
    *,
    run_id: str,
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    rows_total = len(rows)
    filled_rows = [row for row in rows if row.get("gold_grade") is not None]
    complete = len(filled_rows) == rows_total

    pending_by_batch: dict[str, int] = {
        str(batch): 0 for batch in manifest["rows_by_batch"]
    }
    for row in rows:
        if row.get("gold_grade") is None:
            batch = str(row.get("batch"))
            pending_by_batch[batch] = pending_by_batch.get(batch, 0) + 1

    by_qid = {qid: {"filled": 0, "changed": 0} for qid in _qid_order(manifest)}
    for row in filled_rows:
        qid = str(row["qid"])
        by_qid.setdefault(qid, {"filled": 0, "changed": 0})
        by_qid[qid]["filled"] += 1
        if row["gold_grade"] != row["silver_grade"]:
            by_qid[qid]["changed"] += 1

    threshold_crossings = []
    for row in filled_rows:
        crossing = _threshold_crossing(row)
        if crossing is None:
            continue
        threshold_crossings.append(
            {
                "qid": row["qid"],
                "tmdb_id": row["tmdb_id"],
                "silver_grade": row["silver_grade"],
                "gold_grade": row["gold_grade"],
                "crossing": crossing,
            }
        )

    agreement: dict[str, Any] = {
        "exact": None,
        "within_1": None,
        "disagree_ge1_count": 0,
        "disagree_ge2_count": 0,
    }
    if complete and rows_total:
        exact_count = 0
        within_1_count = 0
        disagree_ge1_count = 0
        disagree_ge2_count = 0
        for row in filled_rows:
            silver_grade = row["silver_grade"]
            gold_grade = row["gold_grade"]
            if gold_grade == silver_grade:
                exact_count += 1
            delta = abs(int(gold_grade) - _grade_for_diff(silver_grade))
            if delta <= 1:
                within_1_count += 1
            if delta >= 1:
                disagree_ge1_count += 1
            if delta >= 2:
                disagree_ge2_count += 1
        agreement = {
            "exact": exact_count / rows_total,
            "within_1": within_1_count / rows_total,
            "disagree_ge1_count": disagree_ge1_count,
            "disagree_ge2_count": disagree_ge2_count,
        }

    return {
        "run_id": run_id,
        "complete": complete,
        "rows_total": rows_total,
        "rows_filled": len(filled_rows),
        "pending_by_batch": pending_by_batch,
        "agreement": agreement,
        "threshold_crossings": threshold_crossings,
        "by_qid": by_qid,
    }


def check_regrade_sheet(run_id: str) -> tuple[Path, dict[str, Any]]:
    run_dir = _run_io.run_dir(run_id)
    regrade_dir = run_dir / "analysis" / "regrade"
    sheet_path = regrade_dir / "regrade_sheet.jsonl"
    manifest_path = regrade_dir / "regrade_manifest.json"
    check_path = regrade_dir / "regrade_check.json"

    manifest = _load_json(manifest_path)
    snapshot = _validate_manifest(manifest, run_id)
    rows = _load_jsonl(sheet_path)
    expected_rows = _expected_rows(run_dir, manifest)

    _compare_structure(
        rows=rows,
        expected_rows=expected_rows,
        snapshot=snapshot,
        manifest=manifest,
    )
    _validate_gold_fields(rows)

    report = _build_report(run_id=run_id, rows=rows, manifest=manifest)
    _run_io._atomic_write_json(check_path, report)
    return check_path, report


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a human-filled CineMatch re-grade sheet."
    )
    parser.add_argument(
        "--run",
        default=None,
        help="Eval run id. Defaults to eval.scripts._run_io.latest_run().",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id = args.run or _run_io.latest_run()
    try:
        check_path, report = check_regrade_sheet(run_id)
    except (CheckError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"wrote {check_path}")
    print(f"complete={str(report['complete']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
