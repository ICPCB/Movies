---
title: Six-phase plan
parent: README.md
section: 5
---

# 5. Six-phase plan

[Index](README.md) · Prev: [Success metrics](02-success-metrics.md) · Next: [Phase 1 — Eval harness](04-phase1-eval-harness.md)

```
Phase 1 — Eval harness scaffold (no code fixes)
  1.1 Build eval/ directory + harness scripts
  1.2 Generate v1 query set (20 queries, 5-axis diversity, vocab-mismatch bias)
  1.3 User reviews and approves the 20 queries
  1.4 Run all 3 pipelines, build per-query top-8 union (soft cap, hard max 15)
  1.5 LLM pre-grades all (query, candidate) pairs → silver labels
  1.6 Compute baseline metrics_provisional.json (silver only, provisional: true)

Phase 2 — Gold review and QC
  2.1 Build review_sheet.jsonl from auto-flag rules
  2.2 User reviews flagged items (Gradio app, splittable across sessions)
  2.3 qc_analyze.py compares gold vs silver on 20% random QC sample
  2.4 Adaptive expansion decision (freeze / expand_manual / review_outlier_query)
  2.5 Recompute metrics.json on merged labels (provisional: false)

Phase 3 — Code audit + library best-practice check (parallel with Phase 2)
  3.1 Per-module audit using categories C1–C6
  3.2 context7 best-practice lookup per library
  3.3 audit/findings.md (only high/medium confidence; low → notes_low_confidence.md)

Phase 4 — Ablation matrix
  4.1 Run wave 1 ablations on the v1 eval set (config overrides via monkeypatch)
  4.2 Wave 2 only if wave 1 leaves unanswered questions
  4.3 audit/ablation_summary.md ranks ablations by paired delta with CIs

Phase 5 — Prioritized fix tickets + AI handoff
  5.1 Combine findings + ablation deltas + costs into priority scores
  5.2 Generate audit/tickets/T-NNN.md (one file per ticket)
  5.3 Assign each ticket to a tool via the routing matrix
  5.4 Decide on ChromaDB re-ingestion based on evidence

Phase 6 (optional) — Expand and re-baseline
  6.1 Once v1 format is proven, expand to 30–50 queries (v2.jsonl)
  6.2 Re-baseline; re-prioritize
```

**Hard rule across all phases:** no code change until Phase 5. Phase 1–4 monkeypatching
of `src.config` constants during ablation runs is allowed (runtime only, no file edits).

Phase 1 details: [04 — Eval harness](04-phase1-eval-harness.md).
Phases 2 & QC: [05 — Metrics, QC, and labels](05-metrics-qc-and-labels.md).
Phase 3 audit: [07 — Code audit method](07-code-audit-method.md).
Phase 4 ablations: [06 — Ablation matrix](06-ablation-matrix.md).
Phase 5 prioritization & tickets: [08 — Prioritization](08-prioritization-and-ticket-schema.md)
and [09 — Handoff](09-ai-handoff-and-conflict-protocol.md).

---

Next: [04 — Phase 1 eval harness](04-phase1-eval-harness.md)
