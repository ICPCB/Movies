"""LangChain + Ollama LLM layer with grounded explanations and fallback.

Two important contracts live in this file:

1. `expand_query` keeps its old JSON shape `{"query": "..."}` so callers
   don't change.

2. Explanations now use an evidence-grounded contract. The LLM must
   return `{"evidence": "<verbatim phrase from supplied metadata>",
   "match_strength": "strong|moderate|weak", "explanation": "..."}`.
   `_accept_grounded_item` rejects any reply whose `evidence` string is
   not literally present in the metadata we showed the model — that is
   how mimicry gets caught. Rejected items fall back to
   `_fallback_explanation`, which never invents reasons; it summarises
   which metadata fields are available and how strongly the user's
   query keywords (with simple plural/synonym awareness) overlap them.
"""
from __future__ import annotations
import json
import re
import concurrent.futures
from src.config import LLM_MODEL, LLM_TIMEOUT_SECONDS
from src.llm.prompts import (
    EXPAND_SYSTEM, EXPAND_HUMAN,
    HYDE_SYSTEM, HYDE_HUMAN,
    EXPLAIN_SYSTEM, EXPLAIN_HUMAN,
    EXPLAIN_BATCH_SYSTEM, EXPLAIN_BATCH_HUMAN,
)

try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import SystemMessage, HumanMessage
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    print("[llm] langchain-ollama not found — LLM features disabled")

_llm: "ChatOllama | None" = None
# Single worker is enough: Ollama serialises requests anyway, and we only use
# the executor to enforce a timeout without leaking a stuck thread per call.
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


def _get_llm():
    global _llm
    if not _AVAILABLE:
        return None
    if _llm is None:
        _llm = ChatOllama(model=LLM_MODEL, temperature=0.2)
    return _llm


def _invoke_with_timeout(messages, timeout: float = LLM_TIMEOUT_SECONDS):
    """Call the LLM, raising TimeoutError if it stalls past `timeout` seconds."""
    llm = _get_llm()
    if llm is None:
        raise RuntimeError("llm-unavailable")
    future = _executor.submit(llm.invoke, messages)
    return future.result(timeout=timeout)


def _extract_json_object(text: str) -> dict | None:
    """Best-effort JSON object extraction from a model reply."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    for pattern in (r'\{.*\}', r'\{[^}]+\}'):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
    return None


def _year_of(movie: dict) -> str:
    y = movie.get("year")
    if y:
        try:
            return str(int(float(y)))
        except (TypeError, ValueError):
            pass
    rd = str(movie.get("release_date", "") or "")
    return rd[:4] if len(rd) >= 4 and rd[:4].isdigit() else ""


# ---------- token / synonym normalization ----------

_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "the", "about", "of", "to", "and", "or", "is", "are", "was",
    "were", "be", "been", "being", "i", "we", "you", "they", "he", "she",
    "it", "in", "on", "at", "for", "with", "by", "as", "from", "that",
    "this", "those", "these", "movie", "film", "story", "feature",
    "trying", "someone", "people", "where", "which", "who", "whom",
    "what", "how", "why", "when", "any", "some", "all",
}

# Each concept maps to a set of related surface forms. If a query token
# normalizes into one of these sets, we treat *any* member as a real
# metadata match — so we never say "no explicit mention of dreams" when
# the overview contains "nightmare" or "lucid".
SYNONYM_GROUPS: dict[str, set[str]] = {
    "dream": {"dream", "nightmare", "lucid", "subconscious"},
    "reality": {"reality", "alternate", "waking", "simulation"},
    "mind": {"mind", "surreal", "hallucination", "illusion", "thought"},
    "heist": {"heist", "thief", "steal", "stolen", "espionage", "robbery"},
    "space": {"space", "mars", "astronaut", "planet", "cosmos", "galaxy"},
    "survival": {"survive", "survival", "stranded", "trapped", "marooned"},
    "cozy": {
        "cozy", "warm", "gentle", "tender", "comforting", "soothing",
        "calm", "peaceful",
    },
    "uplifting": {
        "uplifting", "hopeful", "inspiring", "heartwarming", "feel-good",
        "encouraging", "optimistic",
    },
    "funny": {
        "funny", "comedy", "hilarious", "absurd", "witty", "playful",
        "lighthearted",
    },
    "dark": {
        "dark", "disturbing", "intense", "gritty", "devastating", "raw",
        "unflinching", "bleak",
    },
    "emotional": {
        "emotional", "moving", "touching", "tender", "vulnerable",
        "heartbreaking", "bittersweet",
    },
    "thrilling": {
        "thrilling", "exciting", "adventurous", "daring", "gripping",
        "suspenseful", "edge-of-seat",
    },
}

_PLURAL_SUFFIXES = ("ies", "es", "s")


def _normalize_token(tok: str) -> str:
    """Strip a simple plural suffix when the stem is long enough to be a real word."""
    for suf in _PLURAL_SUFFIXES:
        if len(tok) > len(suf) + 2 and tok.endswith(suf):
            stem = tok[: -len(suf)]
            # 'ies' → 'y' isn't perfect but BGE-style retrieval rarely cares;
            # keep the simple stem so cross-form overlap is preserved.
            return stem
    return tok


def _tokens(text: str) -> set[str]:
    """Lowercased, stop-word-stripped, plural-normalized content tokens."""
    return {
        _normalize_token(t)
        for t in _QUERY_TOKEN_RE.findall(text.lower())
        if t not in _STOPWORDS and len(t) > 2
    }


def _expand_with_synonyms(toks: set[str]) -> set[str]:
    """For every query token, also include every synonym group it belongs to."""
    out = set(toks)
    for group in SYNONYM_GROUPS.values():
        if toks & group:
            out |= group
    return out


# ---------- evidence verification ----------

_VALID_STRENGTHS = {"strong", "moderate", "weak"}


def _metadata_haystack(movie: dict) -> str:
    """Lowercased blob of every field the LLM was allowed to cite."""
    parts = [
        str(movie.get("title", "") or ""),
        str(movie.get("genres", "") or ""),
        str(movie.get("overview", "") or ""),
        str(movie.get("keywords", "") or ""),
        str(movie.get("tagline", "") or ""),
    ]
    return " ".join(parts).lower()


def _accept_grounded_item(item, query: str, movie: dict) -> str | None:
    """Validate one structured explanation. Return the visible string or None."""
    if not isinstance(item, dict):
        return None
    explanation = str(item.get("explanation", "") or "").strip()
    evidence = str(item.get("evidence", "") or "").strip()
    strength = str(item.get("match_strength", "") or "").strip().lower()
    if not explanation or len(explanation.split()) < 5:
        return None
    if strength not in _VALID_STRENGTHS:
        return None
    if evidence:
        # The model claimed a verbatim phrase — confirm it really exists
        # in the supplied metadata. Anything else is fabrication.
        if evidence.lower() not in _metadata_haystack(movie):
            return None
    else:
        # Empty evidence is only legitimate when the model marked the
        # match as weak. Strong/moderate without evidence = fabrication.
        if strength != "weak":
            return None
    # Reject explanations that simply echo the query.
    if explanation.lower().strip(".!? ").startswith(
        query.lower().strip(".!? ")[:40]
    ):
        return None
    return explanation


# ---------- deterministic fallback ----------

def _fallback_explanation(query: str, movie: dict) -> str:
    """Deterministic, non-hallucinating fallback.

    We never claim plot details that aren't in the metadata. We label
    *how* the query relates to the metadata we have — and treat
    plurals/synonyms (dream/dreams/nightmare/lucid, …) as real overlap
    so we don't tell the user "no explicit mention of dreams" when the
    overview says "may be dreams".
    """
    title = str(movie.get("title", "") or "").strip() or "This movie"
    genres = str(movie.get("genres", "") or "").strip()
    overview = str(movie.get("overview", "") or "").strip()
    keywords = str(movie.get("keywords", "") or "").strip()
    tagline = str(movie.get("tagline", "") or "").strip()

    concepts = _expand_with_synonyms(_tokens(query))
    overview_hits = concepts & _tokens(overview)
    keyword_hits = concepts & _tokens(keywords)
    tagline_hits = concepts & _tokens(tagline)
    genre_hits = concepts & _tokens(genres)

    pieces: list[str] = []
    plot_hits = overview_hits | keyword_hits | tagline_hits

    if not overview:
        pieces.append(
            f"{title}: weak match — overview is missing, so this is based "
            f"on limited metadata."
        )
    elif plot_hits:
        shared = ", ".join(sorted(plot_hits)[:5])
        pieces.append(
            f"{title}: overview, keywords, or tagline reference terms "
            f"related to your query ({shared})."
        )
    elif genre_hits:
        shared = ", ".join(sorted(genre_hits)[:3])
        pieces.append(
            f"{title}: weak match — only the genre ({shared}) overlaps "
            f"your query; the overview does not describe these themes."
        )
    else:
        pieces.append(
            f"{title}: weak match — the overview, keywords, and tagline "
            f"do not reference your query terms."
        )

    if genres and not genre_hits and not plot_hits:
        pieces.append(f"Genres: {genres}.")
    return " ".join(pieces).strip()


# ---------- LLM-facing public API ----------

def expand_query(query: str) -> str:
    """Return LLM-expanded query, or original query on any failure."""
    try:
        resp = _invoke_with_timeout([
            SystemMessage(content=EXPAND_SYSTEM),
            HumanMessage(content=EXPAND_HUMAN.format(query=query)),
        ])
    except concurrent.futures.TimeoutError:
        print("[llm] expand_query timed out")
        return query
    except Exception as e:
        print(f"[llm] expand_query error: {e}")
        return query
    obj = _extract_json_object(resp.content)
    if obj and isinstance(obj.get("query"), str) and obj["query"].strip():
        return obj["query"]
    return query


def hyde_generate(query: str) -> str:
    """Generate a HyDE-style synthetic TMDB-flavoured overview for `query`.

    Returns "" on timeout, outage, or unparseable reply. Callers should
    treat "" as "fall back to the regular query for semantic search".
    The reply is plain prose (no JSON), so we sanity-check length only —
    if the model returned an empty string, a single token, or something
    suspiciously long (>800 chars) we reject and let the caller fall back.
    """
    try:
        resp = _invoke_with_timeout([
            SystemMessage(content=HYDE_SYSTEM),
            HumanMessage(content=HYDE_HUMAN.format(query=query)),
        ])
    except concurrent.futures.TimeoutError:
        print("[llm] hyde_generate timed out")
        return ""
    except Exception as e:
        print(f"[llm] hyde_generate error: {e}")
        return ""

    text = str(resp.content or "").strip().strip('"').strip()
    if not text or len(text) < 30 or len(text) > 800:
        return ""
    return text


def explain_movie(query: str, movie: dict) -> str:
    """Single-movie explanation. Returns deterministic fallback on any issue."""
    try:
        resp = _invoke_with_timeout([
            SystemMessage(content=EXPLAIN_SYSTEM),
            HumanMessage(content=EXPLAIN_HUMAN.format(
                query=query,
                title=movie.get("title", ""),
                year=_year_of(movie),
                genres=movie.get("genres", ""),
                tagline=str(movie.get("tagline", ""))[:200],
                overview=str(movie.get("overview", ""))[:500],
                keywords=str(movie.get("keywords", ""))[:300],
            )),
        ])
    except concurrent.futures.TimeoutError:
        print(f"[llm] explain_movie timed out for '{movie.get('title', '')}'")
        return _fallback_explanation(query, movie)
    except Exception as e:
        print(f"[llm] explain_movie error for '{movie.get('title', '')}': {e}")
        return _fallback_explanation(query, movie)

    obj = _extract_json_object(resp.content)
    accepted = _accept_grounded_item(obj, query, movie) if obj else None
    return accepted if accepted is not None else _fallback_explanation(query, movie)


def explain_movies_batch(query: str, movies: list[dict]) -> list[str]:
    """One LLM call to explain a small list of movies, with evidence checking.

    Returns a list of explanations the same length as `movies`. Any
    movie the LLM fails to cover with a grounded reply (parse error,
    fabricated evidence, length mismatch, timeout, or unavailable LLM)
    gets the deterministic fallback so callers can always attach a
    reason.
    """
    if not movies:
        return []

    n = len(movies)
    if not _AVAILABLE:
        return [_fallback_explanation(query, m) for m in movies]

    lines = []
    for i, m in enumerate(movies, 1):
        year = _year_of(m)
        overview = str(m.get("overview", "") or "")[:360]
        keywords = str(m.get("keywords", "") or "")[:200]
        tagline = str(m.get("tagline", "") or "")[:200]
        block = (
            f"{i}. {m.get('title', '')} ({year})\n"
            f"   Genres: {m.get('genres', '')}\n"
            f"   Overview: {overview}"
        )
        if tagline:
            block += f"\n   Tagline: {tagline}"
        if keywords:
            block += f"\n   Keywords: {keywords}"
        lines.append(block)
    movies_block = "\n\n".join(lines)

    try:
        resp = _invoke_with_timeout([
            SystemMessage(content=EXPLAIN_BATCH_SYSTEM),
            HumanMessage(content=EXPLAIN_BATCH_HUMAN.format(
                query=query, movies_block=movies_block,
            )),
        ])
    except concurrent.futures.TimeoutError:
        print(f"[llm] explain_movies_batch timed out for {n} movies")
        return [_fallback_explanation(query, m) for m in movies]
    except Exception as e:
        print(f"[llm] explain_movies_batch error: {e}")
        return [_fallback_explanation(query, m) for m in movies]

    obj = _extract_json_object(resp.content)
    raw = obj.get("explanations") if obj else None
    if not isinstance(raw, list):
        return [_fallback_explanation(query, m) for m in movies]

    out: list[str] = []
    for i, m in enumerate(movies):
        item = raw[i] if i < len(raw) else None
        accepted = _accept_grounded_item(item, query, m) if item is not None else None
        out.append(accepted if accepted is not None else _fallback_explanation(query, m))
    return out
