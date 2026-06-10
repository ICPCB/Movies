"""Deterministic movie mood labeler.

Reads data/movies_clean.csv (27,762 rows = the recommendation universe) and
labels/mood_rules.jsonl, emits labels/movie_mood_labels.jsonl with exactly one
line per movie. No LLM, no network: pure substring/equality rules, so reruns
are byte-identical (sorted tags, canonical JSON, atomic write).

Usage:
    python labels/build_movie_mood_labels.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

LABELS_DIR = Path(__file__).resolve().parent
REPO_ROOT = LABELS_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import MOVIES_CSV  # constant import only; src behavior untouched
from src.utils.dedup import get_movie_key


def load_rules() -> tuple[dict[str, list[str]], list[tuple[str, list[str]]]]:
    """Returns (genre_rules: genre->tags, keyword_rules: [(pattern, tags)])."""
    genre_rules: dict[str, list[str]] = {}
    keyword_rules: list[tuple[str, list[str]]] = []
    with open(LABELS_DIR / "mood_rules.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rule = json.loads(line)
            if rule["match_type"] == "genre":
                genre_rules[rule["pattern"]] = rule["add"]
            else:
                keyword_rules.append((rule["pattern"], rule["add"]))
    # Deterministic application order: longest pattern first, then alpha.
    keyword_rules.sort(key=lambda r: (-len(r[0]), r[0]))
    return genre_rules, keyword_rules


def tags_for_row(genres: str, keywords: str, genre_rules, keyword_rules) -> list[str]:
    tags: set[str] = set()
    genre_list = [g.strip().lower() for g in genres.split(",") if g.strip()]
    for g in genre_list:
        if g in genre_rules:
            tags.update(genre_rules[g])
    kw_text = " , ".join(k.strip().lower() for k in keywords.split(",") if k.strip())
    for pattern, add in keyword_rules:
        if pattern in kw_text:
            tags.update(add)
    return sorted(tags)


def main() -> int:
    import pandas as pd

    genre_rules, keyword_rules = load_rules()
    df = pd.read_csv(MOVIES_CSV)
    out_path = LABELS_DIR / "movie_mood_labels.jsonl"

    rows = []
    for rec in df.itertuples(index=False):
        genres = getattr(rec, "genres_clean", None)
        if not isinstance(genres, str):
            genres = rec.genres if isinstance(rec.genres, str) else ""
        keywords = getattr(rec, "keywords_clean", None)
        if not isinstance(keywords, str):
            keywords = rec.keywords if isinstance(rec.keywords, str) else ""
        # No "movie_id" field: pipeline movies don't carry one either, so
        # keys resolve to the same title+year form the engine uses.
        movie = {
            "id": rec.id,
            "title": rec.title if isinstance(rec.title, str) else "",
            "year": int(rec.year) if not pd.isna(rec.year) else None,
        }
        rows.append(
            {
                "movie_key": get_movie_key(movie),
                "tmdb_id": int(rec.id),
                "film_mood_tags": tags_for_row(genres, keywords, genre_rules, keyword_rules),
                "provenance": "deterministic_rules",
            }
        )

    # Title+year collisions (distinct films, same normalized key) are merged
    # by the engine's dedup; mirror that here with a tag union, first tmdb_id.
    merged: dict[str, dict] = {}
    for row in rows:
        prev = merged.get(row["movie_key"])
        if prev is None:
            merged[row["movie_key"]] = row
        else:
            prev["film_mood_tags"] = sorted(set(prev["film_mood_tags"]) | set(row["film_mood_tags"]))
    rows = list(merged.values())

    # Atomic, deterministic write (stable key order, \n endings).
    fd, tmp = tempfile.mkstemp(dir=LABELS_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

    tagged = sum(1 for r in rows if r["film_mood_tags"])
    print(f"wrote {len(rows)} lines -> {out_path}")
    print(f"movies with >=1 tag: {tagged} ({tagged / len(rows):.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
