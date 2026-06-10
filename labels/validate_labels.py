"""Deterministic validator for CineMatch mood label artifacts.

Hard gate for every generative or rule-based label artifact: any tag not in
the closed film-mood enum, any category not in the user vocab, or any
malformed line fails validation. Invalid data is rejected, never kept.

Usage:
    python labels/validate_labels.py            # validate vocab/map/rules
    python labels/validate_labels.py --movie-labels  # also validate the 27,762-line file
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LABELS_DIR = Path(__file__).resolve().parent


def _load(name: str):
    with open(LABELS_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def validate_vocabs() -> list[str]:
    errors: list[str] = []
    film = _load("film_mood_vocab.json")
    user = _load("user_mood_vocab.json")
    mood_map = _load("user_mood_map.json")

    film_moods = film["film_moods"]
    if len(film_moods) != len(set(film_moods)):
        errors.append("film_mood_vocab: duplicate moods")
    film_set = set(film_moods)

    categories = set(user["categories"].keys())
    for cat, words in user["categories"].items():
        if not words:
            errors.append(f"user_mood_vocab: empty category {cat}")
        lowered = [w.lower() for w in words]
        if lowered != [w for w in words]:
            errors.append(f"user_mood_vocab: non-lowercase word in {cat}")
    for sensation, cat in user["body_sensations"].items():
        if cat not in categories:
            errors.append(f"user_mood_vocab: body sensation '{sensation}' -> unknown category '{cat}'")

    map_cats = set(mood_map["map"].keys())
    if map_cats != categories:
        errors.append(
            f"user_mood_map: categories mismatch (missing: {sorted(categories - map_cats)}, extra: {sorted(map_cats - categories)})"
        )
    for cat, entry in mood_map["map"].items():
        for side in ("desired", "avoid"):
            for tag in entry[side]:
                if tag not in film_set:
                    errors.append(f"user_mood_map: {cat}.{side} tag '{tag}' not in film enum")
        overlap = set(entry["desired"]) & set(entry["avoid"])
        if overlap:
            errors.append(f"user_mood_map: {cat} has tags in both desired and avoid: {sorted(overlap)}")
    return errors


def validate_rules(path: Path | None = None) -> list[str]:
    errors: list[str] = []
    path = path or (LABELS_DIR / "mood_rules.jsonl")
    if not path.exists():
        return [f"mood_rules: {path} missing"]
    film_set = set(_load("film_mood_vocab.json")["film_moods"])
    seen: set[tuple[str, str]] = set()
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                errors.append(f"mood_rules:{i}: blank line")
                continue
            try:
                rule = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"mood_rules:{i}: bad JSON ({e})")
                continue
            if set(rule) != {"match_type", "pattern", "add"}:
                errors.append(f"mood_rules:{i}: keys must be exactly match_type/pattern/add")
                continue
            if rule["match_type"] not in ("genre", "keyword"):
                errors.append(f"mood_rules:{i}: bad match_type {rule['match_type']!r}")
            if rule["pattern"] != rule["pattern"].lower() or not rule["pattern"].strip():
                errors.append(f"mood_rules:{i}: pattern must be non-empty lowercase")
            key = (rule["match_type"], rule["pattern"])
            if key in seen:
                errors.append(f"mood_rules:{i}: duplicate pattern {key}")
            seen.add(key)
            if not rule["add"] or not isinstance(rule["add"], list):
                errors.append(f"mood_rules:{i}: add must be a non-empty list")
            else:
                for tag in rule["add"]:
                    if tag not in film_set:
                        errors.append(f"mood_rules:{i}: tag '{tag}' not in film enum")
    return errors


def validate_movie_labels(path: Path | None = None, expected_count: int | None = None) -> list[str]:
    errors: list[str] = []
    path = path or (LABELS_DIR / "movie_mood_labels.jsonl")
    if not path.exists():
        return [f"movie_labels: {path} missing"]
    film_set = set(_load("film_mood_vocab.json")["film_moods"])
    seen_keys: set[str] = set()
    count = 0
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                errors.append(f"movie_labels:{i}: blank line")
                continue
            count += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"movie_labels:{i}: bad JSON ({e})")
                continue
            if set(row) != {"movie_key", "tmdb_id", "film_mood_tags", "provenance"}:
                errors.append(f"movie_labels:{i}: unexpected keys {sorted(row)}")
                continue
            if row["provenance"] != "deterministic_rules":
                errors.append(f"movie_labels:{i}: provenance must be deterministic_rules")
            if row["movie_key"] in seen_keys:
                errors.append(f"movie_labels:{i}: duplicate movie_key {row['movie_key']}")
            seen_keys.add(row["movie_key"])
            tags = row["film_mood_tags"]
            if tags != sorted(set(tags)):
                errors.append(f"movie_labels:{i}: tags must be sorted and unique")
            for tag in tags:
                if tag not in film_set:
                    errors.append(f"movie_labels:{i}: tag '{tag}' not in film enum")
    if expected_count is not None and count != expected_count:
        errors.append(f"movie_labels: expected {expected_count} lines, found {count}")
    return errors


def main() -> int:
    errors = validate_vocabs()
    errors += validate_rules()
    if "--movie-labels" in sys.argv:
        # 27,762 CSV rows minus 4 title+year collisions merged by engine dedup.
        errors += validate_movie_labels(expected_count=27758)
    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for e in errors[:50]:
            print(" -", e)
        if len(errors) > 50:
            print(f"   ... and {len(errors) - 50} more")
        return 1
    print("OK: all label artifacts valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
