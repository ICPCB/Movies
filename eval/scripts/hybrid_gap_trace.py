"""Diagnose hybrid strict-miss gaps from stored candidate stage scores."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io, compute_metrics, error_report


PRIMARY_K = 5
MODES = ("basic", "advanced", "hybrid")
STAGE_FIELDS = (
    "semantic_score",
    "bm25_score",
    "rrf_score",
    "rerank_score",
    "final_score",
)
DEMOTING_STAGE_KEYS = STAGE_FIELDS + (
    "not_retrieved_by_hybrid",
    "none",
)
PARTITION_KEYS = (
    "hybrid_attributable",
    "shared_miss",
    "no_perfect_candidate",
)


class HybridGapError(ValueError):
    """Raised when hybrid gap tracing must stop before writing."""


def _required_input_paths(run_path: Path) -> tuple[Path, ...]:
    return (
        run_path / "candidates.jsonl",
        run_path / "gold_labels.jsonl",
        run_path / "metrics.json",
        run_path / "analysis" / "error_report" / "summary.gold.json",
        run_path / "analysis" / "error_report" / "per_query_mode.gold.jsonl",
    )


def _ensure_inputs_exist(paths: Iterable[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise HybridGapError(f"required input missing: {path}")


def _read_json_object(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise HybridGapError(f"{path}: invalid JSON") from exc
    if not isinstance(data, dict):
        raise HybridGapError(f"{path}: JSON root must be an object")
    return data


def _load_candidates(path: Path) -> list[Dict[str, Any]]:
    try:
        return compute_metrics._load_candidates(path)
    except ValueError as exc:
        raise HybridGapError(str(exc)) from exc


def _load_gold_labels(path: Path) -> list[Dict[str, Any]]:
    try:
        return error_report._load_gold_labels(path)
    except ValueError as exc:
        raise HybridGapError(str(exc)) from exc


def _strict_miss_qids(summary: Mapping[str, Any], mode: str) -> list[str]:
    try:
        value = summary["by_mode"][mode]["strict_miss_qids"]
    except KeyError as exc:
        raise HybridGapError(f"summary.gold.json missing {mode}.strict_miss_qids") from exc
    if not isinstance(value, list):
        raise HybridGapError(f"summary.gold.json {mode}.strict_miss_qids must be a list")
    qids = [str(qid) for qid in value]
    if len(qids) != len(set(qids)):
        raise HybridGapError(f"summary.gold.json {mode}.strict_miss_qids has duplicates")
    return sorted(qids)


def _metrics_expected_hybrid_misses(metrics: Mapping[str, Any]) -> int:
    try:
        strict_hit_at_5 = float(metrics["by_mode"]["hybrid"]["strict_hit_at_5"])
        queries_total = int(metrics["queries_total"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HybridGapError("metrics.json missing hybrid strict_hit_at_5 or queries_total") from exc
    return round((1.0 - strict_hit_at_5) * queries_total)


def _perfect_ids_by_qid(
    gold_labels: Iterable[Mapping[str, Any]],
) -> Dict[str, set[int]]:
    perfect: Dict[str, set[int]] = defaultdict(set)
    for row in gold_labels:
        if row.get("grade") == 3:
            perfect[str(row["qid"])].add(int(row["tmdb_id"]))
    return dict(perfect)


def _group_candidates_by_qid(
    candidates: Iterable[Mapping[str, Any]],
) -> Dict[str, list[Mapping[str, Any]]]:
    grouped: Dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["qid"])].append(candidate)
    return dict(grouped)


def _mode_data(
    candidate: Mapping[str, Any],
    mode: str,
) -> Optional[Mapping[str, Any]]:
    value = candidate.get("per_mode", {}).get(mode)
    if isinstance(value, Mapping):
        return value
    return None


def _in_top_5(candidate: Mapping[str, Any], mode: str) -> bool:
    mode_data = _mode_data(candidate, mode)
    if mode_data is None or mode_data.get("rank") is None:
        return False
    return int(mode_data["rank"]) < PRIMARY_K


def _perfect_top_5_by_mode(
    *,
    candidates_for_qid: Sequence[Mapping[str, Any]],
    perfect_ids: set[int],
) -> Dict[str, set[int]]:
    by_mode = {mode: set() for mode in MODES}
    for candidate in candidates_for_qid:
        tmdb_id = int(candidate["tmdb_id"])
        if tmdb_id not in perfect_ids:
            continue
        for mode in MODES:
            if _in_top_5(candidate, mode):
                by_mode[mode].add(tmdb_id)
    return by_mode


def _partition_qids(
    *,
    hybrid_strict_miss: Sequence[str],
    perfect_by_qid: Mapping[str, set[int]],
    candidates_by_qid: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Dict[str, list[str]]:
    partition = {key: [] for key in PARTITION_KEYS}

    for qid in sorted(hybrid_strict_miss):
        perfect_ids = set(perfect_by_qid.get(qid, set()))
        if not perfect_ids:
            partition["no_perfect_candidate"].append(qid)
            continue

        perfect_top_5 = _perfect_top_5_by_mode(
            candidates_for_qid=list(candidates_by_qid.get(qid, [])),
            perfect_ids=perfect_ids,
        )
        top_5_basic_or_advanced = bool(
            perfect_top_5["basic"] or perfect_top_5["advanced"]
        )
        top_5_hybrid = bool(perfect_top_5["hybrid"])

        if top_5_basic_or_advanced and not top_5_hybrid:
            partition["hybrid_attributable"].append(qid)
        elif not any(perfect_top_5[mode] for mode in MODES):
            partition["shared_miss"].append(qid)
        else:
            raise HybridGapError(
                f"{qid} cannot be partitioned: perfect candidate is in hybrid top-5"
            )

    return {key: sorted(values) for key, values in partition.items()}


def _select_target(
    *,
    qid: str,
    perfect_ids: set[int],
    candidates_for_qid: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], str]:
    eligible: list[tuple[int, int, Mapping[str, Any]]] = []
    for candidate in candidates_for_qid:
        tmdb_id = int(candidate["tmdb_id"])
        if tmdb_id not in perfect_ids:
            continue
        top_5_modes = sum(1 for mode in MODES if _in_top_5(candidate, mode))
        if top_5_modes > 0:
            eligible.append((top_5_modes, tmdb_id, candidate))

    if not eligible:
        raise HybridGapError(f"{qid} has no top-5 perfect candidate to trace")

    top_5_modes, tmdb_id, target = sorted(
        eligible,
        key=lambda item: (-item[0], item[1]),
    )[0]
    del top_5_modes, tmdb_id

    if _in_top_5(target, "advanced"):
        return target, "advanced"
    if _in_top_5(target, "basic"):
        return target, "basic"
    raise HybridGapError(f"{qid} target has no basic/advanced reference mode")


def _rank_map(
    *,
    qid: str,
    candidates_for_qid: Sequence[Mapping[str, Any]],
    mode: str,
    stage: str,
) -> Dict[int, int]:
    if stage == "final_score":
        return _final_rank_map(
            qid=qid,
            candidates_for_qid=candidates_for_qid,
            mode=mode,
        )

    rows: list[tuple[float, int]] = []
    for candidate in candidates_for_qid:
        mode_data = _mode_data(candidate, mode)
        if mode_data is None:
            continue
        score = mode_data.get(stage)
        if score is None:
            continue
        tmdb_id = int(candidate["tmdb_id"])
        rows.append((float(score), tmdb_id))

    rows.sort(key=lambda item: (-item[0], item[1]))
    return {tmdb_id: rank for rank, (_score, tmdb_id) in enumerate(rows)}


def _final_rank_map(
    *,
    qid: str,
    candidates_for_qid: Sequence[Mapping[str, Any]],
    mode: str,
) -> Dict[int, int]:
    rows: list[tuple[float, int, int]] = []
    for candidate in candidates_for_qid:
        mode_data = _mode_data(candidate, mode)
        if mode_data is None:
            continue
        score = mode_data.get("final_score")
        if score is None:
            continue
        tmdb_id = int(candidate["tmdb_id"])
        rows.append((float(score), tmdb_id, int(mode_data["rank"])))

    by_score = sorted(rows, key=lambda item: (-item[0], item[1]))
    by_stored_rank = sorted(rows, key=lambda item: (item[2], item[1]))
    if [tmdb_id for _score, tmdb_id, _rank in by_score] != [
        tmdb_id for _score, tmdb_id, _rank in by_stored_rank
    ]:
        raise HybridGapError(f"{qid} {mode} final_score ordering mismatches stored rank")

    return {tmdb_id: stored_rank for _score, tmdb_id, stored_rank in rows}


def _stage_ranks_for_mode(
    *,
    qid: str,
    candidates_for_qid: Sequence[Mapping[str, Any]],
    target_tmdb_id: int,
    mode: str,
) -> Dict[str, Optional[int]]:
    return {
        stage: _rank_map(
            qid=qid,
            candidates_for_qid=candidates_for_qid,
            mode=mode,
            stage=stage,
        ).get(target_tmdb_id)
        for stage in STAGE_FIELDS
    }


def _check_final_rank_consistency(
    *,
    qid: str,
    target: Mapping[str, Any],
    mode: str,
    computed_rank: Optional[int],
) -> None:
    mode_data = _mode_data(target, mode)
    if mode_data is None:
        return
    if computed_rank is None:
        raise HybridGapError(f"{qid} {mode} final_score rank is unavailable")
    stored_rank = int(mode_data["rank"])
    if computed_rank != stored_rank:
        tmdb_id = int(target["tmdb_id"])
        raise HybridGapError(
            f"{qid} {mode} final_score rank mismatch for {tmdb_id}: "
            f"computed {computed_rank}, stored {stored_rank}"
        )


def _demoting_stage(
    *,
    target: Mapping[str, Any],
    hybrid_stage_ranks: Mapping[str, Optional[int]],
) -> str:
    if _mode_data(target, "hybrid") is None:
        return "not_retrieved_by_hybrid"
    for stage in STAGE_FIELDS:
        rank = hybrid_stage_ranks[stage]
        if rank is not None and rank >= PRIMARY_K:
            return stage
    return "none"


def _trace_record(
    *,
    qid: str,
    target: Mapping[str, Any],
    reference_mode: str,
    candidates_for_qid: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    target_tmdb_id = int(target["tmdb_id"])
    hybrid_ranks = _stage_ranks_for_mode(
        qid=qid,
        candidates_for_qid=candidates_for_qid,
        target_tmdb_id=target_tmdb_id,
        mode="hybrid",
    )
    reference_ranks = _stage_ranks_for_mode(
        qid=qid,
        candidates_for_qid=candidates_for_qid,
        target_tmdb_id=target_tmdb_id,
        mode=reference_mode,
    )

    _check_final_rank_consistency(
        qid=qid,
        target=target,
        mode="hybrid",
        computed_rank=hybrid_ranks["final_score"],
    )
    _check_final_rank_consistency(
        qid=qid,
        target=target,
        mode=reference_mode,
        computed_rank=reference_ranks["final_score"],
    )

    stage_ranks = {
        "hybrid": hybrid_ranks,
        reference_mode: reference_ranks,
    }
    return {
        "qid": qid,
        "perfect_tmdb_id": target_tmdb_id,
        "title": target["title"],
        "gold_grade": 3,
        "reference_mode": reference_mode,
        "stage_ranks": stage_ranks,
        "demoting_stage": _demoting_stage(
            target=target,
            hybrid_stage_ranks=hybrid_ranks,
        ),
    }


def build_diagnosis(
    *,
    run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    gold_labels: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    strict_miss_by_mode = {
        mode: _strict_miss_qids(summary, mode)
        for mode in MODES
    }
    hybrid_strict_miss = strict_miss_by_mode["hybrid"]
    expected_hybrid_misses = _metrics_expected_hybrid_misses(metrics)
    if len(hybrid_strict_miss) != expected_hybrid_misses:
        raise HybridGapError(
            "hybrid strict_miss_qids count mismatch: "
            f"summary has {len(hybrid_strict_miss)}, metrics imply "
            f"{expected_hybrid_misses}"
        )

    perfect_by_qid = _perfect_ids_by_qid(gold_labels)
    candidates_by_qid = _group_candidates_by_qid(candidates)
    partition = _partition_qids(
        hybrid_strict_miss=hybrid_strict_miss,
        perfect_by_qid=perfect_by_qid,
        candidates_by_qid=candidates_by_qid,
    )

    trace_rows: list[Dict[str, Any]] = []
    demoting_stage_counts = {stage: 0 for stage in DEMOTING_STAGE_KEYS}
    for qid in partition["hybrid_attributable"]:
        target, reference_mode = _select_target(
            qid=qid,
            perfect_ids=set(perfect_by_qid.get(qid, set())),
            candidates_for_qid=list(candidates_by_qid.get(qid, [])),
        )
        record = _trace_record(
            qid=qid,
            target=target,
            reference_mode=reference_mode,
            candidates_for_qid=list(candidates_by_qid.get(qid, [])),
        )
        trace_rows.append(record)
        demoting_stage_counts[record["demoting_stage"]] += 1

    hybrid_strict_miss_total = len(hybrid_strict_miss)
    if sum(len(partition[key]) for key in PARTITION_KEYS) != hybrid_strict_miss_total:
        raise HybridGapError("partition does not sum to hybrid strict miss total")

    diagnosis = {
        "run_id": run_id,
        "labels_file": "gold_labels.jsonl",
        "hybrid_strict_miss_total": hybrid_strict_miss_total,
        "partition": partition,
        "demoting_stage_counts": demoting_stage_counts,
    }
    return trace_rows, diagnosis


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    text = "".join(json.dumps(row) + "\n" for row in rows)
    _run_io._atomic_write_text(path, text)


def run(
    *,
    run_id: Optional[str] = None,
) -> tuple[str, Path, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    run_path = _run_io.run_dir(actual_run_id)
    candidates_path, gold_path, metrics_path, summary_path, per_query_path = (
        _required_input_paths(run_path)
    )
    _ensure_inputs_exist(
        (candidates_path, gold_path, metrics_path, summary_path, per_query_path)
    )

    candidates = _load_candidates(candidates_path)
    gold_labels = _load_gold_labels(gold_path)
    metrics = _read_json_object(metrics_path)
    summary = _read_json_object(summary_path)

    trace_rows, diagnosis = build_diagnosis(
        run_id=actual_run_id,
        candidates=candidates,
        gold_labels=gold_labels,
        metrics=metrics,
        summary=summary,
    )

    output_dir = run_path / "analysis" / "hybrid_gap"
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "trace.jsonl"
    diagnosis_path = output_dir / "diagnosis.json"
    _write_jsonl(trace_path, trace_rows)
    _run_io._atomic_write_json(diagnosis_path, diagnosis)
    return actual_run_id, trace_path, diagnosis_path, diagnosis


def _dominant_demoting_stage(counts: Mapping[str, int]) -> tuple[str, int]:
    return max(
        ((stage, int(counts[stage])) for stage in DEMOTING_STAGE_KEYS),
        key=lambda item: (item[1], -DEMOTING_STAGE_KEYS.index(item[0])),
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose hybrid strict-ranking gaps from stored scores."
    )
    parser.add_argument("--run", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, trace_path, diagnosis_path, diagnosis = run(run_id=args.run)
    except HybridGapError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    partition = diagnosis["partition"]
    dominant_stage, dominant_count = _dominant_demoting_stage(
        diagnosis["demoting_stage_counts"]
    )
    print(f"run_id={run_id}")
    print(f"trace={trace_path}")
    print(f"diagnosis={diagnosis_path}")
    print(f"hybrid_attributable={len(partition['hybrid_attributable'])}")
    print(f"shared_miss={len(partition['shared_miss'])}")
    print(f"no_perfect_candidate={len(partition['no_perfect_candidate'])}")
    print(f"dominant_demoting_stage={dominant_stage} count={dominant_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
