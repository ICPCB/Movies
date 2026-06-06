# Dep #6 — Localized Rerank Strategy Design

## Goal

Design a localized/conditional reranking strategy that preserves the baseline
reranker (`BAAI/bge-reranker-v2-m3`) for the 13 queries where it succeeds and
addresses the q10 failure case without a global model swap.

This is a **design/analysis ticket only**. No `src/*` edits, no production
behavior changes, no model swaps, no new labels. The output is a design report
with proposed regression gates for any future implementation.

---

## Current state

- Branch: `automation/cinematch-accuracy-audit-full`
- HEAD: `f214c4f`
- Dep #4: gate_fail (alt reranker catastrophic regression)
- Dep #5: complete (failure analysis — Direction B recommended)
- Phase 5: BLOCKED (blocked_by_dep_4)

### Key Dep #5 findings (context for this ticket)

1. The alt reranker (`gte-multilingual-reranker-base`) fixed q10 but
   regressed 7/20 queries (35%).
2. The baseline (`bge-reranker-v2-m3`) succeeds on 13/20 queries.
3. The q10 failure is the baseline under-scoring `[REC]` (tmdb=8329, grade 3)
   relative to other found-footage candidates.
4. Regressions are in both advanced+hybrid modes (reranker-dependent).
5. Dominant failure mode: `genre_or_intent_drift` — the alt model collapses
   the baseline's well-separated scores.
6. The alt model's advantage is narrow: better horror/found-footage genre
   recognition.

---

## Files to read (do not change)

```
AGENTS.md
CLAUDE.md
.agents/state.json
eval/scripts/rerank_regression_failure_analysis.py
eval/scripts/rerank_regression_eval.py
eval/scripts/rerank_model_comparison.py
eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/dep5_failure_analysis.json
eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json
eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/full_set_pool_snapshot.json
eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl
eval/queries/v1.jsonl
src/config.py                                    (read blend weights only)
src/retrieval/reranker.py                         (read only — current rerank logic)
src/pipelines/basic.py                            (read only)
src/pipelines/advanced.py                         (read only)
src/pipelines/hybrid.py                           (read only)
docs/superpowers/reports/dep-4-rerank-regression-gate.md
docs/superpowers/reports/dep-5-rerank-regression-failure-analysis.md
docs/superpowers/reports/rerank-02-model-comparison.md
docs/superpowers/reports/decomp-01-q05-q10.md
```

---

## Files allowed to change/create

```
docs/superpowers/reports/dep-6-localized-rerank-strategy-design.md    (CREATE)
.agents/ledger.md                                                      (UPDATE)
.agents/state.json                                                     (UPDATE)
```

---

## Files forbidden to change

```
src/*
eval/scripts/*                                    (read only)
eval/tests/*                                      (read only)
eval/queries/*                                    (read only)
eval/runs/*                                       (read only)
AGENTS.md
CLAUDE.md
.remember/*
.agents/README.md
```

---

## Required analysis

The design report must explore at least the following strategies:

### Strategy 1 — Query-type routing

Could we classify queries by type (e.g., found-footage, genre-specific,
multi-signal) and route them to different rerankers?

Evaluate:
- How would query classification work? (keyword? embedding similarity? manual?)
- What is the routing boundary? (which queries go to which model?)
- What is the regression risk? (misclassification sends a baseline-good query
  to the alt model)
- Is this testable without `src/*` changes? (eval-side prototype possible?)

### Strategy 2 — Conditional reranker fallback

Could we run the baseline reranker, detect low-confidence results, and fall
back to the alt reranker for those specific queries?

Evaluate:
- What confidence signal would trigger fallback? (score spread? max score?
  score entropy?)
- Does the Dep #4 data support identifying a reliable signal?
- What is the false-positive rate? (baseline-good queries triggering fallback)

### Strategy 3 — Ensemble/blend reranking

Could we blend scores from both rerankers (e.g., weighted average, RRF on
reranker outputs)?

Evaluate:
- Would blending preserve the baseline's advantage on 13 queries?
- Would blending rescue q10?
- What blend weights would work? (can be estimated from existing score data)

### Strategy 4 — Fix q10 at a different level

Could q10 be fixed without changing the reranker at all?

Evaluate:
- Query expansion (adding "horror", "found footage", "apartment" signals)
- Candidate recall improvement (expanding semantic search pool)
- Blend weight adjustment for found-footage type queries
- Are any of these testable with existing eval infrastructure?

### Strategy 5 — Single-query reranker override

The simplest strategy: keep the baseline globally, but for queries detected as
found-footage-type, override the reranker with the alt model.

Evaluate:
- How narrow is the "found-footage" detection? (false positives?)
- Is this effectively Strategy 1 with a trivial router?
- What is the minimal `src/*` change this would require?

---

## Required output format

The design report must include:

1. **Strategy comparison table**: feasibility, risk, implementation complexity,
   eval-testability, `src/*` change scope
2. **Recommended strategy** with rationale
3. **Proposed regression gate**: what eval would need to pass before
   implementing the recommended strategy
4. **Proposed Phase 5 ticket outline**: exact files to change, acceptance
   criteria, rollback plan — but NOT the Phase 5 ticket itself
5. **Open questions** for Human decision

---

## Acceptance criteria

1. Design report covers all 5 strategies.
2. Each strategy has a feasibility/risk assessment grounded in Dep #4/5 evidence.
3. Report recommends one strategy with clear rationale.
4. Report includes a proposed regression gate design.
5. Report includes a Phase 5 ticket outline (but does NOT create the ticket).
6. No `src/*` changes.
7. No production behavior changes.
8. No new labels generated.
9. Phase 5 remains BLOCKED.

---

## Stop conditions

Stop and report if:
- Any `src/*` file would need to be read beyond the allowed list
- Any model inference or network call would be needed
- Any label generation would be needed
- The analysis reveals a dependency on data not available in existing artifacts

---

## Dependencies

- Dep #4: gate_fail (commit `d175bf7`)
- Dep #5: complete (commit `f214c4f`)

## Risk level

LOW — design/analysis only. No code changes, no model inference, no label
generation.

## Reviewer

Claude Code Pro (self-review) + Human (strategy decision).
