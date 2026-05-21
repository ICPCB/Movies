# HY-FIX-02B-VALIDATE - RRF Pool Policy Validation

Status: ACTIVE - autonomous checkpoint mode
Date: 2026-05-22
Owner: Codex automation
Mode: analysis-only

## Goal

Validate whether HY-FIX-02A's q08 RRF-pool trace proves a minimal, safe
`src/config.py` implementation for the recall-depth / RRF-pool path.

## Files To Change

- `eval/scripts/hy_fix_rrf_pool_validate.py`
- `eval/tests/test_hy_fix_rrf_pool_validate.py`
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_policy_validation.json`
- `docs/superpowers/plans/2026-05-22-hy-fix-02b-validate-rrf-pool-policy.md`
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`

## Files To Read But Not Change

- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_trace.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json`
- `eval/scripts/_run_io.py`

## Acceptance Criteria

1. `python -m eval.scripts.hy_fix_rrf_pool_validate --run 2026-05-19-1846-nogit`
   writes `analysis/hy_fix_rrf_pool/rrf_pool_policy_validation.json`.
2. The script imports only stdlib and `eval.scripts._run_io`.
3. The script does not import `src`, load models, call Ollama, or call the
   network.
4. The output compares:
   - `cutoff_only_top_80`
   - `cutoff_only_top_100`
   - `cutoff_only_top_150`
   - `cutoff_only_top_200`
   - `cutoff_only_top_250`
   - `quota_preserve_semantic_bm25_small`
   - `fusion_depth_increase_small`
   - `tie_or_boundary_fix_only` when the trace shows boundary-tie evidence.
5. Each policy reports q08 rescue status per deterministic arm, minimum cutoff
   needed per arm, affected fixed-defect qids where data exists, candidate-count
   and memory risk, minimality, implementation safety, exact allowed src/config
   files if justified, and stop reason when not justified.
6. A cutoff-only policy that needs at least 200 candidates to rescue pinned q08
   is medium/high risk unless existing config evidence proves otherwise.
7. The artifact does not recommend `src/*` implementation unless a minimal
   bounded-risk policy rescues q08 in both deterministic arms.

## Validation Commands

```powershell
git status --short --branch
git log --oneline --decorate -8
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hy_fix_rrf_pool_validate --run 2026-05-19-1846-nogit
```

## Stop Conditions

- Stop if required trace/localization artifacts are missing.
- Stop if validation fails and cannot be fixed within this ticket.
- Stop before any `src/*` edit.
- Stop before model, network, or Ollama calls.
- Stop if policy evidence remains insufficient for a safe implementation;
  continue to HY-FIX-03 reranker_scoring q07.

## Reviewer

SELF-REVIEWED. External review optional and non-blocking.
