# Review Packet — RERANK-REGRESSION-EVAL Plan

Advisory external review request. The external reviewer's verdict is
**advisory evidence only** — it is not approval to unblock Phase 5, merge,
push, delete data, change `src/*`, or change ranking/retrieval behavior.

---

## 1. Task / gate name

`RERANK-REGRESSION-EVAL` — the full gold/silver-set reranker-swap regression
eval that gates Phase 5. This packet reviews the **plan**
(`docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md`), not an
implementation. No code was written for this ticket yet.

## 2. Current project state

- Branch: `automation/cinematch-accuracy-audit-full` (automation branch;
  autonomous checkpoint mode).
- CineMatch is a movie-recommendation retrieval pipeline: retrieval (BM25 +
  semantic) → RRF fusion → cross-encoder rerank → final-score blend.
- An accuracy audit found two queries (q05, q10) where the gold target is
  ranked outside the top-5 by the reranker.
- RERANK-02 (committed `f516d15`) compared the production reranker
  `BAAI/bge-reranker-v2-m3` against alternatives on the q05/q10 pools.
  Decision: `model_capability_confirmed` —
  `Alibaba-NLP/gte-multilingual-reranker-base` lifts the q10 target into
  top-5 (rank 7 -> 1, zero-based) but does **not** rescue q05 (it ranks q05
  *worse* than baseline).
- Phase 5 (any `src/*` accuracy change) is **BLOCKED**. A reranker-model swap
  is an architecture change that must first pass a full 20-query regression
  eval proving it does not regress the other 18 queries.
- This plan was authored to specify that regression eval. Its **execution** is
  deferred to `docs/superpowers/MANUAL_REVIEW_QUEUE.md` (model-backed long job
  + product-level gate).

## 3. Relevant plan excerpt

The plan's load-bearing claims:

**Data-availability constraint (plan §2):** The run directory
`eval/runs/2026-05-19-1846-nogit/` has reranker-input pools for only q05/q10
(`analysis/decomp/`) and q03/q08 (`analysis/hybrid_stage_trace/`). `candidates
.jsonl` holds only the final top-15 union per query, not the rerank-input pool
(`RERANK_TOP_K = 50`). A reranker swap can lift a candidate from below the
final cut into the top-5, so a full-set eval needs a pipeline replay to capture
each query's pool — there is no offline shortcut.

**Pipeline facts (plan §3, from `src/retrieval/reranker.py`):**
`rerank()` builds `pool = deduped[:50]`, scores `pairs = [[query, doc], ...]`
with `get_reranker().predict(...)`, then computes
`final_score = rerank_score + 0.08*vote_prior + 0.20*upstream_prior
+ 0.10*source_agreement`, and returns the top-5 by `final_score`. The final
rank is driven by the blended `final_score`, not the raw `rerank_score`.

**Two-stage harness (plan §4):**
- Stage 1 (`--stage capture`): wrap `src.retrieval.reranker.rerank` from the
  eval process to record the pool + document texts + blend inputs for all 20
  queries × 3 modes, driven by recorded deterministic-arm (pinned, no-LLM)
  queries. Output: `full_set_pool_snapshot.json`.
- Stage 2 (`--stage score`): re-score every pool with baseline
  `bge-reranker-v2-m3` and alternative `gte-multilingual-reranker-base`, apply
  the §3 blend, recompute metrics via the imported `compute_metrics.py` against
  the existing read-only gold/silver labels. Output:
  `regression_comparison.json` with one mechanical `gate_verdict`.

**Mechanical gate criteria (plan §5):** headline metrics per mode
(`strict_hit_at_5`, `strict_hit_at_10`, `mrr_at_5`).
- `gate_pass` = no aggregate headline metric regresses in any mode (exact
  non-regression, tolerance 0.0) AND per-query `strict_hit_at_5` hit->miss
  regressions summed across modes == 0 AND q10 reaches top-5 under the alt
  model.
- `gate_fail` = any aggregate regression OR any per-query hit->miss flip OR
  q10 not fixed.
- `gate_inconclusive` = incomplete artifact / model load failure / baseline
  self-check mismatch.

**Phase 5 stance (plan banner, §5, §8, §9):** a `gate_pass` does NOT unblock
Phase 5; it only makes a Phase 5 reranker-swap plan *eligible to be authored*
and Human-reviewed. The plan edits no `src/*`; the reranker swap is simulated
by an eval-process monkeypatch only.

## 4. Relevant diff summary

Commit `35b939e` ("docs: add rerank regression-eval plan and overnight
checkpoint"): 4 files changed, 667 insertions, **0 `src/*` changes**.
- new `docs/superpowers/MANUAL_REVIEW_QUEUE.md`
- new `docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md`
- new `docs/superpowers/reports/overnight-safe-autonomy-summary.md`
- modified `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` (+103 lines:
  `RERANK-02-REVIEW` and `OVERNIGHT-SAFE-AUTONOMY` checkpoints)

No implementation code was written for RERANK-REGRESSION-EVAL — this review is
of the plan only.

## 5. Validation commands and results

- `./venv/Scripts/python.exe -m compileall eval/scripts` — passed.
- `./venv/Scripts/python.exe -m unittest discover -s eval/tests` — 223 OK
  (baseline unchanged; this run added no code).
- `git diff --name-only -- src/` — empty (no `src/*` changes).

## 6. Exact review question

Is the RERANK-REGRESSION-EVAL plan internally consistent and ready to hand to
an implementer? Specifically:
1. Is the two-stage harness design technically sound given the
   data-availability constraint (§2/§4)?
2. Are the mechanical gate criteria (§5) sufficient and unambiguous enough to
   classify a regression with **no human judgment**?
3. Is deferring the plan's *execution* to the manual review queue the correct
   call, or is there a genuinely safe way it could be executed autonomously?
4. Does the plan correctly keep Phase 5 BLOCKED and avoid treating a
   `gate_pass` as approval to swap the model?

## 7. Explicit pass/fail criteria for this review

- **PASS:** the plan is internally consistent; the harness design can actually
  produce the claimed artifacts; the gate criteria are fully mechanical;
  deferring execution is justified; Phase 5 stays BLOCKED; no `src/*` edits are
  implied.
- **FAIL:** the plan has internal contradictions; the harness cannot work as
  described; the gate criteria require human judgment; execution should not be
  deferred / or the plan would improperly unblock Phase 5 or imply `src/*`
  edits.
- **CONCERNS (advisory):** the plan is broadly sound but has specific
  improvable points — list them.
