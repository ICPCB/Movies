# Phase 8 Plan: Mood-Aware Retrieval Fixes

Based on Phase 7 analysis: 40% mood miss rate vs 8% non-mood.
Root cause: emotional preamble pollutes retrieval signal.

## Interventions

### 8-A: Mood Preprocessor
- **File**: `src/retrieval/mood_preprocessor.py` (new)
- **Test**: `src/tests/test_mood_preprocessor.py` (new)
- **What**: `extract_mood_intent(query) -> MoodIntent` — static vocabulary lookup, no LLM.
  Separates user emotional state from desired movie tone.
  Strips emotional preamble to produce `cleaned_query`.
- **Dependencies**: none
- **Risk**: low — new file, no existing code modified

### 8-B: Mood-Aware Synonym Groups
- **File**: `src/llm/langchain_ollama.py` (modify SYNONYM_GROUPS)
- **Test**: `src/tests/test_langchain_ollama.py` (extend)
- **What**: Add mood-to-retrieval synonym groups:
  - cozy → {cozy, warm, gentle, tender, comforting, soothing, calm, peaceful}
  - uplifting → {uplifting, hopeful, inspiring, heartwarming, feel-good, encouraging, optimistic}
  - funny → {funny, comedy, hilarious, absurd, witty, playful, lighthearted}
  - dark → {dark, disturbing, intense, gritty, devastating, raw, unflinching, bleak}
  - emotional → {emotional, moving, touching, tender, vulnerable, heartbreaking, bittersweet}
  - thrilling → {thrilling, exciting, adventurous, daring, gripping, suspenseful, edge-of-seat}
- **Dependencies**: none (parallel with 8-A)
- **Risk**: low — extends existing SYNONYM_GROUPS dict

### 8-C: Prompt Rewriting
- **File**: `src/llm/prompts.py` (modify EXPAND_SYSTEM, HYDE_SYSTEM)
- **What**: Add instruction to use `cleaned_query` when mood is detected.
  "The user's emotional state (sad, tired, etc.) describes THEM, not the movie.
  Focus on the movie-intent portion of the query."
- **Dependencies**: 8-A (needs MoodIntent), 8-B (needs synonym groups)
- **Risk**: medium — changes LLM behavior for all queries with emotional preamble

### 8-D: Safety Filter
- **File**: `src/retrieval/safety_filter.py` (new)
- **Test**: `src/tests/test_safety_filter.py` (new)
- **What**: Post-rerank filter that demotes dark/horror/disturbing candidates when
  `MoodIntent.safety_sensitivity == "safe_hopeful"`.
  No-op when `dark_intended` or `neutral`.
  Demotion is a stable move-to-bottom reorder, not removal and not score multiplication.
  Matching is based only on genres or keywords; title/overview text alone must not demote.
- **Dependencies**: 8-A (needs MoodIntent)
- **Risk**: medium — can suppress legitimate dark results if safety detection is wrong

### 8-E: Pipeline Integration
- **Files**: `src/pipelines/hybrid.py`, `src/pipelines/advanced.py` (modify)
- **What**: Insert mood_preprocessor at pipeline entry, safety_filter after rerank:
  ```
  raw_query → extract_mood_intent → expand(cleaned_query) → retrieve → rerank → safety_filter → explain
  ```
- **Dependencies**: 8-C, 8-D
- **Risk**: high — modifies core pipeline flow. Regression eval mandatory.

### 8-F: Stress Test Queries
- **Files**: `eval/queries/all.jsonl` (append q61-q65), `eval/scripts/_schemas.py` (extend QUERY_IDS_V2)
- **What**: 5 multi-constraint queries testing edge cases:
  - q61: bright family-comedy surface that slowly becomes a psychological thriller about isolation, with no ghosts, monsters, blood, and jazz music.
  - q62: warm-hug first hour followed by a beautiful emotional gut punch.
  - q63: war movie with no battle scenes, explosions, or guns; only letters home and waiting.
  - q64: visually stunning, painting-like, minimal-dialogue film with haunting orchestral score in a decaying European city.
  - q65: happy/energized user intentionally wants an emotionally devastating drama.
- **Dependencies**: none (parallel)
- **Risk**: low — eval-only

### 8-G: Eval Regression Check
- **What**: Full pipeline eval on 65 queries (q01-q65). Compare metrics before/after.
- **Gate criteria**: zero hit→miss regressions on non-mood queries.
- **Dependencies**: 8-E, 8-F
- **Risk**: this IS the risk check. Human gate.
- **Current status**: stopped after the first 65-query run pending deterministic attribution and human review. Do not claim Phase 8 accuracy success until that gate is resolved.

## Execution Order

```
        8-A ──────┐
                  ├── 8-C ──┐
        8-B ──────┘         ├── 8-E ──── 8-G (human gate)
        8-A ──── 8-D ───────┘         /
        8-F ──────────────────────────┘
```

Parallel tracks: {8-A, 8-B, 8-F} can start immediately.

## Expected Metric Impact

- Mood miss rate: directional target only; must be measured in a gated 8-G rerun.
- Non-mood behavior: no-mood prompt/query path should remain isolated, but ranking impact must be measured before any accuracy claim.
- q53 (bored → absurd comedy): rescued by prompt rewriting stripping "bored"
- q60 (bored → dark/disturbing): partially rescued by synonym expansion on "disturbing"
- q22 (tired → cozy): rescued by safety filter demoting horror + cleaned query focusing on "cozy"

## Files Changed (complete list)

New:
- `src/retrieval/mood_preprocessor.py`
- `src/retrieval/safety_filter.py`
- `src/tests/test_mood_preprocessor.py`
- `src/tests/test_safety_filter.py`

Modified:
- `src/llm/langchain_ollama.py` (SYNONYM_GROUPS)
- `src/llm/prompts.py` (EXPAND_SYSTEM, HYDE_SYSTEM)
- `src/pipelines/hybrid.py` (pipeline flow)
- `src/pipelines/advanced.py` (pipeline flow)
- `eval/queries/all.jsonl` (q61-q65)
- `eval/scripts/_schemas.py` (QUERY_IDS_V2)

No approved Phase 8 ticket authorizes a safety-demotion config constant.
