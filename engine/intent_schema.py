from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator


_STRING_LIST = {"type": "array", "items": {"type": "string"}}

INTENT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["mood", "content", "hybrid", "category", "random"],
        },
        "user_moods": _STRING_LIST,
        "desired_film_moods": _STRING_LIST,
        "avoid_film_moods": _STRING_LIST,
        "plot_elements": _STRING_LIST,
        "genres_include": _STRING_LIST,
        "genres_exclude": _STRING_LIST,
        "era": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "min_year": {"type": ["integer", "null"]},
                "max_year": {"type": ["integer", "null"]},
            },
            "required": ["min_year", "max_year"],
        },
        "tone": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "darkness": {"type": "number", "minimum": -1, "maximum": 1},
                "intensity": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["darkness", "intensity"],
        },
        "constraints": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "min_rating": {"type": ["number", "null"]},
            },
            "required": ["min_rating"],
        },
        "free_text_query": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "mode",
        "user_moods",
        "desired_film_moods",
        "avoid_film_moods",
        "plot_elements",
        "genres_include",
        "genres_exclude",
        "era",
        "tone",
        "constraints",
        "free_text_query",
        "confidence",
    ],
}

_VALIDATOR = Draft202012Validator(INTENT_SCHEMA)


def validate_intent(obj: object) -> tuple[bool, list[str]]:
    errors = sorted(
        _VALIDATOR.iter_errors(obj),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    messages = []
    for error in errors:
        path = ".".join(str(part) for part in error.absolute_path)
        messages.append(f"{path}: {error.message}" if path else error.message)
    return not messages, messages


def empty_intent(free_text: str, mode: str = "content") -> dict[str, Any]:
    return {
        "mode": mode,
        "user_moods": [],
        "desired_film_moods": [],
        "avoid_film_moods": [],
        "plot_elements": [],
        "genres_include": [],
        "genres_exclude": [],
        "era": {"min_year": None, "max_year": None},
        "tone": {"darkness": 0.0, "intensity": 0.0},
        "constraints": {"min_rating": None},
        "free_text_query": free_text,
        "confidence": 0.0,
    }
