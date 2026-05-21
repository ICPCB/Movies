---
title: Purpose, goals, and rules
parent: README.md
section: 1-2
---

# 1. Purpose · 2. Goals and non-goals

[Index](README.md) · Next: [Pre-audit observations](01-pre-audit-observations.md)

## 1. Purpose

Define a measurement-first plan to raise the recommendation accuracy of the three
CineMatch pipelines (Basic, Advanced, Hybrid). The plan builds a labeled eval harness,
runs a structural code audit cross-checked against authoritative library docs, runs an
ablation matrix over key configuration knobs, and produces a prioritized list of
self-contained fix tickets that named AI tools can pick up without colliding.

**Out of scope for this spec:** the implementation plan itself. That gets created by the
`writing-plans` skill after this spec is approved.

## 2. Goals and non-goals

### Goals

- Build a reusable labeled eval set focused on vocabulary-mismatch failure modes.
- Compute Hit@5, MRR@5, and NDCG@5 (plus strict-grade variants) with bootstrap CIs.
- Identify the highest-leverage accuracy improvements via a combined signal of
  (structural audit) + (library best-practice check) + (ablation matrix).
- Produce prioritized, self-contained fix tickets assigned to specific AI tools.
- Establish discipline: no code change without a baseline; no metric claim without
  evidence of label provenance (gold-confirmed vs QC-validated silver vs provisional).

### Non-goals

- No multilingual query support (English query → English TMDB metadata stays per
  current scope).
- No new pipeline modes (improve Basic / Advanced / Hybrid).
- No UI changes.
- No code fixes during phases 1–4. The whole point of the harness is "measure first."
- No ChromaDB re-ingestion in phase 1. Only triggered in phase 5 if audit + ablation
  show missing metadata is a measurable bottleneck.

---

Next: [01 — Pre-audit observations](01-pre-audit-observations.md)
