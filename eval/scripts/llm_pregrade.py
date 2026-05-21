"""LLM pre-grading for Phase 1 silver labels."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io, _schemas
from src.config import LLM_MODEL, LLM_TIMEOUT_SECONDS
from src.llm.langchain_ollama import _invoke_with_timeout


VALID_GRADES = {0, 1, 2, 3}
VALID_CONFIDENCES = {"high", "medium", "low"}
GATE_FRESH_CALLS = 20
MIN_PARSE_RATE = 0.95

PROMPT_TEMPLATE = """You are a movie-relevance grader. Given a USER QUERY and a MOVIE's metadata,
assign a relevance grade and a confidence level.

GRADES:
  3 = perfect match (the query clearly describes this exact movie)
  2 = good match (most of the query's themes/plot elements present)
  1 = related (some shared themes/genre but not a strong match)
  0 = irrelevant (no meaningful connection)

CONFIDENCE:
  high   = metadata clearly supports the grade
  medium = metadata partially supports; ambiguity exists
  low    = metadata too thin / could plausibly be a different grade

Ground your grade STRICTLY in the metadata. Do not guess plot details
not present. If the overview is empty or generic, default to confidence: low.

USER QUERY: {query}

MOVIE:
  Title: {title} ({year})
  Genres: {genres}
  Overview: {overview}
  Keywords: {keywords}
  Tagline: {tagline}

Reply as JSON:
{{"grade": <0-3>, "confidence": "<high|medium|low>", "reason": "<one sentence>"}}"""


LLMCaller = Callable[[str], Any]


@dataclass(frozen=True)
class GradeOutcome:
    grade: Optional[int]
    confidence: str
    reason: str
    valid_parse: bool


@dataclass(frozen=True)
class PregradeResult:
    run_id: str
    silver_path: Path
    rows_written: int
    cache_hits: int
    fresh_attempts: int
    successful_parses: int
    parse_rate: Optional[float]
    completed: bool
    aborted: bool
    exit_code: int


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _clean_reason(reason: Any) -> str:
    if reason is None:
        text = ""
    else:
        text = str(reason)
    text = " ".join(text.strip().split())
    return text[:240]


def _response_text(response: Any) -> str:
    if hasattr(response, "content"):
        return str(response.content or "")
    return str(response or "")


def _default_llm_caller(prompt: str) -> Any:
    return _invoke_with_timeout(prompt, timeout=LLM_TIMEOUT_SECONDS)


def _build_prompt(query: str, candidate: Mapping[str, Any]) -> str:
    return PROMPT_TEMPLATE.format(
        query=query,
        title=candidate.get("title", ""),
        year=candidate.get("year", ""),
        genres=candidate.get("genres", ""),
        overview=candidate.get("overview", ""),
        keywords=candidate.get("keywords", ""),
        tagline=candidate.get("tagline", ""),
    )


def _failure(reason: str) -> GradeOutcome:
    return GradeOutcome(
        grade=None,
        confidence="low",
        reason=_clean_reason(reason) or "llm grading failed",
        valid_parse=False,
    )


def _parse_grade_response(response: Any) -> GradeOutcome:
    text = _response_text(response).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return _failure(f"json_parse_error: {exc.msg}")

    if not isinstance(parsed, dict):
        return _failure("json_parse_error: response is not an object")

    grade = parsed.get("grade")
    if isinstance(grade, bool) or grade not in VALID_GRADES:
        return _failure(f"invalid grade: {grade!r}")

    confidence = parsed.get("confidence")
    if confidence not in VALID_CONFIDENCES:
        return _failure(f"invalid confidence: {confidence!r}")

    reason = parsed.get("reason")
    if not isinstance(reason, str):
        return _failure("invalid reason: missing or non-string")

    return GradeOutcome(
        grade=grade,
        confidence=confidence,
        reason=_clean_reason(reason),
        valid_parse=True,
    )


def _grade_candidate(
    query: str,
    candidate: Mapping[str, Any],
    llm_caller: LLMCaller,
) -> GradeOutcome:
    prompt = _build_prompt(query, candidate)
    try:
        response = llm_caller(prompt)
    except (TimeoutError, concurrent.futures.TimeoutError):
        return _failure("timeout")
    except Exception as exc:
        return _failure(f"exception: {exc}")
    return _parse_grade_response(response)


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


def _load_queries(path: Path) -> Dict[str, str]:
    queries: Dict[str, str] = {}
    for record in _read_jsonl(path):
        query_record = _schemas.validate_query_record(record)
        queries[query_record["qid"]] = query_record["query"]
    return queries


def _load_candidates(path: Path) -> List[Dict[str, Any]]:
    return [_schemas.validate_candidate_record(record) for record in _read_jsonl(path)]


def _load_success_cache(path: Path, model: str) -> set[tuple[str, int, str]]:
    if not path.exists():
        return set()

    successes: set[tuple[str, int, str]] = set()
    for record in _read_jsonl(path):
        silver = _schemas.validate_silver_record(record)
        if silver["model"] == model and silver["grade"] is not None:
            successes.add((silver["qid"], silver["tmdb_id"], silver["model"]))
    return successes


def _append_silver_record(path: Path, record: Mapping[str, Any]) -> None:
    _schemas.validate_silver_record(dict(record))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        handle.flush()


def _record_seed(run_id: str, seed: int) -> None:
    manifest_path = _run_io.run_dir(run_id) / "run_manifest.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError("run_manifest.json must contain an object")
    if manifest.get("rng_seed") == seed:
        return
    manifest["rng_seed"] = seed
    _run_io._atomic_write_json(manifest_path, manifest)


def _make_silver_record(
    candidate: Mapping[str, Any],
    outcome: GradeOutcome,
    model: str,
) -> Dict[str, Any]:
    record = {
        "qid": candidate["qid"],
        "tmdb_id": candidate["tmdb_id"],
        "grade": outcome.grade,
        "confidence": outcome.confidence,
        "reason": outcome.reason,
        "model": model,
        "ts": _utc_timestamp(),
    }
    _schemas.validate_silver_record(record)
    return record


def run(
    *,
    run_id: Optional[str] = None,
    limit: Optional[int] = None,
    seed: int = 42,
    llm_caller: Optional[LLMCaller] = None,
    queries_path: Optional[Path] = None,
) -> PregradeResult:
    if limit is not None and limit < 0:
        raise ValueError("--limit must be >= 0")

    actual_run_id = run_id or _run_io.latest_run()
    run_path = _run_io.run_dir(actual_run_id)
    candidates_path = run_path / "candidates.jsonl"
    silver_path = run_path / "silver_labels.jsonl"
    query_catalog_path = queries_path or (_run_io.EVAL_DIR / "queries" / "v1.jsonl")
    caller = llm_caller or _default_llm_caller

    _record_seed(actual_run_id, seed)
    queries = _load_queries(query_catalog_path)
    candidates = _load_candidates(candidates_path)

    rows_written = 0
    cache_hits = 0
    fresh_attempts = 0
    successful_parses = 0
    gate_parse_rate: Optional[float] = None
    limit_stopped = False

    for candidate in candidates:
        qid = candidate["qid"]
        key = (qid, candidate["tmdb_id"], LLM_MODEL)
        success_cache = _load_success_cache(silver_path, LLM_MODEL)
        if key in success_cache:
            cache_hits += 1
            continue

        if limit is not None and fresh_attempts >= limit:
            limit_stopped = True
            break

        query = queries.get(qid)
        if query is None:
            raise ValueError(f"missing query text for qid={qid}")

        outcome = _grade_candidate(query, candidate, caller)
        fresh_attempts += 1
        if outcome.valid_parse:
            successful_parses += 1

        record = _make_silver_record(candidate, outcome, LLM_MODEL)
        _append_silver_record(silver_path, record)
        rows_written += 1

        if fresh_attempts == GATE_FRESH_CALLS:
            gate_parse_rate = successful_parses / GATE_FRESH_CALLS
            if gate_parse_rate < MIN_PARSE_RATE:
                message = (
                    "llm_pregrade aborted: "
                    f"parse_rate={gate_parse_rate:.3f} below 0.95"
                )
                _run_io.append_warning(actual_run_id, message)
                return PregradeResult(
                    run_id=actual_run_id,
                    silver_path=silver_path,
                    rows_written=rows_written,
                    cache_hits=cache_hits,
                    fresh_attempts=fresh_attempts,
                    successful_parses=successful_parses,
                    parse_rate=gate_parse_rate,
                    completed=False,
                    aborted=True,
                    exit_code=2,
                )

    completed = not limit_stopped
    observed_parse_rate: Optional[float]
    if gate_parse_rate is not None:
        observed_parse_rate = gate_parse_rate
    elif fresh_attempts:
        observed_parse_rate = successful_parses / fresh_attempts
    else:
        observed_parse_rate = None

    if completed:
        _run_io.update_timestamp(actual_run_id, "silver_done")

    return PregradeResult(
        run_id=actual_run_id,
        silver_path=silver_path,
        rows_written=rows_written,
        cache_hits=cache_hits,
        fresh_attempts=fresh_attempts,
        successful_parses=successful_parses,
        parse_rate=observed_parse_rate,
        completed=completed,
        aborted=False,
        exit_code=0,
    )


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LLM pre-grade CineMatch candidates into silver labels."
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("--seed", default=42, type=int)
    return parser.parse_args(argv)


def main(
    argv: Optional[list[str]] = None,
    *,
    llm_caller: Optional[LLMCaller] = None,
) -> int:
    args = _parse_args(argv)
    result = run(
        run_id=args.run,
        limit=args.limit,
        seed=args.seed,
        llm_caller=llm_caller,
    )
    parse_rate = "n/a" if result.parse_rate is None else f"{result.parse_rate:.3f}"
    print(f"run_id={result.run_id}")
    print(f"silver_labels={result.silver_path}")
    print(f"rows_written={result.rows_written}")
    print(f"cache_hits={result.cache_hits}")
    print(f"fresh_attempts={result.fresh_attempts}")
    print(f"successful_parses={result.successful_parses}")
    print(f"parse_rate={parse_rate}")
    print(f"completed={str(result.completed).lower()}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
