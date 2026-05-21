"""Trace HY-FIX-02 RRF-pool neighborhoods from recorded control queries."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from eval.scripts import _run_io, hybrid_expansion_stability, hybrid_live_trace


SCHEMA_VERSION = "hy-fix-02.v1"
DEFAULT_QIDS = ("q08",)
CONTROL_ARMS = ("pinned", "no_llm")
SOURCE_ARTIFACTS = {
    "stability_trace": (
        "analysis/hybrid_expansion_stability/stability_trace.jsonl"
    ),
    "localization": "analysis/hy_fix_localize/localization.json",
}
STABILITY_DIAGNOSIS = (
    "analysis/hybrid_expansion_stability/stability_diagnosis.json"
)
OUTPUT_RELATIVE_PATH = Path("analysis") / "hy_fix_rrf_pool" / "rrf_pool_trace.json"
CONFIG_KEYS = (
    "CANDIDATE_POOL",
    "RERANK_POOL",
    "RRF_K",
    "RERANK_TOP_K",
    "FINAL_TOP_K",
    "SEMANTIC_WEIGHT",
    "BM25_WEIGHT",
)
SOURCE_MIX_KEYS = ("dual_source", "semantic_only", "bm25_only")


class HyFixRrfPoolError(ValueError):
    """Raised when HY-FIX-02 tracing must stop before writing."""


def run(
    *,
    run_id: Optional[str] = None,
    qids: str | Sequence[str] | None = None,
    margin: int = 25,
    dry_run: bool = False,
) -> tuple[str, Optional[Path], Dict[str, Any]]:
    """Build or write the HY-FIX-02 RRF-pool trace."""
    if margin < 0:
        raise HyFixRrfPoolError("--margin must be >= 0")

    actual_run_id = run_id or _run_io.latest_run()
    requested_qids = _parse_qids(qids)
    inputs = _load_inputs(actual_run_id, requested_qids)
    plan = _trace_plan(inputs, requested_qids)

    if dry_run:
        return actual_run_id, None, _dry_run_summary(actual_run_id, plan)

    data = _build_trace(actual_run_id, inputs, plan, margin)
    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_io._atomic_write_json(output_path, data)
    return actual_run_id, output_path, data


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Trace q08 RRF-pool neighborhood from recorded HY-STAB queries."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--qids", default=",".join(DEFAULT_QIDS))
    parser.add_argument("--margin", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        run_id, output_path, data = run(
            run_id=args.run,
            qids=args.qids,
            margin=args.margin,
            dry_run=args.dry_run,
        )
    except (HyFixRrfPoolError, FileNotFoundError) as exc:
        print(f"hy_fix_rrf_pool_trace: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(data)
        return 0

    print(f"run_id={run_id}")
    print(f"output={output_path}")
    print("qids=" + ",".join(str(row["qid"]) for row in data["per_qid"]))
    for qid_row in data["per_qid"]:
        qid = qid_row["qid"]
        for arm, arm_data in qid_row["arms"].items():
            print(
                f"{qid} {arm} "
                f"rrf_rank={arm_data['target']['rrf']['rank']} "
                f"reproduced_matches_recorded="
                f"{arm_data['reproduced_matches_recorded']}"
            )
    return 0


def _parse_qids(qids: str | Sequence[str] | None) -> tuple[str, ...]:
    if qids is None:
        values = list(DEFAULT_QIDS)
    elif isinstance(qids, str):
        values = [part.strip() for part in qids.split(",") if part.strip()]
    else:
        values = [str(part).strip() for part in qids if str(part).strip()]
    if not values:
        raise HyFixRrfPoolError("--qids must include at least one qid")
    return tuple(sorted(dict.fromkeys(values)))


def _load_inputs(run_id: str, requested_qids: Sequence[str]) -> Dict[str, Any]:
    run_path = _run_io.run_dir(run_id)
    trace_path = run_path / SOURCE_ARTIFACTS["stability_trace"]
    diagnosis_path = run_path / STABILITY_DIAGNOSIS
    localization_path = run_path / SOURCE_ARTIFACTS["localization"]
    queries_path = _run_io.EVAL_DIR / "queries" / "v1.jsonl"

    missing = [
        path
        for path in (trace_path, diagnosis_path, localization_path, queries_path)
        if not path.exists()
    ]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise HyFixRrfPoolError(f"required input file missing: {missing_text}")

    trace_rows = _read_jsonl(trace_path)
    diagnosis = _read_json_object(diagnosis_path)
    localization = _read_json_object(localization_path)
    queries = _read_queries(queries_path)
    config = _config_from_diagnosis(diagnosis)
    localization_by_qid = _localization_by_qid(localization)

    for qid in requested_qids:
        if qid not in queries:
            raise HyFixRrfPoolError(f"queries file missing qid: {qid}")
        row = localization_by_qid.get(qid)
        if row is None:
            raise HyFixRrfPoolError(f"{qid} missing from localization.json")
        pinned = row.get("arms", {}).get("pinned", {})
        if pinned.get("fix_category") != "recall_depth_fusion_pool":
            raise HyFixRrfPoolError(
                f"{qid} pinned fix_category is not recall_depth_fusion_pool"
            )

    return {
        "trace_rows": trace_rows,
        "localization_by_qid": localization_by_qid,
        "queries": queries,
        "config": config,
    }


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise HyFixRrfPoolError(f"{path}: JSON root must be an object")
    return data


def _read_jsonl(path: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if not isinstance(row, dict):
                raise HyFixRrfPoolError(f"{path}:{line_number}: row must be an object")
            rows.append(row)
    return rows


def _read_queries(path: Path) -> Dict[str, str]:
    queries: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if not isinstance(row, dict):
                raise HyFixRrfPoolError(f"{path}:{line_number}: row must be an object")
            try:
                queries[str(row["qid"])] = str(row["query"])
            except KeyError as exc:
                raise HyFixRrfPoolError(
                    f"{path}:{line_number}: missing qid or query"
                ) from exc
    return queries


def _config_from_diagnosis(diagnosis: Mapping[str, Any]) -> Dict[str, Any]:
    source = diagnosis.get("trace_meta", {}).get("config")
    if not isinstance(source, dict):
        raise HyFixRrfPoolError("stability_diagnosis.json missing trace_meta.config")
    config: Dict[str, Any] = {}
    for key in CONFIG_KEYS:
        if key not in source:
            raise HyFixRrfPoolError(f"trace_meta.config missing {key}")
        config[key] = _json_clone(source[key])
    return config


def _localization_by_qid(localization: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    rows = localization.get("per_target")
    if not isinstance(rows, list):
        raise HyFixRrfPoolError("localization.json missing per_target list")
    result: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        qid = str(row.get("qid", ""))
        if qid:
            result[qid] = row
    return result


def _trace_plan(
    inputs: Mapping[str, Any],
    requested_qids: Sequence[str],
) -> list[Dict[str, Any]]:
    trace_rows = inputs["trace_rows"]
    localization_by_qid = inputs["localization_by_qid"]
    queries = inputs["queries"]
    plan: list[Dict[str, Any]] = []

    for qid in requested_qids:
        localized = localization_by_qid[qid]
        tmdb_id = int(localized["tmdb_id"])
        arms: Dict[str, Any] = {}
        for arm in CONTROL_ARMS:
            rows = _trace_rows_for(trace_rows, qid, tmdb_id, arm)
            arms[arm] = _recorded_arm_queries(qid, arm, rows)
        plan.append(
            {
                "qid": qid,
                "tmdb_id": tmdb_id,
                "title": str(localized["title"]),
                "movie_key": arms["pinned"]["movie_key"],
                "pinned_arm_fix_category": localized["arms"]["pinned"][
                    "fix_category"
                ],
                "raw_query": queries[qid],
                "arms": arms,
            }
        )
    return plan


def _trace_rows_for(
    trace_rows: Sequence[Mapping[str, Any]],
    qid: str,
    tmdb_id: int,
    arm: str,
) -> list[Mapping[str, Any]]:
    rows = [
        row
        for row in trace_rows
        if str(row.get("qid")) == qid
        and str(row.get("arm")) == arm
        and int(row.get("tmdb_id")) == tmdb_id
    ]
    rows.sort(key=lambda row: int(row.get("repeat", 0)))
    if not rows:
        raise HyFixRrfPoolError(f"missing {arm} stability trace rows for {qid}")
    return rows


def _recorded_arm_queries(
    qid: str,
    arm: str,
    rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    first = rows[0]
    resolved = first.get("resolved")
    if not isinstance(resolved, dict):
        raise HyFixRrfPoolError(f"{qid} {arm} trace row missing resolved block")
    try:
        retrieval_query = str(resolved["retrieval_query"])
        rerank_query = str(resolved["rerank_query"])
    except KeyError as exc:
        raise HyFixRrfPoolError(
            f"{qid} {arm} resolved block missing {exc.args[0]}"
        ) from exc

    for row in rows[1:]:
        row_resolved = row.get("resolved")
        if not isinstance(row_resolved, dict):
            raise HyFixRrfPoolError(f"{qid} {arm} trace row missing resolved block")
        if (
            str(row_resolved.get("retrieval_query")) != retrieval_query
            or str(row_resolved.get("rerank_query")) != rerank_query
        ):
            raise HyFixRrfPoolError(
                f"{qid} {arm} recorded queries differ across repeats"
            )

    return {
        "retrieval_query": retrieval_query,
        "rerank_query": rerank_query,
        "recorded_rrf_rank": first.get("rrf", {}).get("rank"),
        "movie_key": str(first.get("movie_key", "")),
    }


def _dry_run_summary(run_id: str, plan: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "qids": [row["qid"] for row in plan],
        "per_qid": [
            {
                "qid": row["qid"],
                "tmdb_id": row["tmdb_id"],
                "title": row["title"],
                "movie_key": row["movie_key"],
                "arms": {
                    arm: {
                        "retrieval_query": row["arms"][arm]["retrieval_query"],
                        "rerank_query": row["arms"][arm]["rerank_query"],
                    }
                    for arm in CONTROL_ARMS
                },
            }
            for row in plan
        ],
    }


def _print_dry_run(summary: Mapping[str, Any]) -> None:
    print(f"run_id={summary['run_id']}")
    print("qids=" + ",".join(str(qid) for qid in summary["qids"]))
    for row in summary["per_qid"]:
        for arm in CONTROL_ARMS:
            arm_data = row["arms"][arm]
            print(
                f"{row['qid']} {arm} "
                f"retrieval_query={arm_data['retrieval_query']} "
                f"rerank_query={arm_data['rerank_query']}"
            )


def _build_trace(
    run_id: str,
    inputs: Mapping[str, Any],
    plan: Sequence[Mapping[str, Any]],
    margin: int,
) -> Dict[str, Any]:
    config = inputs["config"]
    per_qid = []
    for row in plan:
        arms: Dict[str, Any] = {}
        for arm in CONTROL_ARMS:
            arm_plan = row["arms"][arm]
            stage_run = hybrid_expansion_stability.run_stages(
                raw_query=str(row["raw_query"]),
                retrieval_query=str(arm_plan["retrieval_query"]),
                rerank_query=str(arm_plan["rerank_query"]),
            )
            arms[arm] = _build_arm_trace(
                stage_run=stage_run,
                arm_plan=arm_plan,
                movie_key=str(row["movie_key"]),
                config=config,
                margin=margin,
            )
        per_qid.append(
            {
                "qid": row["qid"],
                "tmdb_id": row["tmdb_id"],
                "title": row["title"],
                "movie_key": row["movie_key"],
                "pinned_arm_fix_category": row["pinned_arm_fix_category"],
                "arms": arms,
            }
        )

    per_qid.sort(key=lambda item: str(item["qid"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "source_artifacts": dict(SOURCE_ARTIFACTS),
        "config": config,
        "neighborhood_margin": margin,
        "per_qid": per_qid,
    }


def _build_arm_trace(
    *,
    stage_run: Any,
    arm_plan: Mapping[str, Any],
    movie_key: str,
    config: Mapping[str, Any],
    margin: int,
) -> Dict[str, Any]:
    rrf = list(stage_run.rrf)
    rerank_top_k = int(config["RERANK_TOP_K"])
    target_movie, target_rrf_rank = _find_by_movie_key(rrf, movie_key)
    target = _target_block(stage_run, target_movie, target_rrf_rank, movie_key, config)
    last_in_pool = _entry_at(rrf, rerank_top_k - 1)
    first_out = _entry_at(rrf, rerank_top_k)
    cutoff = _cutoff_block(
        last_in_pool=last_in_pool,
        first_out=first_out,
        target=target,
        rerank_top_k=rerank_top_k,
    )
    neighborhood = [
        _fused_entry(movie, rank)
        for rank, movie in enumerate(rrf[: rerank_top_k + margin])
    ]
    in_pool = neighborhood[:rerank_top_k]

    return {
        "retrieval_query": arm_plan["retrieval_query"],
        "rerank_query": arm_plan["rerank_query"],
        "rrf_list_len": len(rrf),
        "target": target,
        "recorded_rrf_rank": arm_plan["recorded_rrf_rank"],
        "reproduced_matches_recorded": (
            target["rrf"]["rank"] == arm_plan["recorded_rrf_rank"]
        ),
        "cutoff": cutoff,
        "neighborhood": neighborhood,
        "neighborhood_source_mix": _source_mix(neighborhood),
        "in_pool_source_mix": _source_mix(in_pool),
    }


def _target_block(
    stage_run: Any,
    target_movie: Optional[Mapping[str, Any]],
    target_rrf_rank: Optional[int],
    movie_key: str,
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    semantic_movie, semantic_rank = _find_by_movie_key(stage_run.semantic, movie_key)
    bm25_movie, bm25_rank = _find_by_movie_key(stage_run.bm25, movie_key)

    rrf_present = target_movie is not None
    source_count = _source_count(
        target_movie if target_movie is not None else {
            "semantic_rank": semantic_rank,
            "bm25_rank": bm25_rank,
        }
    )
    return {
        "semantic": {
            "present": semantic_movie is not None,
            "rank": semantic_rank,
            "score": _coerce_float(semantic_movie.get("semantic_score"))
            if semantic_movie is not None
            else None,
        },
        "bm25": {
            "present": bm25_movie is not None,
            "rank": bm25_rank,
            "score": _coerce_float(bm25_movie.get("bm25_score"))
            if bm25_movie is not None
            else None,
        },
        "rrf": {
            "present": rrf_present,
            "rank": target_rrf_rank,
            "score": _coerce_float(target_movie.get("rrf_score"))
            if target_movie is not None
            else None,
        },
        "source_count": source_count,
        "in_rerank_pool": (
            target_rrf_rank is not None and target_rrf_rank < int(config["RERANK_TOP_K"])
        ),
    }


def _cutoff_block(
    *,
    last_in_pool: Optional[Dict[str, Any]],
    first_out: Optional[Dict[str, Any]],
    target: Mapping[str, Any],
    rerank_top_k: int,
) -> Dict[str, Any]:
    target_rank = target["rrf"]["rank"]
    target_score = target["rrf"]["score"]
    last_score = last_in_pool["rrf_score"] if last_in_pool is not None else None
    return {
        "rerank_top_k": rerank_top_k,
        "last_in_pool": last_in_pool,
        "first_out_of_pool": first_out,
        "target_rrf_rank": target_rank,
        "ranks_below_cutoff": (
            target_rank - (rerank_top_k - 1) if target_rank is not None else None
        ),
        "rrf_score_gap_to_last_in_pool": (
            last_score - target_score
            if last_score is not None and target_score is not None
            else None
        ),
    }


def _entry_at(rrf: Sequence[Mapping[str, Any]], rank: int) -> Optional[Dict[str, Any]]:
    if rank < 0 or rank >= len(rrf):
        return None
    return _fused_entry(rrf[rank], rank)


def _fused_entry(movie: Mapping[str, Any], rank: int) -> Dict[str, Any]:
    semantic_rank = _rank_value(movie.get("semantic_rank"))
    bm25_rank = _rank_value(movie.get("bm25_rank"))
    return {
        "rrf_rank": rank,
        "movie_key": _movie_key(movie),
        "title": str(movie.get("title", "")),
        "rrf_score": _coerce_float(movie.get("rrf_score")),
        "semantic_rank": semantic_rank,
        "bm25_rank": bm25_rank,
        "source_count": int(semantic_rank is not None) + int(bm25_rank is not None),
    }


def _source_mix(entries: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counts = {key: 0 for key in SOURCE_MIX_KEYS}
    for entry in entries:
        semantic_present = entry.get("semantic_rank") is not None
        bm25_present = entry.get("bm25_rank") is not None
        if semantic_present and bm25_present:
            counts["dual_source"] += 1
        elif semantic_present:
            counts["semantic_only"] += 1
        elif bm25_present:
            counts["bm25_only"] += 1
    return counts


def _find_by_movie_key(
    movies: Sequence[Mapping[str, Any]],
    movie_key: str,
) -> tuple[Optional[Mapping[str, Any]], Optional[int]]:
    for index, movie in enumerate(movies):
        if _movie_key(movie) == movie_key:
            return movie, index
    return None, None


def _movie_key(movie: Mapping[str, Any]) -> str:
    value = movie.get("movie_key")
    if value:
        return str(value)
    return hybrid_live_trace.get_movie_key(dict(movie))


def _source_count(movie: Mapping[str, Any]) -> int:
    return int(movie.get("semantic_rank") is not None) + int(
        movie.get("bm25_rank") is not None
    )


def _rank_value(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
