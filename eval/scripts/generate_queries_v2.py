"""Generate the Phase 6 expanded query set (q21-q60).

Adds 40 new English-only queries with balanced taxonomy coverage including
a mood-intent dimension with five sub-tags.  The mandatory smoke-test
regression query from the Phase 6 plan is included.

High-vocab-distance drafts use essayistic or figurative phrasing that is
unlikely to appear verbatim in TMDB-style plot overviews, stressing
semantic retrieval over keyword overlap.  Mood-intent queries test
emotional-tone retrieval and title/keyword trap resistance.
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

DEFAULT_OUT = PROJECT_ROOT / "eval" / "queries" / "v2.candidate.jsonl"
RESERVED_FINAL_OUT = PROJECT_ROOT / "eval" / "queries" / "v2.jsonl"

REQUIRED_MOOD_COUNT = 8
REQUIRED_MOOD_EMOTIONS = {
    "sad", "lonely", "stressed", "tired", "anxious", "bored", "heartbroken",
}
SMOKE_TEST_SUBSTR = "today I am sad"

_HIGH_NOTE = (
    "High-vocab draft: essayistic phrasing chosen to avoid verbatim TMDB "
    "overview terms."
)
_MEDIUM_NOTE = "Medium-vocab draft for H1 human review."
_LOW_NOTE = (
    "Low-vocab draft with direct plot or genre wording for H1 human review."
)


def _mood(
    emotion: str,
    direction: str,
    energy: str,
    intensity: str,
    safety: str,
) -> Dict[str, str]:
    return {
        "current_emotion": emotion,
        "desired_direction": direction,
        "energy_level": energy,
        "intensity": intensity,
        "safety_sensitivity": safety,
    }


_DRAFTS = [
    # ── MOOD-INTENT QUERIES (10) ──────────────────────────────────────

    {
        "query": (
            "today I am sad give me something that can cheer me up "
            "and forget the sadness"
        ),
        "era": None,
        "genre": ["comedy", "animation"],
        "vocab_distance": "low",
        "specificity": "low",
        "ambiguity": "high",
        "mood": _mood(
            "sad", "cheer_me_up", "light_cozy", "very_light", "safe_hopeful",
        ),
        "notes": "Mandatory smoke-test regression case from Phase 6 plan.",
    },
    {
        "query": (
            "I feel lonely tonight and want a movie that wraps around me "
            "like a warm blanket and reminds me that human connection is "
            "still possible even when everything feels empty"
        ),
        "era": None,
        "genre": ["drama", "romance"],
        "vocab_distance": "medium",
        "specificity": "low",
        "ambiguity": "high",
        "mood": _mood(
            "lonely", "comfort_me", "slow_gentle",
            "medium_emotional", "safe_hopeful",
        ),
        "notes": (
            "Mood: lonely/comfort. Title-trap risk: 'Lonely' in title "
            "may not be comforting."
        ),
    },
    {
        "query": (
            "super stressed from work need something light and funny "
            "to just zone out"
        ),
        "era": "2000-2015",
        "genre": ["comedy"],
        "vocab_distance": "low",
        "specificity": "low",
        "ambiguity": "medium",
        "mood": _mood(
            "stressed", "calm_me_down", "funny_energetic",
            "very_light", "safe_hopeful",
        ),
        "notes": "Mood: stressed/unwind. Low specificity tests broad comedy retrieval.",
    },
    {
        "query": (
            "completely exhausted want a cozy gentle film I can drift "
            "off to without bad dreams"
        ),
        "era": "2015+",
        "genre": ["animation"],
        "vocab_distance": "low",
        "specificity": "low",
        "ambiguity": "medium",
        "mood": _mood(
            "tired", "calm_me_down", "slow_gentle",
            "very_light", "safe_hopeful",
        ),
        "notes": "Mood: tired/cozy. Safety-sensitive: no dark or disturbing content.",
    },
    {
        "query": (
            "feeling really anxious about life and need a story where "
            "someone overcomes terrible odds and finds hope on the other "
            "side of something that seemed completely impossible to survive"
        ),
        "era": "2000-2015",
        "genre": ["sf"],
        "vocab_distance": "medium",
        "specificity": "medium",
        "ambiguity": "medium",
        "mood": _mood(
            "anxious", "give_me_hope", "emotional_but_safe",
            "medium_emotional", "safe_hopeful",
        ),
        "notes": (
            "Mood: anxious/hope. Title-trap risk: 'Hope' in title "
            "may not match hopeful tone."
        ),
    },
    {
        "query": "bored stiff give me the most absurd comedy",
        "era": "1980-2000",
        "genre": ["comedy"],
        "vocab_distance": "low",
        "specificity": "low",
        "ambiguity": "high",
        "mood": _mood(
            "bored", "make_me_laugh", "funny_energetic",
            "very_light", "neutral",
        ),
        "notes": "Mood: bored/laugh. Short query tests broad comedy retrieval.",
    },
    {
        "query": (
            "my heart is completely shattered and I want a movie that "
            "understands what losing the love of your life feels like, "
            "something that lets me weep and feel every second of it "
            "without pretending the pain will just go away"
        ),
        "era": "2015+",
        "genre": ["drama", "romance"],
        "vocab_distance": "medium",
        "specificity": "low",
        "ambiguity": "high",
        "mood": _mood(
            "heartbroken", "help_me_cry", "slow_gentle",
            "heavy_but_requested", "safe_hopeful",
        ),
        "notes": "Mood: heartbroken/cry. Heavy emotion requested but safe resolution.",
    },
    {
        "query": (
            "I want something genuinely dark and psychologically "
            "disturbing, the kind of movie that crawls under your skin "
            "and makes you question what people are capable of when "
            "morality stops mattering"
        ),
        "era": "2015+",
        "genre": ["thriller", "horror"],
        "vocab_distance": "high",
        "specificity": "low",
        "ambiguity": "high",
        "mood": _mood(
            "bored", "help_me_cry", "emotional_but_safe",
            "heavy_but_requested", "dark_intended",
        ),
        "notes": "Mood: dark-intended. User explicitly seeks disturbing content.",
    },
    {
        "query": (
            "I need a devastating raw war film that shows human "
            "suffering without any glory"
        ),
        "era": "pre-1980",
        "genre": ["action"],
        "vocab_distance": "low",
        "specificity": "medium",
        "ambiguity": "medium",
        "mood": _mood(
            "sad", "help_me_cry", "slow_gentle",
            "heavy_but_requested", "dark_intended",
        ),
        "notes": "Mood: dark-intended war. User seeks unflinching realism.",
    },
    {
        "query": (
            "feeling sad after a breakup need a gentle romantic comedy "
            "where love wins in the end"
        ),
        "era": "1980-2000",
        "genre": ["comedy", "romance"],
        "vocab_distance": "low",
        "specificity": "medium",
        "ambiguity": "low",
        "mood": _mood(
            "sad", "cheer_me_up", "light_cozy",
            "very_light", "safe_hopeful",
        ),
        "notes": "Mood: breakup comfort. Tests safe-hopeful rom-com retrieval.",
    },

    # ── PRE-1980 (7) ──────────────────────────────────────────────────

    {
        "query": (
            "a sprawling multigenerational saga tracing how a Sicilian "
            "immigrant family transforms into an American crime dynasty "
            "through loyalty, corruption, betrayal, and the slow moral "
            "erosion of inherited power"
        ),
        "era": "pre-1980",
        "genre": ["thriller"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "high",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "twelve strangers debate guilt behind locked doors",
        "era": "pre-1980",
        "genre": ["thriller"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "high",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a motorcycle odyssey through American counterculture "
            "searching for a freedom that the open road can no longer "
            "deliver as the sixties dream collapses into roadside violence"
        ),
        "era": "pre-1980",
        "genre": ["other"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "high",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "a charming con man and his partner hustle Depression-era "
            "gangsters with elaborate stings, fake betting parlors, and "
            "schemes so layered that the audience gets conned right "
            "alongside the mark"
        ),
        "era": "pre-1980",
        "genre": ["comedy", "thriller"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "prisoners tunnel under a German war camp",
        "era": "pre-1980",
        "genre": ["action"],
        "vocab_distance": "low",
        "specificity": "high",
        "ambiguity": "high",
        "notes": _LOW_NOTE,
    },
    {
        "query": (
            "lifeboat survivors suspect the charming stranger among them "
            "is the enemy, where every polite conversation becomes a weapon "
            "and trust is more dangerous than the open Atlantic"
        ),
        "era": "pre-1980",
        "genre": ["thriller"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "high",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "a Japanese samurai recruits misfit warriors to defend a "
            "farming village against bandits in a story that built the "
            "template every team-assembly action movie still copies"
        ),
        "era": "pre-1980",
        "genre": ["action"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _HIGH_NOTE,
    },

    # ── 1980-2000 (8) ─────────────────────────────────────────────────

    {
        "query": (
            "a fairy tale with sword fights, miracles, pirates, and "
            "true love read by a grandfather to his sick grandson"
        ),
        "era": "1980-2000",
        "genre": ["comedy", "romance", "action"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "high",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a documentary about inner-city teenagers chasing NBA "
            "dreams through high school basketball and scholarship pressure"
        ),
        "era": "1980-2000",
        "genre": ["documentary"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "high",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "an animated lion prince flees guilt into exile before "
            "returning to reclaim his stolen kingdom"
        ),
        "era": "1980-2000",
        "genre": ["animation", "drama"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "medium",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "an old man rides a lawn mower across Iowa to see his dying "
            "brother, proving that stubbornness and tenderness can look "
            "exactly the same from the right distance"
        ),
        "era": "1980-2000",
        "genre": ["drama"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "a coal miner's son secretly studies ballet in Thatcher-era "
            "England while his father and brother picket the closing mines"
        ),
        "era": "1980-2000",
        "genre": ["drama", "romance"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a cyberpunk hacker discovers that consensus reality is a "
            "machine simulation and liberation means choosing a painful "
            "truth over a comfortable digital lie that feels "
            "indistinguishable from freedom"
        ),
        "era": "1980-2000",
        "genre": ["sf", "thriller", "action"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "high",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "a family snowed in at an isolated mountain hotel where the "
            "building's malevolent history slowly possesses the father "
            "and turns every hallway into a corridor of dread"
        ),
        "era": "1980-2000",
        "genre": ["horror", "thriller"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "high",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "brilliant janitor hides from his own genius",
        "era": "1980-2000",
        "genre": ["drama"],
        "vocab_distance": "medium",
        "specificity": "medium",
        "ambiguity": "high",
        "notes": _MEDIUM_NOTE,
    },

    # ── 2000-2015 (7) ─────────────────────────────────────────────────

    {
        "query": (
            "a documentary about emperor penguins surviving the "
            "Antarctic winter to protect one fragile egg"
        ),
        "era": "2000-2015",
        "genre": ["documentary"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "an animated old man ties balloons to his house and flies "
            "away with an accidental boy scout stowaway"
        ),
        "era": "2000-2015",
        "genre": ["animation", "comedy"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a man buried alive in a coffin with nothing but a phone "
            "and a lighter"
        ),
        "era": "2000-2015",
        "genre": ["thriller"],
        "vocab_distance": "low",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _LOW_NOTE,
    },
    {
        "query": (
            "a lone astronaut discovers that his employer, his memories, "
            "and possibly his own body are all part of a lie engineered "
            "to keep a lunar mining operation running without paying for "
            "real human lives"
        ),
        "era": "2000-2015",
        "genre": ["sf"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "animated emotions fight for control inside a girl's head "
            "when her family moves to a new city"
        ),
        "era": "2000-2015",
        "genre": ["animation", "comedy"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "a freed slave and a bounty hunter cross the antebellum "
            "South to rescue a wife from a plantation where cruelty is "
            "performed as hospitality"
        ),
        "era": "2000-2015",
        "genre": ["action"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "a documentary about a man who walked a tightrope between "
            "the Twin Towers as performance art"
        ),
        "era": "2000-2015",
        "genre": ["documentary"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _HIGH_NOTE,
    },

    # ── 2015+ (8) ─────────────────────────────────────────────────────

    {
        "query": "a free solo climber scales sheer granite",
        "era": "2015+",
        "genre": ["documentary"],
        "vocab_distance": "low",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _LOW_NOTE,
    },
    {
        "query": (
            "a Korean family cons their way into a wealthy household's "
            "service and the class tension between basements and sunlit "
            "gardens escalates into something no one in either family "
            "can control"
        ),
        "era": "2015+",
        "genre": ["thriller", "comedy"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "an animated boy musician journeys through the land of the "
            "dead to find his great-great-grandfather and lift a family "
            "curse that silenced music for four generations"
        ),
        "era": "2015+",
        "genre": ["animation", "comedy"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _MEDIUM_NOTE,
    },
    {
        "query": (
            "a horror film about a Black man visiting his white "
            "girlfriend's wealthy suburban family where every smile and "
            "compliment hides something surgical and impossible to escape "
            "once you notice it"
        ),
        "era": "2015+",
        "genre": ["horror", "thriller"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "a shy boy growing up in a rough Miami neighborhood told "
            "across three chapters of childhood, adolescence, and young "
            "adulthood as he discovers identity and intimacy in a world "
            "that punishes both"
        ),
        "era": "2015+",
        "genre": ["drama", "romance"],
        "vocab_distance": "high",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _HIGH_NOTE,
    },
    {
        "query": "a stranded astronaut farms potatoes on Mars",
        "era": "2015+",
        "genre": ["sf", "comedy"],
        "vocab_distance": "low",
        "specificity": "high",
        "ambiguity": "low",
        "notes": _LOW_NOTE,
    },
    {
        "query": (
            "a modern musical where two Los Angeles dreamers fall in love "
            "through jazz and ambition before discovering that some love "
            "stories end at a fork in the road rather than a happily "
            "ever after"
        ),
        "era": "2015+",
        "genre": ["other", "romance"],
        "vocab_distance": "high",
        "specificity": "medium",
        "ambiguity": "medium",
        "notes": _HIGH_NOTE,
    },
    {
        "query": (
            "a one-take war film where two soldiers race across no "
            "man's land to deliver a message before dawn"
        ),
        "era": "2015+",
        "genre": ["action"],
        "vocab_distance": "medium",
        "specificity": "high",
        "ambiguity": "high",
        "notes": _MEDIUM_NOTE,
    },
]


def build_records(seed: int = 42) -> List[Dict[str, Any]]:
    """Return the deterministic v2 draft records for a seed."""
    drafts = [dict(item) for item in _DRAFTS]
    random.Random(seed).shuffle(drafts)

    records: List[Dict[str, Any]] = []
    for index, draft in enumerate(drafts, start=21):
        query = draft["query"]
        tags: Dict[str, Any] = {
            "era": draft["era"],
            "genre": list(draft["genre"]),
            "vocab_distance": draft["vocab_distance"],
            "length": _diversity.length_bucket(query),
            "specificity": draft["specificity"],
            "ambiguity": draft["ambiguity"],
            "mood": draft.get("mood"),
        }
        records.append({
            "qid": f"q{index:02d}",
            "query": query,
            "tags": tags,
            "notes": draft["notes"],
        })
    _validate_records(records)
    return records


def _validate_records(records: List[Dict[str, Any]]) -> None:
    if len(records) != 40:
        raise ValueError(f"expected 40 records, got {len(records)}")

    expected_qids = [f"q{i:02d}" for i in range(21, 61)]
    qids = [record.get("qid") for record in records]
    if qids != expected_qids:
        raise ValueError("qids must be q21..q60 in order")

    for record in records:
        _schemas.validate_query_record_v2(record)
        actual_length = _diversity.length_bucket(record["query"])
        if record["tags"]["length"] != actual_length:
            raise ValueError(f"{record['qid']} has stale tags.length")

    mood_records = [
        r for r in records if r["tags"].get("mood") is not None
    ]
    if len(mood_records) < REQUIRED_MOOD_COUNT:
        raise ValueError(
            f"need >= {REQUIRED_MOOD_COUNT} mood queries, "
            f"got {len(mood_records)}"
        )

    emotions = {r["tags"]["mood"]["current_emotion"] for r in mood_records}
    missing = REQUIRED_MOOD_EMOTIONS - emotions
    if missing:
        raise ValueError(
            f"mood queries missing emotions: {', '.join(sorted(missing))}"
        )

    smoke = [r for r in records if SMOKE_TEST_SUBSTR in r["query"]]
    if not smoke:
        raise ValueError(
            f"mandatory smoke-test query containing "
            f"'{SMOKE_TEST_SUBSTR}' not found"
        )

    queries = [r["query"] for r in records]
    if len(queries) != len(set(queries)):
        raise ValueError("duplicate query texts found")


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
        description="Generate eval/queries/v2.candidate.jsonl for H1 review.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    out_path = args.out
    if _resolved(out_path) == RESERVED_FINAL_OUT.resolve():
        raise SystemExit(
            "generate_queries_v2.py must not write eval/queries/v2.jsonl"
        )

    records = build_records(seed=args.seed)
    write_jsonl(records, out_path)
    print(f"Wrote {len(records)} records to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
