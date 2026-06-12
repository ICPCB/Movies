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
import re
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
GENERIC_PLOT_WORDS = {"story", "movie", "film", "flick", "stuff", "thing"}

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
    return {
        c: sorted(w for w in ws if w not in EXCLUDE_FEELINGS)
        for c, ws in out.items()
        if ws
    }


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
    "courtroom": [
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
    ("a ghost ship", "ghost ship"), ("an escape room", "escape room"),
    ("a rookie cop", "rookie cop"), ("a getaway driver", "getaway driver"),
    ("a masked vigilante", "masked vigilante"), ("a chess prodigy", "chess prodigy"),
    ("a corrupt mayor", "corrupt mayor"), ("a custody battle", "custody battle"),
    ("a wildfire", "wildfire"), ("wrestling", "wrestling"),
    ("surfing", "surfing"), ("an underdog", "underdog"),
    ("winter", "winter"), ("a found family", "found family"),
    ("time travel", "time travel"), ("paradoxes", "paradoxes"),
    ("a swamp creature", "swamp creature"), ("an alien artifact", "alien artifact"),
]

# Plural-subject action clauses: gold keeps the plural surface subject and the
# object noun phrase; the verb is dropped (spec 3.8 atomic noun phrases).
PLURAL_SUBJECT_ACTIONS: list[tuple[str, str, str]] = [
    ("firefighters", "battling a wildfire", "wildfire"),
    ("smugglers", "running a blockade at sea", "blockade"),
    ("journalists", "exposing a corrupt mayor", "corrupt mayor"),
    ("soldiers", "escorting a convoy behind enemy lines", "convoy"),
    ("hunters", "tracking a wounded bear through the snow", "wounded bear"),
    ("monks", "guarding an ancient relic", "ancient relic"),
    ("sailors", "chasing a ghost ship", "ghost ship"),
    ("teenagers", "running an underground radio station", "radio station"),
    ("climbers", "racing a blizzard down a deadly peak", "blizzard"),
    ("rebels", "plotting against a ruthless emperor", "ruthless emperor"),
    ("officers", "chasing a getaway driver in the rain", "getaway driver"),
    ("guards", "patrolling a museum at night", "museum"),
]
PLURAL_SUBJECT_TEMPLATES = [
    "{s} {act}",
    "a movie about {s} {act}",
    "something with {s} {act}",
    "a film about {s} {act}",
]

# Singular subject + gerund clause: gold = subject NP + object NP, verb drops.
# Display subjects reuse pool articles; an optional evaluative adjective is
# inserted in half the records and always drops from gold (it is neither a
# mood enum value nor a type-forming modifier).
SINGULAR_SUBJECT_ACTIONS: list[tuple[str, str, str, str]] = [
    ("a wizard", "wizard", "mentoring an orphan", "orphan"),
    ("a dog", "dog", "guiding a blind veteran", "blind veteran"),
    ("a nun", "nun", "sheltering a runaway", "runaway"),
    ("a hacker", "hacker", "protecting a witness", "witness"),
    ("a ghost", "ghost", "haunting a lighthouse keeper", "lighthouse keeper"),
    ("a dragon", "dragon", "guarding a hidden city", "hidden city"),
    ("a chef", "chef", "training an apprentice", "apprentice"),
    ("a cowboy", "cowboy", "defending a frontier town", "frontier town"),
]
SINGULAR_SUBJECT_TEMPLATES = [
    "{s} {act}",
    "a movie about {s} {act}",
    "a story about {s} {act}",
]
EVALUATIVE_MODIFIERS = ["kind", "gentle", "quiet", "elderly", "little", "scrappy"]

# "{setting-or-topic} {genre} with {NP}" compounds: both NPs are elements,
# the genre word resolves to genres_include.
SETTING_GENRE_WITH: list[tuple[str, str, str, str, str]] = [
    ("deep sea", "horror", "Horror", "a sea creature", "sea creature"),
    ("desert", "western", "Western", "a treasure hunt", "treasure hunt"),
    ("arctic", "thriller", "Thriller", "a research station", "research station"),
    ("jungle", "adventure", "Adventure", "a lost temple", "lost temple"),
    ("high school", "comedy", "Comedy", "a chess prodigy", "chess prodigy"),
    ("time travel", "thriller", "Thriller", "a paradox", "paradox"),
    ("body swap", "comedy", "Comedy", "a wedding", "wedding"),
    ("heist", "thriller", "Thriller", "double crosses", "double crosses"),
    ("ghost ship", "mystery", "Mystery", "a missing crew", "missing crew"),
]

# Film-style modifiers in content queries ground neither moods nor elements
# (spec 3.11.2): they drop from gold entirely.
STYLE_PREFIX_FUSED: list[tuple[str, str, str, str, str, str]] = [
    ("slow burn", "a detective mystery", "detective", "Mystery", "winter", "winter"),
    ("slow burn", "a jewel thief thriller", "jewel thief", "Thriller",
     "a small town", "small town"),
    ("cozy", "a road trip comedy", "road trip", "Comedy",
     "the countryside", "countryside"),
    ("slow burn", "a lighthouse keeper drama", "lighthouse keeper", "Drama",
     "winter", "winter"),
    ("cozy", "a chef drama", "chef", "Drama", "a small town", "small town"),
]
WEATHER_ADJUNCTS = ["in the rain", "in the fog", "at night", "at dawn"]

# "{a} {b} story" compounds: both concepts are elements, "story" is generic
# and never appears in gold; no genre is grounded.
STORY_COMPOUNDS: list[tuple[str, str]] = [
    ("wrestling", "underdog"),
    ("surfing", "underdog"),
    ("street racing", "underdog"),
    ("shipwreck", "survival"),
    ("plane crash", "survival"),
]

# Relative-clause romance trope (spec 3.11.1): "falls in love" is a
# lexicalized trope element kept verbatim alongside the subject/object NPs.
# Each record carries a semantically compatible trailing setting.
FALLS_IN_LOVE_RECORDS: list[tuple[str, list[str], str, str]] = [
    ("a vampire who falls in love with a mortal",
     ["falls in love", "mortal", "vampire"], "a small town", "small town"),
    ("a pirate who falls in love with a mermaid",
     ["falls in love", "mermaid", "pirate"], "the deep sea", "deep sea"),
    ("a knight who falls in love with a duchess",
     ["falls in love", "duchess", "knight"], "the countryside", "countryside"),
    ("an android who falls in love with a poet",
     ["android", "falls in love", "poet"], "space", "space"),
    ("a ghost who falls in love with a violinist",
     ["falls in love", "ghost", "violinist"], "a lighthouse", "lighthouse"),
]

# v6 (gate-review-5, iv38): the trope clause also occurs without an object,
# with the trailing setting attaching directly after "falls in love".
# Subjects rotate non-eval vocabulary; settings come from the pool.
FALLS_IN_LOVE_NO_OBJECT: list[tuple[str, str, str, str]] = [
    ("an android", "android", "space", "space"),
    ("a mermaid", "mermaid", "the deep sea", "deep sea"),
    ("a witch", "witch", "a small town", "small town"),
    ("a puppet", "puppet", "a circus", "circus"),
    ("a snowman", "snowman", "winter", "winter"),
]
# Bare-start "{genre} movie about {trope clause}" prefixes, paired by index
# with the record lists above; "animated" dominates because the bare-start
# animated relative-clause shape was untaught through v5.
FALLS_IN_LOVE_OBJECT_PREFIXES: list[tuple[str, str]] = [
    ("animated", "Animation"), ("animated", "Animation"),
    ("fantasy", "Fantasy"), ("sci-fi", "Science Fiction"),
    ("animated", "Animation"),
]
FALLS_IN_LOVE_NO_OBJECT_PREFIXES: list[tuple[str, str]] = [
    ("sci-fi", "Science Fiction"), ("animated", "Animation"),
    ("fantasy", "Fantasy"), ("animated", "Animation"),
    ("animated", "Animation"),
]

# Place-genre compounds ("a courtroom drama"): the place noun stays a plot
# element and the genre word resolves to genres_include (spec 3.8 fusion rule).
PLACE_GENRE_COMPOUNDS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("courtroom", "drama", "Drama",
     ("con artist", "gangster", "missing child", "kidnapping")),
    ("hospital", "drama", "Drama",
     ("missing child", "unlikely friendship", "rookie cop")),
    ("newsroom", "drama", "Drama",
     ("hacker", "corrupt mayor", "con artist")),
    ("prison", "drama", "Drama",
     ("boxer", "gangster", "unlikely friendship")),
]

SETTING_DISPLAYS = {
    "the desert", "the arctic", "space", "winter", "a small town",
    "the deep sea", "the jungle", "high school", "summer camp", "a casino",
    "a circus", "a train journey", "the countryside", "the suburbs",
    "a lighthouse",
}
EVENT_DISPLAYS = {
    "a wedding", "a family reunion", "a talent show", "a championship",
    "the holidays",
}
SETTINGS = tuple(item for item in PLOT_POOL if item[0] in SETTING_DISPLAYS)
EVENTS = tuple(item for item in PLOT_POOL if item[0] in EVENT_DISPLAYS)
TOPICS = tuple(item for item in PLOT_POOL
               if item[0] not in SETTING_DISPLAYS | EVENT_DISPLAYS)
NATURAL_SET_IN_SETTINGS = tuple(
    item for item in SETTINGS if item[0] != "a train journey"
)
TOPIC_BY_GOLD = {gold: (display, gold) for display, gold in TOPICS}
FUSED_GENRE_TOPIC_GOLDS = {
    "comedy": ("road trip", "robot", "con artist", "chef"),
    "drama": ("boxer", "missing child", "long lost twin", "lighthouse keeper"),
    "thriller": ("heist", "submarine", "jewel thief", "spy", "kidnapping"),
    "horror": ("vampire", "sea monster", "ghost", "witch", "shipwreck"),
    "documentary": ("boxing", "chess", "cooking", "jungle expedition", "mountain climbing"),
    "western": ("cowboy", "gangster", "treasure hunt", "jewel thief"),
    "romance": ("road trip", "chef", "con artist", "spy"),
    "action": ("heist", "robot", "spy", "assassin", "superhero", "street racing"),
    "adventure": ("road trip", "dragon", "treasure hunt", "archaeologist", "knight",
                  "time travel"),
    "mystery": ("detective", "missing child", "long lost twin", "ghost", "lighthouse keeper"),
    "fantasy": ("dragon", "vampire", "wizard", "witch", "knight"),
    "sci-fi": ("robot", "spaceship", "mars colony", "hacker"),
    "crime": ("heist", "bank robbery", "jewel thief", "con artist", "detective", "gangster"),
    "war": ("submarine", "spy", "assassin", "samurai", "gladiator"),
}
FUSED_GENRE_TOPICS = {
    genre: tuple(TOPIC_BY_GOLD[gold] for gold in golds)
    for genre, golds in FUSED_GENRE_TOPIC_GOLDS.items()
}

# Genre words usable literally in text -> canonical TMDB genre.
GENRE_WORDS: list[tuple[str, str]] = [
    ("comedy", "Comedy"), ("drama", "Drama"), ("thriller", "Thriller"),
    ("horror", "Horror"), ("documentary", "Documentary"), ("western", "Western"),
    ("animated", "Animation"), ("romance", "Romance"), ("action", "Action"),
    ("adventure", "Adventure"), ("mystery", "Mystery"), ("fantasy", "Fantasy"),
    ("sci-fi", "Science Fiction"), ("crime", "Crime"), ("war", "War"),
    ("family", "Family"), ("musical", "Music"),
]
MOVIE_REQUIRED_GENRES = {"animated", "action", "sci-fi", "crime", "war", "horror",
                         "family"}

IMPLICIT_FILM_MOODS: dict[str, list[str]] = {
    "funny": ["something that will make me laugh out loud", "a movie with jokes that actually land"],
    "heartwarming": ["something that melts your heart", "a story about people being quietly good to each other"],
    "feel-good": ["a movie that leaves me smiling", "something easy that puts me in a better headspace"],
    "uplifting": ["something that makes me believe things get better", "a film that raises my spirits"],
    "hopeful": ["a story where things turn out okay in the end", "something that says tomorrow can be better"],
    "lighthearted": ["nothing heavy, just something breezy", "something playful that doesn't take itself seriously"],
    "romantic": ["a love story", "two people slowly falling for each other"],
    "inspiring": ["a story that makes me want to chase my dreams", "people beating impossible odds that fires me up"],
    "exciting": ["something with real adrenaline", "a ride that never slows down"],
    "thrilling": ["edge-of-my-seat stuff", "something that gets my pulse racing"],
    "suspenseful": ["something that keeps me guessing until the end", "a slow build where you don't know who to trust"],
    "tense": ["a knot-in-your-stomach atmosphere", "white-knuckle the whole way through"],
    "action-packed": ["wall-to-wall fights and chases", "explosions and set pieces nonstop"],
    "epic": ["a grand sweeping saga across years and continents", "something huge in scope"],
    "mind-bending": ["something that messes with my head", "a film I'll need to rewatch to understand"],
    "thought-provoking": ["something that leaves me with big questions", "a film I'll be chewing on for days"],
    "dark": ["morally murky and shadowy in tone", "something grim with a black streak"],
    "gritty": ["raw street-level realism", "rough around the edges with no gloss"],
    "bleak": ["no comfort and no easy answers", "the kind of film where hope never shows up"],
    "melancholic": ["something quiet and full of longing", "a soft ache of a film"],
    "scary": ["something that makes me sleep with the lights on", "something to keep me checking behind the door"],
    "disturbing": ["something that crawls under your skin and stays there", "imagery I won't shake for days"],
    "bittersweet": ["happy and sad at the same time", "an ending that smiles through tears"],
}

IMPLICIT_FILM_WRAPPERS = ["{ph}", "want {ph}", "in the mood for {ph}", "give me {ph}"]
NOUN_FEELINGS = {
    "awe", "bliss", "contempt", "disdain", "compassion", "empathy",
    "anguish", "grief", "sorrow", "longing", "yearning", "panic",
    "grace", "regret", "melancholy",
}
SPECIAL_FEELINGS = {"victim": "feeling like a victim"}
EXCLUDE_FEELINGS = {
    "overwhelm", "exploring", "rejecting", "questioning", "impotent",
}
NOUN_FEELING_TEMPLATES = [
    "feeling full of {w}",
    "there's so much {w} in me tonight",
    "carrying a lot of {w} today",
]

FINITE_SUBJECTLESS_CONCEPT_PHRASES = {
    "wakes up with no memory",
    "can't remember who he is",
    "lives the same day over and over",
}
PARTICIPIAL_SUBJECTLESS_CONCEPT_PHRASES = {
    "trapped in repeating days",
    "pulling off one last big job",
    "sent back decades to fix a mistake",
    "stranded alone on a deserted island",
    "stuck reliving yesterday no matter what she does",
    "rebuilding life after the end of everything",
    "keeping a group alive through a brutal winter storm",
    "tracking down every person who wronged him",
    "infiltrating the gang while wearing a wire",
    "lost in the wilderness with nothing but a knife",
}
NONFINITE_SUBJECTFUL_CONCEPT_PHRASES = {
    "a crew planning to rob a casino",
    "thieves breaking into an impossible vault",
    "a crew assembling specialists to crack a bank",
    "messages arriving from thirty years in the future",
    "survivors wandering a world after civilization collapsed",
    "the last people alive scavenging ruined cities",
    "a family's new home where strange things happen at night",
    "a stranger to himself with no past he can recall",
    "a shy teenager figuring out who she is over one summer",
    "the last awkward year before adulthood changes everything",
    "a boy learning hard truths the year he turns thirteen",
    "a lawyer defending an innocent man at trial",
    "a jury deciding a case that could ruin a life",
    "an attorney risking everything on a final witness",
    "a detective living a double life inside a crime ring",
    "an officer embedded so deep he forgets whose side he is on",
}

SHOULDER_BODY_WORDS = {
    "tight", "stiff", "knotted", "sore", "achy", "clenched", "rigid",
    "heavy",
}
WHOLE_BODY_EXCLUDED_WORDS = {
    "slow", "blocked", "contained", "expanded", "flowing", "fluid",
    "releasing", "radiating", "full",
}
UNDER_SKIN_BODY_WORDS = {
    "buzzy", "electric", "fluttery", "prickly", "itchy", "shivery",
    "tingling", "jumpy",
}
CHEST_BODY_WORDS = {"heavy", "tight", "hollow", "empty", "fluttery", "knotted"}
BACK_BODY_WORDS = {"tight", "stiff", "knotted", "sore", "achy", "rigid", "heavy"}
JAW_BODY_WORDS = {"tight", "stiff", "knotted", "sore", "achy", "clenched"}

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
    "I want {am1} and {m2} movie",
    "put on something {m1} and {m2}",
]
FILM_MOOD_SINGLE_TEMPLATES = [
    "want something {m} tonight",
    "in the mood for something {m}",
    "give me {am} movie",
    "show me something {m}",
    "something {m} please",
]
USER_AND_FILM_TEMPLATES = [
    "{feeling}, want something {m}",
    "{feeling}, give me something {m}",
    "{feeling}, show me something {m}",
    "{feeling}, in the mood for something {m}",
    "{feeling}, want {am} movie",
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
    "{feeling}, want something {m}, nothing {a} please",
    "{feeling}, give me something {m} but nothing {a}",
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
    "{ag} about {p}",
    "{agm} about {p}",
]
PLOT_TOPIC_PAIR_TEMPLATES = [
    "a movie about {a} and {b}",
    "a story about {a} with {b}",
]
PLOT_SETTING_TEMPLATE = "a story about {topic} set in {setting}"
PLOT_EVENT_TEMPLATE = "a story about {topic} during {event}"
PLOT_FUSED_GENRE_TEMPLATE = "{topic} {genre} set in {setting}"
SUBJECTFUL_IMPLICIT_TEMPLATES = [
    "{ph}",
    "a movie where {ph}",
    "a story where {ph}",
    "something where {ph}",
    "a film where {ph}",
]
FINITE_SUBJECTLESS_IMPLICIT_TEMPLATES = [
    "a movie where someone {ph}",
    "someone {ph}",
    "something about someone who {ph}",
    "a film where someone {ph}",
]
PARTICIPIAL_SUBJECTLESS_IMPLICIT_TEMPLATES = [
    "{ph}",
    "a movie where someone is {ph}",
    "someone {ph}",
    "something about someone {ph}",
]
NONFINITE_SUBJECTFUL_IMPLICIT_TEMPLATES = [
    "{ph}",
    "a movie about {ph}",
    "a story about {ph}",
    "something about {ph}",
    "a film about {ph}",
]
HYBRID_TEMPLATES = [
    "{feeling}, want a movie about {p}",
    "{feeling}, give me a story about {p}",
    "{feeling}, something with {p}",
    "{feeling}, want something about {p}",
]
HYBRID_GENRE_TEMPLATES = [
    "{feeling}, want {ag} about {p}",
    "{feeling}, in the mood for {agm} about {p}",
]
HYBRID_TOPIC_PAIR_TEMPLATE = "{feeling}, want a story about {a} with {b}"
HYBRID_SETTING_TEMPLATE = "{feeling}, give me a story about {topic} set in {setting}"
HYBRID_EVENT_TEMPLATE = "{feeling}, want a story about {topic} during {event}"
HYBRID_FUSED_GENRE_TEMPLATE = "{feeling}, want {topic} {genre} set in {setting}"

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


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])",
                          text.lower()))


def _bare(display: str) -> str:
    for prefix in ("an ", "a ", "the "):
        if display.startswith(prefix):
            return display[len(prefix):]
    return display


def _an(word: str) -> str:
    return f"an {word}" if word[0].lower() in "aeiou" else f"a {word}"


def _compound_topic(display: str) -> str:
    if display.startswith(("a ", "an ")):
        return display
    return f"a {display}"


def _assert_plot_elements(plot: list[str] | tuple[str, ...]) -> None:
    for element in plot:
        words = set(re.findall(r"[a-z]+", element.lower()))
        assert not words & GENERIC_PLOT_WORDS, (
            f"generic word in gold plot element '{element}'"
        )


def _assert_no_keyword_leak(text: str, gold: str, kind: str) -> None:
    assert not _contains_term(text, gold), f"implicit {kind} leaks '{gold}': {text}"


def _body_word_forbidden(body_word: str, category: str,
                         film_moods: set[str]) -> bool:
    word = body_word.lower()
    category_name = category.lower().replace("_", " ").replace("-", " ")
    return word in category_name or word in film_moods


def _assert_separation(*, feeling_text: str = "", want_text: str = "",
                       film_moods: list[str], user_words: set[str]) -> None:
    leaked_film = [m for m in film_moods if _contains_term(feeling_text, m)]
    leaked_user = [w for w in user_words if _contains_term(want_text, w)]
    assert not leaked_film, f"film mood in feeling clause: {leaked_film}: {feeling_text}"
    assert not leaked_user, f"user feeling in want clause: {leaked_user}: {want_text}"


def _assert_fixed_vocab(intent: dict, user_categories: set[str],
                        film_moods: set[str], genres: set[str]) -> None:
    assert set(intent["user_moods"]) <= user_categories
    assert set(intent["desired_film_moods"]) <= film_moods
    assert set(intent["avoid_film_moods"]) <= film_moods
    assert set(intent["genres_include"]) <= genres
    _assert_plot_elements(intent["plot_elements"])


def _assert_explicit_mood_cap(moods: list[str] | tuple[str, ...]) -> None:
    assert len(moods) <= 3, f"more than three explicit film moods: {moods}"


def _feeling_clauses(word: str) -> list[str]:
    if word in EXCLUDE_FEELINGS:
        return []
    if word in SPECIAL_FEELINGS:
        return [SPECIAL_FEELINGS[word]]
    if word in NOUN_FEELINGS:
        return [template.format(w=word) for template in NOUN_FEELING_TEMPLATES]
    return [template.format(w=word) for template in FEELING_TEMPLATES]


def _feeling_clause(word: str, index: int = 0) -> str:
    clauses = _feeling_clauses(word)
    assert clauses, f"excluded feeling reached a template: {word}"
    return clauses[index % len(clauses)]


def _adjective_feelings(words: list[str]) -> list[str]:
    return [
        word for word in words
        if word not in NOUN_FEELINGS
        and word not in SPECIAL_FEELINGS
        and word not in EXCLUDE_FEELINGS
    ]


def _body_candidates(body_sensations: dict[str, str],
                     film_moods: set[str]) -> list[tuple[str, str]]:
    candidates = []
    for word, category in sorted(body_sensations.items()):
        if _body_word_forbidden(word, category, film_moods):
            continue
        if word in SHOULDER_BODY_WORDS:
            candidates.append((f"my shoulders are {word} and I can't unwind", category))
        if word not in WHOLE_BODY_EXCLUDED_WORDS:
            candidates.append((f"my whole body feels {word} tonight", category))
        if word in UNDER_SKIN_BODY_WORDS:
            article = "an" if word[0].lower() in "aeiou" else "a"
            candidates.append((f"{article} {word} feeling under my skin all day", category))
        if word in CHEST_BODY_WORDS:
            candidates.append((f"everything in my chest feels {word} right now", category))
        if word in BACK_BODY_WORDS:
            candidates.append((f"my back feels {word} after a long day", category))
        if word in JAW_BODY_WORDS:
            candidates.append((f"my jaw feels {word} and I can't relax", category))
    return candidates


# ---------------------------------------------------------------------------
# Candidate builders — each returns a deterministic list of (text, intent).
# ---------------------------------------------------------------------------


def gen_mood_user_only(words: dict[str, list[str]], mood_map: dict,
                       body_sensations: dict[str, str], film_moods: list[str]):
    out = []
    for category, cat_words in sorted(words.items()):
        desired, avoid = _map_fields([category], mood_map)
        for word in cat_words:
            _assert_separation(feeling_text=word, film_moods=film_moods,
                               user_words=set())
            for clause in _feeling_clauses(word):
                out.append((clause,
                            dict(user_moods=[category], desired=desired, avoid=avoid)))
        adjective_words = _adjective_feelings(cat_words)
        for i, w1 in enumerate(adjective_words):
            for w2 in adjective_words[i + 1:]:
                for template in FEELING_PAIR_TEMPLATES:
                    out.append((template.format(w1=w1, w2=w2),
                                dict(user_moods=[category], desired=desired, avoid=avoid)))
    # Two-category pairs (rule 1 cross-category tie handling).
    cats = sorted(words)
    for i, c1 in enumerate(cats):
        for c2 in cats[i + 1:]:
            desired, avoid = _map_fields([c1, c2], mood_map)
            for w1 in _adjective_feelings(words[c1])[:3]:
                for w2 in _adjective_feelings(words[c2])[:3]:
                    out.append((FEELING_PAIR_TEMPLATES[0].format(w1=w1, w2=w2),
                                dict(user_moods=[c1, c2], desired=desired, avoid=avoid)))
    explicit = [(t, _intent(t, "mood", **kw)) for t, kw in out]
    implicit = []
    film_set = set(film_moods)
    for text, category in _body_candidates(body_sensations, film_set):
        desired, avoid = _map_fields([category], mood_map)
        _assert_no_keyword_leak(text, category, "user mood")
        _assert_separation(feeling_text=text, film_moods=film_moods,
                           user_words=set())
        implicit.append((text, _intent(text, "mood", user_moods=[category],
                                       desired=desired, avoid=avoid)))
    return explicit, implicit


def gen_mood_film_only(film_moods: list[str]):
    out = []
    moods = sorted(film_moods)
    for m in moods:
        _assert_explicit_mood_cap([m])
        for template in FILM_MOOD_SINGLE_TEMPLATES:
            out.append((template.format(m=m, am=_an(m)), [m]))
    for i, m1 in enumerate(moods):
        for m2 in moods[i + 1:]:
            _assert_explicit_mood_cap([m1, m2])
            for template in FILM_MOOD_TEMPLATES:
                out.append((template.format(m1=m1, m2=m2, am1=_an(m1)),
                            [m1, m2]))
    explicit = [(t, _intent(t, "mood", desired=ms)) for t, ms in out]
    implicit = []
    assert set(IMPLICIT_FILM_MOODS) <= set(film_moods)
    for mood, phrasings in sorted(IMPLICIT_FILM_MOODS.items()):
        for phrasing in phrasings:
            for wrapper in IMPLICIT_FILM_WRAPPERS:
                text = wrapper.format(ph=phrasing)
                _assert_no_keyword_leak(text, mood, "film mood")
                implicit.append((text, _intent(text, "mood", desired=[mood])))
    return explicit, implicit


def gen_mood_user_and_film(words: dict[str, list[str]], mood_map: dict,
                           film_moods: list[str], user_words: set[str]):
    out = []
    for category, cat_words in sorted(words.items()):
        map_desired, map_avoid = _map_fields([category], mood_map)
        for word in cat_words[:8]:
            for m in sorted(film_moods):
                feeling = _feeling_clause(word, len(m))
                template = USER_AND_FILM_TEMPLATES[
                    (len(word) + len(m)) % len(USER_AND_FILM_TEMPLATES)
                ]
                desired = sorted(set(map_desired) | {m})       # rule 3
                avoid = sorted(set(map_avoid) - set(desired))  # rule 3
                _assert_explicit_mood_cap([m])
                _assert_separation(feeling_text=feeling, want_text=m,
                                   film_moods=film_moods, user_words=user_words)
                out.append((template.format(feeling=feeling, m=m, am=_an(m)),
                            dict(user_moods=[category], desired=desired, avoid=avoid)))
    return [(t, _intent(t, "mood", **kw)) for t, kw in out]


def gen_avoid_preferences(words: dict[str, list[str]], mood_map: dict,
                          film_moods: list[str], user_words: set[str]):
    out = []
    moods = sorted(film_moods)
    # a) film desired + explicit avoid (rule 4, no user mood).
    for m in moods:
        for a in moods:
            if a == m:
                continue
            _assert_explicit_mood_cap([m, a])
            template = AVOID_FILM_TEMPLATES[(len(m) + len(a)) % len(AVOID_FILM_TEMPLATES)]
            _assert_separation(want_text=f"{m} {a}", film_moods=film_moods,
                               user_words=user_words)
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
                    _assert_explicit_mood_cap([m, a])
                    desired = sorted((set(map_desired) | {m}) - {a})
                    avoid = sorted((set(map_avoid) | {a}) - set(desired))
                    feeling = _feeling_clause(word, len(m) + len(a))
                    _assert_separation(feeling_text=feeling, want_text=f"{m} {a}",
                                       film_moods=film_moods, user_words=user_words)
                    template = AVOID_USER_TEMPLATES[(len(word) + len(a)) % len(AVOID_USER_TEMPLATES)]
                    out.append((template.format(feeling=feeling, m=m, a=a),
                                dict(user_moods=[category], desired=desired, avoid=avoid)))
    return [(t, _intent(t, "mood", **kw)) for t, kw in out]


def gen_plot_description(film_moods: list[str], user_words: set[str]):
    singles = []
    multi = []
    fused = []
    # Explicit, one element. Each slot draws only from its compatible pool.
    for display, gold in TOPICS:
        for template in PLOT_TEMPLATES_1:
            text = template.format(p=display)
            _assert_separation(want_text=display, film_moods=film_moods,
                               user_words=user_words)
            singles.append((text, dict(plot=[gold])))
    for setting, gold in NATURAL_SET_IN_SETTINGS:
        singles.append((f"a movie set in {setting}", dict(plot=[gold])))
    for event, gold in EVENTS:
        singles.append((f"a movie during {event}", dict(plot=[gold])))

    # Topic pairs stay in about/with slots; locations and events use their
    # dedicated prepositions.
    for i, (d1, g1) in enumerate(TOPICS):
        for j, (d2, g2) in enumerate(TOPICS[i + 1:i + 9]):
            template = PLOT_TOPIC_PAIR_TEMPLATES[(i + j) % len(PLOT_TOPIC_PAIR_TEMPLATES)]
            text = template.format(a=d1, b=d2)
            _assert_separation(want_text=f"{d1} {d2}", film_moods=film_moods,
                               user_words=user_words)
            multi.append((text, dict(plot=[g1, g2])))
        for setting, setting_gold in NATURAL_SET_IN_SETTINGS:
            text = PLOT_SETTING_TEMPLATE.format(topic=d1, setting=setting)
            multi.append((text, dict(plot=[g1, setting_gold])))
        for event, event_gold in EVENTS:
            text = PLOT_EVENT_TEMPLATE.format(topic=d1, event=event)
            multi.append((text, dict(plot=[g1, event_gold])))
    # Targeted v3 bucket (quota-guaranteed in main): plural subjects,
    # three-element queries, place-genre compounds.
    targeted = []
    # Plural subjects with verb-mediated objects: verbs drop from gold, the
    # plural surface subject and object noun phrase stay (spec 3.8); odd
    # templates carry a weather/manner adjunct that also drops (3.11.3).
    for si, (subj, act, obj_gold) in enumerate(PLURAL_SUBJECT_ACTIONS):
        _assert_separation(want_text=f"{subj} {act}", film_moods=film_moods,
                           user_words=user_words)
        for ti, template in enumerate(PLURAL_SUBJECT_TEMPLATES):
            shown_act = act
            if ti % 2 and "in the rain" not in act and "at night" not in act:
                shown_act = f"{act} {WEATHER_ADJUNCTS[(si + ti) % len(WEATHER_ADJUNCTS)]}"
            targeted.append((template.format(s=subj, act=shown_act),
                             dict(plot=[subj, obj_gold])))
    # Three-element queries: two topics plus a setting.
    for i, (d1, g1) in enumerate(TOPICS[::4]):
        d2, g2 = TOPICS[(i * 4 + 9) % len(TOPICS)]
        if g1 == g2:
            continue
        setting, setting_gold = NATURAL_SET_IN_SETTINGS[i % len(NATURAL_SET_IN_SETTINGS)]
        _assert_separation(want_text=f"{d1} {d2} {setting}",
                           film_moods=film_moods, user_words=user_words)
        targeted.append((f"a movie about {d1} and {d2} set in {setting}",
                         dict(plot=[g1, g2, setting_gold])))
    # Place-genre compounds: "a courtroom drama (about X)".
    for place, gw, genre, obj_golds in PLACE_GENRE_COMPOUNDS:
        targeted.append((_an(f"{place} {gw}"), dict(plot=[place], genres=[genre])))
        for obj_gold in obj_golds:
            obj_display = TOPIC_BY_GOLD[obj_gold][0]
            targeted.append((f"{_an(f'{place} {gw}')} about {obj_display}",
                             dict(plot=[place, obj_gold], genres=[genre])))
    # Singular subject + gerund clause; evaluative adjectives drop from gold.
    for si, (display, subj_gold, act, obj_gold) in enumerate(SINGULAR_SUBJECT_ACTIONS):
        _assert_separation(want_text=f"{display} {act}", film_moods=film_moods,
                           user_words=user_words)
        for ti, template in enumerate(SINGULAR_SUBJECT_TEMPLATES):
            if (si + ti) % 2:
                adj = EVALUATIVE_MODIFIERS[(si + ti) % len(EVALUATIVE_MODIFIERS)]
                subj_shown = _an(f"{adj} {_bare(display)}")
            else:
                subj_shown = display
            targeted.append((template.format(s=subj_shown, act=act),
                             dict(plot=[subj_gold, obj_gold])))
    # "{setting-or-topic} {genre} with {NP}" compounds.
    for setting_bare, gw, genre, np_display, np_gold in SETTING_GENRE_WITH:
        head = f"{gw} movie" if gw in MOVIE_REQUIRED_GENRES else gw
        targeted.append((f"{_an(f'{setting_bare} {head}')} with {np_display}",
                         dict(plot=[setting_bare, np_gold], genres=[genre])))
    # Film-style modifiers drop entirely (spec 3.11.2).
    for style, compound_display, topic_gold, genre, setting, setting_gold in STYLE_PREFIX_FUSED:
        text = f"{_an(f'{style} {_bare(compound_display)}')} in {setting}"
        targeted.append((text, dict(plot=[topic_gold, setting_gold],
                                    genres=[genre])))
    # Bare-start "X movie about {p}" records (article-less user typing).
    for gi, gw_genre in enumerate(w for w in GENRE_WORDS if w[0] in MOVIE_REQUIRED_GENRES):
        gw, genre = gw_genre
        display, gold = TOPICS[(gi * 11 + 3) % len(TOPICS)]
        targeted.append((f"{gw} movie about {display}",
                         dict(plot=[gold], genres=[genre])))
    # "{a} {b} story" compounds: generic "story" drops, no genre grounded.
    for a_gold, b_gold in STORY_COMPOUNDS:
        a_display = _bare(TOPIC_BY_GOLD[a_gold][0]) if a_gold in TOPIC_BY_GOLD else a_gold
        targeted.append((_an(f"{a_display} {b_gold} story"),
                         dict(plot=[a_gold, b_gold])))
        targeted.append((f"a movie about {_an(f'{a_display} {b_gold} story')}",
                         dict(plot=[a_gold, b_gold])))
    # Relative-clause romance trope records (with and without trailing
    # setting), quota-guaranteed in their own bucket since v6: random
    # sampling of the targeted bucket must not drop the iv38 shapes.
    trope = []
    for ri, (text, gold, setting, setting_gold) in enumerate(FALLS_IN_LOVE_RECORDS):
        trope.append((text, dict(plot=list(gold))))
        trope.append((f"{text} in {setting}",
                      dict(plot=list(gold) + [setting_gold])))
        gw, genre = FALLS_IN_LOVE_OBJECT_PREFIXES[ri]
        trope.append((f"{gw} movie about {text} in {setting}",
                      dict(plot=list(gold) + [setting_gold], genres=[genre])))
    # Object-less trope clause: setting attaches directly after the clause
    # and the gold keeps the finite "falls in love" inflection verbatim.
    for ri, (subj, subj_gold, setting, setting_gold) in enumerate(
            FALLS_IN_LOVE_NO_OBJECT):
        clause = f"{subj} who falls in love in {setting}"
        gold = [subj_gold, "falls in love", setting_gold]
        trope.append((clause, dict(plot=list(gold))))
        trope.append((f"a movie about {clause}", dict(plot=list(gold))))
        gw, genre = FALLS_IN_LOVE_NO_OBJECT_PREFIXES[ri]
        trope.append((f"{gw} movie about {clause}",
                      dict(plot=list(gold), genres=[genre])))
    # Bare "in {setting}" fused-genre variant (eval-style "thriller in winter").
    for gi, (gw, genre) in enumerate(GENRE_WORDS):
        if gw not in FUSED_GENRE_TOPICS:
            continue
        topic_display, topic_gold = FUSED_GENRE_TOPICS[gw][gi % len(FUSED_GENRE_TOPICS[gw])]
        setting, setting_gold = NATURAL_SET_IN_SETTINGS[
            (gi * 2) % len(NATURAL_SET_IN_SETTINGS)
        ]
        head = f"{gw} movie" if gw in MOVIE_REQUIRED_GENRES else gw
        targeted.append((f"{_compound_topic(topic_display)} {head} in {setting}",
                         dict(plot=[topic_gold, setting_gold], genres=[genre])))
    # Explicit with genre word.
    for gi, (gw, genre) in enumerate(GENRE_WORDS):
        for display, gold in TOPICS[gi::3]:
            template_index = 1 if gw in MOVIE_REQUIRED_GENRES else (gi + len(gold)) % 2
            template = PLOT_GENRE_TEMPLATES[template_index]
            singles.append((template.format(ag=_an(gw),
                                             agm=_an(f"{gw} movie"), p=display),
                            dict(plot=[gold], genres=[genre])))
        if gw not in FUSED_GENRE_TOPICS:
            continue
        for topic_display, topic_gold in FUSED_GENRE_TOPICS[gw]:
            for setting, setting_gold in NATURAL_SET_IN_SETTINGS:
                text = PLOT_FUSED_GENRE_TEMPLATE.format(
                    topic=_compound_topic(topic_display),
                    genre=f"{gw} movie" if gw in MOVIE_REQUIRED_GENRES else gw,
                    setting=setting,
                )
                fused.append((text, dict(plot=[topic_gold, setting_gold],
                                         genres=[genre])))
    singles = [(t, _intent(t, "content", **kw)) for t, kw in singles]
    multi = [(t, _intent(t, "content", **kw)) for t, kw in multi]
    targeted = [(t, _intent(t, "content", **kw)) for t, kw in targeted]
    fused = [(t, _intent(t, "content", **kw)) for t, kw in fused]
    trope = [(t, _intent(t, "content", **kw)) for t, kw in trope]
    # Implicit (rule 7).
    implicit = []
    for concept, phrasings in sorted(CONCEPTS.items()):
        concept_words = {w for w in concept.replace("-", " ").split() if len(w) > 2}
        for phrasing in phrasings:
            if phrasing in FINITE_SUBJECTLESS_CONCEPT_PHRASES:
                templates = FINITE_SUBJECTLESS_IMPLICIT_TEMPLATES
            elif phrasing in PARTICIPIAL_SUBJECTLESS_CONCEPT_PHRASES:
                templates = PARTICIPIAL_SUBJECTLESS_IMPLICIT_TEMPLATES
            elif phrasing in NONFINITE_SUBJECTFUL_CONCEPT_PHRASES:
                templates = NONFINITE_SUBJECTFUL_IMPLICIT_TEMPLATES
            else:
                templates = SUBJECTFUL_IMPLICIT_TEMPLATES
            for template in templates:
                text = template.format(ph=phrasing)
                lowered = text.lower()
                assert concept.lower() not in lowered and not any(
                    w in lowered.replace("-", " ").split() for w in concept_words
                ), f"implicit phrasing leaks concept '{concept}': {text}"
                implicit.append((text, _intent(text, "content", plot=[concept])))
    return singles, multi, targeted, fused, implicit, trope


def gen_hybrid(words: dict[str, list[str]], mood_map: dict,
               film_moods: list[str], user_words: set[str]):
    singles = []
    multi = []
    plural = []
    fused = []
    for category, cat_words in sorted(words.items()):
        desired, avoid = _map_fields([category], mood_map)
        kw = dict(user_moods=[category], desired=desired, avoid=avoid)
        for wi, word in enumerate(cat_words[:6]):
            feeling = _feeling_clause(word, wi)
            for display, gold in TOPICS[wi::4]:
                template = HYBRID_TEMPLATES[(len(word) + len(gold)) % len(HYBRID_TEMPLATES)]
                _assert_separation(feeling_text=feeling, want_text=display,
                                   film_moods=film_moods, user_words=user_words)
                singles.append((template.format(feeling=feeling, p=display),
                                dict(plot=[gold], **kw)))
            for gw, genre in GENRE_WORDS[wi::5]:
                display, gold = TOPICS[(wi * 7 + len(gw)) % len(TOPICS)]
                template_index = 1 if gw in MOVIE_REQUIRED_GENRES else len(gold) % 2
                template = HYBRID_GENRE_TEMPLATES[template_index]
                singles.append((template.format(feeling=feeling, ag=_an(gw),
                                                 agm=_an(f"{gw} movie"), p=display),
                                dict(plot=[gold], genres=[genre], **kw)))
            for pi, (d1, g1) in enumerate(TOPICS[wi::7]):
                d2, g2 = TOPICS[(pi + wi + 11) % len(TOPICS)]
                if g1 == g2:
                    continue
                _assert_separation(feeling_text=feeling,
                                   want_text=f"{d1} {d2}",
                                   film_moods=film_moods, user_words=user_words)
                multi.append((HYBRID_TOPIC_PAIR_TEMPLATE.format(
                                  feeling=feeling, a=d1, b=d2),
                              dict(plot=[g1, g2], **kw)))
            for setting, setting_gold in NATURAL_SET_IN_SETTINGS:
                multi.append((HYBRID_SETTING_TEMPLATE.format(
                                  feeling=feeling, topic=TOPICS[wi % len(TOPICS)][0],
                                  setting=setting),
                              dict(plot=[TOPICS[wi % len(TOPICS)][1], setting_gold],
                                   **kw)))
            for event, event_gold in EVENTS:
                multi.append((HYBRID_EVENT_TEMPLATE.format(
                                  feeling=feeling, topic=TOPICS[(wi + 5) % len(TOPICS)][0],
                                  event=event),
                              dict(plot=[TOPICS[(wi + 5) % len(TOPICS)][1], event_gold],
                                   **kw)))
            subj, act, obj_gold = PLURAL_SUBJECT_ACTIONS[
                (wi * 3 + len(word)) % len(PLURAL_SUBJECT_ACTIONS)
            ]
            _assert_separation(feeling_text=feeling, want_text=f"{subj} {act}",
                               film_moods=film_moods, user_words=user_words)
            plural.append((f"{feeling}, want a movie about {subj} {act}",
                           dict(plot=[subj, obj_gold], **kw)))
            for gi, (gw, genre) in enumerate(GENRE_WORDS):
                if gw not in FUSED_GENRE_TOPICS:
                    continue
                genre_topics = FUSED_GENRE_TOPICS[gw]
                d1, g1 = genre_topics[(wi * 5 + gi) % len(genre_topics)]
                setting, setting_gold = NATURAL_SET_IN_SETTINGS[
                    (wi + gi) % len(NATURAL_SET_IN_SETTINGS)
                ]
                _assert_separation(feeling_text=feeling,
                                   want_text=f"{d1} {gw} {setting}",
                                   film_moods=film_moods, user_words=user_words)
                fused.append((HYBRID_FUSED_GENRE_TEMPLATE.format(
                                  feeling=feeling, topic=_compound_topic(d1),
                                  genre=(f"{gw} movie"
                                         if gw in MOVIE_REQUIRED_GENRES else gw),
                                  setting=setting),
                              dict(plot=[g1, setting_gold], genres=[genre], **kw)))
    return (
        [(t, _intent(t, "hybrid", **kw)) for t, kw in singles],
        [(t, _intent(t, "hybrid", **kw)) for t, kw in multi],
        [(t, _intent(t, "hybrid", **kw)) for t, kw in plural],
        [(t, _intent(t, "hybrid", **kw)) for t, kw in fused],
    )


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
    film_mood_set = set(film_moods)
    user_categories = set(vocab["categories"])
    user_words = {
        word.lower()
        for category_words in vocab["categories"].values()
        for word in category_words
        if word.lower() not in film_mood_set
    }
    allowed_genres = {genre for _, genre in GENRE_WORDS}
    per_category = args.target_total // len(CATEGORY_FILES)
    assert per_category == 600, "v2 quotas require the default 600 records/category"
    seen_texts: set[str] = set()
    rng = random.Random(args.seed)

    user_explicit, user_implicit = gen_mood_user_only(
        words, mood_map, vocab["body_sensations"], film_moods
    )
    film_explicit, film_implicit = gen_mood_film_only(film_moods)
    (plot_single, plot_multi, plot_targeted, plot_fused, implicit_plot,
     plot_trope) = gen_plot_description(film_moods, user_words)
    hybrid_single, hybrid_multi, hybrid_plural, hybrid_fused = gen_hybrid(
        words, mood_map, film_moods, user_words
    )
    candidates: dict[str, list[tuple[str, dict]]] = {
        "mood_user_and_film": gen_mood_user_and_film(
            words, mood_map, film_moods, user_words
        ),
        "avoid_preferences": gen_avoid_preferences(
            words, mood_map, film_moods, user_words
        ),
    }

    chosen: dict[str, list[tuple[str, dict]]] = {}
    for category in sorted(candidates):
        chosen[category] = _take(candidates[category], rng, per_category,
                                 heldout, seen_texts)

    # Quota-controlled v2 slices. Buckets are disjoint by construction.
    user_implicit_take = _take(user_implicit, rng, 90, heldout, seen_texts)
    user_explicit_take = _take(user_explicit, rng, 510, heldout, seen_texts)
    chosen["mood_user_only"] = user_explicit_take + user_implicit_take
    rng.shuffle(chosen["mood_user_only"])

    film_implicit_take = _take(film_implicit, rng, 180, heldout, seen_texts)
    film_explicit_take = _take(film_explicit, rng, 420, heldout, seen_texts)
    chosen["mood_film_only"] = film_explicit_take + film_implicit_take
    rng.shuffle(chosen["mood_film_only"])

    plot_fused_take = _take(plot_fused, rng, 180, heldout, seen_texts)
    plot_targeted_take = _take(plot_targeted, rng, 120, heldout, seen_texts)
    # v6: every trope record ships (no sampling); implicit funds the slots
    # (its slice passes with wide margin against a 0.0 tier-2 bar).
    plot_trope_take = _take(plot_trope, rng, len(plot_trope), heldout, seen_texts)
    assert len(plot_trope_take) == 30, len(plot_trope_take)
    plot_multi_take = _take(plot_multi, rng, 60, heldout, seen_texts)
    implicit_take = _take(implicit_plot, rng, 150, heldout, seen_texts)
    plot_single_take = _take(plot_single, rng, 60, heldout, seen_texts)
    plot_all = (plot_fused_take + plot_targeted_take + plot_trope_take
                + plot_multi_take + implicit_take + plot_single_take)
    rng.shuffle(plot_all)
    chosen["plot_description"] = plot_all

    hybrid_fused_take = _take(hybrid_fused, rng, 180, heldout, seen_texts)
    hybrid_plural_take = _take(hybrid_plural, rng, 30, heldout, seen_texts)
    hybrid_multi_take = _take(hybrid_multi, rng, 60, heldout, seen_texts)
    hybrid_single_take = _take(hybrid_single, rng, 330, heldout, seen_texts)
    chosen["hybrid_queries"] = (
        hybrid_fused_take + hybrid_plural_take + hybrid_multi_take
        + hybrid_single_take
    )
    rng.shuffle(chosen["hybrid_queries"])

    for category, records in sorted(chosen.items()):
        assert len(records) == per_category, (
            f"insufficient candidates for {category}: {len(records)}/{per_category}"
        )

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
            _assert_fixed_vocab(intent, user_categories, film_mood_set, allowed_genres)
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
    marker_sets = {
        "implicit_plot": {t.strip().lower() for t, _ in implicit_take},
        "implicit_film_mood": {t.strip().lower() for t, _ in film_implicit_take},
        "implicit_user_body": {t.strip().lower() for t, _ in user_implicit_take},
        "plot_fused_genre": {t.strip().lower() for t, _ in plot_fused_take},
        "plot_multi": {
            t.strip().lower()
            for t, _ in plot_fused_take + plot_targeted_take + plot_multi_take
        },
        "hybrid_fused_genre": {t.strip().lower() for t, _ in hybrid_fused_take},
        "hybrid_multi": {
            t.strip().lower()
            for t, _ in hybrid_fused_take + hybrid_plural_take + hybrid_multi_take
        },
    }

    def ratio(marker: str, category: str) -> float:
        category_records = [r for r in merged if r["category"] == category]
        count = sum(r["text"].strip().lower() in marker_sets[marker]
                    for r in category_records)
        return count / len(category_records)

    ratios = {
        "mood_film_only_implicit": ratio("implicit_film_mood", "mood_film_only"),
        "mood_user_only_body_implicit": ratio("implicit_user_body", "mood_user_only"),
        "plot_description_multi_element": ratio("plot_multi", "plot_description"),
        "plot_description_fused_genre": ratio("plot_fused_genre", "plot_description"),
        "hybrid_queries_multi_element": ratio("hybrid_multi", "hybrid_queries"),
        "hybrid_queries_fused_genre": ratio("hybrid_fused_genre", "hybrid_queries"),
    }
    assert ratios["mood_film_only_implicit"] >= 0.25
    assert ratios["mood_user_only_body_implicit"] >= 0.15
    assert ratios["plot_description_multi_element"] >= 0.40
    assert ratios["plot_description_fused_genre"] >= 0.25
    assert ratios["hybrid_queries_multi_element"] >= 0.40
    assert ratios["hybrid_queries_fused_genre"] >= 0.25

    print(json.dumps({"total": len(merged), "implicit_plot": len(implicit_texts),
                      "ratios": ratios, "per_category": summary},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
