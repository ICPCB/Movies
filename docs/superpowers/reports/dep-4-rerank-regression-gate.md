# Dep #4 — Rerank Regression Eval Gate Report

**Date**: 2026-06-07  
**Branch**: `automation/cinematch-accuracy-audit-full`  
**Ticket**: `.agents/inbox/codex/dep-4-regression-eval.md`  
**Gate verdict**: `gate_fail`  
**Phase 5 status**: BLOCKED  

---

## Summary

The full 20-query reranker-swap regression evaluation was run against the
675-row label set (post Dep #3b merge). The alternative reranker
(`Alibaba-NLP/gte-multilingual-reranker-base`) was compared to the production
baseline (`BAAI/bge-reranker-v2-m3`).

The alt model fixed q10 (hybrid strict_hit_at_5: 0.0 → 1.0) but caused
catastrophic regressions in advanced and hybrid modes, with 7 per-query
hit→miss flips and ~60% drops in strict_hit_at_5.

The gate verdict is **gate_fail**. The alt reranker is not safe as a drop-in
replacement. Phase 5 remains BLOCKED.

---

## Attempt history

### Attempt 1 (2026-06-06) — STOPPED

1. Codex CLI dispatch failed with HTTP 429 (rate limit).
2. Codex sandbox (`--sandbox workspace-write`) encountered shell errors.
3. Claude Code Pro attempted direct execution but used the wrong global
   Python 3.13 runtime with CPU-only PyTorch (`torch 2.9.1+cpu`), so the
   model/import/load path failed. The Movies venv
   (`venv\Scripts\python.exe`, `torch 2.11.0+cu128`) was the correct
   runtime and had CUDA-capable PyTorch.

No eval data was produced.

### Attempt 2 (2026-06-07) — COMPLETED

Claude Code Pro ran both stages with the correct venv Python.

**Stage 1 (capture)**: Completed successfully. 20 queries × 3 modes captured.
Wrote `full_set_pool_snapshot.json`.

**Stage 2 (score)**: Initially failed because the ticket required
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, but `resolve_and_download_model`
in `rerank_model_comparison.py` calls `HfApi.model_info()` which makes an HTTP
request incompatible with offline mode. Both env vars prevented Stage 2 from
running.

**Ticket deviation**: Stage 2 ran without offline env vars. Both models were
confirmed cached locally by the preflight cache check. No model weight download
was observed; models were already cached; Stage 2 still made a Hugging Face
metadata API request. Wrote `regression_comparison.json`.

---

## Gate checks

| Check | Result |
|-------|--------|
| Baseline self-check | PASSED |
| Basic-mode invariant | PASSED |
| q10 hybrid fixed | YES (baseline=0.0, alt=1.0) |
| Aggregate regression | FAIL (advanced + hybrid) |
| Per-query hit→miss flips | FAIL (7 flips) |
| Gate verdict | `gate_fail` |

---

## Headline metrics (baseline vs alt)

### basic mode (no reranker — invariant expected)

| Metric | Baseline | Alt | Delta |
|--------|----------|-----|-------|
| strict_hit_at_5 | 0.50 | 0.50 | 0.00 |
| strict_hit_at_10 | 0.55 | 0.55 | 0.00 |
| mrr_at_5 | 0.779 | 0.779 | 0.00 |

### advanced mode

| Metric | Baseline | Alt | Delta |
|--------|----------|-----|-------|
| strict_hit_at_5 | 0.50 | 0.20 | **-0.30** |
| strict_hit_at_10 | 0.60 | 0.30 | **-0.30** |
| mrr_at_5 | 0.804 | 0.427 | **-0.377** |

### hybrid mode

| Metric | Baseline | Alt | Delta |
|--------|----------|-----|-------|
| strict_hit_at_5 | 0.50 | 0.20 | **-0.30** |
| strict_hit_at_10 | 0.60 | 0.30 | **-0.30** |
| mrr_at_5 | 0.804 | 0.402 | **-0.402** |

---

## Per-query strict_hit_at_5 changes

| Query | Mode | Baseline | Alt | Change |
|-------|------|----------|-----|--------|
| q01 | adv+hyb | 1.0 | 0.0 | hit→miss |
| q03 | adv+hyb | 1.0 | 0.0 | hit→miss |
| q04 | adv+hyb | 1.0 | 0.0 | hit→miss |
| q10 | adv+hyb | 0.0 | 1.0 | **miss→hit** |
| q11 | adv+hyb | 1.0 | 0.0 | hit→miss |
| q12 | adv+hyb | 1.0 | 0.0 | hit→miss |
| q15 | adv+hyb | 1.0 | 0.0 | hit→miss |
| q18 | adv+hyb | 1.0 | 0.0 | hit→miss |

Net: +1 fix (q10), -7 regressions. All flips are in advanced and hybrid modes.
Basic mode is unaffected (no reranker involvement).

---

## Artifacts

| Artifact | Path |
|----------|------|
| Pool snapshot (Stage 1) | `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/full_set_pool_snapshot.json` |
| Regression comparison (Stage 2) | `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json` |

---

## Conclusion

`Alibaba-NLP/gte-multilingual-reranker-base` is not a viable drop-in
replacement for `BAAI/bge-reranker-v2-m3`. It fixes one query (q10) but
degrades seven others. Phase 5 remains BLOCKED.

Next safe action: Dep #5 regression failure analysis to characterize why the
alt model helps q10 but hurts the other queries, and to determine whether
the path forward is another reranker candidate or a localized strategy.
