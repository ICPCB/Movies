# Phase 8-K Mood Regression Investigation

Verdict: NEEDS_REVIEW. Phase 8 is not complete.

## Scope

- Baseline run: `eval/runs/2026-06-07-combined-nogit`
- Fresh run: `eval/runs/2026-06-08-phase8j-gated-nogit`
- Primary qids: q59 first, then q49 and q53
- Context only: q61, q65, q29 overlap
- No full eval was run. No `src/*`, `eval/scripts/*`, ranking, retrieval, model, prompt, schema, or label provenance behavior was changed.

## Artifact Notes

- Candidate artifacts preserve per-mode rank, semantic score, BM25 score, RRF score, rerank score, and final score where available.
- Run artifacts do not persist the actual mood object used at runtime. Mood fields below come from the immutable query tags in `eval/queries/all.jsonl` and deterministic current `extract_mood_intent(...)` output.
- Silver labels have no explicit `label_provenance` field. Provenance comparison uses baseline `gold_labels.jsonl` where present.
- q29 appears in both the literal non-mood range and explicit mood list. It remains preserved as a hit in all modes in the fresh run.

## q59 - Lonely / Human Connection

Query:
`I feel lonely tonight and want a movie that wraps around me like a warm blanket and reminds me that human connection is still possible even when everything feels empty`

Tagged mood:
- current_emotion: `lonely`
- desired_emotional_direction: `comfort_me`
- energy_level: `slow_gentle`
- intensity: `medium_emotional`
- safety_sensitivity: `safe_hopeful`

Current extracted mood:
- current_emotion: `lonely`
- desired_emotional_direction: `comfort_me`
- desired_movie_tone: `warm`
- energy_level: `light_cozy`
- intensity: not emitted by current extractor
- safety_sensitivity: `safe_hopeful`
- cleaned_query: `a movie that wraps around me like a warm blanket and reminds me that human connection is still possible even when everything feels empty`

### q59 Advanced

Previous result vs fresh 8-G result:
- Baseline hit@5: `1`
- Fresh hit@5: `0`

Expected target labels/movies:
- `Someone, Somewhere` (`tmdb_id=583268`) is the reliable target: silver grade `2`, human-reviewed gold grade `2`, provenance `human_reviewed_ai_assisted`.
- `Disconnect` (`tmdb_id=127517`) was a baseline silver hit, but human-reviewed gold changed it to grade `1`. Treat it as silver artifact context, not a reliable positive target.

Target retrieval and score movement:

| Movie | Baseline rank | Fresh rank | Baseline final | Fresh final | Baseline rerank | Fresh rerank | Label/provenance |
|---|---:|---:|---:|---:|---:|---:|---|
| Disconnect | 1 | not retrieved | 0.328392 | n/a | 0.141021 | n/a | silver 2, human-reviewed gold 1 |
| Someone, Somewhere | 2 | not retrieved | 0.249814 | n/a | 0.071548 | n/a | silver 2, human-reviewed gold 2 |

Fresh top five were all silver grade `1`: `Emma`, `Y Tu Mama Tambien`, `Human`, `On Board`, `The Last Song`.

Failure class:
- Primary: retrieval recall issue caused by candidate drift after mood-aware query handling.
- Secondary: query cleaning issue is plausible because the cleaned query removes the explicit leading loneliness phrase while keeping connection/emptiness language.
- Label/provenance issue exists for `Disconnect` only; it should not be counted as a reliable target after human review.

### q59 Hybrid

Previous result vs fresh 8-G result:
- Baseline hit@5: `1`
- Fresh hit@5: `0`

Target retrieval and score movement:

| Movie | Baseline rank | Fresh rank | Baseline final | Fresh final | Baseline rerank | Fresh rerank | Label/provenance |
|---|---:|---:|---:|---:|---:|---:|---|
| Disconnect | 1 | not retrieved | 0.324094 | n/a | 0.141021 | n/a | silver 2, human-reviewed gold 1 |
| Someone, Somewhere | 3 | not retrieved | 0.185721 | n/a | 0.071548 | n/a | silver 2, human-reviewed gold 2 |

Fresh top five were all silver grade `1`: `The Mountain Between Us`, `Midnight Sun` (2014), `Think Like a Man`, `Waking Life`, `The Tree of Life`.

Failure class:
- Primary: retrieval recall issue. The reliable target `Someone, Somewhere` vanished from the fresh candidate union for q59.
- Secondary: query cleaning/mood extraction interaction. The extracted energy changed from tag `slow_gentle` to runtime `light_cozy`, and the cleaned query drops the explicit `lonely` phrase.
- Not primarily rerank/final scoring: target rows are absent in the fresh run, so rerank/final score cannot recover them.

Recommended next ticket:
- Open a fix-design ticket for q59 only. It should inspect whether cleaned mood queries should retain the current-emotion term or add a bounded mood-context prefix for lonely/comfort queries before retrieval. Do not combine this with q49/q53 fixes.

## q49 - Stressed / Light Funny Work Comedy

Query:
`super stressed from work need something light and funny to just zone out`

Tagged mood:
- current_emotion: `stressed`
- desired_emotional_direction: `calm_me_down`
- energy_level: `funny_energetic`
- intensity: `very_light`
- safety_sensitivity: `safe_hopeful`

Current extracted mood:
- current_emotion: `stressed`
- desired_emotional_direction: `calm_me_down`
- desired_movie_tone: `light`, `funny`
- energy_level: `light_cozy`
- intensity: not emitted by current extractor
- safety_sensitivity: `safe_hopeful`
- cleaned_query: `something light and funny to just zone out`

### q49 Advanced

Previous result vs fresh 8-G result:
- Baseline hit@5: `1`
- Fresh hit@5: `0`

Expected target label/movie:
- `Office Space` (`tmdb_id=1542`) is the target: baseline silver grade `2`, fresh silver grade `2`, human-reviewed gold grade `3`, provenance `human_reviewed_ai_assisted`.

Target retrieval and score movement:

| Movie | Baseline advanced rank | Fresh advanced rank | Baseline final | Fresh final | Baseline rerank | Fresh rerank | Label/provenance |
|---|---:|---:|---:|---:|---:|---:|---|
| Office Space | 3 | not in advanced candidates | 0.181622 | n/a | 0.022750 | n/a | silver 2 -> 2; human-reviewed gold 3 |

Fresh candidate union still contains `Office Space` through basic mode, but the fresh advanced path no longer retrieves it. Fresh advanced top five were all silver grade `1`.

Failure class:
- Primary: retrieval recall issue in advanced mode.
- Secondary: query cleaning issue is plausible because the cleaned query keeps `light and funny` but removes explicit work/stress context that made `Office Space` highly suitable.
- Not a label/provenance issue: the target label remains positive in fresh silver and stronger in human-reviewed gold.
- Not primarily rerank/final scoring: there is no fresh advanced score for `Office Space`.

Recommended next ticket:
- Open a q49 advanced retrieval fix-design ticket after q59. It should test whether preserving workplace/stress context in the cleaned query or mood-aware expansion restores `Office Space` without changing no-mood behavior.

## q53 - Bored / Absurd Comedy

Query:
`bored stiff give me the most absurd comedy`

Tagged mood:
- current_emotion: `bored`
- desired_emotional_direction: `make_me_laugh`
- energy_level: `funny_energetic`
- intensity: `very_light`
- safety_sensitivity: `neutral`

Current extracted mood:
- current_emotion: `null`
- desired_emotional_direction: `make_me_laugh`
- desired_movie_tone: `funny`
- energy_level: `funny_energetic`
- intensity: not emitted by current extractor
- safety_sensitivity: `neutral`
- cleaned_query: `the most absurd comedy`

Because `current_emotion` is `null`, current advanced/hybrid code does not switch retrieval input to the cleaned query for q53.

### q53 Hybrid

Previous result vs fresh 8-G result:
- Baseline hit@5: `1`
- Fresh hit@5: `0`

Expected target labels/movies:
- `Absolutely Anything` (`tmdb_id=86828`): baseline silver grade `3`, carried provenance `silver_llm_pregrade`.
- `Pee-wee's Big Adventure` (`tmdb_id=5070`): baseline silver grade `2`, carried provenance `silver_llm_pregrade`.

Target retrieval and score movement:

| Movie | Baseline rank | Fresh rank | Baseline final | Fresh final | Baseline rerank | Fresh rerank | Label/provenance |
|---|---:|---:|---:|---:|---:|---:|---|
| Pee-wee's Big Adventure | 2 | 4 | 0.172523 | 0.153102 | 0.009176 | 0.009176 | silver 2 -> 1; carried provenance silver_llm_pregrade |
| Absolutely Anything | 5 | not retrieved | 0.163029 | n/a | 0.004004 | n/a | silver 3; carried provenance silver_llm_pregrade |

Fresh top five include `Pee-wee's Big Adventure` at rank 4, but the fresh silver pregrade changed it from grade `2` to grade `1`. `Absolutely Anything` vanished from the fresh candidate union.

Failure class:
- Mixed retrieval recall issue and silver pregrade/eval artifact issue.
- Retrieval recall issue: `Absolutely Anything` disappeared.
- Silver pregrade/eval artifact issue: `Pee-wee's Big Adventure` remained in top five but fresh silver changed from grade `2` to grade `1`.
- Not a direct mood extraction/cleaning issue under current code because `current_emotion` is not detected for q53, so q53 is not mood-cleaned at retrieval time.

Recommended next ticket:
- Do not start with a production fix. First open a label-stability or q53 artifact-triage ticket to decide whether `Pee-wee's Big Adventure` should be frozen as a positive label and whether `Absolutely Anything` recall loss is material.

## Context: q61, q65, q29

q61:
- Query has `tags.mood = null`.
- Current extractor finds no current emotion, but detects funny/energetic tone.
- Fresh 8-G hit@5 is `0` in basic, advanced, and hybrid.
- Failure class: stress-test retrieval/label coverage issue, not a Phase 8 mood regression blocker.

q65:
- Human decision remains Option A: keep inherited mismatched tag `current_emotion = bored` although the query says happy/energized.
- Current extractor returns `current_emotion = null` and cleaned query `a movie that will absolutely destroy me emotionally like completely wreck me in the best way possible`.
- Fresh 8-G hit@5 is basic `1`, advanced `0`, hybrid `0`.
- Failure class: inherited ticket/data issue. Do not add positive emotion schema support in this ticket.

q29:
- q29 overlaps the literal non-mood range and the explicit mood list.
- Fresh 8-G remains a hit in all modes.
- Reporting should preserve both literal and q29-excluded non-mood checks.

## failure class Summary

| QID | Mode | Class |
|---|---|---|
| q59 | advanced | retrieval recall issue; plausible query cleaning issue; silver artifact issue for Disconnect only |
| q59 | hybrid | retrieval recall issue; plausible query cleaning issue; silver artifact issue for Disconnect only |
| q49 | advanced | retrieval recall issue; plausible query cleaning issue; not label/provenance issue |
| q53 | hybrid | mixed retrieval recall issue plus silver pregrade/eval artifact issue |
| q61 | context | stress-test retrieval/label coverage issue |
| q65 | context | inherited 8-F ticket/data issue |

## recommended next ticket

1. Create a q59-only fix-design ticket first. The likely fix area is preserving or reintroducing loneliness/comfort context during mood-aware retrieval while protecting non-mood behavior.
2. Create a separate q49 advanced retrieval ticket if q59 design is accepted.
3. Create a q53 label/artifact triage ticket before any production change.
4. Keep q61/q65 as stress-test/data-ticket context unless the human explicitly opens a stress-query improvement ticket.

Stop here for review. No fixes were implemented.
