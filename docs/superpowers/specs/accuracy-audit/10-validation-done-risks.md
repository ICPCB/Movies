---
title: Validation gate, definition of done, autonomy, next steps, risks
parent: README.md
section: 14, 15, 16, 17, 18
---

# 14. Validation gate · 15. Definition of done · 16. Tool autonomy · 17. Next steps · 18. Risks

[Index](README.md) · Prev: [AI handoff & conflicts](09-ai-handoff-and-conflict-protocol.md) · Next: [Reference](11-reference.md)

## 14. Validation gate

Conditional by ticket type.

### 14.1 Code tickets that can affect retrieval / ranking / eval metrics

1. `python -m compileall src` passes.
2. `python scripts/quality_smoke_test.py --no-llm` passes; no new warnings.
3. `python eval/scripts/run_pipelines.py --queries eval/queries/v1.jsonl` on the eval set.
4. `python eval/scripts/compute_metrics.py` on the resulting run.
5. Paired bootstrap delta vs `eval/runs/current_run.txt`'s baseline.
6. If any metric regresses past the lower CI bound → ticket reopens.
7. If no regression (and, when an impact was claimed, the expected lift is visible or within CI of expected) → ticket merges; update `eval/runs/current_run.txt`.

### 14.2 Non-ranking tickets (docs, schema docs, small unit helpers)

1. `python -m compileall` on the touched path.
2. Relevant unit tests pass.
3. No full eval run required unless the ticket sets `requires_full_eval: true`.

### 14.3 Long-running jobs (e.g., ChromaDB re-ingestion)

1. Ticket sets `requires_human_run: true`.
2. AI prepares commands + verification checklist + rollback plan.
3. Human triggers the run.
4. AI verifies post-run state against checklist; updates ticket.

### 14.4 Re-baseline cadence

- Every 3 merged ranking-affecting tickets, re-run a fresh full pipeline on `eval/queries/v1.jsonl` and rotate `eval/runs/current_run.txt`.
- **Always re-baseline immediately after any high-risk retrieval / reranker / fusion change**, regardless of count.

## 15. Definition of done

The iteration is complete when:

- [ ] All Tier A tickets either merged with validation evidence OR explicitly deferred with a written reason.
- [ ] `eval/runs/<current>/metrics.json` shows ≥ 1 of {Hit@5, MRR@5, NDCG@5} improved beyond the lower CI bound on the strongest mode (Hybrid).
- [ ] No regression in any metric past the lower CI bound.
- [ ] All structural smoke-test warnings identified by the audit are gone.
- [ ] `audit/findings.md` and `audit/tickets/STATUS.md` reflect final state.
- [ ] `docs/ARCHITECTURE.md` updated for any file/contract changes (including the stale config values flagged in [01 §3.2](01-pre-audit-observations.md#32-docsarchitecturemd-is-stale-on-several-config-values)).
- [ ] Decision recorded on re-ingestion: triggered or deferred with evidence.
- [ ] Every metric-improvement claim identifies its label provenance: **gold-confirmed**, **QC-validated silver**, or **partially provisional**.
- [ ] Final report includes four sections: **What changed**, **What improved**, **What did not improve**, **What to try next**.

## 16. Tool autonomy rules

No tool runs long-running eval, ablation, or ingestion without an approved ticket and test plan. **Claude or Codex may run approved validation commands for the active ticket.** ChromaDB re-ingestion remains **human-triggered only**.

Other autonomy limits:
- No tool merges to main; the human merges branches.
- No tool deletes or moves files outside its ticket's declared list.
- No tool changes `eval/queries/v1.jsonl` after grading begins; new queries go in `v2.jsonl`.

## 17. Concrete next steps after spec approval

After the human approves this spec:

1. Invoke `writing-plans` skill to turn this spec into a step-by-step implementation plan, scoped to Phase 1 (eval harness scaffold) as the first execution chunk.
2. Phase 1 execution itself follows the conflict-avoidance protocol — Claude Code Pro owns it.
3. Phases 2–5 are scheduled as follow-on plans once Phase 1 lands.

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM grader (llama3.2) too noisy → unreliable silver labels | QC sample + adaptive expansion; escape hatch at 60% manual review to mark grader unreliable |
| 20 queries too few → wide CIs, inconclusive ablations | Plan already includes Phase 6 expansion to 30–50; v1 still useful for finding clear-signal fixes |
| Re-ingestion looks tempting but ablation shows the gap is small | Re-ingestion gated on evidence; not in Phase 1 |
| Architecture doc drift creating confusion mid-iteration | Doc update is a Definition-of-Done item; flagged early in [01 §3.2](01-pre-audit-observations.md#32-docsarchitecturemd-is-stale-on-several-config-values) |
| Multiple AI tools racing on the same file | Solo-friendly default (one ticket at a time) + STATUS.md + file locks + reviewer-never-edits rule |
| Stale baseline making paired bootstrap meaningless | Re-baseline cadence (every 3 merged ranking tickets + after any high-risk change) |
| Long-running ablations blocking iteration | Wave 1 / Wave 2 split; only Wave 1 required by default |
| Eval harness bugs (e.g., wrong NDCG implementation) masking real wins/losses | Unit tests on `compute_metrics.py` against a tiny synthetic dataset with hand-computed expected outputs; cross-check first run by hand on 1 query |
