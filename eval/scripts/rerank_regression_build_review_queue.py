"""Build the rerank-regression missing-label human review queue.

This sidecar is intentionally offline and deterministic. It only reads existing
run artifacts and writes queue files for later human grading.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / "eval" / "runs"
ANALYSIS_SUBDIR = Path("analysis") / "rerank_regression"

MANIFEST_FILE = "missing_label_manifest.json"
SCORE_TOP15_FILE = "score_stage_top15.json"
SNAPSHOT_FILE = "full_set_pool_snapshot.json"
GOLD_LABELS_FILE = "gold_labels.jsonl"
QUEUE_JSONL_FILE = "missing_label_review_queue.jsonl"
QUEUE_CSV_FILE = "missing_label_review_queue.csv"
QUEUE_SUMMARY_FILE = "missing_label_review_queue_summary.txt"

QUEUE_FIELDS = sorted(
    [
        "document_text_excerpt",
        "grade",
        "grader_notes",
        "models_affected",
        "modes_affected",
        "movie_key",
        "qid",
        "query_text",
        "queue_position",
        "ranks_observed",
        "source_artifact_paths",
        "source_top_fields",
        "title",
        "tmdb_id",
    ]
)

RankKey = Tuple[str, str, int]
LabelKey = Tuple[str, int]


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _read_jsonl_objects(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
            rows.append(row)
    return rows


def _artifact_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _coerce_tmdb_id(value: Any) -> int:
    return int(value)


def _gold_labeled_keys(gold_rows: Iterable[Mapping[str, Any]]) -> Set[LabelKey]:
    keys: Set[LabelKey] = set()
    for row in gold_rows:
        if row.get("gold_grade") is None:
            continue
        keys.add((str(row["qid"]), _coerce_tmdb_id(row["tmdb_id"])))
    return keys


def _query_text_by_qid(snapshot: Mapping[str, Any]) -> Dict[str, str]:
    query_text: Dict[str, str] = {}
    for query in snapshot.get("queries", []):
        qid = str(query.get("qid", ""))
        if qid:
            query_text[qid] = str(query.get("query", ""))
    return query_text


def _normalize_excerpt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")[:500]


def _excerpt_by_key(snapshot: Mapping[str, Any]) -> Dict[LabelKey, str]:
    excerpts: Dict[LabelKey, str] = {}
    for query in snapshot.get("queries", []):
        qid = str(query.get("qid", ""))
        modes = query.get("modes", {})
        if not isinstance(modes, Mapping):
            continue
        for mode in ("advanced", "hybrid"):
            mode_payload = modes.get(mode, {})
            if not isinstance(mode_payload, Mapping):
                continue
            pool = mode_payload.get("pool") or []
            for movie in pool:
                if not isinstance(movie, Mapping) or "tmdb_id" not in movie:
                    continue
                key = (qid, _coerce_tmdb_id(movie["tmdb_id"]))
                if key not in excerpts:
                    excerpts[key] = _normalize_excerpt(movie.get("document_text"))
    return excerpts


def _ordered_source_paths(manifest_path: Path, source_paths: Iterable[str]) -> List[str]:
    ordered: List[str] = []
    seen: Set[str] = set()
    for path in [_artifact_path(manifest_path), *sorted(source_paths)]:
        if path and path not in seen:
            ordered.append(path)
            seen.add(path)
    return ordered


def build_review_queue(
    *,
    manifest: Mapping[str, Any],
    score_top15: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    gold_rows: Sequence[Mapping[str, Any]],
    manifest_path: Path,
) -> List[Dict[str, Any]]:
    if not isinstance(score_top15, Mapping):
        raise ValueError("score_top15 must be a JSON object")
    missing_labels = manifest.get("missing_labels")
    if not isinstance(missing_labels, list):
        raise ValueError("manifest missing_labels must be a list")

    excluded = _gold_labeled_keys(gold_rows)
    query_text = _query_text_by_qid(snapshot)
    excerpts = _excerpt_by_key(snapshot)

    grouped: Dict[LabelKey, Dict[str, Any]] = {}
    for row in missing_labels:
        if not isinstance(row, Mapping):
            raise ValueError("manifest missing_labels rows must be objects")
        key = (str(row["qid"]), _coerce_tmdb_id(row["tmdb_id"]))
        if key not in grouped:
            grouped[key] = {
                "qid": key[0],
                "tmdb_id": key[1],
                "movie_key": str(row.get("movie_key", "")),
                "title": str(row.get("title", "")),
                "modes_affected": set(),
                "models_affected": set(),
                "ranks_observed": set(),
                "source_artifact_paths": set(),
                "source_top_fields": set(),
            }
        entry = grouped[key]
        if not entry["movie_key"] and row.get("movie_key") is not None:
            entry["movie_key"] = str(row.get("movie_key", ""))
        if not entry["title"] and row.get("title") is not None:
            entry["title"] = str(row.get("title", ""))
        entry["modes_affected"].add(str(row["mode"]))
        entry["models_affected"].add(str(row["model"]))
        entry["ranks_observed"].add(
            (str(row["mode"]), str(row["model"]), int(row["rank"]))
        )
        if row.get("source_artifact_path"):
            entry["source_artifact_paths"].add(str(row["source_artifact_path"]))
        if row.get("source_top_field"):
            entry["source_top_fields"].add(str(row["source_top_field"]))

    rows: List[Dict[str, Any]] = []
    for key in sorted(grouped):
        if key in excluded:
            continue
        entry = grouped[key]
        ranks_observed = [
            {"mode": mode, "model": model, "rank": rank}
            for mode, model, rank in sorted(entry["ranks_observed"])
        ]
        rows.append(
            {
                "document_text_excerpt": excerpts.get(key, ""),
                "grade": None,
                "grader_notes": None,
                "models_affected": sorted(entry["models_affected"]),
                "modes_affected": sorted(entry["modes_affected"]),
                "movie_key": entry["movie_key"],
                "qid": key[0],
                "query_text": query_text.get(key[0], ""),
                "queue_position": 0,
                "ranks_observed": ranks_observed,
                "source_artifact_paths": _ordered_source_paths(
                    manifest_path, entry["source_artifact_paths"]
                ),
                "source_top_fields": sorted(entry["source_top_fields"]),
                "title": entry["title"],
                "tmdb_id": key[1],
            }
        )

    for index, row in enumerate(rows):
        row["queue_position"] = index
    return rows


def build_review_queue_from_paths(
    *,
    manifest_path: Path,
    score_top15_path: Path,
    snapshot_path: Path,
    gold_labels_path: Path,
) -> List[Dict[str, Any]]:
    manifest = _read_json_object(manifest_path)
    score_top15 = _read_json_object(score_top15_path)
    snapshot = _read_json_object(snapshot_path)
    gold_rows = _read_jsonl_objects(gold_labels_path)
    return build_review_queue(
        manifest=manifest,
        score_top15=score_top15,
        snapshot=snapshot,
        gold_rows=gold_rows,
        manifest_path=manifest_path,
    )


def _tmp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(path)
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _jsonl_text(rows: Sequence[Mapping[str, Any]]) -> str:
    return "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows
    )


def _csv_value(field: str, value: Any) -> str:
    if value is None:
        return ""
    if field == "ranks_observed":
        return "|".join(
            f"{rank['mode']}:{rank['model']}:{rank['rank']}" for rank in value
        )
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return str(value)


def _atomic_write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(path)
    try:
        with tmp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=QUEUE_FIELDS,
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {field: _csv_value(field, row[field]) for field in QUEUE_FIELDS}
                )
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def build_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    counts_by_qid: Counter[str] = Counter()
    counts_by_mode: Counter[str] = Counter()
    counts_by_model: Counter[str] = Counter()
    rows_with_excerpt = 0

    for row in rows:
        counts_by_qid[str(row["qid"])] += 1
        for mode in row["modes_affected"]:
            counts_by_mode[str(mode)] += 1
        for model in row["models_affected"]:
            counts_by_model[str(model)] += 1
        if row["document_text_excerpt"]:
            rows_with_excerpt += 1

    return {
        "total_rows": len(rows),
        "counts_by_qid": dict(sorted(counts_by_qid.items())),
        "counts_by_mode": dict(sorted(counts_by_mode.items())),
        "counts_by_model": dict(sorted(counts_by_model.items())),
        "rows_with_excerpt": rows_with_excerpt,
        "rows_without_excerpt": len(rows) - rows_with_excerpt,
    }


def _summary_text(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"total_rows={summary['total_rows']}",
            f"counts_by_qid={json.dumps(summary['counts_by_qid'], sort_keys=True)}",
            f"counts_by_mode={json.dumps(summary['counts_by_mode'], sort_keys=True)}",
            f"counts_by_model={json.dumps(summary['counts_by_model'], sort_keys=True)}",
            f"rows_with_excerpt={summary['rows_with_excerpt']}",
            f"rows_without_excerpt={summary['rows_without_excerpt']}",
        ]
    ) + "\n"


def write_review_queue_artifacts(
    *,
    rows: Sequence[Mapping[str, Any]],
    jsonl_path: Path,
    csv_path: Path,
    summary_path: Path,
) -> Dict[str, Any]:
    summary = build_summary(rows)
    _atomic_write_text(jsonl_path, _jsonl_text(rows))
    _atomic_write_csv(csv_path, rows)
    _atomic_write_text(summary_path, _summary_text(summary))
    return summary


def _run_paths(run_id: str) -> Dict[str, Path]:
    run_dir = RUNS_DIR / run_id
    analysis_dir = run_dir / ANALYSIS_SUBDIR
    return {
        "manifest": analysis_dir / MANIFEST_FILE,
        "score_top15": analysis_dir / SCORE_TOP15_FILE,
        "snapshot": analysis_dir / SNAPSHOT_FILE,
        "gold_labels": run_dir / GOLD_LABELS_FILE,
        "jsonl": analysis_dir / QUEUE_JSONL_FILE,
        "csv": analysis_dir / QUEUE_CSV_FILE,
        "summary": analysis_dir / QUEUE_SUMMARY_FILE,
    }


def persist_review_queue(run_id: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    paths = _run_paths(run_id)
    rows = build_review_queue_from_paths(
        manifest_path=paths["manifest"],
        score_top15_path=paths["score_top15"],
        snapshot_path=paths["snapshot"],
        gold_labels_path=paths["gold_labels"],
    )
    summary = write_review_queue_artifacts(
        rows=rows,
        jsonl_path=paths["jsonl"],
        csv_path=paths["csv"],
        summary_path=paths["summary"],
    )
    return rows, summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the rerank-regression missing-label review queue."
    )
    parser.add_argument("--run", required=True, help="Run id under eval/runs/")
    args = parser.parse_args(argv)

    _rows, summary = persist_review_queue(args.run)
    print(
        "review_queue "
        f"run={args.run} "
        f"total_rows={summary['total_rows']} "
        f"rows_with_excerpt={summary['rows_with_excerpt']} "
        f"rows_without_excerpt={summary['rows_without_excerpt']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
