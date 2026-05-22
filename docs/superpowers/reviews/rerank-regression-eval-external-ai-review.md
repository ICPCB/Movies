# External AI Review — RERANK-REGRESSION-EVAL Plan

- Reviewer: Codex CLI (`codex-cli 0.133.0`, OpenAI-compatible), advisory only.
- Date: 2026-05-23
- Subject: `docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md`
- Packet: `docs/superpowers/reviews/rerank-regression-eval-review-packet.md`
- Raw transcript: `codex-regression-review-raw.txt` (untracked working file).

**This review is advisory evidence only.** It is NOT approval to unblock
Phase 5, merge, push, delete data, change `src/*`, change ranking/retrieval
behavior, or accept any product-level decision. The reviewer was run in a
read-only task and modified no files.

---

## Verdict: CONCERNS

The reviewer found the plan broadly sound — harness design technically
justified, execution-deferral correct, Phase 5 correctly kept BLOCKED — but
raised four specific, actionable improvements. All four were verified against
the source and **applied** to the plan.

## Reviewer answers (summary)

- **Q1 — two-stage harness soundness:** broadly sound; the replay requirement
  follows from the missing full rerank pools; capture + re-score matches
  `src/retrieval/reranker.py:rerank`. Flagged a depth mismatch (see Concern 1).
- **Q2 — gate criteria mechanical-ness:** mostly mechanical; flagged
  null/excluded-metric handling and an under-specified q10-fix mode (Concerns
  2, 3).
- **Q3 — execution deferral correctness:** correct — a model-backed GPU
  replay/re-score gating a product decision has no safe autonomous execution
  path under the stated rules.
- **Q4 — Phase 5 stays blocked:** yes — the plan consistently states a
  `gate_pass` only makes a Phase 5 plan eligible to be authored.

## Concerns and resolutions

| # | Concern (Codex) | Resolution |
|---|---|---|
| 1 | §4 Stage 2 said "top-5 lists" but §5 gates `strict_hit_at_10`; artifact must retain ≥ top-10 (ideally top-15) to match `compute_metrics.py`. | **Applied.** §4 Stage 2 step 2 now requires ranking the full pool and retaining ≥ **top-15** records per `(qid, mode)` per model. |
| 2 | §5 did not say how to treat `None` / null-excluded metric values from `compute_metrics.py`. | **Applied.** §5 `gate_inconclusive` now explicitly covers a `None`/null-excluded headline metric or a changed `queries_excluded_null`; an undefined metric is never scored pass/fail. |
| 3 | §5 q10-fix condition said "deterministic headline arm" without naming the exact mode. | **Applied.** §5 `gate_pass` item 3 now requires q10 to reach `strict_hit_at_5` in the **`hybrid` mode** (the mode where the q10 defect was identified). |
| 4 | §4 monkeypatch target could be bypassed — a pipeline-local imported `rerank` reference would not see a patch of `src.retrieval.reranker.rerank`. | **Applied + verified.** Confirmed `src/pipelines/advanced.py:25` and `hybrid.py:27` do `from src.retrieval.reranker import rerank`. §4 Stage 1 now patches `src.pipelines.advanced.rerank` and `src.pipelines.hybrid.rerank`, asserts each resolved to a callable, and adds a `basic`-mode invariant check (basic does not rerank). |

## Net effect

The plan was revised in commit-pending edits; no `src/*` was touched. The
external review surfaced real internal-consistency gaps that are now closed.
The verdict remains advisory — Human authorization is still required before the
regression eval executes, and Phase 5 remains BLOCKED.
