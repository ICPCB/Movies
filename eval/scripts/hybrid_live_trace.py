"""Live hybrid-pipeline trace for hybrid-attributable strict misses."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io, error_report
from src.utils.dedup import deduplicate_movies, get_movie_key


SCHEMA_VERSION = "hy-trace-01.v1"
HYBRID_ATTRIBUTABLE_QIDS = (
    "q03",
    "q04",
    "q05",
    "q06",
    "q07",
    "q08",
    "q10",
    "q18",
)
LOSS_CLASSIFICATIONS = (
    "unretrieved",
    "retrieved_dropped_at_fusion",
    "retrieved_dropped_before_rerank_pool",
    "rerank_recovered_final_demoted",
    "rerank_demoted",
    "hybrid_top5_hit",
    "other",
)
LOSS_CLASSIFICATION_COUNT_KEYS = LOSS_CLASSIFICATIONS + ("unstable",)


runtime_config = None
normalize_query = None
expand_retrieval_query = None
expand_query = None
parse_filters = None
semantic_search = None
bm25_search = None
rrf_fusion = None
rerank = None
_score = None

CANDIDATE_POOL = None
RERANK_POOL = None
RERANK_TOP_K = None
FINAL_TOP_K = None
RRF_K = None
SEMANTIC_WEIGHT = None
BM25_WEIGHT = None
RERANK_VOTE_COUNT_WEIGHT = None
RERANK_UPSTREAM_WEIGHT = None
RERANK_SOURCE_AGREEMENT_BONUS = None


class HybridLiveTraceError(ValueError):
    """Raised when live hybrid tracing must stop before writing."""


@dataclass(frozen=True)
class Target:
    qid: str
    tmdb_id: int
    title: str
    year: Any
    release_date: str
    movie_key: str
    gold_grade: int = 3


@dataclass(frozen=True)
class TraceInputs:
    run_id: str
    run_path: Path
    queries_path: Path
    movies_csv_path: Path
    qids: tuple[str, ...]
    queries: Mapping[str, str]
    targets: tuple[Target, ...]


@dataclass(frozen=True)
class StageRun:
    retrieval_query: str
    rerank_query: str
    filters: Optional[Mapping[str, Any]]
    semantic: tuple[dict, ...]
    bm25: tuple[dict, ...]
    rrf: tuple[dict, ...]
    scored_pool: tuple[dict, ...]


def _ensure_live_imports() -> None:
    global runtime_config
    global normalize_query, expand_retrieval_query, expand_query, parse_filters
    global semantic_search, bm25_search, rrf_fusion, rerank, _score
    global CANDIDATE_POOL, RERANK_POOL, RERANK_TOP_K, FINAL_TOP_K, RRF_K
    global SEMANTIC_WEIGHT, BM25_WEIGHT
    global RERANK_VOTE_COUNT_WEIGHT, RERANK_UPSTREAM_WEIGHT
    global RERANK_SOURCE_AGREEMENT_BONUS

    if runtime_config is None:
        from src import config as loaded_config
        from src.config import (
            BM25_WEIGHT as loaded_bm25_weight,
            CANDIDATE_POOL as loaded_candidate_pool,
            FINAL_TOP_K as loaded_final_top_k,
            RERANK_POOL as loaded_rerank_pool,
            RERANK_SOURCE_AGREEMENT_BONUS as loaded_source_agreement_bonus,
            RERANK_TOP_K as loaded_rerank_top_k,
            RERANK_UPSTREAM_WEIGHT as loaded_upstream_weight,
            RERANK_VOTE_COUNT_WEIGHT as loaded_vote_count_weight,
            RRF_K as loaded_rrf_k,
            SEMANTIC_WEIGHT as loaded_semantic_weight,
        )

        runtime_config = loaded_config
        CANDIDATE_POOL = loaded_candidate_pool
        RERANK_POOL = loaded_rerank_pool
        RERANK_TOP_K = loaded_rerank_top_k
        FINAL_TOP_K = loaded_final_top_k
        RRF_K = loaded_rrf_k
        SEMANTIC_WEIGHT = loaded_semantic_weight
        BM25_WEIGHT = loaded_bm25_weight
        RERANK_VOTE_COUNT_WEIGHT = loaded_vote_count_weight
        RERANK_UPSTREAM_WEIGHT = loaded_upstream_weight
        RERANK_SOURCE_AGREEMENT_BONUS = loaded_source_agreement_bonus

    if normalize_query is None or expand_retrieval_query is None:
        from src.retrieval.query_processor import (
            expand_retrieval_query as loaded_expand_retrieval_query,
            normalize_query as loaded_normalize_query,
        )

        normalize_query = loaded_normalize_query
        expand_retrieval_query = loaded_expand_retrieval_query

    if parse_filters is None:
        from src.retrieval.filters import parse_filters as loaded_parse_filters

        parse_filters = loaded_parse_filters

    if semantic_search is None:
        from src.retrieval.semantic import semantic_search as loaded_semantic_search

        semantic_search = loaded_semantic_search

    if bm25_search is None:
        from src.retrieval.bm25 import bm25_search as loaded_bm25_search

        bm25_search = loaded_bm25_search

    if rrf_fusion is None:
        from src.retrieval.fusion import rrf_fusion as loaded_rrf_fusion

        rrf_fusion = loaded_rrf_fusion

    if rerank is None:
        from src.retrieval.reranker import rerank as loaded_rerank

        rerank = loaded_rerank

    if expand_query is None:
        from src.llm.langchain_ollama import expand_query as loaded_expand_query

        expand_query = loaded_expand_query

    if _score is None:
        from src.pipelines.hybrid import _score as loaded_score

        _score = loaded_score


def _require_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise HybridLiveTraceError(f"required input missing: {path}")


def _read_json_object(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except json.JSONDecodeError as exc:
        raise HybridLiveTraceError(f"{path}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise HybridLiveTraceError(f"{path}: JSON root must be an object")
    return value


def _resolve_queries_path(path: str | Path) -> Path:
    queries_path = Path(path)
    if queries_path.is_absolute():
        return queries_path
    return _run_io.PROJECT_ROOT / queries_path


def _load_traced_qids(path: Path) -> tuple[str, ...]:
    diagnosis = _read_json_object(path)
    try:
        value = diagnosis["partition"]["hybrid_attributable"]
    except KeyError as exc:
        raise HybridLiveTraceError(
            "hybrid_gap diagnosis missing partition.hybrid_attributable"
        ) from exc
    if not isinstance(value, list):
        raise HybridLiveTraceError(
            "hybrid_gap diagnosis partition.hybrid_attributable must be a list"
        )
    qids = tuple(str(qid) for qid in value)
    if qids != HYBRID_ATTRIBUTABLE_QIDS:
        raise HybridLiveTraceError(
            "hybrid_attributable qids mismatch: "
            f"expected {list(HYBRID_ATTRIBUTABLE_QIDS)}, got {list(qids)}"
        )
    return qids


def _load_queries(path: Path) -> Dict[str, str]:
    queries: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HybridLiveTraceError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise HybridLiveTraceError(f"{path}:{line_number}: row must be an object")
            try:
                qid = str(row["qid"])
                query = str(row["query"])
            except KeyError as exc:
                raise HybridLiveTraceError(
                    f"{path}:{line_number}: missing qid or query"
                ) from exc
            queries[qid] = query
    return queries


def _load_movie_rows_by_tmdb_id(path: Path) -> Dict[int, Mapping[str, str]]:
    rows: Dict[int, Mapping[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "id" not in reader.fieldnames:
            raise HybridLiveTraceError(f"{path}: movies CSV must contain id column")
        for line_number, row in enumerate(reader, start=2):
            raw_id = row.get("id")
            try:
                tmdb_id = int(float(str(raw_id)))
            except (TypeError, ValueError) as exc:
                raise HybridLiveTraceError(
                    f"{path}:{line_number}: id must be a TMDB integer"
                ) from exc
            rows[tmdb_id] = row
    return rows


def _load_gold_labels(path: Path) -> list[Dict[str, Any]]:
    try:
        return error_report._load_gold_labels(path)
    except ValueError as exc:
        raise HybridLiveTraceError(str(exc)) from exc


def _target_from_movie_row(qid: str, tmdb_id: int, row: Mapping[str, Any]) -> Target:
    movie = {
        "title": row.get("title", ""),
        "year": row.get("year", ""),
        "release_date": row.get("release_date", ""),
    }
    return Target(
        qid=qid,
        tmdb_id=tmdb_id,
        title=str(movie["title"]),
        year=movie["year"],
        release_date=str(movie["release_date"] or ""),
        movie_key=get_movie_key(movie),
    )


def _resolve_targets(
    *,
    qids: Sequence[str],
    gold_labels: Sequence[Mapping[str, Any]],
    movie_rows_by_tmdb_id: Mapping[int, Mapping[str, Any]],
) -> tuple[Target, ...]:
    perfect_by_qid: Dict[str, set[int]] = defaultdict(set)
    traced_qids = set(qids)
    for row in gold_labels:
        qid = str(row["qid"])
        if qid in traced_qids and row.get("grade") == 3:
            perfect_by_qid[qid].add(int(row["tmdb_id"]))

    targets: list[Target] = []
    for qid in qids:
        tmdb_ids = sorted(perfect_by_qid.get(qid, set()))
        if not tmdb_ids:
            raise HybridLiveTraceError(f"{qid} has no gold grade-3 target")
        for tmdb_id in tmdb_ids:
            row = movie_rows_by_tmdb_id.get(tmdb_id)
            if row is None:
                raise HybridLiveTraceError(
                    f"{qid} gold grade-3 tmdb_id {tmdb_id} missing from movies CSV"
                )
            targets.append(_target_from_movie_row(qid, tmdb_id, row))
    return tuple(sorted(targets, key=lambda target: (target.qid, target.tmdb_id)))


def _prepare_inputs(
    *,
    run_id: Optional[str],
    repeat: int,
    queries: str | Path,
) -> TraceInputs:
    if repeat < 1:
        raise HybridLiveTraceError("--repeat must be >= 1")

    actual_run_id = run_id or _run_io.latest_run()
    run_path = _run_io.run_dir(actual_run_id)
    queries_path = _resolve_queries_path(queries)
    movies_csv_path = _run_io.PROJECT_ROOT / "data" / "movies_clean.csv"
    gold_path = run_path / "gold_labels.jsonl"
    diagnosis_path = run_path / "analysis" / "hybrid_gap" / "diagnosis.json"

    _require_paths((gold_path, diagnosis_path, queries_path, movies_csv_path))

    qids = _load_traced_qids(diagnosis_path)
    query_map = _load_queries(queries_path)
    missing_queries = [qid for qid in qids if qid not in query_map]
    if missing_queries:
        raise HybridLiveTraceError(
            "queries file missing traced qid(s): " + ", ".join(missing_queries)
        )

    gold_labels = _load_gold_labels(gold_path)
    movie_rows_by_tmdb_id = _load_movie_rows_by_tmdb_id(movies_csv_path)
    targets = _resolve_targets(
        qids=qids,
        gold_labels=gold_labels,
        movie_rows_by_tmdb_id=movie_rows_by_tmdb_id,
    )

    return TraceInputs(
        run_id=actual_run_id,
        run_path=run_path,
        queries_path=queries_path,
        movies_csv_path=movies_csv_path,
        qids=qids,
        queries=query_map,
        targets=targets,
    )


def _snapshot_movies(movies: Iterable[Mapping[str, Any]]) -> tuple[dict, ...]:
    return tuple(dict(movie) for movie in movies)


def _run_hybrid_stages(query: str) -> StageRun:
    _ensure_live_imports()

    processed = normalize_query(query)

    deterministic_query = expand_retrieval_query(processed)
    if runtime_config.HYBRID_USE_LLM_EXPANSION and runtime_config.LLM_RETRIEVAL_ENABLED:
        retrieval_query = expand_retrieval_query(expand_query(processed) or processed)
    else:
        retrieval_query = deterministic_query
    rerank_query = deterministic_query

    filters = parse_filters(query) or None

    sem = semantic_search(retrieval_query, top_k=CANDIDATE_POOL, filters=filters)
    sem = deduplicate_movies(sem, prefer_score="semantic_score")
    sem_snapshot = _snapshot_movies(sem)

    bm = bm25_search(retrieval_query, top_k=CANDIDATE_POOL, filters=filters)
    bm = deduplicate_movies(bm, prefer_score="bm25_score")
    bm_snapshot = _snapshot_movies(bm)

    fused = rrf_fusion(sem, bm, top_k=RERANK_POOL)
    fused = deduplicate_movies(fused, prefer_score="rrf_score")
    fused.sort(key=lambda x: _score(x, "final_score", "rrf_score"), reverse=True)
    fused_snapshot = _snapshot_movies(fused)

    scored_pool = rerank(
        rerank_query,
        fused,
        top_k=RERANK_TOP_K,
        rerank_pool=RERANK_TOP_K,
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


def _movie_key(movie: Mapping[str, Any]) -> str:
    value = movie.get("movie_key")
    if value:
        return str(value)
    return get_movie_key(dict(movie))


def _find_by_movie_key(
    movies: Sequence[Mapping[str, Any]],
    movie_key: str,
) -> tuple[Optional[Mapping[str, Any]], Optional[int]]:
    for index, movie in enumerate(movies):
        if _movie_key(movie) == movie_key:
            return movie, index
    return None, None


def _find_semantic_by_tmdb_id(
    movies: Sequence[Mapping[str, Any]],
    tmdb_id: int,
) -> tuple[Optional[Mapping[str, Any]], Optional[int]]:
    for index, movie in enumerate(movies):
        try:
            movie_id = int(str(movie.get("id", "")))
        except (TypeError, ValueError):
            continue
        if movie_id == tmdb_id:
            return movie, index
    return None, None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_value(movie: Mapping[str, Any], key: str, fallback: str) -> float:
    if _score is not None:
        return float(_score(dict(movie), key, fallback))
    primary = _coerce_float(movie.get(key))
    if primary is not None:
        return primary
    fallback_value = _coerce_float(movie.get(fallback))
    return fallback_value if fallback_value is not None else 0.0


def _stage_presence(
    movies: Sequence[Mapping[str, Any]],
    target: Target,
    score_key: str,
) -> Dict[str, Any]:
    movie, rank = _find_by_movie_key(movies, target.movie_key)
    present = movie is not None
    return {
        "present": present,
        "rank": rank if present else None,
        "score": _coerce_float(movie.get(score_key)) if present else None,
        "list_len": len(movies),
    }


def _rank_by_score(
    movies: Sequence[Mapping[str, Any]],
    target_key: str,
    *,
    key: str,
    fallback: str,
) -> tuple[Optional[Mapping[str, Any]], Optional[int]]:
    ordered = sorted(
        movies,
        key=lambda movie: _score_value(movie, key, fallback),
        reverse=True,
    )
    return _find_by_movie_key(ordered, target_key)


def _identity_warning(
    semantic_movies: Sequence[Mapping[str, Any]],
    target: Target,
) -> Optional[str]:
    by_key, _rank_by_key = _find_by_movie_key(semantic_movies, target.movie_key)
    by_id, _rank_by_id = _find_semantic_by_tmdb_id(semantic_movies, target.tmdb_id)

    if by_key is not None:
        try:
            semantic_id = int(str(by_key.get("id", "")))
        except (TypeError, ValueError):
            return None
        if semantic_id != target.tmdb_id:
            return (
                "semantic movie_key matched but id "
                f"{semantic_id} != tmdb_id {target.tmdb_id}"
            )

    if by_key is None and by_id is not None:
        return (
            "semantic id matched tmdb_id but movie_key "
            f"{_movie_key(by_id)} != target movie_key {target.movie_key}"
        )

    return None


def _rerank_capture(
    scored_pool: Sequence[Mapping[str, Any]],
    target: Target,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    in_pool_movie, _pool_rank = _find_by_movie_key(scored_pool, target.movie_key)
    if in_pool_movie is None:
        return (
            {"in_pool": False, "rerank_score": None, "rerank_rank": None},
            {
                "final_score": None,
                "final_rank": None,
                "in_top5": False,
                "in_top15": False,
            },
        )

    rerank_movie, rerank_rank = _rank_by_score(
        scored_pool,
        target.movie_key,
        key="rerank_score",
        fallback="rerank_score",
    )
    final_movie, final_rank = _rank_by_score(
        scored_pool,
        target.movie_key,
        key="final_score",
        fallback="rerank_score",
    )

    return (
        {
            "in_pool": True,
            "rerank_score": _coerce_float(rerank_movie.get("rerank_score"))
            if rerank_movie is not None
            else None,
            "rerank_rank": rerank_rank,
        },
        {
            "final_score": _coerce_float(final_movie.get("final_score"))
            if final_movie is not None
            else None,
            "final_rank": final_rank,
            "in_top5": final_rank is not None and final_rank < 5,
            "in_top15": final_rank is not None and final_rank < 15,
        },
    )


def classify_loss(record: Mapping[str, Any]) -> str:
    semantic_present = bool(record["semantic"]["present"])
    bm25_present = bool(record["bm25"]["present"])
    rrf_present = bool(record["rrf"]["present"])
    in_pool = bool(record["rerank"]["in_pool"])
    rerank_rank = record["rerank"]["rerank_rank"]
    final_rank = record["final"]["final_rank"]

    if not semantic_present and not bm25_present:
        return "unretrieved"
    if (semantic_present or bm25_present) and not rrf_present:
        return "retrieved_dropped_at_fusion"
    if rrf_present and not in_pool:
        return "retrieved_dropped_before_rerank_pool"
    if in_pool and final_rank is not None and final_rank < 5:
        return "hybrid_top5_hit"
    if (
        in_pool
        and rerank_rank is not None
        and rerank_rank < 5
        and (final_rank is None or final_rank >= 5)
    ):
        return "rerank_recovered_final_demoted"
    if in_pool and rerank_rank is not None and rerank_rank >= 5:
        return "rerank_demoted"
    return "other"


def _trace_record(
    *,
    run_id: str,
    qid: str,
    target: Target,
    repeat: int,
    stage_run: StageRun,
) -> Dict[str, Any]:
    rerank_data, final_data = _rerank_capture(stage_run.scored_pool, target)
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "qid": qid,
        "tmdb_id": target.tmdb_id,
        "movie_key": target.movie_key,
        "title": target.title,
        "gold_grade": target.gold_grade,
        "repeat": repeat,
        "resolved": {
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


def _trace_all(inputs: TraceInputs, repeat: int) -> list[Dict[str, Any]]:
    targets_by_qid: Dict[str, list[Target]] = defaultdict(list)
    for target in inputs.targets:
        targets_by_qid[target.qid].append(target)

    rows: list[Dict[str, Any]] = []
    for qid in inputs.qids:
        query = inputs.queries[qid]
        for repeat_index in range(repeat):
            stage_run = _run_hybrid_stages(query)
            for target in targets_by_qid[qid]:
                rows.append(
                    _trace_record(
                        run_id=inputs.run_id,
                        qid=qid,
                        target=target,
                        repeat=repeat_index,
                        stage_run=stage_run,
                    )
                )
    rows.sort(key=lambda row: (row["qid"], int(row["tmdb_id"]), int(row["repeat"])))
    return rows


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _config_value(name: str) -> Any:
    if runtime_config is None:
        return None
    return getattr(runtime_config, name, None)


def _trace_config() -> Dict[str, Any]:
    return {
        "CANDIDATE_POOL": CANDIDATE_POOL,
        "RERANK_POOL": RERANK_POOL,
        "RERANK_TOP_K": RERANK_TOP_K,
        "FINAL_TOP_K": FINAL_TOP_K,
        "RRF_K": RRF_K,
        "SEMANTIC_WEIGHT": SEMANTIC_WEIGHT,
        "BM25_WEIGHT": BM25_WEIGHT,
        "RERANK_VOTE_COUNT_WEIGHT": RERANK_VOTE_COUNT_WEIGHT,
        "RERANK_UPSTREAM_WEIGHT": RERANK_UPSTREAM_WEIGHT,
        "RERANK_SOURCE_AGREEMENT_BONUS": RERANK_SOURCE_AGREEMENT_BONUS,
        "HYBRID_USE_LLM_EXPANSION": _config_value("HYBRID_USE_LLM_EXPANSION"),
        "LLM_RETRIEVAL_ENABLED": _config_value("LLM_RETRIEVAL_ENABLED"),
    }


def _per_target(
    trace_rows: Sequence[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    grouped: Dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in trace_rows:
        grouped[(str(row["qid"]), int(row["tmdb_id"]))].append(row)

    per_target: list[Dict[str, Any]] = []
    for qid, tmdb_id in sorted(grouped):
        rows = sorted(grouped[(qid, tmdb_id)], key=lambda row: int(row["repeat"]))
        classifications = [str(row["loss_classification"]) for row in rows]
        stable = len(set(classifications)) == 1
        per_target.append(
            {
                "qid": qid,
                "tmdb_id": tmdb_id,
                "title": str(rows[0]["title"]),
                "classifications": classifications,
                "stable": stable,
                "classification": classifications[0] if stable else "unstable",
            }
        )
    return per_target


def _loss_counts(per_target: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts = {key: 0 for key in LOSS_CLASSIFICATION_COUNT_KEYS}
    for row in per_target:
        classification = str(row["classification"])
        if classification not in counts:
            classification = "other"
        counts[classification] += 1
    return counts


def _mechanism_summary(counts: Mapping[str, int]) -> Dict[str, int]:
    return {
        "recall_depth": int(counts["unretrieved"])
        + int(counts["retrieved_dropped_at_fusion"])
        + int(counts["retrieved_dropped_before_rerank_pool"]),
        "final_score_blend": int(counts["rerank_recovered_final_demoted"]),
        "reranker": int(counts["rerank_demoted"]),
        "resolved_or_unstable": int(counts["hybrid_top5_hit"])
        + int(counts["other"])
        + int(counts["unstable"]),
    }


def _dominant_mechanism(
    counts: Mapping[str, int],
    mechanism_summary: Mapping[str, int],
) -> str:
    if int(counts["unstable"]) >= 3 or int(counts["rerank_demoted"]) >= 2:
        return "inconclusive"

    recall_depth = int(mechanism_summary["recall_depth"])
    final_score_blend = int(mechanism_summary["final_score_blend"])
    resolved_or_unstable = int(mechanism_summary["resolved_or_unstable"])
    reranker_count = int(mechanism_summary["reranker"])

    if recall_depth >= 5 and final_score_blend <= 1 and resolved_or_unstable <= 2:
        return "recall_depth"
    if final_score_blend >= 5 and recall_depth <= 1 and resolved_or_unstable <= 2:
        return "final_score_blend"
    if recall_depth >= 2 and final_score_blend >= 2:
        return "mixed"
    if reranker_count > 0 and reranker_count >= max(
        recall_depth,
        final_score_blend,
        resolved_or_unstable,
    ):
        return "reranker"
    return "inconclusive"


def build_diagnosis(
    *,
    inputs: TraceInputs,
    repeat: int,
    trace_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    _ensure_live_imports()
    per_target = _per_target(trace_rows)
    counts = _loss_counts(per_target)
    mechanisms = _mechanism_summary(counts)
    targets_total = len(inputs.targets)

    if sum(counts.values()) != targets_total:
        raise HybridLiveTraceError("loss_classification_counts does not sum to targets_total")
    if sum(mechanisms.values()) != targets_total:
        raise HybridLiveTraceError("mechanism_summary does not sum to targets_total")

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": inputs.run_id,
        "trace_meta": {
            "traced_at": _utc_timestamp(),
            "pipeline_traced": "src/pipelines/hybrid.py run() lines 52-100",
            "repeats": repeat,
            "embedding_model": _config_value("EMBEDDING_MODEL"),
            "reranker_model": _config_value("RERANKER_MODEL"),
            "llm_model": _config_value("LLM_MODEL"),
            "config": _trace_config(),
            "qids_traced": list(inputs.qids),
            "targets_total": targets_total,
        },
        "per_target": per_target,
        "loss_classification_counts": counts,
        "mechanism_summary": mechanisms,
        "dominant_mechanism": _dominant_mechanism(counts, mechanisms),
    }


def _write_trace_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    text = "".join(json.dumps(row) + "\n" for row in rows)
    _run_io._atomic_write_text(path, text)


def _output_paths(run_path: Path) -> tuple[Path, Path]:
    output_dir = run_path / "analysis" / "hybrid_live_trace"
    return output_dir / "trace.jsonl", output_dir / "diagnosis.json"


def dry_run_summary(inputs: TraceInputs) -> Dict[str, Any]:
    targets_by_qid: Dict[str, list[Target]] = defaultdict(list)
    for target in inputs.targets:
        targets_by_qid[target.qid].append(target)

    return {
        "run_id": inputs.run_id,
        "qids_traced": list(inputs.qids),
        "targets_by_qid": {
            qid: [
                {
                    "tmdb_id": target.tmdb_id,
                    "title": target.title,
                    "movie_key": target.movie_key,
                }
                for target in sorted(targets_by_qid[qid], key=lambda item: item.tmdb_id)
            ]
            for qid in inputs.qids
        },
    }


def run(
    *,
    run_id: Optional[str] = None,
    repeat: int = 3,
    queries: str | Path | None = None,
    dry_run: bool = False,
) -> tuple[str, Optional[Path], Optional[Path], Dict[str, Any]]:
    queries_path = queries if queries is not None else _run_io.EVAL_DIR / "queries" / "v1.jsonl"
    inputs = _prepare_inputs(run_id=run_id, repeat=repeat, queries=queries_path)

    if dry_run:
        return inputs.run_id, None, None, dry_run_summary(inputs)

    trace_rows = _trace_all(inputs, repeat)
    diagnosis = build_diagnosis(inputs=inputs, repeat=repeat, trace_rows=trace_rows)

    trace_path, diagnosis_path = _output_paths(inputs.run_path)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    _write_trace_jsonl(trace_path, trace_rows)
    _run_io._atomic_write_json(diagnosis_path, diagnosis)
    return inputs.run_id, trace_path, diagnosis_path, diagnosis


def _print_dry_run(summary: Mapping[str, Any]) -> None:
    print(f"run_id={summary['run_id']}")
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
        description="Trace live hybrid pipeline ranks for hybrid-attributable targets."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--repeat", default=3, type=int)
    parser.add_argument(
        "--queries",
        default=str(_run_io.EVAL_DIR / "queries" / "v1.jsonl"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, trace_path, diagnosis_path, result = run(
            run_id=args.run,
            repeat=args.repeat,
            queries=args.queries,
            dry_run=args.dry_run,
        )
    except HybridLiveTraceError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(result)
        return 0

    print(f"run_id={run_id}")
    print(f"trace={trace_path}")
    print(f"diagnosis={diagnosis_path}")
    print(f"repeats={result['trace_meta']['repeats']}")
    print(f"targets_total={result['trace_meta']['targets_total']}")
    print(f"loss_classification_counts={result['loss_classification_counts']}")
    print(f"dominant_mechanism={result['dominant_mechanism']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
