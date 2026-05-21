# HY-FIX-03 - Reranker Scoring q07 Analysis

Status: ACTIVE - autonomous checkpoint mode
Date: 2026-05-22
Owner: Codex automation
Mode: analysis-only

## Goal

Validate whether the q07 `reranker_scoring` defect proves a minimal, safe
implementation change for reranker scoring or final-score blending.

## Files To Change

- `eval/scripts/hy_fix_reranker_scoring_q07.py`
- `eval/tests/test_hy_fix_reranker_scoring_q07.py`
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_reranker_scoring/q07_reranker_scoring_analysis.json`
- `docs/superpowers/plans/2026-05-22-hy-fix-03-reranker-scoring-q07-analysis.md`
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`

## Files To Read But Not Change

- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_trace.jsonl`
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/error_report/per_query_mode.gold.jsonl`
- `eval/scripts/_run_io.py`

## Acceptance Criteria

1. `python -m eval.scripts.hy_fix_reranker_scoring_q07 --run 2026-05-19-1846-nogit`
   writes `analysis/hy_fix_reranker_scoring/q07_reranker_scoring_analysis.json`.
2. The script imports only stdlib and `eval.scripts._run_io`.
3. The script does not import `src`, load models, call Ollama, or call the
   network.
4. The artifact records q07 pinned/no_llm deterministic ranks from
   HY-FIX-01/HY-STAB-01 evidence.
5. The artifact records whether basic already finds q07 in top 5 and whether
   hybrid misses the perfect q07 target in top 5.
6. The artifact compares at least:
   - `final_blend_reweight_only`
   - `reranker_document_text_change`
   - `rerank_query_change`
   - `final_top_k_expand_only`
7. The artifact must not recommend `src/*` implementation unless existing
   artifacts prove a minimal bounded-risk policy that rescues q07 without
   broad reranker behavior changes.

## Validation Commands

```powershell
git status --short --branch
git log --oneline --decorate -8
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hy_fix_reranker_scoring_q07 --run 2026-05-19-1846-nogit
```

## Stop Conditions

- Stop if required localization, stability trace, candidates, or error-report
  artifacts are missing.
- Stop if validation fails and cannot be fixed within this ticket.
- Stop before any `src/*` edit.
- Stop before model, network, or Ollama calls.
- Stop if q07 evidence remains insufficient for a safe localized
  implementation; continue to mixed q05/q10 analysis.

## Reviewer

SELF-REVIEWED. External review optional and non-blocking.
