"""Deterministically build eval/queries/mood_v1.jsonl (ULTRAPLAN phase 6).

50 mood/hybrid queries derived ONLY from the human-provided feeling vocabulary
(labels/user_mood_vocab.json) and the static mood map
(labels/user_mood_map.json): 18 single-mood queries, 18 hybrid mood+plot
queries (fixed plot-element list), and 14 two-mood combinations of adjacent
categories in sorted order. No model, no network, byte-identical on rerun.

Usage:
    python eval/scripts/build_mood_queries.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
VOCAB_PATH = ROOT / "labels" / "user_mood_vocab.json"
MAP_PATH = ROOT / "labels" / "user_mood_map.json"
FILM_VOCAB_PATH = ROOT / "labels" / "film_mood_vocab.json"
OUT_PATH = ROOT / "eval" / "queries" / "mood_v1.jsonl"

# Fixed plot elements for hybrid queries, index-aligned with the sorted
# category list. Generic, era-free phrasing on purpose.
PLOT_ELEMENTS = [
    "a road trip with strangers",
    "a small coastal town",
    "an underdog boxing comeback",
    "a daring mountain rescue",
    "two pen pals finally meeting",
    "a museum heist puzzle",
    "rebuilding a family restaurant",
    "a retired detective's last case",
    "a school talent show",
    "a lighthouse keeper's secret",
    "an unlikely animal friendship",
    "a community garden project",
    "a wrongly accused drifter",
    "a cross-country train journey",
    "a rookie firefighter crew",
    "a wedding gone sideways",
    "a second-chance romance",
    "a neighborhood mystery club",
]


def main() -> int:
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    mood_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))["map"]
    film_moods = set(
        json.loads(FILM_VOCAB_PATH.read_text(encoding="utf-8"))["film_moods"]
    )
    categories = sorted(vocab["categories"])
    assert len(categories) == 18, f"expected 18 categories, got {len(categories)}"
    assert set(categories) == set(mood_map), "vocab/map category mismatch"

    records: list[dict] = []

    def add(query: str, mode: str, slugs: list[str]) -> None:
        desired: set[str] = set()
        avoid: set[str] = set()
        for slug in slugs:
            desired.update(mood_map[slug]["desired"])
            avoid.update(mood_map[slug]["avoid"])
        avoid -= desired  # desired wins, same rule as the web UI
        unknown = (desired | avoid) - film_moods
        assert not unknown, f"off-enum film moods: {unknown}"
        records.append(
            {
                "qid": f"mq{len(records) + 1:02d}",
                "query": query,
                "tags": {
                    "mode": mode,
                    "user_mood_categories": slugs,
                    "desired_film_moods": sorted(desired),
                    "avoid_film_moods": sorted(avoid),
                },
                "notes": (
                    "mood_v1: built deterministically from human_provided vocab + "
                    "authored_static_table map by eval/scripts/build_mood_queries.py; "
                    "no gold relevance labels yet."
                ),
            }
        )

    # 18 single-mood queries: first two feeling words, first two desired moods.
    for slug in categories:
        words = vocab["categories"][slug][:2]
        desired = mood_map[slug]["desired"][:2]
        add(
            f"feeling {' and '.join(words)}, want something "
            f"{' and '.join(desired)}",
            "mood",
            [slug],
        )

    # 18 hybrid queries: first feeling word + fixed plot element.
    for index, slug in enumerate(categories):
        word = vocab["categories"][slug][0]
        add(
            f"feeling {word}, in the mood for {PLOT_ELEMENTS[index]}",
            "hybrid",
            [slug],
        )

    # 14 adjacent two-mood combinations.
    for index in range(14):
        first, second = categories[index], categories[index + 1]
        add(
            f"feeling {vocab['categories'][first][0]} but also "
            f"{vocab['categories'][second][0]}",
            "mood",
            [first, second],
        )

    assert len(records) == 50, f"expected 50 queries, got {len(records)}"
    assert len({record["qid"] for record in records}) == 50

    tmp = OUT_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
    os.replace(tmp, OUT_PATH)
    print(f"wrote {len(records)} queries -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
