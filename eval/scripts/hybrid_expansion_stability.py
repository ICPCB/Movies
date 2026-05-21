"""Hybrid expansion-stability diagnostics for hybrid-attributable misses."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io, hybrid_live_trace
from eval.scripts.hybrid_live_trace import (
    HYBRID_ATTRIBUTABLE_QIDS,
    HybridLiveTraceError,
    StageRun,
    Target,
    TraceInputs,
    _dominant_mechanism,
    _ensure_live_imports,
    _identity_warning,
    _loss_counts,
    _mechanism_summary,
    _per_target,
    _prepare_inputs,
    _rerank_capture,
    _snapshot_movies,
    _stage_presence,
    classify_loss,
)


SCHEMA_VERSION = "hy-stab-01.v1"
ARM_ORDER = ("live", "pinned", "no_llm")
DEFAULT_ARMS = ARM_ORDER
EXPANSION_SOURCE = {
    "live": "live",
    "pinned": "pinned",
    "no_llm": "deterministic",
}
ATTRIBUTION_KEYS = (
    "fixed_defect",
    "expansion_dependent",
    "expansion_variance_only",
    "stable_hit",
    "inconclusive",
)
LIVE_DECOMPOSITION_NOTE = "live arm; repeat 0 only \u2014 varies across repeats"


class HybridStabilityError(HybridLiveTraceError):
    """Raised when expansion-stability tracing must stop before writing."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _parse_arms(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        requested = list(DEFAULT_ARMS)
    elif isinstance(value, str):
        requested = [part.strip() for part in value.split(",") if part.strip()]
    else:
        requested = [str(part).strip() for part in value if str(part).strip()]

    if not requested:
        raise HybridStabilityError("--arms must include at least one arm")

    unknown = [arm for arm in requested if arm not in ARM_ORDER]
    if unknown:
        allowed = ",".join(ARM_ORDER)
        raise HybridStabilityError(
            f"--arms contains unsupported arm(s): {', '.join(unknown)} "
            f"(allowed: {allowed})"
        )

    requested_set = set(requested)
    return tuple(arm for arm in ARM_ORDER if arm in requested_set)


def _config_value(name: str) -> Any:
    config = hybrid_live_trace.runtime_config
    if config is None:
        return None
    return getattr(config, name, None)


def _trace_config() -> Dict[str, Any]:
    return {
        "CANDIDATE_POOL": hybrid_live_trace.CANDIDATE_POOL,
        "RERANK_POOL": hybrid_live_trace.RERANK_POOL,
        "RERANK_TOP_K": hybrid_live_trace.RERANK_TOP_K,
        "FINAL_TOP_K": hybrid_live_trace.FINAL_TOP_K,
        "RRF_K": hybrid_live_trace.RRF_K,
        "SEMANTIC_WEIGHT": hybrid_live_trace.SEMANTIC_WEIGHT,
        "BM25_WEIGHT": hybrid_live_trace.BM25_WEIGHT,
        "RERANK_VOTE_COUNT_WEIGHT": hybrid_live_trace.RERANK_VOTE_COUNT_WEIGHT,
        "RERANK_UPSTREAM_WEIGHT": hybrid_live_trace.RERANK_UPSTREAM_WEIGHT,
        "RERANK_SOURCE_AGREEMENT_BONUS": (
            hybrid_live_trace.RERANK_SOURCE_AGREEMENT_BONUS
        ),
    }


def _require_live_imports() -> None:
    _ensure_live_imports()


def run_stages(
    *,
    raw_query: str,
    retrieval_query: str,
    rerank_query: str,
) -> StageRun:
    """Run the live hybrid stages using caller-supplied query strings."""

    _require_live_imports()

    filters = hybrid_live_trace.parse_filters(raw_query) or None

    sem = hybrid_live_trace.semantic_search(
        retrieval_query,
        top_k=hybrid_live_trace.CANDIDATE_POOL,
        filters=filters,
    )
    sem = hybrid_live_trace.deduplicate_movies(sem, prefer_score="semantic_score")
    sem_snapshot = _snapshot_movies(sem)

    bm = hybrid_live_trace.bm25_search(
        retrieval_query,
        top_k=hybrid_live_trace.CANDIDATE_POOL,
        filters=filters,
    )
    bm = hybrid_live_trace.deduplicate_movies(bm, prefer_score="bm25_score")
    bm_snapshot = _snapshot_movies(bm)

    fused = hybrid_live_trace.rrf_fusion(
        sem,
        bm,
        top_k=hybrid_live_trace.RERANK_POOL,
    )
    fused = hybrid_live_trace.deduplicate_movies(fused, prefer_score="rrf_score")
    fused.sort(
        key=lambda movie: hybrid_live_trace._score(
            movie,
            "final_score",
            "rrf_score",
        ),
        reverse=True,
    )
    fused_snapshot = _snapshot_movies(fused)

    scored_pool = hybrid_live_trace.rerank(
        rerank_query,
        fused,
        top_k=hybrid_live_trace.RERANK_TOP_K,
        rerank_pool=hybrid_live_trace.RERANK_TOP_K,
    )
    scored_snapshot = _snapshot_movies(scored_pool)

    return StageRun(
        retrieval_query=retrieval_query,
        rerank_query=rerank_query,
        filters=filters,
        semantic=sem_snapshot,
        bm25=bm_snapshot,
        rrf=fused_snapshot,
        scored_pool=scored_snapshot,
    )


def _trace_record(
    *,
    run_id: str,
    arm: str,
    target: Target,
    repeat: int,
    stage_run: StageRun,
) -> Dict[str, Any]:
    rerank_data, final_data = _rerank_capture(stage_run.scored_pool, target)
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "arm": arm,
        "qid": target.qid,
        "tmdb_id": target.tmdb_id,
        "movie_key": target.movie_key,
        "title": target.title,
        "gold_grade": target.gold_grade,
        "repeat": repeat,
        "resolved": {
            "expansion_source": EXPANSION_SOURCE[arm],
            "retrieval_query": stage_run.retrieval_query,
            "rerank_query": stage_run.rerank_query,
            "filters": stage_run.filters,
        },
        "semantic": _stage_presence(stage_run.semantic, target, "semantic_score"),
        "bm25": _stage_presence(stage_run.bm25, target, "bm25_score"),
        "rrf": _stage_presence(stage_run.rrf, target, "rrf_score"),
        "rerank": rerank_data,
        "final": final_data,
        "identity_warning": _identity_warning(stage_run.semantic, target),
        "loss_classification": None,
    }
    record["loss_classification"] = classify_loss(record)
    return record


def _targets_by_qid(targets: Iterable[Target]) -> Dict[str, list[Target]]:
    grouped: Dict[str, list[Target]] = defaultdict(list)
    for target in targets:
        grouped[target.qid].append(target)
    for targets_for_qid in grouped.values():
        targets_for_qid.sort(key=lambda target: target.tmdb_id)
    return grouped


def _trace_all(
    *,
    inputs: TraceInputs,
    repeat: int,
    arms: Sequence[str],
) -> tuple[list[Dict[str, Any]], Dict[tuple[str, str, int], StageRun]]:
    _require_live_imports()

    targets_by_qid = _targets_by_qid(inputs.targets)
    rows: list[Dict[str, Any]] = []
    stage_runs: Dict[tuple[str, str, int], StageRun] = {}

    for qid in inputs.qids:
        raw_query = inputs.queries[qid]
        processed = hybrid_live_trace.normalize_query(raw_query)
        deterministic_query = hybrid_live_trace.expand_retrieval_query(processed)
        rerank_query = deterministic_query
        pinned_expansion: Optional[str] = None

        if "pinned" in arms:
            pinned_expansion = hybrid_live_trace.expand_query(processed)

        for arm in arms:
            for repeat_index in range(repeat):
                if arm == "live":
                    retrieval_query = hybrid_live_trace.expand_retrieval_query(
                        hybrid_live_trace.expand_query(processed) or processed
                    )
                elif arm == "pinned":
                    retrieval_query = hybrid_live_trace.expand_retrieval_query(
                        pinned_expansion or processed
                    )
                elif arm == "no_llm":
                    retrieval_query = deterministic_query
                else:
                    raise HybridStabilityError(f"unsupported arm: {arm}")

                stage_run = run_stages(
                    raw_query=raw_query,
                    retrieval_query=retrieval_query,
                    rerank_query=rerank_query,
                )
                stage_runs[(arm, qid, repeat_index)] = stage_run
                for target in targets_by_qid[qid]:
                    rows.append(
                        _trace_record(
                            run_id=inputs.run_id,
                            arm=arm,
                            target=target,
                            repeat=repeat_index,
                            stage_run=stage_run,
                        )
                    )

    arm_rank = {arm: index for index, arm in enumerate(ARM_ORDER)}
    rows.sort(
        key=lambda row: (
            arm_rank[str(row["arm"])],
            str(row["qid"]),
            int(row["tmdb_id"]),
            int(row["repeat"]),
        )
    )
    return rows, stage_runs


def _per_arm_diagnosis(
    *,
    arm: str,
    trace_rows: Sequence[Mapping[str, Any]],
    targets_total: int,
) -> Dict[str, Any]:
    arm_rows = [row for row in trace_rows if row["arm"] == arm]
    per_target = _per_target(arm_rows)
    counts = _loss_counts(per_target)
    mechanisms = _mechanism_summary(counts)

    if sum(counts.values()) != targets_total:
        raise HybridStabilityError(
            f"{arm} loss_classification_counts does not sum to targets_total"
        )
    if sum(mechanisms.values()) != targets_total:
        raise HybridStabilityError(
            f"{arm} mechanism_summary does not sum to targets_total"
        )

    return {
        "per_target": per_target,
        "loss_classification_counts": counts,
        "mechanism_summary": mechanisms,
        "dominant_mechanism": _dominant_mechanism(counts, mechanisms),
    }


def _per_target_index(
    per_arm: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Dict[tuple[str, int], Mapping[str, Any]]]:
    indexed: Dict[str, Dict[tuple[str, int], Mapping[str, Any]]] = {}
    for arm, arm_data in per_arm.items():
        indexed[arm] = {
            (str(row["qid"]), int(row["tmdb_id"])): row
            for row in arm_data["per_target"]
        }
    return indexed


def _stable_value(row: Optional[Mapping[str, Any]]) -> Optional[bool]:
    if row is None:
        return None
    return bool(row["stable"])


def _classification_value(row: Optional[Mapping[str, Any]]) -> Optional[str]:
    if row is None:
        return None
    return str(row["classification"])


def _is_hit(row: Mapping[str, Any]) -> bool:
    return bool(row["stable"]) and str(row["classification"]) == "hybrid_top5_hit"


def _is_miss(row: Mapping[str, Any]) -> bool:
    return bool(row["stable"]) and str(row["classification"]) not in {
        "hybrid_top5_hit",
        "other",
    }


def _live_final_rank(
    *,
    trace_rows: Sequence[Mapping[str, Any]],
    qid: str,
    tmdb_id: int,
) -> Dict[str, Any]:
    ranks = [
        int(row["final"]["final_rank"])
        for row in trace_rows
        if row["arm"] == "live"
        and row["qid"] == qid
        and int(row["tmdb_id"]) == tmdb_id
        and row["final"]["final_rank"] is not None
    ]
    if not ranks:
        return {"min": None, "median": None, "max": None, "n_present": 0}
    return {
        "min": min(ranks),
        "median": statistics.median(ranks),
        "max": max(ranks),
        "n_present": len(ranks),
    }


def _attribute_target(
    *,
    live: Optional[Mapping[str, Any]],
    pinned: Optional[Mapping[str, Any]],
    no_llm: Optional[Mapping[str, Any]],
) -> str:
    if pinned is None or no_llm is None:
        return "inconclusive"

    if (
        live is not None
        and bool(live["stable"])
        and str(live["classification"]) == "hybrid_top5_hit"
    ):
        return "stable_hit"

    if (
        not bool(pinned["stable"])
        or not bool(no_llm["stable"])
        or str(pinned["classification"]) == "other"
        or str(no_llm["classification"]) == "other"
    ):
        return "inconclusive"

    n_hit = _is_hit(no_llm)
    p_hit = _is_hit(pinned)
    n_miss = _is_miss(no_llm)
    p_miss = _is_miss(pinned)

    if n_miss and p_miss:
        return "fixed_defect"
    if (n_miss and p_hit) or (n_hit and p_miss):
        return "expansion_dependent"
    if n_hit and p_hit:
        return "expansion_variance_only"
    return "inconclusive"


def _instability_attribution(
    *,
    inputs: TraceInputs,
    trace_rows: Sequence[Mapping[str, Any]],
    per_arm: Mapping[str, Mapping[str, Any]],
) -> tuple[list[Dict[str, Any]], Dict[str, int]]:
    indexed = _per_target_index(per_arm)
    summary = {key: 0 for key in ATTRIBUTION_KEYS}
    rows: list[Dict[str, Any]] = []

    for target in sorted(inputs.targets, key=lambda item: (item.qid, item.tmdb_id)):
        key = (target.qid, target.tmdb_id)
        live = indexed.get("live", {}).get(key)
        pinned = indexed.get("pinned", {}).get(key)
        no_llm = indexed.get("no_llm", {}).get(key)
        attribution = _attribute_target(live=live, pinned=pinned, no_llm=no_llm)
        summary[attribution] += 1
        rows.append(
            {
                "qid": target.qid,
                "tmdb_id": target.tmdb_id,
                "title": target.title,
                "live_stable": _stable_value(live),
                "live_classification": _classification_value(live),
                "pinned_stable": _stable_value(pinned),
                "pinned_classification": _classification_value(pinned),
                "no_llm_stable": _stable_value(no_llm),
                "no_llm_classification": _classification_value(no_llm),
                "live_final_rank": _live_final_rank(
                    trace_rows=trace_rows,
                    qid=target.qid,
                    tmdb_id=target.tmdb_id,
                ),
                "attribution": attribution,
            }
        )

    return rows, summary


def _dominant_finding(
    *,
    attribution_summary: Mapping[str, int],
    per_arm: Mapping[str, Mapping[str, Any]],
) -> str:
    control_unstable = any(
        int(per_arm[arm]["loss_classification_counts"].get("unstable", 0)) > 0
        for arm in ("pinned", "no_llm")
        if arm in per_arm
    )
    if int(attribution_summary["inconclusive"]) >= 3 or control_unstable:
        return "inconclusive"

    expansion_total = int(attribution_summary["expansion_variance_only"]) + int(
        attribution_summary["expansion_dependent"]
    )
    fixed_defect = int(attribution_summary["fixed_defect"])

    if expansion_total >= 5 and fixed_defect <= 1:
        return "expansion_related"
    if fixed_defect >= 3 and expansion_total <= 2:
        return "fixed_defect"
    if fixed_defect >= 2 and expansion_total >= 2:
        return "mixed"
    return "inconclusive"


def build_diagnosis(
    *,
    inputs: TraceInputs,
    repeat: int,
    arms: Sequence[str],
    trace_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    _require_live_imports()

    targets_total = len(inputs.targets)
    per_arm = {
        arm: _per_arm_diagnosis(
            arm=arm,
            trace_rows=trace_rows,
            targets_total=targets_total,
        )
        for arm in arms
    }
    attribution_rows, attribution_summary = _instability_attribution(
        inputs=inputs,
        trace_rows=trace_rows,
        per_arm=per_arm,
    )

    if sum(attribution_summary.values()) != targets_total:
        raise HybridStabilityError(
            "attribution_summary does not sum to targets_total"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": inputs.run_id,
        "trace_meta": {
            "traced_at": _utc_timestamp(),
            "pipeline_traced": (
                "src/pipelines/hybrid.py run() lines 66-91 "
                "(parse_filters -> rerank); retrieval_query supplied per arm"
            ),
            "arms": list(arms),
            "repeats": repeat,
            "embedding_model": _config_value("EMBEDDING_MODEL"),
            "reranker_model": _config_value("RERANKER_MODEL"),
            "llm_model": _config_value("LLM_MODEL"),
            "config": _trace_config(),
            "qids_traced": list(inputs.qids),
            "targets_total": targets_total,
        },
        "per_arm": per_arm,
        "instability_attribution": attribution_rows,
        "attribution_summary": attribution_summary,
        "dominant_finding": _dominant_finding(
            attribution_summary=attribution_summary,
            per_arm=per_arm,
        ),
    }


def _required_float(movie: Mapping[str, Any], key: str) -> float:
    if key not in movie:
        title = movie.get("title", "<unknown>")
        raise HybridStabilityError(f"{title}: missing required field {key}")
    try:
        return float(movie[key])
    except (TypeError, ValueError) as exc:
        title = movie.get("title", "<unknown>")
        raise HybridStabilityError(f"{title}: field {key} must be numeric") from exc


def _movie_key(movie: Mapping[str, Any]) -> str:
    value = movie.get("movie_key")
    if value:
        return str(value)
    return hybrid_live_trace.get_movie_key(dict(movie))


def _rank_maps(scored_pool: Sequence[Mapping[str, Any]]) -> tuple[dict[int, int], dict[int, int]]:
    rerank_order = sorted(
        range(len(scored_pool)),
        key=lambda index: _required_float(scored_pool[index], "rerank_score"),
        reverse=True,
    )
    final_order = sorted(
        range(len(scored_pool)),
        key=lambda index: _required_float(scored_pool[index], "final_score"),
        reverse=True,
    )
    rerank_ranks = {movie_index: rank for rank, movie_index in enumerate(rerank_order)}
    final_ranks = {movie_index: rank for rank, movie_index in enumerate(final_order)}
    return rerank_ranks, final_ranks


def _decomposed_row(
    movie: Mapping[str, Any],
    *,
    rerank_rank: int,
    final_rank: int,
    include_title: bool,
) -> Dict[str, Any]:
    rerank_score = _required_float(movie, "rerank_score")
    quality_prior = _required_float(movie, "quality_prior")
    upstream_prior = _required_float(movie, "upstream_prior")
    source_agreement = _required_float(movie, "source_agreement")
    final_score = _required_float(movie, "final_score")
    vote = float(hybrid_live_trace.RERANK_VOTE_COUNT_WEIGHT) * quality_prior
    upstream = float(hybrid_live_trace.RERANK_UPSTREAM_WEIGHT) * upstream_prior
    agreement = (
        float(hybrid_live_trace.RERANK_SOURCE_AGREEMENT_BONUS) * source_agreement
    )
    total = rerank_score + vote + upstream + agreement
    if abs(total - final_score) > 1e-6:
        title = movie.get("title", "<unknown>")
        raise HybridStabilityError(
            f"{title}: decomposed contributions do not sum to final_score"
        )

    row: Dict[str, Any] = {}
    if include_title:
        row["final_rank"] = final_rank
        row["title"] = str(movie.get("title", ""))
    row.update(
        {
            "movie_key": _movie_key(movie),
            "rerank_score": rerank_score,
            "rerank_rank": rerank_rank,
            "quality_prior": quality_prior,
            "upstream_prior": upstream_prior,
            "source_agreement": source_agreement,
            "final_score": final_score,
            "final_rank": final_rank,
            "contributions": {
                "rerank_score": rerank_score,
                "vote": vote,
                "upstream": upstream,
                "agreement": agreement,
            },
        }
    )
    return row


def _decompose_pool(
    *,
    scored_pool: Sequence[Mapping[str, Any]],
    target: Target,
) -> Dict[str, Any]:
    rerank_ranks, final_ranks = _rank_maps(scored_pool)
    decomposed: list[Dict[str, Any]] = []
    target_row: Optional[Dict[str, Any]] = None

    for index, movie in enumerate(scored_pool):
        row = _decomposed_row(
            movie,
            rerank_rank=rerank_ranks[index],
            final_rank=final_ranks[index],
            include_title=True,
        )
        decomposed.append(row)
        if _movie_key(movie) == target.movie_key:
            target_row = _decomposed_row(
                movie,
                rerank_rank=rerank_ranks[index],
                final_rank=final_ranks[index],
                include_title=False,
            )

    if target_row is None:
        return {
            "target_in_pool": False,
            "target": None,
            "leapfrog_competitors": [],
            "leapfrog_count": 0,
        }

    leapfrogs = [
        row
        for row in decomposed
        if int(row["final_rank"]) < int(target_row["final_rank"])
        and int(row["rerank_rank"]) > int(target_row["rerank_rank"])
    ]
    leapfrogs.sort(key=lambda row: int(row["final_rank"]))
    return {
        "target_in_pool": True,
        "target": target_row,
        "leapfrog_competitors": leapfrogs,
        "leapfrog_count": len(leapfrogs),
    }


def _q03_target(inputs: TraceInputs) -> Target:
    matches = [target for target in inputs.targets if target.qid == "q03"]
    if not matches:
        raise HybridStabilityError("q03 target missing from trace inputs")
    return sorted(matches, key=lambda target: target.tmdb_id)[0]


def build_q03_blend_decomposition(
    *,
    inputs: TraceInputs,
    arms: Sequence[str],
    stage_runs: Mapping[tuple[str, str, int], StageRun],
) -> Dict[str, Any]:
    _require_live_imports()

    target = _q03_target(inputs)
    vote_weight = hybrid_live_trace.RERANK_VOTE_COUNT_WEIGHT
    upstream_weight = hybrid_live_trace.RERANK_UPSTREAM_WEIGHT
    agreement_weight = hybrid_live_trace.RERANK_SOURCE_AGREEMENT_BONUS
    per_arm: Dict[str, Any] = {}

    for arm in arms:
        stage_run = stage_runs.get((arm, "q03", 0))
        if stage_run is None:
            raise HybridStabilityError(f"q03 repeat-0 stage run missing for {arm}")
        decomposed = _decompose_pool(
            scored_pool=stage_run.scored_pool,
            target=target,
        )
        per_arm[arm] = {
            "repeat": 0,
            "retrieval_query": stage_run.retrieval_query,
            "target_in_pool": decomposed["target_in_pool"],
            "target": decomposed["target"],
            "leapfrog_competitors": decomposed["leapfrog_competitors"],
            "leapfrog_count": decomposed["leapfrog_count"],
            "note": LIVE_DECOMPOSITION_NOTE if arm == "live" else None,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": inputs.run_id,
        "qid": "q03",
        "tmdb_id": target.tmdb_id,
        "title": target.title,
        "blend_formula": (
            "final_score = rerank_score + "
            f"{vote_weight}*quality_prior + "
            f"{upstream_weight}*upstream_prior + "
            f"{agreement_weight}*source_agreement"
        ),
        "config_weights": {
            "RERANK_VOTE_COUNT_WEIGHT": vote_weight,
            "RERANK_UPSTREAM_WEIGHT": upstream_weight,
            "RERANK_SOURCE_AGREEMENT_BONUS": agreement_weight,
        },
        "priors_are_pool_normalized": True,
        "per_arm": per_arm,
    }


def _write_trace_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    text = "".join(json.dumps(row) + "\n" for row in rows)
    _run_io._atomic_write_text(path, text)


def _output_paths(run_path: Path) -> tuple[Path, Path, Path]:
    output_dir = run_path / "analysis" / "hybrid_expansion_stability"
    return (
        output_dir / "stability_trace.jsonl",
        output_dir / "stability_diagnosis.json",
        output_dir / "q03_blend_decomposition.json",
    )


def dry_run_summary(inputs: TraceInputs, arms: Sequence[str]) -> Dict[str, Any]:
    targets_by_qid = _targets_by_qid(inputs.targets)
    return {
        "run_id": inputs.run_id,
        "arms": list(arms),
        "qids_traced": list(inputs.qids),
        "targets_by_qid": {
            qid: [
                {
                    "tmdb_id": target.tmdb_id,
                    "title": target.title,
                    "movie_key": target.movie_key,
                }
                for target in targets_by_qid[qid]
            ]
            for qid in inputs.qids
        },
    }


def run(
    *,
    run_id: Optional[str] = None,
    repeat: int = 5,
    queries: str | Path | None = None,
    arms: str | Sequence[str] | None = None,
    dry_run: bool = False,
) -> tuple[str, Optional[Path], Optional[Path], Optional[Path], Dict[str, Any]]:
    selected_arms = _parse_arms(arms)
    queries_path = queries if queries is not None else _run_io.EVAL_DIR / "queries" / "v1.jsonl"
    inputs = _prepare_inputs(run_id=run_id, repeat=repeat, queries=queries_path)

    if dry_run:
        return inputs.run_id, None, None, None, dry_run_summary(inputs, selected_arms)

    trace_rows, stage_runs = _trace_all(
        inputs=inputs,
        repeat=repeat,
        arms=selected_arms,
    )
    diagnosis = build_diagnosis(
        inputs=inputs,
        repeat=repeat,
        arms=selected_arms,
        trace_rows=trace_rows,
    )
    decomposition = build_q03_blend_decomposition(
        inputs=inputs,
        arms=selected_arms,
        stage_runs=stage_runs,
    )

    trace_path, diagnosis_path, decomposition_path = _output_paths(inputs.run_path)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    _write_trace_jsonl(trace_path, trace_rows)
    _run_io._atomic_write_json(diagnosis_path, diagnosis)
    _run_io._atomic_write_json(decomposition_path, decomposition)
    return inputs.run_id, trace_path, diagnosis_path, decomposition_path, diagnosis


def _print_dry_run(summary: Mapping[str, Any]) -> None:
    print(f"run_id={summary['run_id']}")
    print("arms=" + ",".join(str(arm) for arm in summary["arms"]))
    print("qids_traced=" + " ".join(str(qid) for qid in summary["qids_traced"]))
    targets_by_qid = summary["targets_by_qid"]
    for qid in summary["qids_traced"]:
        print(f"{qid}:")
        for target in targets_by_qid[qid]:
            print(
                "  "
                f"tmdb_id={target['tmdb_id']} "
                f"title={target['title']} "
                f"movie_key={target['movie_key']}"
            )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace hybrid query-expansion stability across controlled arms."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--repeat", default=5, type=int)
    parser.add_argument(
        "--queries",
        default=str(_run_io.EVAL_DIR / "queries" / "v1.jsonl"),
    )
    parser.add_argument("--arms", default=",".join(DEFAULT_ARMS))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, trace_path, diagnosis_path, decomposition_path, result = run(
            run_id=args.run,
            repeat=args.repeat,
            queries=args.queries,
            arms=args.arms,
            dry_run=args.dry_run,
        )
    except HybridLiveTraceError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(result)
        return 0

    print(f"run_id={run_id}")
    print(f"stability_trace={trace_path}")
    print(f"stability_diagnosis={diagnosis_path}")
    print(f"q03_blend_decomposition={decomposition_path}")
    print("arms=" + ",".join(str(arm) for arm in result["trace_meta"]["arms"]))
    print(f"repeats={result['trace_meta']['repeats']}")
    print(f"targets_total={result['trace_meta']['targets_total']}")
    print(f"attribution_summary={result['attribution_summary']}")
    print(f"dominant_finding={result['dominant_finding']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
