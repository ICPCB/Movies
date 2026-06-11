"""Deterministic intent-parser training-dataset generator.

Implements the interface stub contract (spec docs/superpowers/specs/
2026-06-11-llama-intent-parser-lora.md sections 3-4):
- Deterministic: same arguments -> byte-identical output across runs
  (sorted iteration + fixed seed, like eval/scripts/build_mood_queries.py).
- Seeds: labels/user_mood_map.json, labels/user_mood_vocab.json,
  labels/film_mood_vocab.json, the spec section 3.7 concept-inference table
  (extended below), and template expansion. --seed-examples optionally adds
  pre-existing records (provenance forced to "ai_draft" unless honest).
- Emits the six category files plus final_intent_train.jsonl (merged,
  deterministic train/val/test split markers), ~3,600 records total.
- Every record passes engine.intent_schema.validate_intent; implicit plot
  records pass the no-literal-concept assertion; no record text matches an
  eval/queries/intent_v1.jsonl query.

Gold rules implemented exactly per spec section 3:
1. user mood only: user_moods = categories; desired/avoid = static map
   (avoid loses ties to desired across categories); mode "mood".
2. film mood only: desired = stated enum moods; no user_moods; mode "mood".
3. user + film mood: desired = map(desired) | explicit; avoid = map(avoid)
   - desired.
4. avoid preferences: explicit avoid always beats the map in both directions.
5. plot description: plot_elements = short noun phrases; mode "content".
6. hybrid: feeling clause -> mood fields; want clause -> plot_elements;
   mode "hybrid".
7. implicit plot: gold = canonical concept; concept words never in the text.

Usage:
    python training/build_intent_dataset.py [--seed-examples PATH]
        [--target-total 3600] [--seed 20260611] [--out-dir training/]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.intent_schema import empty_intent, validate_intent  # noqa: E402

CATEGORY_FILES = (
    "mood_user_only.jsonl",
    "mood_film_only.jsonl",
    "mood_user_and_film.jsonl",
    "avoid_preferences.jsonl",
    "plot_description.jsonl",
    "hybrid_queries.jsonl",
)
MERGED_FILE = "final_intent_train.jsonl"
ALLOWED_PROVENANCE = ("deterministic_rules", "ai_draft")
SPLITS = ("train", "val", "test")
INTENT_V1 = ROOT / "eval" / "queries" / "intent_v1.jsonl"
LABELS = ROOT / "labels"

# ---------------------------------------------------------------------------
# Stub contract functions (unchanged signatures).
# ---------------------------------------------------------------------------


def validate_record(record: dict, heldout_texts: set[str]) -> list[str]:
    """Gate every generated record. Returns a list of violations (empty = ok)."""
    errors = []
    for key in ("text", "intent", "category", "provenance", "split"):
        if key not in record:
            errors.append(f"missing key: {key}")
    if errors:
        return errors
    if record["category"] + ".jsonl" not in CATEGORY_FILES:
        errors.append(f"unknown category: {record['category']}")
    if record["provenance"] not in ALLOWED_PROVENANCE:
        errors.append(f"dishonest provenance: {record['provenance']}")
    if record["split"] not in SPLITS:
        errors.append(f"unknown split: {record['split']}")
    ok, schema_errors = validate_intent(record["intent"])
    if not ok:
        errors.extend(schema_errors)
    if record["text"].strip().lower() in heldout_texts:
        errors.append("text collides with held-out intent_v1 eval query")
    return errors


def load_heldout_texts() -> set[str]:
    return {
        json.loads(line)["query"].strip().lower()
        for line in INTENT_V1.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


# ---------------------------------------------------------------------------
# Seed data.
# ---------------------------------------------------------------------------


def _load_labels() -> tuple[dict, dict, list[str]]:
    vocab = json.loads((LABELS / "user_mood_vocab.json").read_text(encoding="utf-8"))
    mood_map = json.loads((LABELS / "user_mood_map.json").read_text(encoding="utf-8"))["map"]
    film_moods = json.loads(
        (LABELS / "film_mood_vocab.json").read_text(encoding="utf-8")
    )["film_moods"]
    return vocab, mood_map, list(film_moods)


def _unambiguous_words(vocab: dict) -> dict[str, list[str]]:
    """category -> feeling words that belong to exactly one category.

    Ambiguous words ("warm" is connected_loving AND tender) would make the
    single-category gold a judgment call - exclude them so every gold label
    is derivable, never guessed.
    """
    word_cats: dict[str, set[str]] = {}
    for category, words in sorted(vocab["categories"].items()):
        for word in words:
            word_cats.setdefault(word.lower(), set()).add(category)
    out: dict[str, list[str]] = {c: [] for c in sorted(vocab["categories"])}
    for word, cats in sorted(word_cats.items()):
        if len(cats) == 1:
            out[next(iter(cats))].append(word)
    return {c: sorted(ws) for c, ws in out.items() if ws}


# Spec section 3.7 concept-inference table — canonical concept -> implicit
# phrasings. Spec rows are the seed; additional phrasings extend it (allowed:
# "seed, extend in dataset generation"). No phrasing may contain a content
# word of its concept (asserted at generation time).
CONCEPTS: dict[str, list[str]] = {
    "time loop": [
        "trapped in repeating days",
        "lives the same day over and over",
        "stuck reliving yesterday no matter what she does",
        "every morning starts exactly like the last one",
        "he keeps waking up to the same Monday",
    ],
    "amnesia": [
        "wakes up with no memory",
        "can't remember who he is",
        "she has forgotten her whole life after the accident",
        "a stranger to himself with no past he can recall",
    ],
    "heist": [
        "a crew planning to rob a casino",
        "pulling off one last big job",
        "thieves breaking into an impossible vault",
        "a crew assembling specialists to crack a bank",
    ],
    "body swap": [
        "two people wake up in each other's bodies",
        "a mother and daughter switch places for a week",
        "he opens his eyes inside someone else's life",
    ],
    "time travel": [
        "a scientist visits his own past",
        "sent back decades to fix a mistake",
        "she steps through a door into 1955",
        "messages arriving from thirty years in the future",
    ],
    "post-apocalyptic": [
        "survivors wandering a world after civilization collapsed",
        "the last people alive scavenging ruined cities",
        "rebuilding life after the end of everything",
    ],
    "ai uprising": [
        "machines turn against their creators",
        "the robots decide humanity is the problem",
        "a computer system seizes control of everything",
    ],
    "alien invasion": [
        "ships appear over every city and start attacking",
        "strange visitors from another world arrive with bad intentions",
        "the sky fills with hostile craft from beyond",
    ],
    "zombie outbreak": [
        "the dead rise and attack the living",
        "an infection turns neighbors into shambling monsters",
        "the bitten get back up and start biting",
    ],
    "haunted house": [
        "a family's new home where strange things happen at night",
        "doors slam and voices whisper in the old mansion",
        "the previous owners never really left the place",
    ],
    "revenge": [
        "a man hunts down the people who destroyed his family",
        "she returns years later to make them all pay",
        "tracking down every person who wronged him",
    ],
    "survival": [
        "stranded alone on a deserted island",
        "lost in the wilderness with nothing but a knife",
        "keeping a group alive through a brutal winter storm",
    ],
    "coming of age": [
        "a shy teenager figuring out who she is over one summer",
        "the last awkward year before adulthood changes everything",
        "a boy learning hard truths the year he turns thirteen",
    ],
    "courtroom drama": [
        "a lawyer defending an innocent man at trial",
        "a jury deciding a case that could ruin a life",
        "an attorney risking everything on a final witness",
    ],
    "undercover cop": [
        "a detective living a double life inside a crime ring",
        "an officer embedded so deep he forgets whose side he is on",
        "infiltrating the gang while wearing a wire",
    ],
}

# Explicit plot-element pool: (display form used in text, gold element).
PLOT_POOL: list[tuple[str, str]] = [
    ("a heist", "heist"), ("a road trip", "road trip"), ("a submarine", "submarine"),
    ("space", "space"), ("a robot", "robot"), ("a dragon", "dragon"),
    ("pirates", "pirates"), ("a vampire", "vampire"), ("boxing", "boxing"),
    ("chess", "chess"), ("cooking", "cooking"), ("a treasure hunt", "treasure hunt"),
    ("a jungle expedition", "jungle expedition"), ("an archaeologist", "archaeologist"),
    ("a bank robbery", "bank robbery"), ("a jewel thief", "jewel thief"),
    ("a con artist", "con artist"), ("a spaceship", "spaceship"),
    ("a mars colony", "mars colony"), ("a sea monster", "sea monster"),
    ("a ghost", "ghost"), ("a detective", "detective"), ("a spy", "spy"),
    ("an assassin", "assassin"), ("a samurai", "samurai"), ("a cowboy", "cowboy"),
    ("a gladiator", "gladiator"), ("vikings", "vikings"), ("a knight", "knight"),
    ("a wizard", "wizard"), ("a witch", "witch"), ("a superhero", "superhero"),
    ("a gangster", "gangster"), ("a prison escape", "prison escape"),
    ("a kidnapping", "kidnapping"), ("a plane crash", "plane crash"),
    ("a shipwreck", "shipwreck"), ("the desert", "desert"), ("the arctic", "arctic"),
    ("mountain climbing", "mountain climbing"), ("the deep sea", "deep sea"),
    ("a volcano", "volcano"), ("a small town", "small town"),
    ("summer camp", "summer camp"), ("high school", "high school"),
    ("a wedding", "wedding"), ("a family reunion", "family reunion"),
    ("a chef", "chef"), ("a boxer", "boxer"), ("a race car driver", "race car driver"),
    ("a talent show", "talent show"), ("an unlikely friendship", "unlikely friendship"),
    ("a missing child", "missing child"), ("a long lost twin", "long lost twin"),
    ("a circus", "circus"), ("a lighthouse keeper", "lighthouse keeper"),
    ("a train journey", "train journey"), ("a casino", "casino"),
    ("street racing", "street racing"), ("a hacker", "hacker"),
]

# Genre words usable literally in text -> canonical TMDB genre.
GENRE_WORDS: list[tuple[str, str]] = [
    ("comedy", "Comedy"), ("drama", "Drama"), ("thriller", "Thriller"),
    ("horror", "Horror"), ("documentary", "Documentary"), ("western", "Western"),
    ("animated", "Animation"), ("romance", "Romance"), ("action", "Action"),
    ("adventure", "Adventure"), ("mystery", "Mystery"), ("fantasy", "Fantasy"),
    ("sci-fi", "Science Fiction"), ("crime", "Crime"), ("war", "War"),
]

FEELING_TEMPLATES = [
    "feeling {w} today",
    "feeling {w} tonight",
    "I'm {w} right now",
    "I feel so {w}",
    "I am feeling {w}",
    "been {w} all day",
    "I'm feeling really {w} lately",
    "honestly feeling {w} this evening",
]
FEELING_PAIR_TEMPLATES = [
    "feeling {w1} and {w2}",
    "I'm {w1} and {w2} tonight",
    "I feel {w1} and a bit {w2}",
    "been {w1} and {w2} all week",
]
FILM_MOOD_TEMPLATES = [
    "want something {m1} and {m2}",
    "in the mood for something {m1} and {m2}",
    "give me something {m1} and {m2}",
    "show me something {m1} and {m2}",
    "looking for something {m1} and {m2} tonight",
    "I want a {m1} and {m2} movie",
    "put on something {m1} and {m2}",
]
FILM_MOOD_SINGLE_TEMPLATES = [
    "want something {m} tonight",
    "in the mood for something {m}",
    "give me a {m} movie",
    "show me something {m}",
    "something {m} please",
]
USER_AND_FILM_TEMPLATES = [
    "feeling {w}, want something {m}",
    "I'm {w}, give me something {m}",
    "feeling {w} tonight, show me something {m}",
    "I feel {w}, in the mood for something {m}",
    "been {w} all day, want a {m} movie",
]
AVOID_FILM_TEMPLATES = [
    "want something {m} tonight, nothing {a} please",
    "something {m} but not {a}",
    "give me something {m}, no {a} stuff",
    "show me something {m}, avoid anything {a}",
    "want something {m} but skip anything {a}",
    "something {m} please, absolutely nothing {a}",
]
AVOID_ONLY_TEMPLATES = [
    "anything tonight but nothing {a} please",
    "surprise me, just nothing {a}",
    "whatever you pick, no {a} stuff",
]
AVOID_USER_TEMPLATES = [
    "feeling {w}, want something {m}, nothing {a} please",
    "I'm {w}, give me something {m} but nothing {a}",
]
PLOT_TEMPLATES_1 = [
    "a movie about {p}",
    "something with {p} in it",
    "a story about {p}",
    "a film about {p}",
    "I want to watch something about {p}",
]
PLOT_TEMPLATES_2 = [
    "a movie about {p1} and {p2}",
    "a story about {p1} involving {p2}",
    "something with {p1} and {p2}",
    "a film about {p1} set around {p2}",
]
PLOT_GENRE_TEMPLATES = [
    "a {g} about {p}",
    "a {g} movie about {p}",
    "an {g} movie about {p}",
]
IMPLICIT_TEMPLATES = [
    "{ph}",
    "a movie where {ph}",
    "a story where {ph}",
    "something about {ph}",
    "a film where {ph}",
]
HYBRID_TEMPLATES = [
    "feeling {w}, want a movie about {p}",
    "I'm {w}, give me a story about {p}",
    "feeling {w} tonight, something with {p}",
    "I feel {w}, want something about {p}",
]
HYBRID_GENRE_TEMPLATES = [
    "feeling {w}, want a {g} about {p}",
    "I'm {w}, in the mood for a {g} movie about {p}",
]

CONFIDENCE = 0.95


# ---------------------------------------------------------------------------
# Gold-intent helpers (spec section 3).
# ---------------------------------------------------------------------------


def _map_fields(categories: list[str], mood_map: dict) -> tuple[list[str], list[str]]:
    desired: set[str] = set()
    avoid: set[str] = set()
    for slug in categories:
        desired.update(mood_map[slug]["desired"])
        avoid.update(mood_map[slug]["avoid"])
    avoid -= desired  # rule 1: avoid loses ties to desired
    return sorted(desired), sorted(avoid)


def _intent(text: str, mode: str, *, user_moods=(), desired=(), avoid=(),
            plot=(), genres=()) -> dict:
    intent = empty_intent(text, mode)
    intent["user_moods"] = sorted(user_moods)
    intent["desired_film_moods"] = sorted(desired)
    intent["avoid_film_moods"] = sorted(avoid)
    intent["plot_elements"] = list(plot)
    intent["genres_include"] = sorted(genres)
    intent["confidence"] = CONFIDENCE
    return intent


# ---------------------------------------------------------------------------
# Candidate builders — each returns a deterministic list of (text, intent).
# ---------------------------------------------------------------------------


def gen_mood_user_only(words: dict[str, list[str]], mood_map: dict):
    out = []
    for category, cat_words in sorted(words.items()):
        desired, avoid = _map_fields([category], mood_map)
        for word in cat_words:
            for template in FEELING_TEMPLATES:
                out.append((template.format(w=word),
                            dict(user_moods=[category], desired=desired, avoid=avoid)))
        for i, w1 in enumerate(cat_words):
            for w2 in cat_words[i + 1:]:
                for template in FEELING_PAIR_TEMPLATES:
                    out.append((template.format(w1=w1, w2=w2),
                                dict(user_moods=[category], desired=desired, avoid=avoid)))
    # Two-category pairs (rule 1 cross-category tie handling).
    cats = sorted(words)
    for i, c1 in enumerate(cats):
        for c2 in cats[i + 1:]:
            desired, avoid = _map_fields([c1, c2], mood_map)
            for w1 in words[c1][:3]:
                for w2 in words[c2][:3]:
                    out.append((FEELING_PAIR_TEMPLATES[0].format(w1=w1, w2=w2),
                                dict(user_moods=[c1, c2], desired=desired, avoid=avoid)))
    return [(t, _intent(t, "mood", **kw)) for t, kw in out]


def gen_mood_film_only(film_moods: list[str]):
    out = []
    moods = sorted(film_moods)
    for m in moods:
        for template in FILM_MOOD_SINGLE_TEMPLATES:
            out.append((template.format(m=m), [m]))
    for i, m1 in enumerate(moods):
        for m2 in moods[i + 1:]:
            for template in FILM_MOOD_TEMPLATES:
                out.append((template.format(m1=m1, m2=m2), [m1, m2]))
    return [(t, _intent(t, "mood", desired=ms)) for t, ms in out]


def gen_mood_user_and_film(words: dict[str, list[str]], mood_map: dict,
                           film_moods: list[str]):
    out = []
    for category, cat_words in sorted(words.items()):
        map_desired, map_avoid = _map_fields([category], mood_map)
        for word in cat_words[:8]:
            for m in sorted(film_moods):
                template = USER_AND_FILM_TEMPLATES[
                    (len(word) + len(m)) % len(USER_AND_FILM_TEMPLATES)
                ]
                desired = sorted(set(map_desired) | {m})       # rule 3
                avoid = sorted(set(map_avoid) - set(desired))  # rule 3
                out.append((template.format(w=word, m=m),
                            dict(user_moods=[category], desired=desired, avoid=avoid)))
    return [(t, _intent(t, "mood", **kw)) for t, kw in out]


def gen_avoid_preferences(words: dict[str, list[str]], mood_map: dict,
                          film_moods: list[str]):
    out = []
    moods = sorted(film_moods)
    # a) film desired + explicit avoid (rule 4, no user mood).
    for m in moods:
        for a in moods:
            if a == m:
                continue
            template = AVOID_FILM_TEMPLATES[(len(m) + len(a)) % len(AVOID_FILM_TEMPLATES)]
            out.append((template.format(m=m, a=a),
                        dict(desired=[m], avoid=[a])))
    # b) avoid only.
    for a in moods:
        for template in AVOID_ONLY_TEMPLATES:
            out.append((template.format(a=a), dict(avoid=[a])))
    # c) user mood + explicit want + explicit avoid (explicit beats map both ways).
    for category, cat_words in sorted(words.items()):
        map_desired, map_avoid = _map_fields([category], mood_map)
        for word in cat_words[:4]:
            for m in moods[::3]:
                for a in moods[1::4]:
                    if a == m:
                        continue
                    desired = sorted((set(map_desired) | {m}) - {a})
                    avoid = sorted((set(map_avoid) | {a}) - set(desired))
                    template = AVOID_USER_TEMPLATES[(len(word) + len(a)) % len(AVOID_USER_TEMPLATES)]
                    out.append((template.format(w=word, m=m, a=a),
                                dict(user_moods=[category], desired=desired, avoid=avoid)))
    return [(t, _intent(t, "mood", **kw)) for t, kw in out]


def gen_plot_description():
    out = []
    pool = list(PLOT_POOL)
    # Explicit, one element.
    for display, gold in pool:
        for template in PLOT_TEMPLATES_1:
            out.append((template.format(p=display), dict(plot=[gold])))
    # Explicit, two elements.
    for i, (d1, g1) in enumerate(pool):
        for d2, g2 in pool[i + 1:i + 4]:
            template = PLOT_TEMPLATES_2[(len(g1) + len(g2)) % len(PLOT_TEMPLATES_2)]
            out.append((template.format(p1=d1, p2=d2), dict(plot=[g1, g2])))
    # Explicit with genre word.
    for gi, (gw, genre) in enumerate(GENRE_WORDS):
        for display, gold in pool[gi::3]:
            template = PLOT_GENRE_TEMPLATES[1 if gw[0] not in "aeiou" else 2]
            out.append((template.format(g=gw, p=display),
                        dict(plot=[gold], genres=[genre])))
    explicit = [(t, _intent(t, "content", **kw)) for t, kw in out]
    # Implicit (rule 7).
    implicit = []
    for concept, phrasings in sorted(CONCEPTS.items()):
        concept_words = {w for w in concept.replace("-", " ").split() if len(w) > 2}
        for phrasing in phrasings:
            for template in IMPLICIT_TEMPLATES:
                text = template.format(ph=phrasing)
                lowered = text.lower()
                assert concept.lower() not in lowered and not any(
                    w in lowered.replace("-", " ").split() for w in concept_words
                ), f"implicit phrasing leaks concept '{concept}': {text}"
                implicit.append((text, _intent(text, "content", plot=[concept])))
    return explicit, implicit


def gen_hybrid(words: dict[str, list[str]], mood_map: dict):
    out = []
    pool = list(PLOT_POOL)
    for category, cat_words in sorted(words.items()):
        desired, avoid = _map_fields([category], mood_map)
        kw = dict(user_moods=[category], desired=desired, avoid=avoid)
        for wi, word in enumerate(cat_words[:6]):
            for display, gold in pool[wi::4]:
                template = HYBRID_TEMPLATES[(len(word) + len(gold)) % len(HYBRID_TEMPLATES)]
                out.append((template.format(w=word, p=display),
                            dict(plot=[gold], **kw)))
            for gw, genre in GENRE_WORDS[wi::5]:
                display, gold = pool[(wi * 7 + len(gw)) % len(pool)]
                template = HYBRID_GENRE_TEMPLATES[len(gold) % len(HYBRID_GENRE_TEMPLATES)]
                out.append((template.format(w=word, g=gw, p=display),
                            dict(plot=[gold], genres=[genre], **kw)))
    return [(t, _intent(t, "hybrid", **kw)) for t, kw in out]


# ---------------------------------------------------------------------------
# Assembly.
# ---------------------------------------------------------------------------


def _take(candidates, rng: random.Random, target: int, heldout: set[str],
          seen_texts: set[str]) -> list[tuple[str, dict]]:
    rng.shuffle(candidates)
    picked = []
    for text, intent in candidates:
        key = text.strip().lower()
        if key in heldout or key in seen_texts:
            continue
        seen_texts.add(key)
        picked.append((text, intent))
        if len(picked) >= target:
            break
    return picked


def _load_seed_examples(path: Path, heldout: set[str], seen: set[str]) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        rec.setdefault("provenance", "ai_draft")
        rec.setdefault("split", "train")
        violations = validate_record(rec, heldout)
        if violations:
            raise SystemExit(f"seed example invalid: {violations}: {line[:120]}")
        key = rec["text"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        records.append(rec)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-examples", default=None,
                        help="optional local seed jsonl (full record shape; "
                             "provenance defaults to ai_draft)")
    parser.add_argument("--target-total", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=20260611)
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    heldout = load_heldout_texts()
    vocab, mood_map, film_moods = _load_labels()
    words = _unambiguous_words(vocab)
    per_category = args.target_total // len(CATEGORY_FILES)
    seen_texts: set[str] = set()
    rng = random.Random(args.seed)

    explicit_plot, implicit_plot = gen_plot_description()
    candidates: dict[str, list[tuple[str, dict]]] = {
        "mood_user_only": gen_mood_user_only(words, mood_map),
        "mood_film_only": gen_mood_film_only(film_moods),
        "mood_user_and_film": gen_mood_user_and_film(words, mood_map, film_moods),
        "avoid_preferences": gen_avoid_preferences(words, mood_map, film_moods),
        "hybrid_queries": gen_hybrid(words, mood_map),
    }

    chosen: dict[str, list[tuple[str, dict]]] = {}
    for category in sorted(candidates):
        chosen[category] = _take(candidates[category], rng, per_category,
                                 heldout, seen_texts)
    # plot_description: roughly half explicit, half implicit.
    explicit_take = _take(explicit_plot, rng, per_category - per_category // 3,
                          heldout, seen_texts)
    implicit_take = _take(implicit_plot, rng, per_category - len(explicit_take),
                          heldout, seen_texts)
    plot_all = explicit_take + implicit_take
    rng.shuffle(plot_all)
    chosen["plot_description"] = plot_all

    # Deterministic split markers: per category, every 20th record is val,
    # the following one test (90/5/5).
    merged: list[dict] = []
    summary: dict[str, dict] = {}
    implicit_texts = {t.strip().lower() for t, _ in implicit_take}
    for filename in CATEGORY_FILES:
        category = filename[: -len(".jsonl")]
        records = []
        for i, (text, intent) in enumerate(chosen[category]):
            split = "val" if i % 20 == 18 else "test" if i % 20 == 19 else "train"
            record = {
                "text": text,
                "intent": intent,
                "category": category,
                "provenance": "deterministic_rules",
                "split": split,
            }
            violations = validate_record(record, heldout)
            if violations:
                raise SystemExit(f"generated record invalid ({category}): "
                                 f"{violations}: {text}")
            records.append(record)
        path = out_dir / filename
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                    for r in records),
            encoding="utf-8", newline="\n",
        )
        merged.extend(records)
        splits = {s: sum(1 for r in records if r["split"] == s) for s in SPLITS}
        summary[category] = {"records": len(records), **splits}

    if args.seed_examples:
        seed_path = Path(args.seed_examples)
        if not seed_path.exists():
            raise SystemExit(f"--seed-examples not found: {seed_path}")
        merged.extend(_load_seed_examples(seed_path, heldout, seen_texts))

    (out_dir / MERGED_FILE).write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                for r in merged),
        encoding="utf-8", newline="\n",
    )
    n_implicit = sum(
        1 for r in merged
        if r["category"] == "plot_description"
        and r["text"].strip().lower() in implicit_texts
    )
    print(json.dumps({"total": len(merged), "implicit_plot": n_implicit,
                      "per_category": summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
