"""Run Phase 1 candidate pipelines and write candidates.jsonl."""

from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io, _schemas
from src.utils.dedup import get_movie_key


MODE_ORDER = ("basic", "advanced", "hybrid")
MODE_INDEX = {mode: index for index, mode in enumerate(MODE_ORDER)}
SCORE_KEYS = (
    "semantic_score",
    "bm25_score",
    "rrf_score",
    "rerank_score",
    "final_score",
)
SOFT_CAP = 8
HARD_MAX = 15
TOP5_COUNT = 5


def _coerce_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        as_float = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not math.isfinite(as_float):
        raise ValueError(f"{name} must be finite")
    as_int = int(as_float)
    if as_float != as_int:
        raise ValueError(f"{name} must be an integer")
    return as_int


def _coerce_score(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(score):
        return 0.0
    return score


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _candidate_tmdb_id(movie: Mapping[str, Any]) -> int:
    for key in ("tmdb_id", "movie_id", "id"):
        value = movie.get(key)
        if value not in (None, ""):
            return _coerce_int(value, key)
    raise ValueError("candidate is missing tmdb_id/movie_id/id")


def _candidate_movie_key(movie: Mapping[str, Any]) -> str:
    value = movie.get("movie_key")
    if value not in (None, ""):
        return str(value)
    return get_movie_key(dict(movie))


def _candidate_year(movie: Mapping[str, Any]) -> int:
    value = movie.get("year")
    if value not in (None, ""):
        try:
            return _coerce_int(value, "year")
        except ValueError:
            pass
    release_date = _coerce_text(movie.get("release_date"))
    if len(release_date) >= 4 and release_date[:4].isdigit():
        return int(release_date[:4])
    return 0


def _mode_evidence(movie: Mapping[str, Any], rank: int) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {"rank": rank}
    for key in SCORE_KEYS:
        if key in movie:
            evidence[key] = _coerce_score(movie.get(key))
    return evidence


def _merge_missing_fields(
    keeper: MutableMapping[str, Any],
    challenger: Mapping[str, Any],
) -> None:
    for key, value in challenger.items():
        if key not in keeper or keeper.get(key) in (None, "", 0, 0.0):
            if value not in (None, "", 0, 0.0):
                keeper[key] = value


def _entry_sort_key(entry: Mapping[str, Any]) -> tuple[int, int, int]:
    per_mode = entry["per_mode"]
    best_rank = min(mode_data["rank"] for mode_data in per_mode.values())
    best_mode = min(
        MODE_INDEX[mode]
        for mode, mode_data in per_mode.items()
        if mode_data["rank"] == best_rank
    )
    return best_rank, best_mode, entry["first_seen"]


def _build_record(qid: str, entry: Mapping[str, Any]) -> Dict[str, Any]:
    movie = entry["movie"]
    per_mode = {
        mode: entry["per_mode"][mode]
        for mode in MODE_ORDER
        if mode in entry["per_mode"]
    }
    record = {
        "qid": qid,
        "tmdb_id": entry["tmdb_id"],
        "movie_key": entry["movie_key"],
        "title": _coerce_text(movie.get("title")),
        "year": _candidate_year(movie),
        "overview": _coerce_text(movie.get("overview")),
        "genres": _coerce_text(movie.get("genres")),
        "keywords": _coerce_text(movie.get("keywords")),
        "tagline": _coerce_text(movie.get("tagline")),
        "per_mode": per_mode,
        "in_top_k_of": [mode for mode in MODE_ORDER if mode in per_mode],
        "source": "union",
    }
    _schemas.validate_candidate_record(record)
    return record


def build_candidate_union(
    qid: str,
    per_mode_results: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    soft_cap: int = SOFT_CAP,
    hard_max: int = HARD_MAX,
    top5_count: int = TOP5_COUNT,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """Build one query's deduplicated candidate union.

    The input values are already-ranked result lists for each mode. The return
    value is (candidate_records, warnings), where warnings are diagnostic
    strings that callers should append to the run manifest.
    """

    entries: Dict[int, Dict[str, Any]] = {}
    warnings: List[str] = []
    seen_warning_keys: set[tuple[str, int, str, str]] = set()
    first_seen = 0

    for mode in MODE_ORDER:
        if mode not in per_mode_results:
            continue
        for rank, movie in enumerate(per_mode_results[mode]):
            if not isinstance(movie, Mapping):
                continue

            tmdb_id = _candidate_tmdb_id(movie)
            movie_key = _candidate_movie_key(movie)
            entry = entries.get(tmdb_id)
            if entry is None:
                entry = {
                    "tmdb_id": tmdb_id,
                    "movie_key": movie_key,
                    "movie_keys": {movie_key},
                    "movie": dict(movie),
                    "per_mode": {},
                    "first_seen": first_seen,
                }
                entries[tmdb_id] = entry
                first_seen += 1
            else:
                if movie_key not in entry["movie_keys"]:
                    existing = entry["movie_key"]
                    warning_key = (qid, tmdb_id, existing, movie_key)
                    if warning_key not in seen_warning_keys:
                        warnings.append(
                            "dedup_bug: "
                            f"qid={qid} tmdb_id={tmdb_id} "
                            f"movie_keys={existing},{movie_key}"
                        )
                        seen_warning_keys.add(warning_key)
                    entry["movie_keys"].add(movie_key)
                _merge_missing_fields(entry["movie"], movie)

            if mode not in entry["per_mode"]:
                entry["per_mode"][mode] = _mode_evidence(movie, rank)

    sorted_entries = sorted(entries.values(), key=_entry_sort_key)
    required_ids = {
        entry["tmdb_id"]
        for entry in sorted_entries
        if any(
            mode_data["rank"] < top5_count
            for mode_data in entry["per_mode"].values()
        )
    }

    selected_ids = set()
    for entry in sorted_entries[:soft_cap]:
        selected_ids.add(entry["tmdb_id"])
    for entry in sorted_entries:
        if entry["tmdb_id"] in required_ids:
            selected_ids.add(entry["tmdb_id"])

    selected_entries = [
        entry for entry in sorted_entries if entry["tmdb_id"] in selected_ids
    ]
    if len(selected_entries) > hard_max:
        required_entries = [
            entry for entry in selected_entries if entry["tmdb_id"] in required_ids
        ]
        optional_entries = [
            entry for entry in selected_entries if entry["tmdb_id"] not in required_ids
        ]
        selected_entries = (required_entries + optional_entries)[:hard_max]
        selected_entries.sort(key=_entry_sort_key)

    records = [_build_record(qid, entry) for entry in selected_entries]
    return records, warnings


def _load_queries(path: Path, limit: int | None) -> List[Dict[str, Any]]:
    queries: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            try:
                _schemas.validate_query_record(record)
            except ValueError:
                _schemas.validate_query_record_v2(record)
            queries.append(record)
            if limit is not None and len(queries) >= limit:
                break
    return queries


def _pipeline_accepts_explanations(run_func: Callable[..., Any]) -> bool:
    return "with_explanation" in inspect.signature(run_func).parameters


def _call_pipeline(run_func: Callable[..., Any], query: str, top_k: int) -> List[dict]:
    if _pipeline_accepts_explanations(run_func):
        result = run_func(query, top_k=top_k, with_explanation=False)
    else:
        result = run_func(query, top_k=top_k)
    if not isinstance(result, list):
        raise ValueError("pipeline returned a non-list result")
    return result


def _run_all_modes(query: str, top_k: int) -> Dict[str, List[dict]]:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from src.pipelines import advanced, basic, hybrid

    return {
        "basic": _call_pipeline(basic.run, query, top_k),
        "advanced": _call_pipeline(advanced.run, query, top_k),
        "hybrid": _call_pipeline(hybrid.run, query, top_k),
    }


def _write_candidates(run_id: str, records: Iterable[Mapping[str, Any]]) -> Path:
    candidates_path = _run_io.run_dir(run_id) / "candidates.jsonl"
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    text = "\n".join(lines)
    if text:
        text += "\n"
    _run_io._atomic_write_text(candidates_path, text)
    return candidates_path


def run(
    *,
    queries_path: Path,
    top_k: int,
    seed: int,
    run_id: str | None,
    limit: int | None,
) -> tuple[str, Path, int]:
    if top_k != HARD_MAX:
        raise ValueError("CX-03 requires --top-k 15")
    if limit is not None and limit < 0:
        raise ValueError("--limit must be >= 0")

    actual_run_id = run_id or _run_io.new_run_id()
    _run_io.ensure_run_dir(actual_run_id)
    _run_io.write_manifest(actual_run_id, rng_seed=seed)
    _run_io.write_config_snapshot(actual_run_id)

    queries = _load_queries(queries_path, limit)
    all_records: List[Dict[str, Any]] = []

    for query_record in queries:
        qid = query_record["qid"]
        query = query_record["query"]
        print(f"running {qid}", flush=True)
        per_mode_results = _run_all_modes(query, top_k)
        records, warnings = build_candidate_union(qid, per_mode_results)
        for warning in warnings:
            print(warning, file=sys.stderr, flush=True)
            _run_io.append_warning(actual_run_id, warning)
        all_records.extend(records)

    candidates_path = _write_candidates(actual_run_id, all_records)
    _run_io.update_timestamp(actual_run_id, "candidates_done")
    return actual_run_id, candidates_path, len(all_records)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run CineMatch Phase 1 pipelines and build candidates.jsonl."
    )
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--top-k", required=True, type=int)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--limit", default=None, type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id, candidates_path, record_count = run(
        queries_path=args.queries,
        top_k=args.top_k,
        seed=args.seed,
        run_id=args.run_id,
        limit=args.limit,
    )
    print(f"run_id={run_id}")
    print(f"candidates={candidates_path}")
    print(f"records={record_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
