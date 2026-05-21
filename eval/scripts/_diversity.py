"""Diversity summary helpers for Phase 1 query JSONL files."""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


ERA_VALUES = ("pre-1980", "1980-2000", "2000-2015", "2015+")
GENRE_VALUES = (
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
)
VOCAB_DISTANCE_VALUES = ("high", "medium", "low")
LENGTH_VALUES = ("short", "medium", "long")
AMBIGUITY_VALUES = ("low", "medium", "high")

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")


def word_count(query: str) -> int:
    """Return the word count used for the query length tag."""
    if not isinstance(query, str):
        return 0
    return len(_WORD_RE.findall(query))


def length_bucket(query: str) -> str:
    """Classify query length from text, never from tags.length."""
    count = word_count(query)
    if count <= 8:
        return "short"
    if count <= 20:
        return "medium"
    return "long"


def _blank_counts(values: Iterable[str]) -> Dict[str, int]:
    return {value: 0 for value in values}


def _increment(counts: Dict[str, int], key: Any) -> None:
    if not isinstance(key, str):
        key = str(key)
    counts[key] = counts.get(key, 0) + 1


def summarize(records: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Return counts for the five diversity axes.

    Length is recomputed from the query word count so the summary catches stale
    or incorrect authored tags.
    """
    summary = {
        "era": _blank_counts(ERA_VALUES),
        "genre": _blank_counts(GENRE_VALUES),
        "vocab_distance": _blank_counts(VOCAB_DISTANCE_VALUES),
        "length": _blank_counts(LENGTH_VALUES),
        "ambiguity": _blank_counts(AMBIGUITY_VALUES),
    }

    for record in records:
        tags = record.get("tags", {})
        if not isinstance(tags, Mapping):
            tags = {}

        _increment(summary["era"], tags.get("era"))
        _increment(summary["vocab_distance"], tags.get("vocab_distance"))
        _increment(summary["length"], length_bucket(record.get("query", "")))
        _increment(summary["ambiguity"], tags.get("ambiguity"))

        genres = tags.get("genre", [])
        if not isinstance(genres, list):
            genres = [genres]
        for genre in genres:
            _increment(summary["genre"], genre)

    return summary


def summarize_file(path: str | Path) -> Dict[str, Dict[str, int]]:
    """Load a JSONL query file and return summarize(records)."""
    records = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return summarize(records)
