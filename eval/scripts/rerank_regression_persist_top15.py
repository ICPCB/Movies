"""Persist score-stage top-15 rerank lists and refresh the missing-label manifest.

This sidecar is intentionally separate from rerank_regression_eval.py.  It
reuses that module's scoring and ranking helpers, writes a deterministic
top-15 artifact, and regenerates the label-extension manifest without rerunning
the regression score stage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


from eval.scripts import _run_io
from eval.scripts import rerank_model_comparison as rmc
from eval.scripts.rerank_regression_eval import (
    ALL_MODES,
    ALT_MODEL_ID,
    ANALYSIS_SUBDIR,
    BASELINE_MODEL,
    BASIC_MODE,
    COMPARISON_FILE,
    MODES_WITH_RERANK,
    POOL_SNAPSHOT_FILE,
    _alt_score_pairs,
    _baseline_score_pairs,
    _build_ranked_top15,
    _coerce_int,
    _coerce_text,
)


SCORE_TOP15_SCHEMA = "rerank-regression-score-stage-top15.v1"
SCORE_TOP15_FILE = "score_stage_top15.json"
MANIFEST_SCHEMA = "rerank-regression-missing-label-manifest.v1"
MANIFEST_FILE = "missing_label_manifest.json"
MANIFEST_SUMMARY_FILE = "missing_label_manifest_summary.txt"
TICKET = "RERANK-REGRESSION-EVAL"
STAGE = "score"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

FlatPair = Tuple[str, str, int, str, str]  # qid, mode, pool index, query, document


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"{path}: JSONL row must be an object")
                rows.append(row)
    return rows


def _stable_json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_text(path, _stable_json_text(payload))


def _artifact_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _analysis_dir(run_id: str) -> Path:
    return _run_io.run_dir(run_id) / ANALYSIS_SUBDIR


def _score_top15_path(run_id: str) -> Path:
    return _analysis_dir(run_id) / SCORE_TOP15_FILE


def _manifest_path(run_id: str) -> Path:
    return _analysis_dir(run_id) / MANIFEST_FILE


def _manifest_summary_path(run_id: str) -> Path:
    return _analysis_dir(run_id) / MANIFEST_SUMMARY_FILE


def _snapshot_path(run_id: str) -> Path:
    return _analysis_dir(run_id) / POOL_SNAPSHOT_FILE


def _comparison_path(run_id: str) -> Path:
    return _analysis_dir(run_id) / COMPARISON_FILE


def _gold_labels_path(run_id: str) -> Path:
    return _run_io.run_dir(run_id) / "gold_labels.jsonl"


def _flatten_pairs(
    snapshot: Mapping[str, Any],
) -> Tuple[List[FlatPair], Dict[Tuple[str, str], List[Mapping[str, Any]]]]:
    flat_pairs: List[FlatPair] = []
    pools_by_qid_mode: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for q in snapshot["queries"]:
        qid = str(q["qid"])
        for mode in MODES_WITH_RERANK:
            arm = q["modes"][mode]
            pool = list(arm["pool"])
            pools_by_qid_mode[(qid, mode)] = pool
            for idx, movie in enumerate(pool):
                flat_pairs.append(
                    (
                        qid,
                        mode,
                        idx,
                        _coerce_text(arm.get("rerank_query", "")),
                        _coerce_text(movie.get("document_text", "")),
                    )
                )
    return flat_pairs, pools_by_qid_mode


def _force_local_model_loading() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _cached_resolve_and_download_model(
    spec: Any,
    libraries: Mapping[str, Any],
) -> Dict[str, Any]:
    local_path = libraries["snapshot_download"](
        repo_id=spec.model_id,
        allow_patterns=list(rmc.SNAPSHOT_ALLOW_PATTERNS),
        local_files_only=True,
    )
    local = Path(local_path)
    return {
        "resolved_revision": local.name,
        "reported_repo_bytes": None,
        "reported_repo_gb": None,
        "local_snapshot_path": str(local),
        "local_snapshot_bytes": rmc.local_tree_size(local),
        "local_snapshot_gb": rmc.bytes_to_gb(rmc.local_tree_size(local)),
    }


@contextmanager
def _local_alt_model_resolution() -> Iterator[None]:
    original = rmc.resolve_and_download_model
    rmc.resolve_and_download_model = _cached_resolve_and_download_model
    try:
        yield
    finally:
        rmc.resolve_and_download_model = original


def _group_scores(
    flat_pairs: Sequence[FlatPair],
    scores: Sequence[float],
) -> Dict[Tuple[str, str], List[float]]:
    if len(scores) != len(flat_pairs):
        raise AssertionError(f"scores={len(scores)} pairs={len(flat_pairs)}")
    grouped: Dict[Tuple[str, str], List[float]] = {}
    for (qid, mode, _idx, _query, _doc), score in zip(flat_pairs, scores):
        grouped.setdefault((qid, mode), []).append(float(score))
    return grouped


def _strip_ranked_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    final_score = float(record.get("final_score", 0.0))
    return {
        "rank": _coerce_int(record.get("rank")),
        "tmdb_id": _coerce_int(record.get("tmdb_id")),
        "movie_key": _coerce_text(record.get("movie_key", "")),
        "title": _coerce_text(record.get("title", "")),
        "rerank_score": float(record.get("rerank_score", final_score)),
        "final_score": final_score,
    }


def _strip_ranked_top15(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [_strip_ranked_record(record) for record in records[:15]]


def _query_by_qid(snapshot: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {str(q["qid"]): q for q in snapshot["queries"]}


def _assert_basic_invariant(
    snapshot: Mapping[str, Any],
    per_qid_top15: Mapping[str, Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]]],
) -> None:
    for q in snapshot["queries"]:
        qid = str(q["qid"])
        expected = _strip_ranked_top15(q["modes"][BASIC_MODE]["baseline_top"])
        baseline_basic = per_qid_top15[qid]["baseline"][BASIC_MODE]
        alt_basic = per_qid_top15[qid]["alt"][BASIC_MODE]
        if baseline_basic != expected or alt_basic != expected:
            raise AssertionError(f"basic invariant failed for {qid}")


def _assert_baseline_self_check(
    snapshot: Mapping[str, Any],
    per_qid_top15: Mapping[str, Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]]],
) -> None:
    by_qid = _query_by_qid(snapshot)
    for qid in ("q05", "q10"):
        if qid not in by_qid:
            raise AssertionError(f"missing {qid} in snapshot")
        for mode in MODES_WITH_RERANK:
            recorded = by_qid[qid]["modes"][mode]["baseline_top"]
            n_compare = min(5, len(recorded))
            recorded_keys = [_coerce_text(row.get("movie_key", "")) for row in recorded[:n_compare]]
            rescored = per_qid_top15[qid]["baseline"][mode][:n_compare]
            rescored_keys = [_coerce_text(row.get("movie_key", "")) for row in rescored]
            if recorded_keys != rescored_keys:
                raise AssertionError(
                    f"baseline self-check mismatch for {qid}/{mode}: "
                    f"recorded={recorded_keys} rescored={rescored_keys}"
                )


def build_score_stage_top15(
    *,
    run_id: str,
    snapshot: Mapping[str, Any],
    source_snapshot_path: Path,
) -> Dict[str, Any]:
    _force_local_model_loading()
    flat_pairs, pools_by_qid_mode = _flatten_pairs(snapshot)
    pair_only = [(query, document) for (_qid, _mode, _idx, query, document) in flat_pairs]
    print(f"[top15] total advanced+hybrid pairs to score: {len(pair_only)}", flush=True)

    baseline_scores_flat = _baseline_score_pairs(pair_only)
    with _local_alt_model_resolution():
        alt_scores_flat, _alt_loader_meta = _alt_score_pairs(pair_only)
    baseline_scores = _group_scores(flat_pairs, baseline_scores_flat)
    alt_scores = _group_scores(flat_pairs, alt_scores_flat)

    per_qid_top15: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}
    for q in snapshot["queries"]:
        qid = str(q["qid"])
        basic_top = _strip_ranked_top15(q["modes"][BASIC_MODE]["baseline_top"])
        per_qid_top15[qid] = {
            "baseline": {BASIC_MODE: deepcopy(basic_top)},
            "alt": {BASIC_MODE: deepcopy(basic_top)},
        }
        for mode in MODES_WITH_RERANK:
            pool = pools_by_qid_mode[(qid, mode)]
            per_qid_top15[qid]["baseline"][mode] = _strip_ranked_top15(
                _build_ranked_top15(pool, baseline_scores[(qid, mode)])
            )
            per_qid_top15[qid]["alt"][mode] = _strip_ranked_top15(
                _build_ranked_top15(pool, alt_scores[(qid, mode)])
            )

    _assert_basic_invariant(snapshot, per_qid_top15)
    _assert_baseline_self_check(snapshot, per_qid_top15)

    return {
        "schema_version": SCORE_TOP15_SCHEMA,
        "ticket": TICKET,
        "stage": STAGE,
        "run_id": run_id,
        "generated_at": _coerce_text(snapshot.get("generated_at") or "1970-01-01T00:00:00Z"),
        "source_snapshot": _artifact_path(source_snapshot_path),
        "models": {
            "baseline": {
                "model_id": BASELINE_MODEL,
                "loader": "sentence_transformers.CrossEncoder",
            },
            "alt": {
                "model_id": ALT_MODEL_ID,
                "loader": "transformers.AutoModelForSequenceClassification",
            },
        },
        "scope": {
            "queries_total": len(snapshot["queries"]),
            "modes": list(ALL_MODES),
            "modes_with_rerank": list(MODES_WITH_RERANK),
        },
        "per_qid_top15": per_qid_top15,
    }


def persist_score_stage_top15(
    *,
    run_id: str,
    snapshot_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], Path]:
    snapshot_path = snapshot_path or _snapshot_path(run_id)
    output_path = output_path or _score_top15_path(run_id)
    snapshot = _read_json_object(snapshot_path)
    artifact = build_score_stage_top15(
        run_id=run_id,
        snapshot=snapshot,
        source_snapshot_path=snapshot_path,
    )
    _atomic_write_json(output_path, artifact)
    print(f"[top15] wrote {_artifact_path(output_path)}", flush=True)
    return artifact, output_path


def _label_keys(labels: Sequence[Mapping[str, Any]]) -> set[Tuple[str, int]]:
    keys: set[Tuple[str, int]] = set()
    for row in labels:
        qid = _coerce_text(row.get("qid", ""))
        tmdb_id = _coerce_int(row.get("tmdb_id"))
        if qid and tmdb_id:
            keys.add((qid, tmdb_id))
    return keys


def _affects(rank: int) -> List[str]:
    if rank < 5:
        return ["@5", "@10", "@15"]
    if rank < 10:
        return ["@10", "@15"]
    return ["@15"]


def _append_missing_rows(
    *,
    rows: List[Dict[str, Any]],
    label_keys: set[Tuple[str, int]],
    qid: str,
    mode: str,
    model: str,
    top_records: Sequence[Mapping[str, Any]],
    source_artifact_path: str,
    source_top_field: str,
) -> None:
    for record in top_records:
        tmdb_id = _coerce_int(record.get("tmdb_id"))
        if (qid, tmdb_id) in label_keys:
            continue
        rank = _coerce_int(record.get("rank"))
        rows.append(
            {
                "qid": qid,
                "mode": mode,
                "model": model,
                "rank": rank,
                "tmdb_id": tmdb_id,
                "movie_key": _coerce_text(record.get("movie_key", "")),
                "title": _coerce_text(record.get("title", "")),
                "affects": _affects(rank),
                "source_artifact_path": source_artifact_path,
                "source_top_field": source_top_field,
            }
        )


def _queries_excluded_null(comparison: Mapping[str, Any]) -> Dict[str, Dict[str, int]]:
    return {
        "baseline": {
            mode: _coerce_int(
                (comparison.get("metrics_baseline_by_mode", {}).get(mode) or {}).get(
                    "queries_excluded_null"
                )
            )
            for mode in ALL_MODES
        },
        "alt": {
            mode: _coerce_int(
                (comparison.get("metrics_alt_by_mode", {}).get(mode) or {}).get(
                    "queries_excluded_null"
                )
            )
            for mode in ALL_MODES
        },
    }


def _sorted_counter(counter: Counter[str]) -> Dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def build_missing_label_manifest(
    *,
    run_id: str,
    snapshot: Mapping[str, Any],
    score_top15: Mapping[str, Any],
    comparison: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    snapshot_path: Path,
    score_top15_path: Path,
    comparison_path: Path,
    gold_labels_path: Path,
) -> Dict[str, Any]:
    label_keys = _label_keys(labels)
    snapshot_rel = _artifact_path(snapshot_path)
    score_rel = _artifact_path(score_top15_path)
    comparison_rel = _artifact_path(comparison_path)
    gold_rel = _artifact_path(gold_labels_path)

    rows: List[Dict[str, Any]] = []
    for q in snapshot["queries"]:
        qid = _coerce_text(q.get("qid", ""))
        basic_top = q["modes"][BASIC_MODE]["baseline_top"]
        for model in ("baseline", "alt"):
            _append_missing_rows(
                rows=rows,
                label_keys=label_keys,
                qid=qid,
                mode=BASIC_MODE,
                model=model,
                top_records=basic_top,
                source_artifact_path=snapshot_rel,
                source_top_field="modes.basic.baseline_top",
            )
        for mode in MODES_WITH_RERANK:
            _append_missing_rows(
                rows=rows,
                label_keys=label_keys,
                qid=qid,
                mode=mode,
                model="baseline",
                top_records=q["modes"][mode]["baseline_top"],
                source_artifact_path=snapshot_rel,
                source_top_field=f"modes.{mode}.baseline_top",
            )
            _append_missing_rows(
                rows=rows,
                label_keys=label_keys,
                qid=qid,
                mode=mode,
                model="alt",
                top_records=score_top15["per_qid_top15"][qid]["alt"][mode],
                source_artifact_path=score_rel,
                source_top_field=f"per_qid_top15.{qid}.alt.{mode}",
            )

    rows.sort(
        key=lambda row: (
            _coerce_text(row["qid"]),
            _coerce_text(row["mode"]),
            _coerce_text(row["model"]),
            _coerce_int(row["rank"]),
            _coerce_int(row["tmdb_id"]),
        )
    )

    counts_by_model = Counter(_coerce_text(row["model"]) for row in rows)
    counts_by_mode = Counter(_coerce_text(row["mode"]) for row in rows)
    counts_by_affects_min_k = Counter(_coerce_text(row["affects"][0]) for row in rows)
    unique_label_keys = {(row["qid"], _coerce_int(row["tmdb_id"])) for row in rows}
    gate = comparison.get("gate_verdict", {})

    return {
        "schema_version": MANIFEST_SCHEMA,
        "run_id": run_id,
        "generated_from": [snapshot_rel, score_rel, comparison_rel, gold_rel],
        "note": (
            "This manifest uses recorded snapshot top-15 lists for basic and baseline "
            "rows, plus score_stage_top15.json for alt advanced/hybrid rows. It does "
            "not create or modify labels."
        ),
        "regression_gate_verdict": _coerce_text(gate.get("value", "")),
        "queries_excluded_null": _queries_excluded_null(comparison),
        "records_total": len(rows),
        "unique_label_keys_total": len(unique_label_keys),
        "counts_by_model": _sorted_counter(counts_by_model),
        "counts_by_mode": _sorted_counter(counts_by_mode),
        "counts_by_affects_min_k": _sorted_counter(counts_by_affects_min_k),
        "missing_labels": rows,
    }


def _manifest_summary_text(manifest: Mapping[str, Any], manifest_path: Path) -> str:
    counts_by_qid = Counter(
        _coerce_text(row["qid"]) for row in manifest.get("missing_labels", [])
    )
    lines = [
        f"manifest={_artifact_path(manifest_path)}",
        f"records_total={manifest['records_total']}",
        f"unique_label_keys_total={manifest['unique_label_keys_total']}",
        "counts_by_model="
        + json.dumps(manifest["counts_by_model"], ensure_ascii=False, sort_keys=True),
        "counts_by_mode="
        + json.dumps(manifest["counts_by_mode"], ensure_ascii=False, sort_keys=True),
        "counts_by_affects_min_k="
        + json.dumps(
            manifest["counts_by_affects_min_k"], ensure_ascii=False, sort_keys=True
        ),
        "counts_by_qid="
        + json.dumps(_sorted_counter(counts_by_qid), ensure_ascii=False, sort_keys=True),
    ]
    return "\n".join(lines) + "\n"


def regenerate_missing_label_manifest(
    *,
    run_id: str,
    snapshot_path: Optional[Path] = None,
    score_top15_path: Optional[Path] = None,
    comparison_path: Optional[Path] = None,
    gold_labels_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    summary_path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], Path, Path]:
    snapshot_path = snapshot_path or _snapshot_path(run_id)
    score_top15_path = score_top15_path or _score_top15_path(run_id)
    comparison_path = comparison_path or _comparison_path(run_id)
    gold_labels_path = gold_labels_path or _gold_labels_path(run_id)
    manifest_path = manifest_path or _manifest_path(run_id)
    summary_path = summary_path or _manifest_summary_path(run_id)

    manifest = build_missing_label_manifest(
        run_id=run_id,
        snapshot=_read_json_object(snapshot_path),
        score_top15=_read_json_object(score_top15_path),
        comparison=_read_json_object(comparison_path),
        labels=_read_jsonl(gold_labels_path),
        snapshot_path=snapshot_path,
        score_top15_path=score_top15_path,
        comparison_path=comparison_path,
        gold_labels_path=gold_labels_path,
    )
    _atomic_write_json(manifest_path, manifest)
    _atomic_write_text(summary_path, _manifest_summary_text(manifest, manifest_path))
    print(
        f"[manifest] wrote {_artifact_path(manifest_path)} "
        f"records_total={manifest['records_total']} "
        f"unique_label_keys_total={manifest['unique_label_keys_total']}",
        flush=True,
    )
    print(
        f"[manifest] counts_by_model={manifest['counts_by_model']} "
        f"counts_by_mode={manifest['counts_by_mode']}",
        flush=True,
    )
    return manifest, manifest_path, summary_path


def run(run_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    print(f"[top15] loading {_artifact_path(_snapshot_path(run_id))}", flush=True)
    score_top15, score_path = persist_score_stage_top15(run_id=run_id)
    manifest, _manifest, _summary = regenerate_missing_label_manifest(run_id=run_id)
    print(
        f"[done] score_stage_top15={_artifact_path(score_path)} "
        f"manifest_records={manifest['records_total']}",
        flush=True,
    )
    return score_top15, manifest


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist RERANK-REGRESSION-EVAL score-stage top-15 sidecar."
    )
    parser.add_argument("--run", required=True, help="run id, e.g. 2026-05-19-1846-nogit")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    run(args.run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
