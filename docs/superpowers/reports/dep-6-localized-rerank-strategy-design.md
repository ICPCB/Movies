# Dep #6 — Localized Rerank Strategy Design

**Date**: 2026-06-07  
**Branch**: `automation/cinematch-accuracy-audit-full`  
**Prerequisites**: Dep #4 gate_fail, Dep #5 analysis complete  
**Phase 5 status**: BLOCKED  

---

## Summary

Five strategies were evaluated for fixing q10 without a global reranker swap.
**Strategy 4 (blend-weight adjustment)** is recommended — the q10 failure is
primarily a blend formula issue, not a reranker model issue.

Key discovery: `[REC]` (the q10 grade-3 target) has a baseline rerank_score of
0.0665, which is **higher** than the candidates at ranks 3, 5, and 6 (0.034,
0.022, 0.017). It falls to rank 7 because the final_score formula adds upstream
priors (RRF, vote count, source agreement) that favor other candidates. The
reranker correctly identifies `[REC]` as more relevant than several top-5
entries — the blend formula overrides this signal.

---

## Current blend formula (from `src/retrieval/reranker.py`)

```python
final_score = (
    rerank_score
    + 0.08 * vote_prior        # RERANK_VOTE_COUNT_WEIGHT
    + 0.20 * upstream_prior    # RERANK_UPSTREAM_WEIGHT
    + 0.10 * source_agreement  # RERANK_SOURCE_AGREEMENT_BONUS
)
```

The upstream_prior (0.20) and source_agreement (0.10) together contribute up
to 0.30 to final_score. For candidates with high RRF scores but moderate
rerank scores, this can push them above candidates with higher rerank scores
but lower upstream evidence.

---

## q10 evidence

| Rank | Title | rerank_score | final_score | Grade |
|------|-------|-------------|-------------|-------|
| 0 | Ghost Team One | 0.177 | 0.471 | 2 |
| 1 | Apartment 143 | 0.120 | 0.412 | 2 |
| 2 | Grave Encounters | 0.101 | 0.405 | 2 |
| 3 | Found Footage 3D | 0.034 | 0.369 | 2 |
| 4 | Mr. Jones | 0.147 | 0.363 | 0 |
| 5 | A Haunted House | 0.022 | 0.356 | 0 |
| 6 | Amityville Haunting | 0.017 | 0.350 | 0 |
| **7** | **[REC]** | **0.067** | **0.347** | **3** |

`[REC]`'s rerank_score (0.067) is higher than ranks 3 (0.034), 5 (0.022),
and 6 (0.017). It's pushed to rank 7 by lower upstream priors (rrf=0.058,
semantic_rank=7, bm25_rank=54). The blend formula over-weights upstream
evidence, causing the cross-encoder's quality signal to be overridden.

---

## Strategy comparison

### Strategy 1 — Query-type routing

**Concept**: Classify queries by type and route to different rerankers.

| Dimension | Assessment |
|-----------|------------|
| Feasibility | Medium — requires a query classifier |
| Risk | High — misclassification sends baseline-good queries to alt model |
| Complexity | High — new classification layer + routing logic |
| Eval-testable | No — needs `src/*` changes for routing |
| `src/*` scope | `src/retrieval/reranker.py`, `src/pipelines/*.py`, new classifier |

**Verdict**: Overcomplicated for a single-query fix. The alt model's advantage
is too narrow (1/20 queries) to justify a classification infrastructure.

---

### Strategy 2 — Conditional reranker fallback

**Concept**: Run baseline, detect low-confidence, fall back to alt model.

| Dimension | Assessment |
|-----------|------------|
| Feasibility | Low — no reliable confidence signal found in Dep #4 data |
| Risk | Medium — false positives on baseline-good queries |
| Complexity | Medium — score-spread or entropy threshold logic |
| Eval-testable | Partially — could prototype on existing score data |
| `src/*` scope | `src/retrieval/reranker.py` |

**Evidence check**: In q10, the baseline's top-5 rerank_score spread is
0.034–0.177 (range 0.143). In q01 (baseline succeeds), the spread is
0.018–0.076 (range 0.058). The baseline-failure spread is actually *wider*
than the baseline-success spread — the opposite of what a "low confidence"
signal would need. No reliable confidence boundary exists.

**Verdict**: Not feasible. Score distributions don't support a reliable
fallback trigger.

---

### Strategy 3 — Ensemble/blend reranking

**Concept**: Blend scores from both rerankers.

| Dimension | Assessment |
|-----------|------------|
| Feasibility | Medium — requires loading two models |
| Risk | Medium — any blend weight risks degrading one direction |
| Complexity | Medium — weighted average or RRF on reranker outputs |
| Eval-testable | Yes — could compute from existing Dep #4 score data |
| `src/*` scope | `src/retrieval/reranker.py`, `src/models.py` |

**Evidence check**: The alt model ranks `[REC]` at position 1 but demotes 7
queries' targets. Any blend weight strong enough to pull `[REC]` into top-5
would partially apply the alt model's regressions. The models' score
distributions are too different (baseline: well-separated; alt: compressed)
for a simple blend to work.

**Verdict**: Risky. Likely introduces partial regressions on the 7 degraded
queries without fully fixing q10.

---

### Strategy 4 — Fix q10 at the blend level (RECOMMENDED)

**Concept**: Reduce the upstream prior weights so the cross-encoder's rerank
score has more influence on final ranking.

| Dimension | Assessment |
|-----------|------------|
| Feasibility | **High** — the blend weights are already configurable |
| Risk | **Low** — small weight adjustment, testable with existing eval |
| Complexity | **Low** — change 2-3 constants in `src/config.py` |
| Eval-testable | **Yes** — can be simulated from existing pool snapshot data |
| `src/*` scope | `src/config.py` only (constants, not logic) |

**Evidence**: `[REC]` has a higher rerank_score than 3 candidates ranked above
it. The gap between `[REC]`'s final_score (0.347) and rank 4's (0.363) is only
0.016. Reducing `RERANK_UPSTREAM_WEIGHT` from 0.20 to ~0.12 or
`RERANK_SOURCE_AGREEMENT_BONUS` from 0.10 to ~0.05 would narrow this gap.

**Key advantage**: This keeps the existing reranker model (which succeeds on
13/20 queries) and only adjusts how its scores are combined with upstream
signals. No new model, no routing, no classification.

**Regression risk**: Reducing upstream weight means candidates with strong
upstream evidence but weak rerank scores will drop. This could affect queries
where the blend currently compensates for moderate rerank scores. Must be
validated with a full 20-query regression gate.

---

### Strategy 5 — Single-query reranker override

**Concept**: Keep baseline globally; for found-footage queries, use alt model.

| Dimension | Assessment |
|-----------|------------|
| Feasibility | Medium — trivial routing but brittle detection |
| Risk | Medium — false positives on non-found-footage queries |
| Complexity | Low — simple keyword check + model swap |
| Eval-testable | Partially |
| `src/*` scope | `src/retrieval/reranker.py`, `src/models.py` |

**Verdict**: Fragile. "Found footage" is a narrow genre keyword; query
rephrasing would break the detection. Strategy 4 is more robust.

---

## Strategy comparison table

| Strategy | Feasibility | Risk | Complexity | Eval-testable | `src/*` scope |
|----------|-------------|------|------------|---------------|---------------|
| 1. Query routing | Medium | High | High | No | Multiple files |
| 2. Conditional fallback | Low | Medium | Medium | Partial | reranker.py |
| 3. Ensemble blend | Medium | Medium | Medium | Yes | reranker.py, models.py |
| **4. Blend-weight adj.** | **High** | **Low** | **Low** | **Yes** | **config.py only** |
| 5. Single-query override | Medium | Medium | Low | Partial | reranker.py, models.py |

---

## Recommendation: Strategy 4 — Blend-weight adjustment

### Rationale

1. The q10 failure is a blend formula issue, not a reranker model issue. The
   cross-encoder already scores `[REC]` higher than 3 of the top-5 candidates.
2. The fix is the smallest possible change: adjust 1-2 weight constants in
   `src/config.py`.
3. The existing eval infrastructure can validate the change with a full
   20-query regression gate using the same `rerank_regression_eval.py` script.
4. No new model needs to be loaded, cached, or maintained.
5. The change is fully reversible (revert the constants).

### Proposed weight investigation

Before implementing, an eval-side simulation should test candidate weights:

| Parameter | Current | Candidates to test |
|-----------|---------|-------------------|
| `RERANK_UPSTREAM_WEIGHT` | 0.20 | 0.12, 0.15, 0.10 |
| `RERANK_SOURCE_AGREEMENT_BONUS` | 0.10 | 0.05, 0.08 |
| `RERANK_VOTE_COUNT_WEIGHT` | 0.08 | 0.05, 0.08 (keep) |

The simulation can recompute `final_score` from the pool snapshot's recorded
`rerank_score`, `rrf_score`, `vote_count`, `semantic_rank`, and `bm25_rank`
values. This avoids re-running the reranker models entirely.

---

## Proposed regression gate for Strategy 4

### Pre-implementation eval (Dep #7)

Before any `src/*` change:

1. Write a simulation script that takes the existing `full_set_pool_snapshot.json`
   and recomputes `final_score` for each candidate using candidate weight sets.
2. For each weight set, compute `strict_hit_at_5` and `mrr_at_5` for all 20
   queries × 3 modes.
3. Identify the weight set that:
   - Fixes q10 (strict_hit_at_5 → 1.0 in advanced + hybrid)
   - Does NOT regress any query's strict_hit_at_5 (no hit→miss flips)
   - Minimizes aggregate metric delta
4. If no such weight set exists, report FAIL and recommend Strategy 3 or a
   different approach.

### Post-implementation eval (Phase 5 gate)

If Dep #7 finds a viable weight set:

1. Apply the weights to `src/config.py`.
2. Re-run the full regression eval (`rerank_regression_eval.py --stage all`).
3. Gate criteria: same as Dep #4 (no regression, no hit→miss flips, q10 fixed).

---

## Proposed Phase 5 ticket outline (NOT created — for reference)

**Goal**: Apply validated blend weights from Dep #7 to production config.

**Files to change** (exact):
- `src/config.py` — update `RERANK_UPSTREAM_WEIGHT`, `RERANK_SOURCE_AGREEMENT_BONUS`,
  and/or `RERANK_VOTE_COUNT_WEIGHT` to values validated by Dep #7.

**Files to read** (not change):
- `src/retrieval/reranker.py` — verify blend formula unchanged
- `eval/scripts/rerank_regression_eval.py` — run post-implementation gate
- All Dep #5, #6, #7 artifacts

**Acceptance criteria**:
1. `src/config.py` updated with exact validated weights from Dep #7.
2. Full regression eval passes (gate_pass).
3. No other `src/*` files changed.
4. q10 strict_hit_at_5 = 1.0 in hybrid mode.
5. No per-query hit→miss flips.
6. Baseline self-check passes.
7. Basic-mode invariant holds.

**Rollback plan**: Revert `src/config.py` to previous weight values.

---

## Open questions for Human decision

1. **Should we proceed with Dep #7 (blend-weight simulation)?** This is an
   eval-only ticket that reads existing artifacts and writes a simulation
   report. No `src/*` changes until a viable weight set is confirmed.

2. **If Dep #7 finds a viable weight set, should we create the Phase 5
   ticket?** The Phase 5 ticket would change only `src/config.py` constants.

3. **Should q05 be investigated separately?** q05's issue is different from
   q10 — the DECOMP-01 analysis showed q05's target is at RRF rank 66, well
   outside any reasonable pool. A blend-weight adjustment won't fix q05.
   q05 likely needs upstream work (query expansion or recall improvement).

---

## Conclusion

Phase 5 remains **BLOCKED**. The recommended next step is Dep #7: blend-weight
simulation — an eval-only ticket that tests whether adjusting
`RERANK_UPSTREAM_WEIGHT` and `RERANK_SOURCE_AGREEMENT_BONUS` can fix q10
without regressing any other query. If Dep #7 succeeds, a Phase 5 ticket can
be authored for the minimal `src/config.py` change.
