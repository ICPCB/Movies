"""Schema validators for Phase 1 eval JSONL records."""

import re
from datetime import datetime
from typing import Any, Dict


QUERY_IDS = {f"q{i:02d}" for i in range(1, 21)}
MODES = {"basic", "advanced", "hybrid"}

ERA_VALUES = {"pre-1980", "1980-2000", "2000-2015", "2015+"}
GENRE_VALUES = {
    "drama",
    "thriller",
    "sf",
    "animation",
    "horror",
    "comedy",
    "action",
    "romance",
    "documentary",
    "other",
}
VOCAB_DISTANCE_VALUES = {"low", "medium", "high"}
LENGTH_VALUES = {"short", "medium", "long"}
SPECIFICITY_VALUES = {"low", "medium", "high"}
AMBIGUITY_VALUES = {"low", "medium", "high"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
GRADE_VALUES = {0, 1, 2, 3, None}

_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)


def _allowed(values: set) -> str:
    return ", ".join(sorted(str(value) for value in values))


def _require(data: Dict[str, Any], key: str, prefix: str = "") -> Any:
    if key not in data:
        name = f"{prefix}.{key}" if prefix else key
        raise ValueError(f"{name} is required")
    return data[key]


def _reject_unknown(data: Dict[str, Any], allowed_keys: set, prefix: str) -> None:
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ValueError(f"{prefix} has unexpected keys: {', '.join(unknown)}")


def _require_object(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_int(value: Any, name: str) -> int:
    if not _is_int(value):
        raise ValueError(f"{name} must be an integer")
    return value


def _is_number(value: Any) -> bool:
    return (isinstance(value, int) or isinstance(value, float)) and not isinstance(
        value, bool
    )


def _require_enum(value: Any, name: str, allowed_values: set) -> None:
    try:
        is_allowed = value in allowed_values
    except TypeError:
        is_allowed = False
    if not is_allowed:
        raise ValueError(f"{name} must be one of: {_allowed(allowed_values)}")


def validate_query_record(d: Dict[str, Any]) -> Dict[str, Any]:
    """Validate one eval/queries/v1.jsonl record."""
    record = _require_object(d, "query record")
    required = {"qid", "query", "tags", "notes"}
    _reject_unknown(record, required, "query record")

    qid = _require_str(_require(record, "qid"), "qid")
    _require_enum(qid, "qid", QUERY_IDS)
    _require_str(_require(record, "query"), "query")

    notes = _require_str(_require(record, "notes"), "notes")
    if len(notes) > 200:
        raise ValueError("notes must be <= 200 characters")

    tags = _require_object(_require(record, "tags"), "tags")
    tag_keys = {
        "era",
        "genre",
        "vocab_distance",
        "length",
        "specificity",
        "ambiguity",
    }
    _reject_unknown(tags, tag_keys, "tags")

    _require_enum(_require(tags, "era", "tags"), "tags.era", ERA_VALUES)
    _require_enum(
        _require(tags, "vocab_distance", "tags"),
        "tags.vocab_distance",
        VOCAB_DISTANCE_VALUES,
    )
    _require_enum(_require(tags, "length", "tags"), "tags.length", LENGTH_VALUES)
    _require_enum(
        _require(tags, "specificity", "tags"),
        "tags.specificity",
        SPECIFICITY_VALUES,
    )
    _require_enum(
        _require(tags, "ambiguity", "tags"),
        "tags.ambiguity",
        AMBIGUITY_VALUES,
    )

    genres = _require(tags, "genre", "tags")
    if not isinstance(genres, list) or not genres:
        raise ValueError("tags.genre must be a non-empty list")
    for index, genre in enumerate(genres):
        if not isinstance(genre, str):
            raise ValueError(f"tags.genre[{index}] must be a string")
        _require_enum(genre, f"tags.genre[{index}]", GENRE_VALUES)

    return record


def validate_candidate_record(d: Dict[str, Any]) -> Dict[str, Any]:
    """Validate one candidates.jsonl record."""
    record = _require_object(d, "candidate record")
    required = {
        "qid",
        "tmdb_id",
        "movie_key",
        "title",
        "year",
        "overview",
        "genres",
        "keywords",
        "tagline",
        "per_mode",
        "in_top_k_of",
        "source",
    }
    _reject_unknown(record, required, "candidate record")

    _require_str(_require(record, "qid"), "qid")
    _require_int(_require(record, "tmdb_id"), "tmdb_id")
    _require_str(_require(record, "movie_key"), "movie_key")
    _require_str(_require(record, "title"), "title")
    _require_int(_require(record, "year"), "year")
    _require_str(_require(record, "overview"), "overview")
    _require_str(_require(record, "genres"), "genres")
    _require_str(_require(record, "keywords"), "keywords")
    _require_str(_require(record, "tagline"), "tagline")

    source = _require_str(_require(record, "source"), "source")
    if source != "union":
        raise ValueError('source must be "union"')

    per_mode = _require_object(_require(record, "per_mode"), "per_mode")
    if not per_mode:
        raise ValueError("per_mode must contain at least one mode")
    for mode, mode_data in per_mode.items():
        if mode not in MODES:
            raise ValueError(f"per_mode has unexpected mode: {mode}")
        if mode_data is None:
            raise ValueError(f"per_mode.{mode} must be an object, not None")
        mode_record = _require_object(mode_data, f"per_mode.{mode}")
        rank = _require_int(
            _require(mode_record, "rank", f"per_mode.{mode}"),
            f"per_mode.{mode}.rank",
        )
        if rank < 0:
            raise ValueError(f"per_mode.{mode}.rank must be >= 0")
        for key, value in mode_record.items():
            if key == "rank":
                continue
            if not _is_number(value):
                raise ValueError(f"per_mode.{mode}.{key} must be a number")

    in_top_k_of = _require(record, "in_top_k_of")
    if not isinstance(in_top_k_of, list):
        raise ValueError("in_top_k_of must be a list")
    for index, mode in enumerate(in_top_k_of):
        if not isinstance(mode, str):
            raise ValueError(f"in_top_k_of[{index}] must be a string")
        if mode not in MODES:
            raise ValueError(f"in_top_k_of[{index}] must be one of: {_allowed(MODES)}")
        if mode not in per_mode:
            raise ValueError(f"in_top_k_of[{index}] must also appear in per_mode")

    return record


def validate_silver_record(d: Dict[str, Any]) -> Dict[str, Any]:
    """Validate one silver_labels.jsonl record."""
    record = _require_object(d, "silver record")
    required = {"qid", "tmdb_id", "grade", "confidence", "reason", "model", "ts"}
    _reject_unknown(record, required, "silver record")

    _require_str(_require(record, "qid"), "qid")
    _require_int(_require(record, "tmdb_id"), "tmdb_id")

    grade = _require(record, "grade")
    if grade not in GRADE_VALUES or isinstance(grade, bool):
        raise ValueError("grade must be one of: 0, 1, 2, 3, None")

    confidence = _require(record, "confidence")
    _require_enum(confidence, "confidence", CONFIDENCE_VALUES)
    if grade is None and confidence != "low":
        raise ValueError('confidence must be "low" when grade is None')

    reason = _require_str(_require(record, "reason"), "reason")
    if len(reason) > 240:
        raise ValueError("reason must be <= 240 characters")

    _require_str(_require(record, "model"), "model")
    ts = _require_str(_require(record, "ts"), "ts")
    if not _TS_RE.fullmatch(ts):
        raise ValueError("ts must be ISO-8601 UTC second precision ending in Z")
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ts must be parseable ISO-8601") from exc

    return record
