# Phase 7-B Mood Query Triage

Ticket: 7-B
Run: `eval/runs/2026-06-07-combined-nogit`
Artifacts inspected:
- `analysis/error_report/per_query_mode.jsonl`
- `analysis/error_report/summary.json`
- `silver_labels.jsonl`
- `eval/queries/all.jsonl`

Important scope note: all classifications below are HYPOTHESES based on top-5 error-report evidence only. They are not final label decisions until human review validates the movie/query fit.

## Summary

`summary.json` reports these mood query misses:
- Any-mode mood misses: `q21`, `q22`, `q53`, `q60`
- All-mode mood misses: `q22`
- Hybrid-only mood misses: `q21`, `q60`
- Strict-only mood issues among inspected mood queries: `q29`, `q49`, `q55`, `q59`

Classification key:
- `LABEL`: the top-5 contains plausible matches, but silver grades are too low or null.
- `RETRIEVAL`: the top-5 results are wrong for the mood intent.
- `BOTH`: evidence suggests both wrong retrieval and questionable labels.
- `OK`: no current failure requiring action from top-5 evidence.

## Triage Table

| qid | Classification | Summary miss status | Evidence summary | Top-5 snapshot |
| --- | --- | --- | --- | --- |
| q21 | BOTH | Hybrid miss; strict miss in basic, advanced, hybrid | Basic and advanced find grade-2 rom-com-ish items, but no grade-3. Hybrid has no relevant hit. Some hybrid results look potentially reviewable for breakup-safe comfort despite grade 1. | Basic: `Sad Movie` g2, `Breakup Buddies` g2. Advanced: `Love Is All` g2, `Ti ricordi di me?` g2. Hybrid: `Happiness for Beginners` g1, `More the Merrier` g1, `Playing It Cool` g1, `The Good Guy` g1, `Happy Christmas` g1. |
| q22 | RETRIEVAL | Basic, advanced, and hybrid miss; strict miss in all modes | No null grades. Returned titles do not satisfy "cozy gentle film ... without bad dreams", and advanced/hybrid rank `A Quiet Place` first. This is a clear safe-hopeful retrieval failure. | Basic: `Get Well Soon` g1, `Rogue River` g0, `Swiss Army Man` g1. Advanced: `A Quiet Place` g0, `Dark Circles` g1. Hybrid: `A Quiet Place` g0, `A Quiet Place Part II` g1, `Kaboom` g1. |
| q29 | OK | No miss; strict miss only in basic | Advanced and hybrid pass strict with grade-3 hopeful survival/odds titles. Basic has only grade-2 relevant results, but at least one relevant hit appears. No label action is required from this top-5 evidence unless strict calibration is revisited. | Basic: `A Good Person` g2, `50/50` g2. Advanced: `The Rescue` g3, `The Boy Who Harnessed the Wind` g2, `The Impossible` g2. Hybrid: `Soul Surfer` g3, `The Rescue` g3. |
| q49 | LABEL | No miss; strict miss in all modes | Each mode has a grade-2 plausible stress/unwind comedy match but no grade-3. This looks more like silver strictness or query-era grading friction than a recall failure. | Basic: `Office Space` g2 at rank 5. Advanced: `Office Space` g2 at rank 3. Hybrid: `Hector and the Search for Happiness` g2 at rank 4. |
| q50 | OK | No miss; no strict miss | All modes pass strict. `Happy-Go-Lucky` is grade 3 in all modes or top-2. | Basic: `Happy-Go-Lucky` g3 rank 1. Advanced: `Happy-Go-Lucky` g3 rank 1. Hybrid: `Happy-Go-Lucky` g3 rank 2. |
| q53 | RETRIEVAL | Advanced miss; strict miss in advanced | Basic and hybrid find absurd comedy results, but advanced returns mostly non-comedy or weakly related titles. No null labels. | Basic: `Ernest Scared Stupid` g3, `Gaston Lagaffe` g2. Advanced: `Requiem for a Dream` g1, `Inception` g1, `Identity Thief` g1, `In Time` g1, `Waking Life` g1. Hybrid: `Pee-wee's Big Adventure` g2, `Absolutely Anything` g3. |
| q54 | OK | No miss; no strict miss | All modes pass strict with emotionally heavy grief/love-loss results. | Basic: `If Anything Happens I Love You` g3, `Anatomy of a Love Seen` g2. Advanced: `Pieces of a Woman` g3 plus multiple `Eleanor Rigby` g2 entries. Hybrid: `If Anything Happens I Love You` g3. |
| q55 | LABEL | No any-mode miss; strict miss in basic; advanced/hybrid strict status is null because of one null grade | The requested dark-intended war/suffering intent is broadly retrieved, but `Fury` has a null silver grade due to a parse error. Basic contains only grade-2 war titles and no grade-3. | Basic: `Left Behind: World at War` g2, `Hamburger Hill` g2, `Casualties of War` g2. Advanced: `Blizzard of Souls` g2, `Fury` null, `Black Hawk Down` g2. Hybrid: `Fury` null rank 1, `Hamburger Hill` g2, `Black Hawk Down` g2. |
| q59 | LABEL | No miss; strict miss in all modes | Each mode has grade-2 human-connection or comfort candidates but no grade-3. This is probably silver calibration for comfort/warmth, not a hard retrieval miss. | Basic: `Christmas Connection` g2. Advanced: `Disconnect` g2, `Someone, Somewhere` g2. Hybrid: `Disconnect` g2, `Someone, Somewhere` g2. |
| q60 | RETRIEVAL | Hybrid miss; strict miss in advanced and hybrid | Basic satisfies dark/disturbing intent, but hybrid drifts into title-word matches like "Dark" and unrelated results. Advanced has a grade-2 hit but no perfect match. | Basic: `Evil Dead` g2, `Deep Dark` g2, `August Underground` g3. Advanced: `Edge of Darkness` g2, `Dr. Jekyll and Mr. Hyde` g2. Hybrid: `Dark Skies` g1, `The Dark Knight` g1, `Mirrors` g1, `Transformers: Rise of the Beasts` g0, `Dark City` g1. |

## Per-Query Notes

### q21

Mood tags: `sad`, `cheer_me_up`, `light_cozy`, `very_light`, `safe_hopeful`.

Hypothesis: BOTH. Hybrid fails outright with all grade-1 results. Basic and advanced find only grade-2 candidates, which may indicate label strictness around gentle breakup rom-com comfort. Human review should decide whether `Happiness for Beginners` or any grade-2 rom-com candidates should be upgraded, but the hybrid result set still looks weaker than the basic/advanced sets.

Potential label-review pairs:
- `(q21, 881209)` `Happiness for Beginners`, currently grade 1
- `(q21, 18422)` `Sad Movie`, currently grade 2
- `(q21, 284298)` `Breakup Buddies`, currently grade 2
- `(q21, 5497)` `Love Is All`, currently grade 2

### q22

Mood tags: `tired`, `calm_me_down`, `slow_gentle`, `very_light`, `safe_hopeful`.

Hypothesis: RETRIEVAL. All modes miss and there are no null labels. The retrieved sets conflict with the explicit "without bad dreams" safety cue: `A Quiet Place`, `Dark Circles`, `Rogue River`, and `A Quiet Place Part II` are especially poor top-5 evidence for a cozy safe query.

Potential label-review pairs: none from top-5 evidence.

### q29

Mood tags: `anxious`, `give_me_hope`, `emotional_but_safe`, `medium_emotional`, `safe_hopeful`.

Hypothesis: OK. The query is not in any normal miss list. Advanced and hybrid pass strict through high-grade survival/hope results such as `The Rescue` and `Soul Surfer`. Basic has no grade-3 item, but it still has relevant grade-2 results.

Potential label-review pairs: none required.

### q49

Mood tags: `stressed`, `calm_me_down`, `funny_energetic`, `very_light`, `safe_hopeful`.

Hypothesis: LABEL. All modes avoid normal miss status, but all fail strict because the best plausible matches are grade 2. `Office Space` is an obvious work-stress comedy match even though it is outside the query tag's `2000-2015` era bucket, so this may be a label/query-tag strictness issue rather than retrieval failure.

Potential label-review pairs:
- `(q49, 1542)` `Office Space`, currently grade 2
- `(q49, 254375)` `Hector and the Search for Happiness`, currently grade 2

### q50

Mood tags: `sad`, `cheer_me_up`, `light_cozy`, `very_light`, `safe_hopeful`.

Hypothesis: OK. This mandatory smoke-test mood query passes normal and strict checks in all modes. `Happy-Go-Lucky` is grade 3 and ranks first in basic/advanced and second in hybrid.

Potential label-review pairs: none required.

### q53

Mood tags: `bored`, `make_me_laugh`, `funny_energetic`, `very_light`, `neutral`.

Hypothesis: RETRIEVAL. Advanced misses with top-5 results that are not good fits for "most absurd comedy"; `Requiem for a Dream`, `Inception`, `In Time`, and `Waking Life` point to advanced-mode semantic drift. Basic and hybrid prove relevant absurd-comedy candidates are reachable in this corpus.

Potential label-review pairs: none from top-5 evidence.

### q54

Mood tags: `heartbroken`, `help_me_cry`, `slow_gentle`, `heavy_but_requested`, `safe_hopeful`.

Hypothesis: OK. All modes pass strict with strong grief/love-loss evidence. `If Anything Happens I Love You` and `Pieces of a Woman` provide grade-3 anchors, and several `Disappearance of Eleanor Rigby` results are grade 2.

Potential label-review pairs: none required.

### q55

Mood tags: `sad`, `help_me_cry`, `slow_gentle`, `heavy_but_requested`, `dark_intended`.

Hypothesis: LABEL. The top-5 contains war/suffering titles, but strict evidence is compromised by a null silver label. `silver_labels.jsonl` confirms `(q55, 228150)` `Fury` has `grade: null`, `confidence: low`, and `reason: "json_parse_error: Expecting ',' delimiter"`. This is the specific parse-error null flagged by the ticket.

Potential label-review pairs:
- `(q55, 228150)` `Fury`, currently null due to parse error
- `(q55, 10652)` `Hamburger Hill`, currently grade 2
- `(q55, 10142)` `Casualties of War`, currently grade 2
- `(q55, 567566)` `Blizzard of Souls`, currently grade 2
- `(q55, 855)` `Black Hawk Down`, currently grade 2

### q59

Mood tags: `lonely`, `comfort_me`, `slow_gentle`, `medium_emotional`, `safe_hopeful`.

Hypothesis: LABEL. All modes avoid normal miss status, but strict fails everywhere because the best human-connection candidates are grade 2. `Someone, Somewhere` and `Christmas Connection` look plausible for comfort/human connection; whether they deserve grade 3 needs human judgment.

Potential label-review pairs:
- `(q59, 583268)` `Someone, Somewhere`, currently grade 2
- `(q59, 474994)` `Christmas Connection`, currently grade 2
- `(q59, 127517)` `Disconnect`, currently grade 2

### q60

Mood tags: `bored`, `help_me_cry`, `emotional_but_safe`, `heavy_but_requested`, `dark_intended`.

Hypothesis: RETRIEVAL. Basic succeeds with a grade-3 disturbing-horror anchor, but hybrid misses completely and appears to overuse dark/title tokens: `Dark Skies`, `The Dark Knight`, `Transformers: Rise of the Beasts`, and `Dark City` are weak evidence for the requested psychologically disturbing moral-breakdown intent. Advanced is partial but not strict.

Potential label-review pairs: none from top-5 evidence.

## q55 Null Status

Confirmed. In `eval/runs/2026-06-07-combined-nogit/silver_labels.jsonl`, `(q55, 228150)` `Fury` has:

```json
{"qid": "q55", "tmdb_id": 228150, "grade": null, "confidence": "low", "reason": "json_parse_error: Expecting ',' delimiter", "model": "llama3.2", "ts": "2026-06-07T13:56:13Z"}
```

This null appears in top-5 evidence for:
- q55 advanced rank 2: `Fury` null
- q55 hybrid rank 1: `Fury` null

## Recommended Label Fixes For Human Review

High priority:
- `(q55, 228150)` `Fury`: replace null parse-error label with a human-reviewed grade.

Strict-calibration candidates:
- `(q49, 1542)` `Office Space`: currently grade 2 for a work-stress unwind comedy query.
- `(q59, 583268)` `Someone, Somewhere`: currently grade 2 for lonely/comfort/human-connection query.
- `(q59, 474994)` `Christmas Connection`: currently grade 2 for lonely/comfort/warm-blanket query.
- `(q21, 881209)` `Happiness for Beginners`: currently grade 1 in hybrid for breakup-safe hopeful comfort.
- `(q21, 18422)` `Sad Movie`: currently grade 2 in basic for breakup rom-com comfort.
- `(q21, 284298)` `Breakup Buddies`: currently grade 2 in basic for breakup rom-com comfort.

Retrieval-only failures to carry into Phase 7-C/8 planning:
- `q22`: safe/cozy tired query retrieves horror, thriller, or unsettling titles.
- `q53`: advanced mode misses broad absurd-comedy intent.
- `q60`: hybrid mode appears title-token driven around "dark" rather than psychologically disturbing mood fit.

## Next

HUMAN GATE -> 7-C

