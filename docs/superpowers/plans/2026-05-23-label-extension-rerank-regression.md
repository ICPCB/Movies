# LABEL-EXTENSION — Rerank Regression Null-Metric Resolution

## Goal
Resolve the `RERANK-REGRESSION-EVAL` `gate_inconclusive` verdict by extending labels for every unlabeled candidate that appears in score-stage top-15 candidate sets, then rerun score-stage metrics to obtain a real `gate_pass` or `gate_fail`.

## Files to change
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest_summary.txt`
- `eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl` only if silver label generation is separately authorized and can label the manifest candidate set
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl` only as a derived merge/update artifact after silver labels are extended
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json` only from rerunning score stage
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` if a checkpoint commit is created
- `docs/superpowers/reports/rerank-regression-eval.md` if the score rerun report is refreshed

## Files to read but not change
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/full_set_pool_snapshot.json`
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`
- `eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl`
- `eval/scripts/rerank_regression_eval.py`
- `eval/scripts/llm_pregrade.py`
- `eval/scripts/merge_labels.py`
- `eval/scripts/compute_metrics.py`
- `docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md`
- `docs/superpowers/reports/rerank-regression-eval.md`

## Current evidence
- `regression_comparison.json` reports `gate_verdict.value = gate_inconclusive`.
- Every baseline and alt mode has `queries_excluded_null = 20`.
- The score stage loads labels from `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`.
- Persisted snapshot top-15 lists contain 744 missing top-15 manifest rows and 325 unique `(qid, tmdb_id)` missing label keys.
- Existing artifacts do not persist alt advanced/hybrid top-15 lists; `regression_comparison.json` stores metrics and per-query strict-hit results, not the ranked alt records. A complete label-extension pass therefore needs either score-stage artifact extension or a rerun that captures alt top-15 before labeling.

## Acceptance criteria
1. Missing-label manifest is deterministic and sorted by `qid`, `mode`, `model`, `rank`, `tmdb_id`.
2. Manifest rows include `qid`, `mode`, `model`, `rank`, `tmdb_id`, `movie_key`, `title`, `affects`, and `source_artifact_path`.
3. No label is treated as human gold unless it comes from an explicit human regrade workflow.
4. If silver labels are generated, the process records silver vs gold counts separately.
5. Score-stage rerun reaches `queries_excluded_null = 0` in every baseline and alt mode before any gate verdict is trusted.
6. Phase 5 remains blocked regardless of score result; a `gate_pass` only authorizes authoring a new Human-reviewed Phase 5 plan.

## Validation commands
```powershell
./venv/Scripts/python.exe -m pytest eval/tests/test_rerank_regression_eval.py eval/tests/test_compute_metrics.py eval/tests/test_merge_labels.py
./venv/Scripts/python.exe -m eval.scripts.rerank_regression_eval --run 2026-05-19-1846-nogit --stage score
./venv/Scripts/python.exe -c "import json; p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json'; d=json.load(open(p,encoding='utf-8')); print(d['gate_verdict']['value']); print({k:v['queries_excluded_null'] for k,v in d['metrics_baseline_by_mode'].items()}); print({k:v['queries_excluded_null'] for k,v in d['metrics_alt_by_mode'].items()})"
```

## Dependencies
- Existing run artifacts for `2026-05-19-1846-nogit`.
- Local reranker model snapshots required by score stage.
- Separate authorization for any LLM/API/human judgment used to create new silver labels.
- A way to capture or reconstruct alt advanced/hybrid top-15 records, because current artifacts do not persist them.

## Risk level
Medium: extending labels changes evaluation ground truth artifacts, and incomplete alt top-15 coverage would leave null metrics or produce a misleading gate result.

## Reviewer
Claude or Human review recommended before merging any label-extension commit because this touches evaluation labels and gate evidence.

## Codex prompt
Implement LABEL-EXTENSION for `RERANK-REGRESSION-EVAL` without modifying `src/*` and without pushing. Start from `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest.json`. First make the score-stage ranked top-15 evidence complete for both baseline and alt models, including alt advanced/hybrid records, without replaying retrieval. Then extend labels only through an authorized silver-label workflow; do not mark silver labels as human gold. Rerun `./venv/Scripts/python.exe -m eval.scripts.rerank_regression_eval --run 2026-05-19-1846-nogit --stage score` and stop unless every mode in both baseline and alt has `queries_excluded_null = 0`. Report silver vs gold label counts, validation output, final gate verdict, and keep Phase 5 blocked.
