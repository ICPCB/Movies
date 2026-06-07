"""Compute Phase 1 provisional metrics for an eval run.

``queries_excluded_null`` is a per-mode aggregate counter. A query is counted
at most once when any null-sensitive metric at @5, @10, or @15 is undefined
because a null silver label prevents that metric from being proven.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io, _schemas


MODE_ORDER = ("basic", "advanced", "hybrid")
AXES = ("era", "genre", "vocab_distance", "length", "ambiguity")
TOP_KS = (5, 10, 15)
PRIMARY_K = 5
RELEVANCE = {3: 1.0, 2: 0.7, 1: 0.3, 0: 0.0}
METRIC_FAMILIES = ("hit", "strict_hit", "mrr", "strict_mrr", "ndcg")
CI_FAMILIES = ("hit", "mrr", "ndcg")


def _metric_key(family: str, k: int) -> str:
    return f"{family}_at_{k}"


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
                raise ValueError(f"{path}:{line_number}: record must be an object")
            yield value


def _load_manifest(run_id: str) -> Dict[str, Any]:
    path = _run_io.run_dir(run_id) / "run_manifest.json"
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError("run_manifest.json must contain an object")
    return manifest


def _load_candidates(path: Path) -> List[Dict[str, Any]]:
    return [_schemas.validate_candidate_record(record) for record in _read_jsonl(path)]


def _load_silver_labels(path: Path) -> List[Dict[str, Any]]:
    return [_schemas.validate_silver_record(record) for record in _read_jsonl(path)]


def _load_queries(path: Path) -> Dict[str, Dict[str, Any]]:
    queries: Dict[str, Dict[str, Any]] = {}
    for record in _read_jsonl(path):
        try:
            query = _schemas.validate_query_record(record)
        except ValueError:
            query = _schemas.validate_query_record_v2(record)
        queries[query["qid"]] = query
    return queries


def _label_map(
    silver_records: Iterable[Mapping[str, Any]],
) -> Dict[tuple[str, int], Optional[int]]:
    labels: Dict[tuple[str, int], Optional[int]] = {}
    for record in silver_records:
        labels[(str(record["qid"]), int(record["tmdb_id"]))] = record.get("grade")
    return labels


def _group_candidates_by_qid(
    candidates: Iterable[Mapping[str, Any]],
) -> Dict[str, List[Mapping[str, Any]]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["qid"])].append(candidate)
    return dict(grouped)


def _top_for_mode(
    candidates_for_query: Iterable[Mapping[str, Any]],
    mode: str,
    labels: Mapping[tuple[str, int], Optional[int]],
    k: int,
) -> List[Dict[str, Any]]:
    """Return top-K mode rows with formula positions converted to 1-based."""

    rows: List[Dict[str, Any]] = []
    for candidate in candidates_for_query:
        mode_data = candidate.get("per_mode", {}).get(mode)
        if mode_data is None:
            continue
        rank0 = int(mode_data["rank"])
        if rank0 >= k:
            continue
        qid = str(candidate["qid"])
        tmdb_id = int(candidate["tmdb_id"])
        rows.append(
            {
                "qid": qid,
                "tmdb_id": tmdb_id,
                "rank": rank0 + 1,
                "grade": labels.get((qid, tmdb_id)),
            }
        )
    rows.sort(key=lambda row: (row["rank"], row["tmdb_id"]))
    return rows[:k]


def _top5_for_mode(
    candidates_for_query: Iterable[Mapping[str, Any]],
    mode: str,
    labels: Mapping[tuple[str, int], Optional[int]],
) -> List[Dict[str, Any]]:
    return _top_for_mode(candidates_for_query, mode, labels, PRIMARY_K)


def _dcg_from_relevances(relevances: Sequence[float]) -> float:
    return float(
        sum(rel / math.log2(index + 2) for index, rel in enumerate(relevances))
    )


def _dcg_at_k(ranked_rows: Iterable[Mapping[str, Any]]) -> float:
    total = 0.0
    for row in ranked_rows:
        grade = row["grade"]
        total += RELEVANCE[grade] / math.log2(int(row["rank"]) + 1)
    return float(total)


def _dcg_at_5(ranked_rows: Iterable[Mapping[str, Any]]) -> float:
    return _dcg_at_k(ranked_rows)


def _ideal_dcg_for_query(
    candidates_for_query: Iterable[Mapping[str, Any]],
    labels: Mapping[tuple[str, int], Optional[int]],
    k: int = PRIMARY_K,
) -> float:
    relevances: List[float] = []
    seen: set[int] = set()
    for candidate in candidates_for_query:
        tmdb_id = int(candidate["tmdb_id"])
        if tmdb_id in seen:
            continue
        seen.add(tmdb_id)
        qid = str(candidate["qid"])
        grade = labels.get((qid, tmdb_id))
        if grade is None:
            continue
        relevances.append(RELEVANCE[grade])
    return _dcg_from_relevances(sorted(relevances, reverse=True)[:k])


def _coerce_ideal_dcgs(ideal_dcg: Mapping[int, float] | float) -> Dict[int, float]:
    if isinstance(ideal_dcg, Mapping):
        return {k: float(ideal_dcg.get(k, 0.0)) for k in TOP_KS}
    return {k: float(ideal_dcg) for k in TOP_KS}


def _hit_at_k(
    ranked_rows: Iterable[Mapping[str, Any]],
    predicate,
) -> Tuple[Optional[float], bool]:
    rows = list(ranked_rows)
    if any(row["grade"] is not None and predicate(row["grade"]) for row in rows):
        return 1.0, False
    if any(row["grade"] is None for row in rows):
        return None, True
    return 0.0, False


def _mrr_at_k(
    ranked_rows: Iterable[Mapping[str, Any]],
    predicate,
) -> Tuple[Optional[float], bool]:
    for row in sorted(ranked_rows, key=lambda item: item["rank"]):
        grade = row["grade"]
        if grade is None:
            return None, True
        if predicate(grade):
            return float(1.0 / int(row["rank"])), False
    return 0.0, False


def _ndcg_at_k(
    ranked_rows: Iterable[Mapping[str, Any]],
    ideal_dcg: float,
) -> Tuple[Optional[float], bool, bool]:
    rows = list(ranked_rows)
    if any(row["grade"] is None for row in rows):
        return None, True, False
    if ideal_dcg <= 0.0:
        return None, False, True
    return float(_dcg_at_k(rows) / ideal_dcg), False, False


def _query_mode_metrics(
    candidates_for_query: Iterable[Mapping[str, Any]],
    mode: str,
    labels: Mapping[tuple[str, int], Optional[int]],
    ideal_dcg: Mapping[int, float] | float,
) -> Dict[str, Any]:
    candidates = list(candidates_for_query)
    ideal_dcgs = _coerce_ideal_dcgs(ideal_dcg)

    metrics: Dict[str, Any] = {
        "excluded_null": False,
        "ideal_dcg_zero": False,
    }

    # The output has one null-exclusion counter per mode. This loop marks the
    # query once if any metric at any Phase 1 K is undefined because of a null.
    for k in TOP_KS:
        ranked_rows = _top_for_mode(candidates, mode, labels, k)

        hit, hit_excluded = _hit_at_k(
            ranked_rows, lambda grade: grade >= 2
        )
        strict_hit, strict_hit_excluded = _hit_at_k(
            ranked_rows, lambda grade: grade == 3
        )
        mrr, mrr_excluded = _mrr_at_k(
            ranked_rows, lambda grade: grade >= 2
        )
        strict_mrr, strict_mrr_excluded = _mrr_at_k(
            ranked_rows, lambda grade: grade == 3
        )
        ndcg, ndcg_excluded, ideal_zero = _ndcg_at_k(
            ranked_rows, ideal_dcgs[k]
        )

        metrics[_metric_key("hit", k)] = hit
        metrics[_metric_key("strict_hit", k)] = strict_hit
        metrics[_metric_key("mrr", k)] = mrr
        metrics[_metric_key("strict_mrr", k)] = strict_mrr
        metrics[_metric_key("ndcg", k)] = ndcg

        metrics[f"hit_excluded_null_at_{k}"] = hit_excluded
        metrics[f"strict_hit_excluded_null_at_{k}"] = strict_hit_excluded
        metrics[f"mrr_excluded_null_at_{k}"] = mrr_excluded
        metrics[f"strict_mrr_excluded_null_at_{k}"] = strict_mrr_excluded
        metrics[f"ndcg_excluded_null_at_{k}"] = ndcg_excluded

        if (
            hit_excluded
            or strict_hit_excluded
            or mrr_excluded
            or strict_mrr_excluded
            or ndcg_excluded
        ):
            metrics["excluded_null"] = True
        if k == PRIMARY_K and ideal_zero:
            metrics["ideal_dcg_zero"] = True

    return metrics


def _defined(values: Iterable[Optional[float]]) -> List[float]:
    return [float(value) for value in values if value is not None]


def _mean_or_zero(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _mean_or_none(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return float(sum(values) / len(values))


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(sorted_values[lower])
    weight = rank - lower
    return float(
        sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    )


def _bootstrap_half_width(
    values: Sequence[float],
    *,
    b: int,
    rng: random.Random,
) -> float:
    if b <= 0 or not values:
        return 0.0

    n = len(values)
    means: List[float] = []
    for _ in range(b):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)

    means.sort()
    low = _percentile(means, 2.5)
    high = _percentile(means, 97.5)
    return float((high - low) / 2.0)


def _by_mode_summary(
    per_query: Mapping[str, Mapping[str, Dict[str, Any]]],
    *,
    bootstrap_b: int,
    rng: random.Random,
) -> Dict[str, Dict[str, Any]]:
    by_mode: Dict[str, Dict[str, Any]] = {}
    for mode in MODE_ORDER:
        rows = [per_query[qid][mode] for qid in sorted(per_query)]
        entry: Dict[str, Any] = {}

        for k in TOP_KS:
            for family in METRIC_FAMILIES:
                key = _metric_key(family, k)
                values = _defined(row[key] for row in rows)
                if family == "ndcg":
                    entry[key] = _mean_or_none(values)
                else:
                    entry[key] = _mean_or_zero(values)

        entry["ci_half_widths"] = {}
        for k in TOP_KS:
            for family in CI_FAMILIES:
                key = _metric_key(family, k)
                entry["ci_half_widths"][key] = _bootstrap_half_width(
                    _defined(row[key] for row in rows),
                    b=bootstrap_b,
                    rng=rng,
                )

        entry["queries_excluded_null"] = sum(
            1 for row in rows if row["excluded_null"]
        )
        entry["queries_with_ideal_dcg_zero"] = sum(
            1 for row in rows if row["ideal_dcg_zero"]
        )
        by_mode[mode] = entry
    return by_mode


def _bucket_qids(
    qids: Iterable[str],
    query_records: Mapping[str, Mapping[str, Any]],
    axis: str,
) -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = defaultdict(list)
    for qid in sorted(qids):
        tags = query_records[qid]["tags"]
        value = tags[axis]
        if axis == "genre":
            for genre in value:
                buckets[str(genre)].append(qid)
        else:
            buckets[str(value)].append(qid)
    return dict(buckets)


def _axis_summary(
    qids: Sequence[str],
    query_records: Mapping[str, Mapping[str, Any]],
    per_query: Mapping[str, Mapping[str, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    by_axis: Dict[str, Dict[str, Any]] = {}
    for axis in AXES:
        axis_data: Dict[str, Any] = {}
        for bucket, bucket_qids in sorted(
            _bucket_qids(qids, query_records, axis).items()
        ):
            mode_data: Dict[str, Dict[str, Any]] = {}
            for mode in MODE_ORDER:
                # Keep prior n semantics by using the Hit@5 defined population.
                # Hit@10/@15 can have smaller defined populations if later nulls
                # make those broader windows unprovable.
                hit_values_by_k = {
                    k: _defined(
                        per_query[qid][mode][_metric_key("hit", k)]
                        for qid in bucket_qids
                    )
                    for k in TOP_KS
                }
                entry: Dict[str, Any] = {
                    _metric_key("hit", k): _mean_or_zero(hit_values_by_k[k])
                    for k in TOP_KS
                }
                entry["n"] = len(hit_values_by_k[PRIMARY_K])
                if entry["n"] < PRIMARY_K:
                    entry["low_sample"] = True
                mode_data[mode] = entry
            axis_data[bucket] = {"by_mode": mode_data}
        by_axis[axis] = axis_data
    return by_axis


def compute_metrics(
    *,
    run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    silver_labels: Sequence[Mapping[str, Any]],
    query_records: Mapping[str, Mapping[str, Any]],
    bootstrap_b: int = 1000,
    seed: int = 42,
) -> Dict[str, Any]:
    if bootstrap_b < 0:
        raise ValueError("--bootstrap-b must be >= 0")

    labels = _label_map(silver_labels)
    grouped = _group_candidates_by_qid(candidates)
    qids = sorted(grouped)
    missing_queries = sorted(set(qids) - set(query_records))
    if missing_queries:
        raise ValueError(
            "missing query tag records for qid(s): " + ", ".join(missing_queries)
        )

    ideal_dcg = {
        qid: {
            k: _ideal_dcg_for_query(grouped[qid], labels, k)
            for k in TOP_KS
        }
        for qid in qids
    }
    per_query: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for qid in qids:
        per_query[qid] = {}
        for mode in MODE_ORDER:
            per_query[qid][mode] = _query_mode_metrics(
                grouped[qid],
                mode,
                labels,
                ideal_dcg[qid],
            )

    rng = random.Random(seed)
    return {
        "provisional": True,
        "run_id": run_id,
        "label_source": "silver_only",
        "queries_total": len(qids),
        "by_mode": _by_mode_summary(
            per_query,
            bootstrap_b=bootstrap_b,
            rng=rng,
        ),
        "by_axis": _axis_summary(qids, query_records, per_query),
        "bootstrap": {
            "B": bootstrap_b,
            "method": "stratified_over_queries",
            "seed": seed,
        },
    }


def run(
    *,
    run_id: Optional[str] = None,
    queries_path: Optional[Path] = None,
    bootstrap_b: int = 1000,
    seed: int = 42,
) -> tuple[str, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    run_path = _run_io.run_dir(actual_run_id)
    _load_manifest(actual_run_id)
    candidates = _load_candidates(run_path / "candidates.jsonl")
    silver_labels = _load_silver_labels(run_path / "silver_labels.jsonl")
    queries = _load_queries(queries_path or (_run_io.EVAL_DIR / "queries" / "v1.jsonl"))

    metrics = compute_metrics(
        run_id=actual_run_id,
        candidates=candidates,
        silver_labels=silver_labels,
        query_records=queries,
        bootstrap_b=bootstrap_b,
        seed=seed,
    )

    metrics_path = run_path / "metrics_provisional.json"
    _run_io._atomic_write_json(metrics_path, metrics)
    _run_io.update_timestamp(actual_run_id, "provisional_metrics_done")
    return actual_run_id, metrics_path, metrics


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute CineMatch Phase 1 provisional metrics."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--queries", default=None, type=Path)
    parser.add_argument("--bootstrap-b", default=1000, type=int)
    parser.add_argument("--seed", default=42, type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id, metrics_path, metrics = run(
        run_id=args.run,
        queries_path=args.queries,
        bootstrap_b=args.bootstrap_b,
        seed=args.seed,
    )
    print(f"run_id={run_id}")
    print(f"metrics={metrics_path}")
    print(f"queries_total={metrics['queries_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
