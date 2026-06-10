"""Lazy lookup of deterministic film-mood labels for the serving path.

Loads labels/movie_mood_labels.jsonl (provenance: deterministic_rules) once
per process and answers movie_key -> film_mood_tags. The serving layer never
invents mood tags; an unknown movie_key simply has no tags.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

LABELS_PATH = Path(__file__).resolve().parent.parent / "labels" / "movie_mood_labels.jsonl"

_LOCK = Lock()
_labels: dict[str, list[str]] | None = None


def load(path: Path | None = None, *, labels: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Return the movie_key -> tags map, loading it on first use.

    Tests may inject a small map via `labels`; passing either argument
    replaces the cached map.
    """
    global _labels
    with _LOCK:
        if labels is not None:
            _labels = dict(labels)
        elif path is not None or _labels is None:
            source = path or LABELS_PATH
            loaded: dict[str, list[str]] = {}
            if source.exists():
                with source.open(encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        row = json.loads(line)
                        loaded[row["movie_key"]] = list(row.get("film_mood_tags", []))
            _labels = loaded
        return _labels


def tags_for(movie_key: str) -> list[str]:
    return load().get(movie_key, [])
