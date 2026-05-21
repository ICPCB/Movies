---
title: CineMatch — Accuracy Audit & Improvement Design (Index)
date: 2026-05-19
status: draft (pending user review)
audited_commit: 3680020
owner: human (Nguyễn Hoàng Minh) + Claude Code Pro + ChatGPT Plus + Codex + Copilot CLI free
---

# CineMatch — Accuracy Audit & Improvement Design

A measurement-first plan to raise the recommendation accuracy of the three
CineMatch pipelines (Basic, Advanced, Hybrid). The plan builds a labeled eval
harness, runs a structural code audit cross-checked against authoritative
library docs, runs an ablation matrix over key configuration knobs, and
produces a prioritized list of self-contained fix tickets that named AI tools
can pick up without colliding.

This index points to the split sections of the spec. The pointer file
[`../2026-05-19-accuracy-audit-design.md`](../2026-05-19-accuracy-audit-design.md)
preserves the original location.

## Contents

| # | File | Original sections |
|---|---|---|
| 00 | [Purpose, goals, and rules](00-purpose-goals-and-rules.md) | §1 Purpose · §2 Goals and non-goals |
| 01 | [Pre-audit observations](01-pre-audit-observations.md) | §3 Pre-audit observations |
| 02 | [Success metrics](02-success-metrics.md) | §4 Success metrics |
| 03 | [Six-phase plan](03-six-phase-plan.md) | §5 Six-phase plan |
| 04 | [Phase 1 — Eval harness design](04-phase1-eval-harness.md) | §6.1–6.5, §6.8 Eval harness structure |
| 05 | [Metrics, QC, and labels](05-metrics-qc-and-labels.md) | §6.6 LLM pre-grading · §6.7 Manual review · §7 Metrics & QC |
| 06 | [Ablation matrix](06-ablation-matrix.md) | §8 Ablation matrix |
| 07 | [Code audit method](07-code-audit-method.md) | §9 Code audit method |
| 08 | [Prioritization and ticket schema](08-prioritization-and-ticket-schema.md) | §10 Prioritization · §11 Ticket schema |
| 09 | [AI handoff and conflict protocol](09-ai-handoff-and-conflict-protocol.md) | §12 AI handoff routing · §13 Conflict avoidance protocol |
| 10 | [Validation, definition of done, risks](10-validation-done-risks.md) | §14 Validation gate · §15 Definition of done · §16 Tool autonomy · §17 Next steps · §18 Risks |
| 11 | [Reference](11-reference.md) | §19 Reference |

## Reading order

For first-time readers: read 00 → 11 in sequence.

For implementers picking up a ticket: 04 (harness shape), 05 (labels &
metrics), 08 (ticket schema), 09 (handoff rules), then the specific ticket.

For reviewers: 02 (metrics definitions), 05 (label provenance), 10 (definition
of done) anchor the acceptance criteria.

## Out of scope for this spec

The implementation plan itself. That gets created by the `writing-plans` skill
after this spec is approved. See
[10-validation-done-risks.md](10-validation-done-risks.md) §17 for the
post-approval handoff steps.
