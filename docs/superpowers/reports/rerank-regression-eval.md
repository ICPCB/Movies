# RERANK-REGRESSION-EVAL — Full 20-Query Reranker-Swap Regression Eval

- Ticket: `RERANK-REGRESSION-EVAL`
- Timestamp: 2026-05-23
- Run: `2026-05-19-1846-nogit`
- Branch: `automation/cinematch-accuracy-audit-full`
- Plan: `docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md`
  (READY, externally reviewed, four fixes applied)
- Authorization: Human grant for execution under the plan's §6.9 budget;
  candidate swap = `Alibaba-NLP/gte-multilingual-reranker-base`; production
  reranker = `BAAI/bge-reranker-v2-m3`.
- Scope: q01..q20, all three modes; no `src/*` edits; no LLM call in the
  scoring path; deterministic arm (LLM stubbed to identity).

---

## 1. Verdict

**`gate_inconclusive`** — `phase5_unblocked = False`.

Phase 5 remains **BLOCKED**.

The eval ran cleanly end-to-end (baseline self-check PASS, basic invariant
PASS, all 2000 baseline+alt scoring pairs completed) but `compute_metrics.py`
reports `queries_excluded_null = 20` for every mode in both runs — every query
has at least one unlabeled candidate in top-10/@15, so the @10/@15 aggregates
are masked by `_mean_or_zero` filtering `None` values and cannot be trusted as
"no regression." Per the plan §5 fix #2, that condition is `gate_inconclusive`,
not a silent pass or fail.

A `gate_pass` here would have made a Phase 5 reranker-swap plan eligible to be
authored. `gate_inconclusive` does **not** authorize Phase 5 or any `src/*`
edit. Independent of the gate verdict, the eval is informative — see §5.

## 2. Stage 1 — pool capture

- Wrappers: `src.pipelines.advanced.rerank` and `src.pipelines.hybrid.rerank`
  monkey-patched in the eval process; `src.pipelines.basic` verified to bind
  no `rerank` symbol (basic does not rerank). LLM stubs installed for
  `expand_query`, `hyde_generate`, `explain_movies_batch` in
  `src.llm.langchain_ollama` **and** rebound in the pipeline namespaces (since
  pipelines do `from ... import expand_query`).
- 20 queries × 3 modes; basic captured top-15 directly; advanced/hybrid pools
  captured at depth 50 (`RERANK_TOP_K`). 60 pools total, 50/50 each.
- Snapshot: `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/
  full_set_pool_snapshot.json` — schema `rerank-regression-pool.v1`.
- No `src/*` edit; no live LLM call.

## 3. Stage 2 — dual-model re-score, blend, metric recompute

- Baseline scored via production-equivalent
  `sentence_transformers.CrossEncoder("BAAI/bge-reranker-v2-m3")` on CUDA.
- Alt scored via the RERANK-02B transformers adapter for
  `Alibaba-NLP/gte-multilingual-reranker-base` (revision
  `8215cf04918ba6f7b6a62bb44238ce2953d8831c`, position_ids repair,
  `list[tuple[query, document]]` tokenization, fp16 CUDA).
- 2000 (query, document) pairs scored per model; both stages completed,
  elapsed Stage 2 ≈ 45 s; well within the §6.9 budget.
- Final-score blend reproduced verbatim from `src/retrieval/reranker.py`
  (vote/upstream/source-agreement priors with the same weights, identical
  `log1p` and max-normalization).
- Per `(qid, mode)` ranked lists retained at **top-15** (plan §4 fix #1).
- Metrics recomputed via the imported
  `eval.scripts.compute_metrics.compute_metrics` against the read-only
  `gold_labels.jsonl` (the merged gold-over-silver authoritative labels).
- Artifact:
  `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json`
  — schema `rerank-regression-comparison.v1`.

## 4. Mechanical checks

| Check | Result | Detail |
|---|---|---|
| baseline self-check (q05/q10 top-5 reproduced) | **PASS** | All 4 (qid, mode) comparisons match |
| basic-mode invariant (rank-list families) | **PASS** | hit / strict_hit / mrr / strict_mrr identical at @5/@10/@15 |
| `src/*` diff | **empty** | No source edits |
| LLM in scoring path | **none** | Stubs in capture; no LLM at scoring |
| per-query `strict_hit@5` flips (hit→miss) | **0** | No per-query regressions |
| `queries_excluded_null` per mode (baseline / alt) | basic 20/20, advanced 20/20, hybrid 20/20 | **Label-coverage gap drives the inconclusive verdict** |

Note on the basic-mode `ndcg`: `compute_metrics._ideal_dcg_for_query` computes
the per-query ideal DCG over the **full union** of candidates (basic + advanced
+ hybrid). When the alt model promotes higher-graded movies into the
advanced/hybrid top-15, the union's per-query ideal DCG rises, and basic's
ndcg = basic_dcg / ideal_dcg correspondingly shifts — even though basic's own
top-K ordering and DCG numerator are identical. This is a `compute_metrics`
artifact, not a basic-mode regression. The harness's basic-mode invariant
deliberately compares rank-list families only (hit, strict_hit, mrr,
strict_mrr); see `_basic_byMode_summary_equal` docstring.

## 5. Per-mode aggregates (baseline → alt)

| mode | strict_hit@5 | strict_hit@10 | mrr@5 | hit@5 | queries_excluded_null |
|---|---|---|---|---|---|
| basic    | 0.5000 → 0.5000 | 1.0000 → 1.0000 | 0.7792 → 0.7792 | 0.9000 → 0.9000 | 20 / 20 |
| advanced | 0.9000 → **1.0000** | 1.0000 → 1.0000 | 0.9487 → **1.0000** | 1.0000 → 1.0000 | 20 / 20 |
| hybrid   | 0.9000 → **1.0000** | 1.0000 → 1.0000 | 0.9487 → **1.0000** | 1.0000 → 1.0000 | 20 / 20 |

Read with the caveat that `queries_excluded_null = 20` masks @10/@15 (every
query has unlabeled @15 candidates). The @5 column is the most reliable signal:
the alt model **does not regress** any aggregate metric in any mode, and
**improves** advanced and hybrid `strict_hit@5` and `mrr@5`.

## 6. Per-query strict_hit@5 — q05 and q10

| qid | mode | baseline | alt | note |
|---|---|---|---|---|
| q05 | basic | 1.0 | 1.0 | unchanged |
| q05 | advanced | None | None | both inconclusive (top-5 contains unlabeled candidate) |
| q05 | hybrid | None | None | both inconclusive |
| q10 | basic | 1.0 | 1.0 | unchanged |
| q10 | advanced | None | **1.0** | alt clears the label gap and lands a grade-3 in top-5 |
| q10 | hybrid | None | **1.0** | same — alt's hybrid top-5 is fully labeled AND contains a grade-3 |

Across all 60 (qid, mode) cells: 0 hit→miss, 0 miss→hit on defined cells, 26
same, 34 None. The "None" cells are dominated by the label-coverage gap, not
ranking failures. For q05, both baseline and alt remain inconclusive in
advanced/hybrid — the candidate set's labels do not cover q05's promoted
top-5 movies in either run. **q05 is not resolved by this swap.**

## 7. What this means for Phase 5

`gate_inconclusive` keeps Phase 5 **BLOCKED**. A reranker swap cannot be
greenlit on this evidence alone — even though the @5-level signals are
encouraging, the @10/@15 aggregates are masked by missing labels and cannot
be ruled out as a regression risk.

To get a definitive verdict, the **labels must be extended** to cover the
candidates the alt model promotes into top-15 across all 20 queries. That is
a label-pipeline task (a new silver pregrade pass over the new candidate
union, optionally followed by gold regrade for any movie the alt model ranks
into the top-5), not a `src/*` change.

## 8. Phase 5 gate

**Phase 5 remains BLOCKED.** `phase5_unblocked = False` in the artifact.

The eval makes **no `src/*` edit**, **no LLM call** in the scoring path, and
produces only artifacts, this report, and a ledger checkpoint.
