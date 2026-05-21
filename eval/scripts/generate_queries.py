"""Generate the Phase 1 draft query set.

The eight high-vocab-distance drafts intentionally use essayistic or figurative
phrasing such as "chase guilt", "weaponize popularity", "exhausted
tenderness", "failing upward", and "sunlit folk nightmare". Those phrases are
unlikely to appear verbatim in TMDB-style plot overviews, which usually name
plot events, characters, and settings more directly. This draft therefore
stresses semantic retrieval behavior rather than exact keyword overlap.
"""

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

from eval.scripts import _diversity, _schemas  # noqa: E402


DEFAULT_OUT = PROJECT_ROOT / "eval" / "queries" / "v1.candidate.jsonl"
RESERVED_FINAL_OUT = PROJECT_ROOT / "eval" / "queries" / "v1.jsonl"

EXPECTED_COUNTS = {
    "era": {"pre-1980": 4, "1980-2000": 5, "2000-2015": 6, "2015+": 5},
    "vocab_distance": {"high": 8, "medium": 8, "low": 4},
    "length": {"short": 8, "medium": 8, "long": 4},
    "ambiguity": {"low": 4, "medium": 12, "high": 4},
}
REQUIRED_GENRES = ("drama", "thriller", "sf", "animation", "horror", "comedy")

_HIGH_NOTE = (
    "High-vocab draft: essayistic phrasing chosen to avoid verbatim TMDB overview terms."
)
_MEDIUM_NOTE = "Medium-vocab draft for H1 human review."
_LOW_NOTE = "Low-vocab draft with direct plot or genre wording for H1 human review."

_DRAFTS = [
    {
        "query": "crooked detectives chase guilt through one bad night",
        "era": "2015+",
        "genre": ["thriller", "action", "drama"],
        "vocab_distance": "high",
        "specificity": "low",
        "ambiguity": "high",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "lonely astronaut debates a polite machine",
        "era": "pre-1980",
        "genre": ["sf", "drama"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "kids outrun grief with a giant forest friend",
        "era": "1980-2000",
        "genre": ["animation", "drama"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "shark attack at a beach resort",
        "era": "pre-1980",
        "genre": ["thriller", "horror"],
        "vocab_distance": "low",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _LOW_NOTE,
    },
    {
        "query": "teenage witches weaponize popularity and resentment",
        "era": "1980-2000",
        "genre": ["horror", "comedy"],
        "vocab_distance": "high",
        "specificity": "low",
        "ambiguity": "high",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "animated toys fear being replaced",
        "era": "1980-2000",
        "genre": ["animation", "comedy"],
        "vocab_distance": "low",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _LOW_NOTE,
    },
    {
        "query": "a newsroom drama about truth, ratings, and public panic",
        "era": "pre-1980",
        "genre": ["drama"],
        "vocab_distance": "medium",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a paranoid political thriller where surveillance turns hotel rooms, "
            "offices, and casual friendships into traps that make every private "
            "word feel dangerous"
        ),
        "era": "pre-1980",
        "genre": ["thriller", "drama"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "a romantic comedy about fake identities, email, and urban bookstores",
        "era": "1980-2000",
        "genre": ["comedy", "romance"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": "a body horror story where ambition mutates into something intimate and disgusting",
        "era": "1980-2000",
        "genre": ["horror", "drama"],
        "vocab_distance": "medium",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": "a heist movie about folding cities and stolen dreams",
        "era": "2000-2015",
        "genre": ["sf", "thriller", "action"],
        "vocab_distance": "medium",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a quiet domestic drama where custody paperwork, exhausted tenderness, "
            "and half packed rooms reveal a marriage coming apart without "
            "theatrical villainy"
        ),
        "era": "2000-2015",
        "genre": ["drama", "romance"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "found footage friends chased through a haunted apartment maze",
        "era": "2000-2015",
        "genre": ["horror", "thriller"],
        "vocab_distance": "medium",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a superhero comedy where a smug celebrity keeps failing upward until "
            "public worship, accidental courage, and damaged ego become impossible "
            "to separate"
        ),
        "era": "2000-2015",
        "genre": ["comedy", "action"],
        "vocab_distance": "high",
        "specificity": "low",
        "ambiguity": "high",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "a trash robot falls in love in space",
        "era": "2000-2015",
        "genre": ["animation", "sf", "comedy"],
        "vocab_distance": "low",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _LOW_NOTE,
    },
    {
        "query": "a mockumentary about vampires sharing chores, rent, and eternal grudges",
        "era": "2000-2015",
        "genre": ["comedy", "horror"],
        "vocab_distance": "medium",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": "grieving tourists enter a sunlit folk nightmare",
        "era": "2015+",
        "genre": ["horror", "drama"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "a class satire inside a sinking luxury vacation for wealthy guests",
        "era": "2015+",
        "genre": ["comedy", "drama"],
        "vocab_distance": "medium",
        "specificity": "low",
        "ambiguity": "high",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a multiverse family comedy about taxes, laundry, martial arts, and "
            "a tired mother trying to forgive herself across several impossible "
            "lives"
        ),
        "era": "2015+",
        "genre": ["sf", "comedy", "drama"],
        "vocab_distance": "medium",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": "animated spider hero learns from alternate spider people and mentors",
        "era": "2015+",
        "genre": ["animation", "action", "sf"],
        "vocab_distance": "low",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _LOW_NOTE,
    },
]


def build_records(seed: int = 42) -> List[Dict[str, Any]]:
    """Return the deterministic draft records for a seed."""
    drafts = [dict(item) for item in _DRAFTS]
    random.Random(seed).shuffle(drafts)

    records = []
    for index, draft in enumerate(drafts, start=1):
        query = draft["query"]
        tags = {
            "era": draft["era"],
            "genre": list(draft["genre"]),
            "vocab_distance": draft["vocab_distance"],
            "length": _diversity.length_bucket(query),
            "specificity": draft["specificity"],
            "ambiguity": draft["ambiguity"],
        }
        records.append(
            {
                "qid": f"q{index:02d}",
                "query": query,
                "tags": tags,
                "notes": draft["notes"],
            }
        )
    _validate_records(records)
    return records


def _validate_records(records: List[Dict[str, Any]]) -> None:
    if len(records) != 20:
        raise ValueError(f"expected 20 records, got {len(records)}")

    expected_qids = [f"q{i:02d}" for i in range(1, 21)]
    qids = [record.get("qid") for record in records]
    if qids != expected_qids:
        raise ValueError("qids must be q01..q20 in order")

    for record in records:
        _schemas.validate_query_record(record)
        actual_length = _diversity.length_bucket(record["query"])
        if record["tags"]["length"] != actual_length:
            raise ValueError(f"{record['qid']} has stale tags.length")

    summary = _diversity.summarize(records)
    for axis, expected in EXPECTED_COUNTS.items():
        actual = {key: summary[axis][key] for key in expected}
        if actual != expected:
            raise ValueError(f"{axis} counts mismatch: expected {expected}, got {actual}")

    missing = [
        genre for genre in REQUIRED_GENRES if summary["genre"].get(genre, 0) < 2
    ]
    if missing:
        raise ValueError(f"genre counts below target for: {', '.join(missing)}")


def write_jsonl(records: Iterable[Dict[str, Any]], path: Path) -> None:
    """Write records as deterministic UTF-8 JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _resolved(path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate eval/queries/v1.candidate.jsonl for H1 review."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    out_path = args.out
    if _resolved(out_path) == RESERVED_FINAL_OUT.resolve():
        raise SystemExit("generate_queries.py must not write eval/queries/v1.jsonl")

    records = build_records(seed=args.seed)
    write_jsonl(records, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
