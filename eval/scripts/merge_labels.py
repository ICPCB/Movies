"""Merge human gold labels over silver labels and recompute metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from eval.scripts import _run_io, build_regrade_sheet, check_regrade_sheet, compute_metrics


GRADE_VALUES = {0, 1, 2, 3}
GOLD_LABEL_KEYS = (
    "qid",
    "tmdb_id",
    "grade",
    "label_source",
    "silver_grade",
    "gold_grade",
    "gold_notes",
)


class MergeLabelsError(ValueError):
    """Raised when gold/silver label merging must stop before writing."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise MergeLabelsError(f"{path.name} missing") from exc
    if not isinstance(value, dict):
        raise MergeLabelsError(f"{path.name} must contain a JSON object")
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
                raise MergeLabelsError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise MergeLabelsError(f"{path}:{line_number}: row must be an object")
            rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    lines = [json.dumps(dict(row), ensure_ascii=False) for row in rows]
    text = "\n".join(lines)
    if text:
        text += "\n"
    _run_io._atomic_write_text(path, text)


def _ensure_fresh_complete_check(
    *,
    run_id: str,
    sheet_path: Path,
    check_path: Path,
) -> dict[str, Any]:
    if not check_path.exists():
        raise MergeLabelsError(
            "regrade_check.json missing or complete:false — run RG-02 first"
        )

    check = _read_json(check_path)
    if check.get("run_id") != run_id or check.get("complete") is not True:
        raise MergeLabelsError(
            "regrade_check.json missing or complete:false — run RG-02 first"
        )
    if check_path.stat().st_mtime < sheet_path.stat().st_mtime:
        raise MergeLabelsError("regrade_check.json is stale — re-run RG-02")
    return check


def _validate_regrade_rows(
    *,
    rows: list[dict[str, Any]],
    manifest: Mapping[str, Any],
) -> None:
    rows_total = manifest.get("rows_total")
    if not isinstance(rows_total, int) or isinstance(rows_total, bool):
        raise MergeLabelsError("regrade_manifest.json rows_total must be an integer")
    if len(rows) != rows_total:
        raise MergeLabelsError("regrade_sheet.jsonl row count differs from manifest")

    seen: set[tuple[str, int]] = set()
    for index, row in enumerate(rows, start=1):
        qid = row.get("qid")
        tmdb_id = row.get("tmdb_id")
        if not isinstance(qid, str):
            raise MergeLabelsError(f"row {index}: qid must be a string")
        if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool):
            raise MergeLabelsError(f"row {index}: tmdb_id must be an integer")
        key = (qid, tmdb_id)
        if key in seen:
            raise MergeLabelsError(f"row {index}: duplicate gold label for {qid}:{tmdb_id}")
        seen.add(key)

        gold_grade = row.get("gold_grade")
        if (
            not isinstance(gold_grade, int)
            or isinstance(gold_grade, bool)
            or gold_grade not in GRADE_VALUES
        ):
            raise MergeLabelsError(
                f"row {index} ({qid}:{tmdb_id}): gold_grade must be one of 0, 1, 2, 3"
            )


def _gold_map(
    rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, int], tuple[int, Any]]:
    result: dict[tuple[str, int], tuple[int, Any]] = {}
    for row in rows:
        key = (str(row["qid"]), int(row["tmdb_id"]))
        result[key] = (int(row["gold_grade"]), row.get("gold_notes"))
    return result


def _merge_gold_over_silver(
    *,
    silver_rows: list[Mapping[str, Any]],
    gold_by_key: Mapping[tuple[str, int], tuple[int, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_silver_keys: set[tuple[str, int]] = set()

    for silver in silver_rows:
        key = (str(silver["qid"]), int(silver["tmdb_id"]))
        seen_silver_keys.add(key)
        silver_grade = silver.get("grade")
        if key in gold_by_key:
            gold_grade, gold_notes = gold_by_key[key]
            row = {
                "qid": key[0],
                "tmdb_id": key[1],
                "grade": gold_grade,
                "label_source": "gold",
                "silver_grade": silver_grade,
                "gold_grade": gold_grade,
                "gold_notes": gold_notes,
            }
        else:
            row = {
                "qid": key[0],
                "tmdb_id": key[1],
                "grade": silver_grade,
                "label_source": "silver",
                "silver_grade": silver_grade,
                "gold_grade": None,
                "gold_notes": None,
            }
        merged.append(row)

    for qid, tmdb_id in sorted(set(gold_by_key) - seen_silver_keys):
        gold_grade, gold_notes = gold_by_key[(qid, tmdb_id)]
        merged.append(
            {
                "qid": qid,
                "tmdb_id": tmdb_id,
                "grade": gold_grade,
                "label_source": "gold",
                "silver_grade": None,
                "gold_grade": gold_grade,
                "gold_notes": gold_notes,
            }
        )

    for index, row in enumerate(merged, start=1):
        if tuple(row) != GOLD_LABEL_KEYS:
            raise MergeLabelsError(f"merged row {index}: unexpected gold label keys")
        if row["label_source"] == "gold":
            if row["grade"] != row["gold_grade"] or row["gold_grade"] is None:
                raise MergeLabelsError(f"merged row {index}: invalid gold invariant")
        elif row["label_source"] == "silver":
            if row["grade"] != row["silver_grade"] or row["gold_grade"] is not None:
                raise MergeLabelsError(f"merged row {index}: invalid silver invariant")
        else:
            raise MergeLabelsError(f"merged row {index}: invalid label_source")

    return merged


def _ensure_no_top5_nulls(
    *,
    candidates: Iterable[Mapping[str, Any]],
    labels: Mapping[tuple[str, int], Any],
) -> None:
    for candidate in candidates:
        qid = str(candidate["qid"])
        tmdb_id = int(candidate["tmdb_id"])
        per_mode = candidate.get("per_mode", {})
        if not isinstance(per_mode, dict):
            continue
        for mode in compute_metrics.MODE_ORDER:
            mode_data = per_mode.get(mode)
            if mode_data is None:
                continue
            rank = int(mode_data["rank"])
            if rank < compute_metrics.PRIMARY_K and labels.get((qid, tmdb_id)) is None:
                raise MergeLabelsError(
                    f"merged label feeding top-5 is null: ({qid}, {mode}, {tmdb_id})"
                )


def _label_provenance(
    merged_rows: Iterable[Mapping[str, Any]],
    gold_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = list(merged_rows)
    gold_count = sum(1 for row in rows if row["label_source"] == "gold")
    silver_count = sum(1 for row in rows if row["label_source"] == "silver")
    return {
        "gold": gold_count,
        "silver": silver_count,
        "total": len(rows),
        "regraded_queries": sorted({str(row["qid"]) for row in gold_rows}),
    }


def merge_labels(
    *,
    run_id: str | None = None,
    queries_path: Path | None = None,
    bootstrap_b: int = 1000,
    seed: int = 42,
) -> tuple[str, Path, Path, dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    run_path = _run_io.run_dir(actual_run_id)
    regrade_dir = run_path / "analysis" / "regrade"
    sheet_path = regrade_dir / "regrade_sheet.jsonl"
    manifest_path = regrade_dir / "regrade_manifest.json"
    check_path = regrade_dir / "regrade_check.json"

    # Keep these imports as library references; RG-02 owns generation, ML-01 only reads.
    _ = build_regrade_sheet.ROW_KEYS, check_regrade_sheet.GRADE_VALUES

    _ensure_fresh_complete_check(
        run_id=actual_run_id,
        sheet_path=sheet_path,
        check_path=check_path,
    )

    manifest = _read_json(manifest_path)
    if manifest.get("run_id") != actual_run_id:
        raise MergeLabelsError("regrade_manifest.json run_id does not match requested run")
    regrade_rows = _load_jsonl(sheet_path)
    _validate_regrade_rows(rows=regrade_rows, manifest=manifest)

    gold_by_key = _gold_map(regrade_rows)
    silver_rows = compute_metrics._load_silver_labels(run_path / "silver_labels.jsonl")
    merged_rows = _merge_gold_over_silver(
        silver_rows=silver_rows,
        gold_by_key=gold_by_key,
    )

    candidates = compute_metrics._load_candidates(run_path / "candidates.jsonl")
    label_by_key = {
        (str(row["qid"]), int(row["tmdb_id"])): row["grade"] for row in merged_rows
    }
    _ensure_no_top5_nulls(candidates=candidates, labels=label_by_key)

    queries_file = queries_path or (_run_io.EVAL_DIR / "queries" / "all.jsonl")
    queries = compute_metrics._load_queries(queries_file)
    metrics = compute_metrics.compute_metrics(
        run_id=actual_run_id,
        candidates=candidates,
        silver_labels=merged_rows,
        query_records=queries,
        bootstrap_b=bootstrap_b,
        seed=seed,
    )

    provenance = _label_provenance(merged_rows, regrade_rows)
    metrics["provisional"] = False
    metrics["label_source"] = "merged_gold_over_silver"
    metrics["label_provenance"] = provenance
    metrics["built_from"] = {
        "silver_labels": "silver_labels.jsonl",
        "gold_labels": "gold_labels.jsonl",
        "regrade_sheet": "analysis/regrade/regrade_sheet.jsonl",
    }

    gold_path = run_path / "gold_labels.jsonl"
    metrics_path = run_path / "metrics.json"
    _write_jsonl(gold_path, merged_rows)
    _run_io._atomic_write_json(metrics_path, metrics)
    return actual_run_id, gold_path, metrics_path, provenance


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge CineMatch gold re-grade labels over silver labels."
    )
    parser.add_argument(
        "--run",
        default=None,
        help="Eval run id. Defaults to eval.scripts._run_io.latest_run().",
    )
    parser.add_argument(
        "--queries",
        default=None,
        type=Path,
        help="Path to queries JSONL. Default: eval/queries/all.jsonl",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, gold_path, metrics_path, provenance = merge_labels(
            run_id=args.run,
            queries_path=args.queries,
        )
    except (
        MergeLabelsError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"gold_labels={gold_path}")
    print(f"metrics={metrics_path}")
    print(
        f"merged {provenance['gold']} gold over "
        f"{provenance['total']} silver; metrics.json provisional=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
