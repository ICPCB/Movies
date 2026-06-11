"""Two-tier intent parser (ULTRAPLAN phase 7).

Tier 1 is a deterministic lexicon parser: it recognizes feeling words from
labels/user_mood_vocab.json (categories + body sensations), translates them
through labels/user_mood_map.json, and extracts era / genre / rating hints
with regexes. No model, <5ms, runs on every request.

Tier 2 optionally asks local Ollama (llama3.2) to extract NON-mood fields
(plot elements, genres, era) with a few-shot JSON prompt. Mood fields always
come from tier 1 — the LLM never invents user moods or film-mood mappings.
Any tier-2 failure (Ollama down, bad JSON, schema violation) falls back to
the tier-1 intent.
"""

from __future__ import annotations

import json
import re
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from engine.intent_schema import empty_intent, validate_intent

_LABELS_DIR = Path(__file__).resolve().parent.parent / "labels"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "llama3.2"
OLLAMA_TIMEOUT_SECONDS = 20.0

GENRES = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music", "Mystery",
    "Romance", "Science Fiction", "TV Movie", "Thriller", "War", "Western",
]
_GENRE_SYNONYMS = {"sci-fi": "Science Fiction", "scifi": "Science Fiction"}

_WORD_RE = re.compile(r"[a-z][a-z'-]*")
_DECADE_RE = re.compile(r"\b(?:the\s+)?((?:19|20)\d0)s\b")
_SHORT_DECADE_RE = re.compile(r"\b(?:the\s+)?(\d0)s\b")
_BEFORE_RE = re.compile(r"\bbefore\s+((?:19|20)\d\d)\b")
_AFTER_RE = re.compile(r"\b(?:after|since|from)\s+((?:19|20)\d\d)\b")
_RANGE_RE = re.compile(r"\b((?:19|20)\d\d)\s*(?:-|to|through)\s*((?:19|20)\d\d)\b")
_RATING_RE = re.compile(r"\brat(?:ed|ing)\s+(?:above|over|at least)\s+(\d(?:\.\d)?)\b")

_STOPWORDS = {
    "a", "an", "and", "also", "but", "feel", "feeling", "for", "i", "im",
    "in", "is", "it", "like", "me", "mood", "movie", "movies", "my", "of",
    "or", "really", "so", "some", "something", "the", "to", "tonight",
    "very", "want", "watch", "with",
}


@lru_cache(maxsize=1)
def _lexicon() -> dict[str, Any]:
    vocab = json.loads(
        (_LABELS_DIR / "user_mood_vocab.json").read_text(encoding="utf-8")
    )
    mood_map = json.loads(
        (_LABELS_DIR / "user_mood_map.json").read_text(encoding="utf-8")
    )["map"]
    film_moods = set(
        json.loads(
            (_LABELS_DIR / "film_mood_vocab.json").read_text(encoding="utf-8")
        )["film_moods"]
    )
    word_to_categories: dict[str, list[str]] = {}
    phrases: dict[str, list[str]] = {}

    def register(word: str, category: str) -> None:
        target = word.lower()
        bucket = phrases if " " in target else word_to_categories
        bucket.setdefault(target, [])
        if category not in bucket[target]:
            bucket[target].append(category)

    for category, words in vocab["categories"].items():
        for word in words:
            register(word, category)
    for word, category in vocab.get("body_sensations", {}).items():
        register(word, category)
    # The category names themselves ("hopeful", "sad", "curious", ...) are
    # natural feeling words too.
    for category in vocab["categories"]:
        for part in category.split("_"):
            register(part, category)
    register("guilty", "guilt")
    register("joyful", "aliveness_joy")
    return {
        "words": word_to_categories,
        "phrases": sorted(phrases.items(), key=lambda item: -len(item[0])),
        "map": mood_map,
        "film_moods": film_moods,
    }


def _find_categories(lowered: str) -> tuple[list[str], set[str]]:
    """Return (categories, matched word/phrase set).

    A word may belong to several feeling categories ("anxious" is listed
    under both fear and stressed_tense). Greedy set cover picks the fewest
    categories that explain every matched word, so "calm and caring" resolves
    to tender rather than two half-matching categories.
    """
    lexicon = _lexicon()
    word_categories: dict[str, list[str]] = {}
    remaining = lowered
    for phrase, categories in lexicon["phrases"]:
        if re.search(rf"\b{re.escape(phrase)}\b", remaining):
            word_categories[phrase] = categories
            remaining = remaining.replace(phrase, " ")
    for token in _WORD_RE.findall(remaining):
        categories = lexicon["words"].get(token)
        if categories:
            word_categories[token] = categories

    uncovered = set(word_categories)
    picked: list[str] = []
    while uncovered:
        coverage: dict[str, set[str]] = {}
        for word in uncovered:
            for category in word_categories[word]:
                coverage.setdefault(category, set()).add(word)
        best = sorted(
            coverage.items(), key=lambda item: (-len(item[1]), item[0])
        )[0]
        picked.append(best[0])
        uncovered -= best[1]
    return picked, set(word_categories)


def _mood_fields(categories: list[str]) -> dict[str, list[str]]:
    mood_map = _lexicon()["map"]
    desired: set[str] = set()
    avoid: set[str] = set()
    for slug in categories:
        entry = mood_map[slug]
        desired.update(entry["desired"])
        avoid.update(entry["avoid"])
    avoid -= desired  # a desired mood always wins over another mood's avoid
    return {
        "user_moods": categories,
        "desired_film_moods": sorted(desired),
        "avoid_film_moods": sorted(avoid),
    }


def _find_genres(lowered: str) -> list[str]:
    found: list[str] = []
    for synonym, genre in _GENRE_SYNONYMS.items():
        if re.search(rf"\b{re.escape(synonym)}\b", lowered) and genre not in found:
            found.append(genre)
    for genre in GENRES:
        if re.search(rf"\b{re.escape(genre.lower())}\b", lowered) and genre not in found:
            found.append(genre)
    return found


def _find_era(lowered: str) -> dict[str, int | None]:
    era: dict[str, int | None] = {"min_year": None, "max_year": None}
    range_match = _RANGE_RE.search(lowered)
    if range_match:
        era["min_year"] = int(range_match.group(1))
        era["max_year"] = int(range_match.group(2))
        return era
    decade_match = _DECADE_RE.search(lowered)
    if decade_match:
        start = int(decade_match.group(1))
        return {"min_year": start, "max_year": start + 9}
    short_match = _SHORT_DECADE_RE.search(lowered)
    if short_match:
        tens = int(short_match.group(1))
        start = (1900 if tens >= 30 else 2000) + tens
        return {"min_year": start, "max_year": start + 9}
    before_match = _BEFORE_RE.search(lowered)
    if before_match:
        era["max_year"] = int(before_match.group(1)) - 1
    after_match = _AFTER_RE.search(lowered)
    if after_match:
        era["min_year"] = int(after_match.group(1))
    return era


def _content_tokens(lowered: str, matched: set[str]) -> list[str]:
    consumed = set()
    for entry in matched:
        consumed.update(entry.split())
    return [
        token
        for token in _WORD_RE.findall(lowered)
        if token not in _STOPWORDS and token not in consumed
    ]


_FEELING_MARKER_RE = re.compile(r"\b(i'?m|i am|i feel|feel|feeling|felt)\b")
# Everything after a desire marker describes the MOVIE the user wants,
# not how the user feels ("feeling sad, want something warm and funny").
_DESIRE_SPLIT_RE = re.compile(
    r"\b(want|wanna|need|give me|show me|in the mood for|looking for)\b"
)


def parse_tier1(text: str, mode: str | None = None) -> dict[str, Any]:
    """Deterministic lexicon parse. Always returns a schema-valid intent.

    Feeling words describe the USER only when the text reads like a feeling
    ("I'm...", "feeling...") or the caller explicitly asked for mood mode —
    otherwise "a tense thriller" would invert into avoid-tense. Text after a
    desire marker describes the film: film-mood enum words there become
    desired_film_moods directly, never user moods.
    """
    lowered = text.lower()
    split = _DESIRE_SPLIT_RE.search(lowered)
    feeling_part = lowered[: split.start()] if split else lowered
    wanted_part = lowered[split.end() :] if split else ""

    if mode == "mood" or _FEELING_MARKER_RE.search(lowered):
        categories, matched = _find_categories(feeling_part)
    else:
        categories, matched = [], set()
    film_moods = _lexicon()["film_moods"]
    wanted_moods = [
        token for token in _WORD_RE.findall(wanted_part) if token in film_moods
    ]
    leftover = [
        token
        for token in _content_tokens(lowered, matched)
        if token not in film_moods
    ]

    if mode in ("category", "random"):
        resolved_mode = mode
    elif categories and len(leftover) >= 3:
        resolved_mode = "hybrid"
    elif categories:
        resolved_mode = "mood"
    elif mode in ("mood", "content", "hybrid"):
        resolved_mode = mode
    else:
        resolved_mode = "content"

    intent = empty_intent(text, resolved_mode)
    if categories:
        intent.update(_mood_fields(categories))
    intent["genres_include"] = _find_genres(lowered)
    intent["era"] = _find_era(lowered)
    rating_match = _RATING_RE.search(lowered)
    if rating_match:
        intent["constraints"] = {"min_rating": float(rating_match.group(1))}
    intent["confidence"] = 0.9 if categories or intent["genres_include"] else 0.3
    return intent


_TIER2_SYSTEM = (
    "You extract movie-search fields from one user request. "
    "Reply with ONLY a JSON object with exactly these keys: "
    '{"plot_elements": [..], "genres_include": [..], "genres_exclude": [..]}. '
    "plot_elements are short noun phrases copied or lightly normalized from "
    "the request describing story content (heist, road trip, submarine). "
    f"Genres must come from this list only: {', '.join(GENRES)}. "
    "Never include feelings, moods, tones, eras, or invented details. "
    "Use [] when a field is absent."
)

_TIER2_EXAMPLES: list[tuple[str, dict]] = [
    (
        "a slow burn heist thriller in winter",
        {
            "plot_elements": ["heist", "winter"],
            "genres_include": ["Thriller"],
            "genres_exclude": [],
        },
    ),
    (
        "feeling exhausted, something light, no horror please",
        {
            "plot_elements": [],
            "genres_include": [],
            "genres_exclude": ["Horror"],
        },
    ),
    (
        "animated movie about a robot who falls in love in space",
        {
            "plot_elements": ["robot", "falls in love", "space"],
            "genres_include": ["Animation"],
            "genres_exclude": [],
        },
    ),
]


def _ollama_chat(text: str, timeout: float) -> dict:
    messages = [{"role": "system", "content": _TIER2_SYSTEM}]
    for example_text, example_json in _TIER2_EXAMPLES:
        messages.append({"role": "user", "content": example_text})
        messages.append(
            {"role": "assistant", "content": json.dumps(example_json)}
        )
    messages.append({"role": "user", "content": text})
    body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        reply = json.loads(response.read().decode("utf-8"))
    return json.loads(reply["message"]["content"])


def parse(
    text: str,
    mode: str | None = None,
    use_llm: bool = False,
    llm_call=None,
    timeout: float = OLLAMA_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Full parse: tier 1 always; tier 2 fills non-mood fields when asked.

    `llm_call(text, timeout) -> dict` is injectable for tests.
    """
    intent = parse_tier1(text, mode)
    if not use_llm:
        return intent
    try:
        extracted = (llm_call or _ollama_chat)(text, timeout)
        plot = [
            str(item).strip()
            for item in extracted.get("plot_elements", [])
            if str(item).strip()
        ][:8]
        include = [g for g in extracted.get("genres_include", []) if g in GENRES]
        exclude = [g for g in extracted.get("genres_exclude", []) if g in GENRES]
        candidate = dict(intent)
        candidate["plot_elements"] = plot
        # Tier-1 lexicon genre hits stay; tier-2 may only add valid genres.
        for genre in include:
            if genre not in candidate["genres_include"]:
                candidate["genres_include"].append(genre)
        candidate["genres_exclude"] = exclude
        valid, _ = validate_intent(candidate)
        if valid:
            return candidate
    except Exception:
        pass  # any tier-2 failure falls back to the deterministic tier-1 parse
    return intent
