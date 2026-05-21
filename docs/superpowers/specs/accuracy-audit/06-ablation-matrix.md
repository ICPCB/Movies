---
title: Ablation matrix
parent: README.md
section: 8
---

# 8. Ablation matrix

[Index](README.md) · Prev: [Metrics, QC, and labels](05-metrics-qc-and-labels.md) · Next: [Code audit method](07-code-audit-method.md)

## 8.1 Ablation execution model

Each ablation is a runtime config override on a parent baseline run. Critical properties:

- **Reuses the parent run's queries and merged labels.** No re-grading of items that already have labels.
- **For new candidates surfaced by the ablation:** LLM pre-grades them only (silver). Ablation metrics tag `partially_provisional: true` and report `new_silver_count`.
- **Apples-to-apples:** query set is held fixed across an ablation set.
- **No file edits.** Override applied by monkeypatching `src.config` constants at runtime in the ablation subprocess.

```
ablate.py --parent eval/runs/<parent_id>/ --override RRF_K=5 --name rrf_k_5
  → eval/runs/<parent_id>-ablation-rrf_k_5/
      run_manifest.json (parent_run, override, new_silver_count)
      candidates.jsonl
      silver_labels.jsonl (only for new candidates)
      metrics.json (partially_provisional: true if new_silver_count > 0)
      ablation_report.json (paired delta vs parent, per-metric, per-axis)
```

## 8.2 Wave 1 (run first — highest expected information)

| Ablation | Override | Why |
|---|---|---|
| `no_llm_expansion` | `LLM_RETRIEVAL_ENABLED=False` | Measures contribution of LLM query rewrite |
| `no_hyde` | `USE_HYDE_IN_ADVANCED=False` | Measures contribution of HyDE in Advanced |
| `no_deterministic_expansion` | `expand_retrieval_query()` returns input | Measures the hardcoded trigger system |
| `no_cross_encoder_reranker` | Advanced and Hybrid skip `rerank()`; `final_score = rrf_score`. Basic unaffected (no reranker by design). | Measures the reranker itself, not just its priors |
| `rrf_k_sweep` | `RRF_K ∈ {5, 15, 30, 60, 100}` | Map the curve around current baseline of 15 |
| `no_reranker_priors` | `RERANK_VOTE_COUNT_WEIGHT = RERANK_UPSTREAM_WEIGHT = RERANK_SOURCE_AGREEMENT_BONUS = 0` | Tests priors independent of reranker |

## 8.3 Wave 2 (run only if Wave 1 leaves open questions)

| Ablation | Override | Why |
|---|---|---|
| `bm25_equal` | All BM25 boosts = 1.0 | Does the 2.5× overview boost do real work? |
| `bm25_title_heavy` | `BM25_TITLE_BOOST=2.0` | Does title weight matter for short queries? |
| `rerank_top_k_30` | `RERANK_TOP_K=30` | Smaller rerank pool — quality vs cost |
| `rerank_top_k_80` | `RERANK_TOP_K=80` | Larger pool — does extra depth help? |

## 8.4 Output → Phase 5 input

`audit/ablation_summary.md` ranks ablations by absolute |Δmetric| averaged across the three primary metrics, with CI width as tiebreaker. Inconclusive ablations (delta CI includes 0) reported and tagged, not used for prioritization.

The output feeds the prioritization formula in [08 — Prioritization](08-prioritization-and-ticket-schema.md).
