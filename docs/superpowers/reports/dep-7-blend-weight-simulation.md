# Dep #7 — Blend-Weight Simulation Report

**Date**: 2026-06-07  
**Branch**: `automation/cinematch-accuracy-audit-full`  
**Prerequisite**: Dep #6 strategy design (Strategy 4 recommended)  
**Verdict**: `gate_candidate_pass`  
**Phase 5 status**: BLOCKED  

---

## Summary

The blend-weight simulation tested 40 weight combinations against the existing
Dep #4 pool snapshot. **12 out of 40 weight sets fix q10 `strict_hit_at_5` in
both advanced and hybrid modes without regressing any other query.**

The critical variable is `RERANK_UPSTREAM_WEIGHT`: reducing it from 0.20 to
≤ 0.12 lifts `[REC]` (grade-3 target, tmdb=8329) into the top-5. All viable
sets keep `RERANK_VOTE_COUNT_WEIGHT` at 0.08 (unchanged).

---

## Methodology

The simulation:

1. Reads the Dep #4 `full_set_pool_snapshot.json` (20 queries × 3 modes,
   pool of 50 candidates per query/mode in advanced+hybrid).
2. Joins `baseline_top` entries (which have `rerank_score`) with pool entries
   (which have `vote_count`, `rrf_score`, `semantic_rank`, `bm25_rank`).
3. Recomputes `final_score` for the top-15 candidates using each weight set.
4. Normalizes `vote_prior` and `upstream_prior` over the **full pool** of 50
   candidates (matching production behavior in `src/retrieval/reranker.py`).
5. Uses `strict_hit_at_5` with `grade == 3` (matching `compute_metrics.py`'s
   strict_hit definition).

### Bug fixes during development

Two issues were caught and fixed before the final run:

1. **Wrong strict_hit threshold**: initial code used `grade >= 2` (regular hit)
   instead of `grade == 3` (strict_hit). This caused the simulation to report
   q10 as already fixed under current weights (4 grade-2 targets in top-5).
   Fixed to `grade == 3` to match `compute_metrics.py` line 242.

2. **Wrong normalization scope**: initial code normalized `vote_prior` and
   `upstream_prior` over baseline_top (15 entries) instead of the full pool
   (50 entries). Production code normalizes over the full rerank pool. Fixed
   to use `pool_all` for normalization, matching production behavior.

---

## Current weights (baseline)

| Parameter | Value |
|-----------|-------|
| `RERANK_UPSTREAM_WEIGHT` | 0.20 |
| `RERANK_SOURCE_AGREEMENT_BONUS` | 0.10 |
| `RERANK_VOTE_COUNT_WEIGHT` | 0.08 |

**q10 status with current weights**: `strict_hit_at_5 = False` (consistent
with Dep #4 result).

---

## Viable weight sets (12 of 40)

All 12 viable weight sets fix q10 in both advanced and hybrid modes with zero
regressions:

| # | Upstream | Agreement | Votes | q10 fixed | Regressions |
|---|----------|-----------|-------|-----------|-------------|
| 1 | **0.08** | 0.02 | 0.08 | Yes | 0 |
| 2 | **0.08** | 0.05 | 0.08 | Yes | 0 |
| 3 | **0.08** | 0.08 | 0.08 | Yes | 0 |
| 4 | **0.08** | 0.10 | 0.08 | Yes | 0 |
| 5 | **0.10** | 0.02 | 0.08 | Yes | 0 |
| 6 | **0.10** | 0.05 | 0.08 | Yes | 0 |
| 7 | **0.10** | 0.08 | 0.08 | Yes | 0 |
| 8 | **0.10** | 0.10 | 0.08 | Yes | 0 |
| 9 | **0.12** | 0.02 | 0.08 | Yes | 0 |
| 10 | **0.12** | 0.05 | 0.08 | Yes | 0 |
| 11 | **0.12** | 0.08 | 0.08 | Yes | 0 |
| 12 | **0.12** | 0.10 | 0.08 | Yes | 0 |

### Key observations

1. **`RERANK_UPSTREAM_WEIGHT` ≤ 0.12 is the critical threshold.** All viable
   sets have upstream weight ≤ 0.12. The current value of 0.20 is too high.

2. **`RERANK_SOURCE_AGREEMENT_BONUS` is not critical.** All values (0.02–0.10)
   work when upstream weight is ≤ 0.12.

3. **`RERANK_VOTE_COUNT_WEIGHT` stays at 0.08.** Reducing to 0.05 does not
   produce viable sets (not in the viable list).

4. **The fix is robust.** 12 different weight combinations all work, meaning
   the fix is not fragile or dependent on a single precise value.

---

## Recommended weight set

**Conservative choice**: `upstream=0.12, agreement=0.10, votes=0.08`

This is the **smallest change** from current weights:
- `RERANK_UPSTREAM_WEIGHT`: 0.20 → 0.12 (reduced by 0.08)
- `RERANK_SOURCE_AGREEMENT_BONUS`: 0.10 → 0.10 (unchanged)
- `RERANK_VOTE_COUNT_WEIGHT`: 0.08 → 0.08 (unchanged)

Rationale: minimize disruption by changing only one parameter, and by the
smallest viable amount.

---

## Simulation limitations

1. **Reranking scope**: the simulation reorders only the top-15 baseline
   candidates (those with recorded `rerank_score`). In production, the
   reranker scores all 50 pool candidates. Candidates ranked 16–50 could
   theoretically move into the top-5 with different weights, but the
   simulation cannot test this.

2. **No second-order effects**: changing upstream weights could alter which
   candidates enter the rerank pool in the first place (if upstream scores
   affect pool selection). In the current architecture, pool selection is
   based on `final_score` before reranking, so this is not an issue — the
   pool is selected by RRF score, not by the blend formula.

3. **Simulation vs production**: the recommended weights must be validated
   with a full production regression eval (`rerank_regression_eval.py --stage
   all`) before any `src/*` change is made.

---

## Next step: Phase 5 ticket (not yet created)

If Human approves the Dep #7 findings:

1. Create Phase 5 ticket to change `src/config.py`:
   - `RERANK_UPSTREAM_WEIGHT = 0.12` (from 0.20)
2. Run full regression eval with the new weights in production.
3. Gate criteria: same as Dep #4 (no regression, no hit→miss flips, q10 fixed).
4. If gate passes: merge. If gate fails: revert.

---

## Artifact

| File | Description |
|------|-------------|
| `eval/runs/.../blend_weight_simulation.json` | Full simulation output |
| `eval/scripts/rerank_blend_weight_simulation.py` | Simulation script |
| `eval/tests/test_rerank_blend_weight_simulation.py` | Tests (15 pass) |
