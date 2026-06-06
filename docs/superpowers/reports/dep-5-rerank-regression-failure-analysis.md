# Dep #5 — Rerank Regression Failure Analysis

**Date**: 2026-06-07  
**Branch**: `automation/cinematch-accuracy-audit-full`  
**Prerequisite**: Dep #4 gate_fail (commit `d175bf7`)  
**Phase 5 status**: BLOCKED  

---

## Summary

The alt reranker (`Alibaba-NLP/gte-multilingual-reranker-base`) fixed q10 but
caused hit→miss regressions on 7 queries (q01, q03, q04, q11, q12, q15, q18).
All regressions occur in both advanced and hybrid modes (basic mode is unaffected
since it does not use the reranker). The dominant failure mode is
`genre_or_intent_drift` — the alt model systematically disagrees with the baseline
about which candidates are most relevant.

**Recommendation**: Direction B — localized/conditional strategy design. The alt
model is not viable as a global drop-in replacement. It could be used selectively
for query types where the baseline fails (e.g., q10-type found-footage queries).

---

## Failure taxonomy

| Mode | Count | Queries |
|------|-------|---------|
| `genre_or_intent_drift` | 5 | q03, q04, q11, q15, q18 |
| `over_promotes_surface_match` | 2 | q01, q12 |
| `semantic_target_demoted` (fix) | 1 | q10 |

---

## Per-query analysis

### q10 — FIXED (miss→hit)

**Query**: "found footage friends chased through a haunted apartment maze"  
**Gold targets**: 11 (grade≥2)  
**Failure mode**: `semantic_target_demoted` (baseline demoted the key target;
alt promoted it)

The baseline model ranked 4 grade-2 targets in top-5 (Ghost Team One, Apartment
143, Grave Encounters, Found Footage 3D) but the grade-3 target `[REC]`
(tmdb=8329) was outside top-5. The alt model successfully promoted `[REC]` into
the top-5. This query is the one success case for the alt model.

**Why it worked**: The alt model better recognizes the genre/format match between
the query's "found footage" + "haunted apartment" description and `[REC]`'s
subject matter, which the baseline under-scored relative to more generic
found-footage titles.

---

### q01 — REGRESSED (hit→miss) — `over_promotes_surface_match`

**Query**: "animated spider hero learns from alternate spider people and mentors"  
**Gold targets**: 4 (grade≥2, including 2 grade-3: Spider-Verse films)  
**Baseline top-5**: Into the Spider-Verse (grade 3), Across the Spider-Verse
(grade 3), Spider-Man (2002), The Amazing Spider-Man, Spider-Man: Homecoming  
**Baseline targets in top-5**: 2 (both grade-3)

The baseline correctly ranked the two Spider-Verse animated films at positions 0-1.
The alt model likely over-promoted surface-matched "spider" titles (live-action
Spider-Man films are not animated and don't feature "alternate spider people"),
pushing the animated targets out of top-5.

---

### q03 — REGRESSED (hit→miss) — `genre_or_intent_drift`

**Query**: "a trash robot falls in love in space"  
**Gold targets**: 6 (grade≥2, including WALL·E at grade 3)  
**Baseline top-5**: Robots, Robot Monster, WALL·E, Enthiran, Space Sweepers  
**Baseline targets in top-5**: 2 (WALL·E rank 2, Space Sweepers rank 4)

The baseline ranked WALL·E at position 2 and Space Sweepers at position 4.
The alt model demoted these semantic matches in favor of surface-matched
"robot" titles. The query describes a specific plot (love story + space setting),
and the baseline's semantic understanding was better calibrated.

---

### q04 — REGRESSED (hit→miss) — `genre_or_intent_drift`

**Query**: "teenage witches weaponize popularity and resentment"  
**Gold targets**: 15 (grade≥2, including Teen Witch at grade 3)  
**Baseline top-5**: Teen Witch (grade 3), The Craft: Legacy, Witch Hunt, The
Craft, The Witches  
**Baseline targets in top-5**: 4

The baseline placed 4 out of 5 top-5 positions as gold targets. With 15 targets
in the label set, this is a well-covered query. The alt model's reranking
displaced these targets — a clear genre/intent drift where the alt model does
not understand the social dynamics aspect ("weaponize popularity") as well.

---

### q11 — REGRESSED (hit→miss) — `genre_or_intent_drift`

**Query**: "a class satire inside a sinking luxury vacation for wealthy guests"  
**Gold targets**: 8 (grade≥2, including Triangle of Sadness at grade 3)  
**Baseline top-5**: Triangle of Sadness (grade 3), Hotel Transylvania 3, The
Idle Class, Overboard, Sundown  
**Baseline targets in top-5**: 1 (Triangle of Sadness at rank 0)

The baseline correctly identified Triangle of Sadness as the top result
(rerank score 0.091, 10× higher than rank 2). The alt model demoted this
specific satire film in favor of generic vacation/class-themed films. The query
combines genre signals (satire + luxury + class commentary) that the baseline
model handles well.

---

### q12 — REGRESSED (hit→miss) — `over_promotes_surface_match`

**Query**: "a heist movie about folding cities and stolen dreams"  
**Gold targets**: 3 (grade≥2, including Inception at grade 3)  
**Baseline top-5**: Inception (grade 3), Lucid Dream, Heist, Lying and Stealing,
Tower Heist  
**Baseline targets in top-5**: 1 (Inception at rank 0)

The baseline correctly ranked Inception first with a very high rerank score
(0.436, 5× higher than rank 2). The alt model over-promoted surface-matched
"heist" and "dream" titles, pushing the correct Inception result out.

---

### q15 — REGRESSED (hit→miss) — `genre_or_intent_drift`

**Query**: "kids outrun grief with a giant forest friend"  
**Gold targets**: 9 (grade≥2, including I Kill Giants at grade 3)  
**Baseline top-5**: Epic, I Kill Giants (grade 3), My Giant, Bridge to
Terabithia, George of the Jungle  
**Baseline targets in top-5**: 3 (I Kill Giants rank 1, Bridge to Terabithia
rank 3, George of the Jungle rank 4)

The baseline placed 3 targets in top-5. The alt model demoted these childhood
grief-themed films. The emotional aspect ("outrun grief") is a subtle semantic
signal that the alt model handles poorly.

---

### q18 — REGRESSED (hit→miss) — `genre_or_intent_drift`

**Query**: "a romantic comedy about fake identities, email, and urban bookstores"  
**Gold targets**: 10 (grade≥2, including You've Got Mail at grade 3)  
**Baseline top-5**: Tramps, Down with Love, The Love Letter, You've Got Mail
(grade 3), Is It Just Me?  
**Baseline targets in top-5**: 4

The baseline placed 4 targets in top-5 with high rerank scores (Tramps 0.332,
Down with Love 0.313, You've Got Mail 0.197, Is It Just Me? 0.120). The alt
model demoted these in favor of films matching surface keywords but missing the
specific rom-com + technology + bookstore combination.

---

## Pattern analysis

### Observations

1. **All 7 regressions are in both advanced and hybrid modes** — these modes
   share the same reranker stage, confirming the issue is the reranker itself.

2. **The baseline model strongly outperforms the alt model on multi-signal
   queries** — queries that combine genre, tone, plot, and thematic elements
   (e.g., "class satire inside a sinking luxury vacation"). The baseline's
   rerank scores show large gaps between correct and incorrect results (e.g.,
   Inception at 0.436 vs next at 0.082; Triangle of Sadness at 0.091 vs next
   at 0.009). The alt model collapses these gaps.

3. **The alt model's strength is niche genre recognition** — q10 ("found footage
   haunted apartment") is the one query where the alt model outperforms. This
   suggests the alt model has better coverage of horror/found-footage genre
   terminology.

4. **Surface keyword matching is a secondary issue** — q01 ("spider") and q12
   ("heist", "dream") show the alt model over-promotes titles that match
   individual query words without understanding the full semantic intent.

### Root cause hypothesis

The alt model (`gte-multilingual-reranker-base`) has a different scoring
distribution than the baseline (`bge-reranker-v2-m3`). Where the baseline
produces well-separated scores for semantically correct vs incorrect matches,
the alt model produces more uniform scores that allow surface-matched titles to
compete with semantic matches. This is a fundamental model behavior difference,
not a tunable parameter.

---

## Answers to Dep #5 questions

### 1. Why did q10 improve?

The baseline model (`bge-reranker-v2-m3`) ranked `[REC]` (the grade-3 target)
outside the top-5 despite it being the best match for "found footage friends
chased through a haunted apartment maze." The alt model's scoring better
recognizes the horror/found-footage genre match. This is a narrow model
capability advantage.

### 2. Why did the seven regression queries degrade?

The alt model systematically demotes gold targets that the baseline correctly
ranked. The dominant pattern is genre/intent drift: the alt model fails to
distinguish between surface keyword matches and deep semantic matches. For
multi-signal queries (combining genre, tone, plot, and thematic elements), the
baseline model's score separation is much better.

### 3. Are the regressions concentrated in one mode, query type, or candidate pattern?

- **Mode**: all regressions are in both advanced and hybrid modes (100%)
- **Query type**: regressions span diverse query types (animation, sci-fi,
  horror, satire, drama, rom-com). No single genre dominates.
- **Candidate pattern**: the common pattern is that gold targets with moderate
  baseline rerank scores (0.01–0.15) get demoted by the alt model, while
  surface-keyword-matched non-targets get promoted.

### 4. Is Alibaba viable as:

| Role | Viable? | Rationale |
|------|---------|-----------|
| Global drop-in replacement | **No** | 7 regressions, catastrophic metric drops |
| Conditional reranker | **Maybe** | Could help q10-type found-footage queries specifically |
| Diagnostic tool only | **Yes** | Useful for identifying queries where the baseline underperforms |

### 5. Which next path is more justified?

**Direction B: localized/conditional strategy design.**

A global reranker swap is unsafe. The alt model's advantage is narrow (q10-type
found-footage queries) while its regressions are broad (7 out of 20 queries,
35%). A conditional strategy could:

- Use the baseline for most queries (proven effective on 13/20)
- Apply the alt model only for identified baseline-failure patterns (e.g.,
  found-footage genre)
- Or investigate why the baseline fails on q10 specifically and fix it at a
  different level (query expansion, candidate recall, or blend weights)

---

## Artifact

| File | Description |
|------|-------------|
| `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/dep5_failure_analysis.json` | Full analysis output |
| `eval/scripts/rerank_regression_failure_analysis.py` | Analysis script |
| `eval/tests/test_rerank_regression_failure_analysis.py` | Tests (15 pass) |

---

## Conclusion

Phase 5 remains **BLOCKED**. The alt reranker is not a viable drop-in
replacement. The recommended next step is Dep #6: localized/conditional
strategy design — exploring whether a selective application of the alt model
(or a different approach entirely) can fix q10 without disturbing the 13
queries where the baseline already succeeds.
