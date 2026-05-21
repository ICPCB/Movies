"""Query normalization and deterministic movie-domain expansion."""
from __future__ import annotations

import re
import unicodedata


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STEM_SUFFIXES = ("ing", "ers", "ies", "ied", "ed", "es", "s")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _stem(token: str) -> str:
    for suffix in _STEM_SUFFIXES:
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            if suffix in {"ies", "ied"}:
                return token[: -len(suffix)] + "y"
            return token[: -len(suffix)]
    return token


def _tokens(text: str) -> set[str]:
    return {_stem(t) for t in _TOKEN_RE.findall(_ascii(text).lower())}


def _has_any(tokens: set[str], choices: set[str]) -> bool:
    stems = {_stem(t) for t in choices}
    return bool(tokens & stems)


def normalize_query(query: str) -> str:
    """Normalize an English movie search query.

    CineMatch indexes English TMDB metadata, so retrieval is optimized
    for English input even when the movie's original language is not
    English. Multilingual query translation is intentionally out of
    scope for the core system.
    """
    return " ".join(str(query or "").strip().split())


def expand_retrieval_query(query: str) -> str:
    """Add compact movie-domain metadata terms for first-pass recall.

    This is deliberately deterministic and conservative. The original
    query still goes to the cross-encoder reranker, so these extra terms
    only help candidate generation find movies whose TMDB metadata uses
    different wording than the user.
    """
    normalized = normalize_query(query)
    tokens = _tokens(normalized)
    extras: list[str] = []

    if (
        _has_any(tokens, {"poor", "unemployed", "working"})
        and _has_any(tokens, {"rich", "wealthy", "glamorous"})
        and _has_any(tokens, {"family", "household", "house", "home"})
    ):
        extras.append(
            "unemployed wealthy family working class class differences "
            "social satire con artist"
        )

    if (
        _has_any(tokens, {"hitman", "assassin", "killer", "cleaner"})
        and _has_any(tokens, {"girl", "child", "kid", "daughter", "young"})
        and _has_any(tokens, {"protect", "guard", "defend", "guardian"})
    ):
        extras.append(
            "assassin cleaner guardian child protection crime thriller"
        )

    if (
        _has_any(tokens, {"robot", "android", "machine"})
        and _has_any(tokens, {"trash", "waste", "earth", "planet"})
    ):
        extras.append("garbage compacting robot abandoned earth environmental science fiction")

    if (
        _has_any(tokens, {"dream", "subconscious", "mind"})
        and _has_any(tokens, {"heist", "steal", "thief", "secret"})
    ):
        extras.append("layered dreams mind theft corporate espionage psychological thriller")

    if (
        _has_any(tokens, {"astronaut", "space", "mars"})
        and _has_any(tokens, {"stranded", "survive", "survival", "marooned"})
    ):
        extras.append("astronaut accidentally left behind mars survival rescue mission science fiction")

    if (
        _has_any(tokens, {"boxer", "boxing", "fighter"})
        and _has_any(tokens, {"train", "training", "steps", "meat", "locker", "champion"})
    ):
        extras.append(
            "underdog boxing training sports drama championship fight"
        )

    if (
        _has_any(tokens, {"age", "ages", "aging", "backwards", "reverse"})
        and _has_any(tokens, {"man", "century", "twentieth", "life", "old"})
    ):
        extras.append(
            "reverse aging lifelong romance historical twentieth century unusual birth"
        )

    if (
        _has_any(tokens, {"palindrom", "backward", "backwards", "reverse", "forward"})
        and _has_any(tokens, {"timeline", "time", "temporal", "chrono"})
    ):
        # Matches queries about non-linear time narratives (Memento, Tenet, etc.)
        extras.append(
            "nonlinear timeline reverse chronology time paradox backwards temporal "
            "alternate timeline loop palindromic parallel timeline time manipulation"
        )

    if not extras:
        return normalized

    return " ".join([normalized, *extras])
