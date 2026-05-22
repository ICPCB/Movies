# Manual Review Queue

Items deferred from autonomous runs because they require human or
product-level judgment, external credentials, destructive actions, or a
decision the automation rules reserve for a human.

This queue does **not** block autonomous safe work — it records what a human
must decide later. Each entry is self-contained.

Entry schema:

- **Timestamp** — when the item was deferred (UTC).
- **Task / gate** — short id and name.
- **Reason for deferral** — why automation cannot safely finish it.
- **Files / artifacts involved** — exact paths.
- **Repo state at deferral** — branch + relevant commit/working-tree facts.
- **Decision the human must make** — the concrete question.
- **Recommended next action** — what to do once decided.

---

## Open items

### 2026-05-23 — RERANK-REGRESSION-EVAL execution (Phase 5 gate)

- **Timestamp:** 2026-05-23T (overnight safe-autonomy run)
- **Task / gate:** Full gold/silver-set rerank regression eval — the gate that
  must pass before Phase 5 can be unblocked.
- **Reason for deferral:**
  1. **Product-level gate.** The eval's purpose is to decide whether to swap
     the production reranker (`bge-reranker-v2-m3` →
     `Alibaba-NLP/gte-multilingual-reranker-base`). That is an architecture
     change; unblocking Phase 5 on the result is a product decision the
     automation rules reserve for a human. Autonomous judgment, Codex output,
     and external AI review are explicitly **not** human approval for this gate.
  2. **Data not available offline.** The run directory
     `eval/runs/2026-05-19-1846-nogit/` has per-query reranker-input pools for
     **only q05/q10** (`analysis/decomp/`) and q03/q08
     (`analysis/hybrid_stage_trace/`). The other 16 queries have no captured
     rerank pool. A full-set regression eval therefore needs a **pipeline
     replay** (retrieval → RRF pool capture) for all 20 queries — a
     model-backed long job (embedder on GPU), not an offline re-score of
     existing artifacts.
  3. **Long job needing explicit cost/time authorization.** Per the automation
     rules, full evaluations / pipeline replays may run only when an approved
     ticket explicitly authorizes them with a recorded cost/time budget.
- **Files / artifacts involved:**
  - Plan (ready): `docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md`
  - Inputs: `eval/runs/2026-05-19-1846-nogit/{candidates.jsonl,gold_labels.jsonl,silver_labels.jsonl,metrics.json}`
  - RERANK-02 artifact: `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_model_comparison.json`
  - Pipeline source (read-only): `eval/scripts/run_pipelines.py`, `src/retrieval/*`, `src/config.py`
- **Repo state at deferral:** branch `automation/cinematch-accuracy-audit-full`;
  working tree clean except untracked `codex-rerank02-last.txt` and
  `graphify-out/`; HEAD at the overnight checkpoint commit. 223 eval tests OK.
- **Decision the human must make:**
  1. Authorize the model-backed pipeline replay (GPU long job) described in the
     regression-eval plan, with its recorded cost/time budget.
  2. Confirm the candidate model set for the regression eval (the plan proposes
     `Alibaba-NLP/gte-multilingual-reranker-base` as the only swap candidate,
     since RERANK-02 showed it is the only approved model that rescues q10).
  3. After the eval runs: decide whether a partial result
     (q10 rescued, q05 **not** rescued by any tested model) is acceptable
     grounds to author a Phase 5 reranker-swap plan — a product call.
- **Recommended next action:** Human authorizes the regression-eval ticket from
  the ready plan; an authorized session (Codex + Claude gate review) executes
  it; the result is gate-reviewed; only then is a Phase 5 plan considered.
  Phase 5 remains **BLOCKED** until that gate passes and a report proves it.
