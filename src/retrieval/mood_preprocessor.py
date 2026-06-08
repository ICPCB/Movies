"""Deterministic mood intent extraction for movie queries."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass
class MoodIntent:
    current_emotion: str | None
    emotion_source: str
    desired_direction: str | None
    desired_movie_tone: list[str]
    energy_level: str | None
    safety_sensitivity: str
    allow_dark_content: bool | None
    cleaned_query: str


VULNERABLE_EMOTIONS = {
    "sad",
    "lonely",
    "stressed",
    "tired",
    "anxious",
    "bored",
    "heartbroken",
    "exhausted",
    "depressed",
    "overwhelmed",
    "burned_out",
    "drained",
    "frustrated",
    "hopeless",
    "grief",
    "melancholy",
    "worried",
    "afraid",
    "helpless",
    "ashamed",
    "trapped",
    "numb",
    "empty",
}

_USER_STATE_ONLY_EMOTIONS = {"disturbed"}
_SAFE_HOPEFUL_USER_EMOTIONS = VULNERABLE_EMOTIONS | _USER_STATE_ONLY_EMOTIONS

_EMOTION_TERMS = {
    "sad": ("sad", "sadness"),
    "lonely": ("lonely",),
    "stressed": ("stressed", "stress"),
    "tired": ("tired",),
    "anxious": ("anxious", "anxiety"),
    "bored": ("bored",),
    "heartbroken": ("heartbroken", "heart broken", "shattered"),
    "exhausted": ("exhausted",),
    "depressed": ("depressed",),
    "overwhelmed": ("overwhelmed",),
    "burned_out": ("burned out", "burned-out", "burned_out"),
    "drained": ("drained",),
    "frustrated": ("frustrated",),
    "hopeless": ("hopeless",),
    "grief": ("grief", "grieving"),
    "melancholy": ("melancholy",),
    "worried": ("worried",),
    "afraid": ("afraid",),
    "helpless": ("helpless",),
    "ashamed": ("ashamed",),
    "trapped": ("trapped",),
    "numb": ("numb",),
    "empty": ("empty",),
    "disturbed": ("disturbed",),
}

_DESIRED_TONE_TERMS = {
    "cozy": ("cozy",),
    "gentle": ("gentle",),
    "warm": ("warm",),
    "light": ("light",),
    "funny": ("funny", "comedy", "comedies"),
    "hopeful": ("hopeful", "hope"),
    "dark": ("dark",),
    "disturbing": ("disturbing", "disturbingly"),
    "horror": ("horror",),
    "devastating": ("devastating",),
    "raw": ("raw",),
}

_DARK_INTENT_TONES = {"dark", "disturbing", "horror", "devastating"}
_INTENT_MARKER_RE = re.compile(
    r"\b(?:i\s+want|i\s+need|want|need|looking\s+for|give\s+me)\s+",
    re.IGNORECASE,
)
_MOVIE_INTENT_RE = re.compile(
    r"\b(?:something|a\s+movie\s+that|a\s+movie\s+with|a\s+film\s+that|a\s+film\s+with)\b",
    re.IGNORECASE,
)
_MOOD_PHRASE_RE = re.compile(
    r"\bi\s+am\s+in\s+a\s+(?P<text>.+?)\s+mood\b",
    re.IGNORECASE,
)
_USER_STATE_PREFIX_RE = re.compile(
    r"\b(?:after\s+work\s+i\s+feel|i\s+feel|i\s+am\s+feeling|i'm\s+feeling|im\s+feeling|feeling)\b",
    re.IGNORECASE,
)
_USER_BE_RE = re.compile(r"\b(?:i\s+am|i'm|im)\s+(?P<text>.+)", re.IGNORECASE)
_LEADING_INTENSIFIERS = (
    "super",
    "really",
    "very",
    "so",
    "extremely",
    "totally",
    "quite",
)
_USER_STATE_CONTEXT_RE = re.compile(
    r"^(?:(?:from|after|at)\s+[a-z0-9]+|today|tonight|now|right\s+now|"
    r"this\s+(?:morning|afternoon|evening|week|month)|and)(?:\s+|$)"
)


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").strip().split())


def _word_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


def _find_terms(text: str, terms: dict[str, tuple[str, ...]]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for value, aliases in terms.items():
        positions = [
            match.start()
            for alias in aliases
            for match in _word_pattern(alias).finditer(text)
        ]
        if positions:
            found.append((min(positions), value))
    return sorted(found)


def _find_first_term(text: str, terms: dict[str, tuple[str, ...]]) -> str | None:
    matches = _find_terms(text, terms)
    if not matches:
        return None
    return matches[0][1]


def _desired_start(lower_query: str) -> int | None:
    marker = _INTENT_MARKER_RE.search(lower_query)
    if marker:
        return marker.end()

    movie_marker = _MOVIE_INTENT_RE.search(lower_query)
    if movie_marker:
        return movie_marker.start()

    return None


def _emotion_search_span(lower_query: str, desired_start: int | None) -> str:
    if desired_start is None:
        return lower_query
    return lower_query[:desired_start]


def _strip_trailing_intent_marker(prefix: str) -> str:
    stripped = prefix.strip(" ,.;:-")
    stripped = re.sub(
        r"\b(?:i\s+want|i\s+need|want|need|looking\s+for|give\s+me)\s*$",
        "",
        stripped,
    ).strip(" ,.;:-")
    return re.sub(r"\band\s*$", "", stripped).strip(" ,.;:-")


def _context_is_user_state(rest: str) -> bool:
    remaining = rest.strip(" ,.;:-")
    while remaining:
        match = _USER_STATE_CONTEXT_RE.match(remaining)
        if not match:
            return False
        remaining = remaining[match.end() :].strip(" ,.;:-")
    return True


def _extract_adjective_led_emotion(
    lower_query: str, desired_start: int | None
) -> str | None:
    if desired_start is None:
        return None
    prefix = _strip_trailing_intent_marker(lower_query[:desired_start])
    if not prefix:
        return None

    start = 0
    while True:
        matched = False
        for word in _LEADING_INTENSIFIERS:
            match = re.match(rf"{word}\b\s*", prefix[start:])
            if match:
                start += match.end()
                matched = True
                break
        if not matched:
            break

    text = prefix[start:]
    for emotion, aliases in _EMOTION_TERMS.items():
        for alias in aliases:
            match = _word_pattern(alias).match(text)
            if match and _context_is_user_state(text[match.end() :]):
                return emotion
    return None


def _extract_current_emotion(lower_query: str, desired_start: int | None) -> str | None:
    mood_match = _MOOD_PHRASE_RE.search(lower_query)
    if mood_match:
        emotion = _find_first_term(mood_match.group("text"), _EMOTION_TERMS)
        if emotion:
            return emotion

    span_end = desired_start if desired_start is not None else len(lower_query)
    for match in _USER_STATE_PREFIX_RE.finditer(lower_query):
        if match.start() <= span_end:
            emotion = _find_first_term(lower_query[match.end() : span_end], _EMOTION_TERMS)
            if emotion:
                return emotion

    be_match = _USER_BE_RE.search(_emotion_search_span(lower_query, desired_start))
    if be_match:
        return _find_first_term(be_match.group("text"), _EMOTION_TERMS)

    adjective_led_emotion = _extract_adjective_led_emotion(lower_query, desired_start)
    if adjective_led_emotion:
        return adjective_led_emotion

    return None


def _extract_tones(lower_query: str, desired_start: int | None) -> list[str]:
    desired_text = lower_query[desired_start:] if desired_start is not None else lower_query
    return [tone for _, tone in _find_terms(desired_text, _DESIRED_TONE_TERMS)]


def _extract_direction(lower_query: str, tones: list[str]) -> str | None:
    if re.search(r"\b(?:cheer\s+me\s+up|love\s+wins|happily|laugh)\b", lower_query):
        return "cheer_me_up"
    if re.search(r"\b(?:calm|drift\s+off|zone\s+out|bad\s+dreams)\b", lower_query):
        return "calm_me_down"
    if re.search(r"\b(?:comfort|warm\s+blanket|connection)\b", lower_query):
        return "comfort_me"
    if re.search(r"\b(?:funny|absurd|make\s+me\s+laugh)\b", lower_query):
        return "make_me_laugh"
    if re.search(r"\b(?:weep|cry|devastating)\b", lower_query):
        return "help_me_cry"
    if re.search(r"\b(?:hope|overcomes?|survive)\b", lower_query):
        return "give_me_hope"
    if "cozy" in tones or "gentle" in tones:
        return "calm_me_down"
    return None


def _extract_energy_level(lower_query: str, tones: list[str]) -> str | None:
    tone_set = set(tones)
    if tone_set & {"cozy", "light", "warm"}:
        return "light_cozy"
    if "gentle" in tone_set or re.search(r"\b(?:drift\s+off|slow)\b", lower_query):
        return "slow_gentle"
    if tone_set & {"funny"}:
        return "funny_energetic"
    if "hopeful" in tone_set or re.search(r"\b(?:emotional|hope|survive)\b", lower_query):
        return "emotional_but_safe"
    return None


def _cleaned_query(original_query: str, desired_start: int | None) -> str:
    if desired_start is None:
        return original_query
    return original_query[desired_start:].strip(" ,.;:-")


def extract_mood_intent(query: str) -> MoodIntent:
    """Extract user mood and requested movie tone without side effects."""
    normalized = _normalize_query(query)
    lower_query = _ascii(normalized).lower()
    desired_start = _desired_start(lower_query)
    current_emotion = _extract_current_emotion(lower_query, desired_start)
    desired_movie_tone = _extract_tones(lower_query, desired_start)
    has_dark_intent = bool(set(desired_movie_tone) & _DARK_INTENT_TONES)

    if current_emotion in _SAFE_HOPEFUL_USER_EMOTIONS and has_dark_intent:
        safety_sensitivity = "neutral"
        allow_dark_content = True
    elif has_dark_intent:
        safety_sensitivity = "dark_intended"
        allow_dark_content = True
    elif current_emotion in _SAFE_HOPEFUL_USER_EMOTIONS:
        safety_sensitivity = "safe_hopeful"
        allow_dark_content = False
    else:
        safety_sensitivity = "neutral"
        allow_dark_content = None

    return MoodIntent(
        current_emotion=current_emotion,
        emotion_source="free_text" if current_emotion is not None else "none",
        desired_direction=_extract_direction(lower_query, desired_movie_tone),
        desired_movie_tone=desired_movie_tone,
        energy_level=_extract_energy_level(lower_query, desired_movie_tone),
        safety_sensitivity=safety_sensitivity,
        allow_dark_content=allow_dark_content,
        cleaned_query=_cleaned_query(normalized, desired_start),
    )
