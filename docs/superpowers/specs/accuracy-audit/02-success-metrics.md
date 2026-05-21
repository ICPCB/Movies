---
title: Success metrics
parent: README.md
section: 4
---

# 4. Success metrics

[Index](README.md) · Prev: [Pre-audit observations](01-pre-audit-observations.md) · Next: [Six-phase plan](03-six-phase-plan.md)

## 4.1 Primary metrics

Per pipeline mode, on the labeled eval set:

- **Hit@5** — fraction of queries where at least one of the top-5 has grade ≥ 2.
- **MRR@5** — mean reciprocal rank of the first item with grade ≥ 2 in top-5.
- **NDCG@5 (pool-based)** — graded relevance using `3→1.0, 2→0.7, 1→0.3, 0→0.0`,
  with iDCG built from the union of graded candidates across all evaluated modes for
  that query. Labeled "pool-based" because we only know relevance for the candidates
  the systems retrieved, not for every possible relevant movie in the dataset.

## 4.2 Strict variants

Also reported, treating only `grade == 3` (exact target) as relevant:

- **Strict Hit@5**
- **Strict MRR@5**

Strict captures "did the system put *the* target on the top page," while the main
metric captures "did the system put *a good answer* on the top page."

## 4.3 Confidence intervals

Stratified bootstrap by query, B = 1000 iterations, seeded from
`run_manifest.json::rng_seed`. CI half-widths reported alongside each metric.

At n = 20 queries (v1), CIs are wide. Comparisons whose delta CI includes 0 are marked
**inconclusive**. Ablations report **paired** bootstrap on per-query metric deltas
(not unpaired CI overlap). See [05 — Metrics & QC](05-metrics-qc-and-labels.md) §7.4
for the full CI definition.

## 4.4 Per-axis breakdown

Each metric also reported per axis value: era, genre, vocabulary distance, query
length/specificity, ambiguity. Slices with n < 5 are flagged `low_sample` and not used
for decisions.

## 4.5 Raw grades preserved

`metrics.json` keeps the underlying 0/1/2/3 grades so the harness can re-score with
different relevance mappings without re-grading.

---

Next: [03 — Six-phase plan](03-six-phase-plan.md)
