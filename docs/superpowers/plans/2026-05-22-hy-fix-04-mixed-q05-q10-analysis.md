# HY-FIX-04 - Mixed q05/q10 Analysis

Status: ACTIVE - autonomous checkpoint mode
Date: 2026-05-22
Owner: Codex automation
Mode: analysis-only

## Goal

Validate whether the remaining mixed fixed defects, q05 and q10, prove any
minimal safe localized implementation after HY-FIX-02B and HY-FIX-03 both
declined `src/*` changes.

## Files To Change

- `eval/scripts/hy_fix_mixed_q05_q10.py`
- `eval/tests/test_hy_fix_mixed_q05_q10.py`
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_mixed/q05_q10_mixed_analysis.json`
- `docs/superpowers/plans/2026-05-22-hy-fix-04-mixed-q05-q10-analysis.md`
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`

## Files To Read But Not Change

- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_trace.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/error_report/per_query_mode.gold.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_policy_validation.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_reranker_scoring/q07_reranker_scoring_analysis.json`
- `eval/scripts/_run_io.py`

## Acceptance Criteria

1. `python -m eval.scripts.hy_fix_mixed_q05_q10 --run 2026-05-19-1846-nogit`
   writes `analysis/hy_fix_mixed/q05_q10_mixed_analysis.json`.
2. The script imports only stdlib and `eval.scripts._run_io`.
3. The script does not import `src`, load models, call Ollama, or call the
   network.
4. The artifact records q05 and q10 pinned/no_llm deterministic stage
   evidence from localization.
5. The artifact records top-5 mode evidence from the gold error report.
6. The artifact compares at least:
   - `global_cutoff_small`
   - `final_blend_reweight_for_mixed`
   - `reranker_scoring_adjustment`
   - `query_or_label_review`
7. The artifact must not recommend `src/*` implementation unless one policy
   addresses both q05 and q10 with bounded risk and without contradicting
   HY-FIX-02B/HY-FIX-03 blockers.

## Validation Commands

```powershell
git status --short --branch
git log --oneline --decorate -8
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hy_fix_mixed_q05_q10 --run 2026-05-19-1846-nogit
```

## Stop Conditions

- Stop if required localization, stability trace, error-report, or prior
  HY-FIX artifacts are missing.
- Stop if validation fails and cannot be fixed within this ticket.
- Stop before any `src/*` edit.
- Stop before model, network, or Ollama calls.
- Stop if q05/q10 evidence remains mixed or contradictory; produce project
  closeout instead of forcing a broad implementation.

## Reviewer

SELF-REVIEWED. External review optional and non-blocking.
