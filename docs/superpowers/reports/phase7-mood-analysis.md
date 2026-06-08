# Phase 7 Mood-Intent Analysis Report

Run: `eval/runs/2026-06-07-combined-nogit`
Labels: `merged_gold_over_silver` (14 gold / 630 silver / 644 total)
Queries: 60 (q01-q60), 10 mood-tagged

## 1. Mood vs Non-Mood Miss Rates

| Metric | Mood (n=10) | Non-Mood (n=50) |
|--------|-------------|-----------------|
| any-mode miss rate | 40% (4/10) | 8% (4/50) |
| missed qids | q22, q49, q53, q60 | q03, q08, q12, q13 |

Mood queries miss at **5x** the rate of non-mood queries.

## 2. Per-Emotion Breakdown

| Emotion | n | Misses | Miss Rate |
|---------|---|--------|-----------|
| sad | 3 | 0 | 0% |
| bored | 2 | 2 | 100% |
| stressed | 1 | 1 | 100% |
| tired | 1 | 1 | 100% |
| anxious | 1 | 0 | 0% |
| heartbroken | 1 | 0 | 0% |
| lonely | 1 | 0 | 0% |

`sad` succeeds because it often produces queries whose emotional preamble overlaps with movie tone ("feeling sad" → sad movies). `bored`, `stressed`, and `tired` fail because the user's state is opposite to the movie they want (bored → wants excitement; stressed → wants calm; tired → wants cozy).

## 3. Per-Direction Breakdown

| Desired Direction | n | Misses |
|-------------------|---|--------|
| calm_me_down | 2 | 2 |
| make_me_laugh | 1 | 1 |
| help_me_cry | 3 | 1 |
| cheer_me_up | 2 | 0 |
| comfort_me | 1 | 0 |
| give_me_hope | 1 | 0 |

`calm_me_down` and `make_me_laugh` are the hardest directions — they require the pipeline to infer what soothes or amuses the user, not just match keywords.

## 4. Safety Sensitivity

| Safety | n | Misses |
|--------|---|--------|
| safe_hopeful | 7 | 2 (q22, q49) |
| dark_intended | 2 | 1 (q60) |
| neutral | 1 | 1 (q53) |

`safe_hopeful` misses occur when the pipeline returns dark/tense content to a vulnerable user (q22: `A Quiet Place` for a tired user wanting cozy).

## 5. User-State vs Movie-Tone Problem

The core issue: **emotional preamble pollutes retrieval**.

When a user says "I'm exhausted and want something cozy", the pipeline currently sends the full string to:
1. `expand_query()` — LLM sees "exhausted" and may expand toward exhaustion-themed films
2. `semantic_search()` — embedding of "exhausted" pulls movies about fatigue, not comfort
3. `bm25_search()` — keyword "exhausted" matches war/drama overviews

The user's state ("exhausted") describes **them**, not the movie they want. The desired movie tone ("cozy") is the actual retrieval target.

### Evidence from missed queries

- **q22** ("I'm tired... cozy gentle film without bad dreams"): returns `A Quiet Place`, `Dark Circles`, `Rogue River` — horror/thriller titles that match "tired" and "dark" tokens but violate the explicit safety cue.
- **q49** ("super stressed from work... light and funny"): `Office Space` (grade 3) is in top-5 but strict fails because the pipeline also pulls stress-themed dramas.
- **q53** ("I'm bored... most absurd comedy"): advanced mode returns `Requiem for a Dream`, `Inception` — semantic drift from "bored" toward existential content.
- **q60** ("I'm bored and want something dark and disturbing"): hybrid returns `Dark Skies`, `The Dark Knight` — title-token matches on "dark" rather than psychological disturbance.

## 6. Pipeline Gap Analysis

### Current flow (hybrid.py)
```
raw_query → normalize_query → expand_query (LLM) → semantic_search + bm25_search → rrf_fusion → rerank → explain
```

### Missing components

1. **Mood preprocessor**: No code separates user emotional state from movie-intent tokens. `src/retrieval/mood_preprocessor.py` does not exist.

2. **Prompt awareness**: `EXPAND_SYSTEM` and `HYDE_SYSTEM` in `src/llm/prompts.py` have no instruction to strip emotional preamble. The LLM expands "I'm tired and want something cozy" as if the entire string describes a movie.

3. **Safety filter**: No post-rerank filter demotes dark/horror candidates when the user is in a vulnerable state and hasn't requested dark content. `src/retrieval/safety_filter.py` does not exist.

4. **Synonym groups**: `SYNONYM_GROUPS` in `langchain_ollama.py` has 6 groups (dream, reality, mind, time, space, identity) — none for emotional/mood vocabulary. No expansion from "cozy" → {warm, gentle, feel-good, comforting}.

## 7. Gold Metrics (60 queries)

| Mode | sh@5 | mrr@5 |
|------|------|-------|
| basic | 0.667 | 0.796 |
| advanced | 0.650 | 0.834 |
| hybrid | 0.550 | 0.787 |

`queries_excluded_null = 0` across all modes (Fury null fixed).

## 8. Conclusion

Mood queries expose a systematic gap: the pipeline treats user emotional state as retrieval signal. Four interventions are needed:
1. Mood preprocessor to split user-state from movie-tone
2. Prompt rewriting to use cleaned query
3. Safety filter for vulnerable users
4. Mood-aware synonym expansion

These are specified in `docs/superpowers/plans/phase8-mood-retrieval-fixes.md`.
