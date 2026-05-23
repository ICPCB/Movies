# LABEL-EXTENSION — Rerank Regression Null-Metric Resolution

## Goal
Resolve the `RERANK-REGRESSION-EVAL` `gate_inconclusive` verdict by extending labels for every unlabeled candidate that appears in score-stage top-15 candidate sets, then rerun score-stage metrics to obtain a real `gate_pass` or `gate_fail`.

## Revision history
- 2026-05-23 (v1): initial plan committed at 62a53d4.
- 2026-05-23 (v2): resolved Dependency #1 (alt advanced/hybrid top-15 capture) by specifying a sidecar persistence script. `eval/scripts/rerank_regression_eval.py` remains under "Files to read but not change"; the new sidecar produces a separate artifact that the manifest builder consumes. Added explicit schema, files, tests, and acceptance criteria for the sidecar.

## Files to change

### Dependency #1 — alt advanced/hybrid top-15 capture (sidecar)
- `eval/scripts/rerank_regression_persist_top15.py` — NEW. Imports public helpers from `eval.scripts.rerank_regression_eval` (`_baseline_score_pairs`, `_alt_score_pairs`, `_build_ranked_top15`, `_flatten_pairs`, model constants). Loads `full_set_pool_snapshot.json`, re-scores captured pools with baseline (`BAAI/bge-reranker-v2-m3`) and alt (`Alibaba-NLP/gte-multilingual-reranker-base`), and writes a NEW artifact (see below). Atomic write. No mutation of any existing artifact. Does NOT call the orchestrator script's main entry point.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/score_stage_top15.json` — NEW artifact. Persists per-query, per-mode, per-arm ranked top-15 records produced during score stage (see schema below).
- `eval/tests/test_rerank_regression_persist_top15.py` — NEW. Tests must NOT load real reranker models. Use fixtures with stubbed `_baseline_score_pairs` / `_alt_score_pairs` (via `monkeypatch`) returning deterministic synthetic scores, and a tiny in-memory snapshot. Tests assert: deterministic ordering, schema conformance, atomic write behavior, and that re-running the script on identical inputs produces a byte-identical artifact.

### Dependency #2 — manifest regeneration (deterministic)
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest.json` — regenerated to include alt advanced/hybrid rows derived from `score_stage_top15.json`. Sort order remains `(qid, mode, model, rank, tmdb_id)` ascending. Schema version stays `rerank-regression-missing-label-manifest.v1`. `generated_from` list extended to include `score_stage_top15.json`.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest_summary.txt` — regenerated counts to reflect new rows.

### Dependency #3 — silver label generation (DEFERRED to a future ticket; do not perform now)
- `eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl` — only if silver label generation is separately authorized and can label the manifest candidate set.
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl` — only as a derived merge/update artifact after silver labels are extended.

### Dependency #4 — score rerun + reporting (DEFERRED to a future ticket; do not perform now)
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json` — only from rerunning score stage after labels are extended.
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — if a checkpoint commit is created.
- `docs/superpowers/reports/rerank-regression-eval.md` — if the score rerun report is refreshed.

## Files to read but not change
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/full_set_pool_snapshot.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json` (until Dependency #4)
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`
- `eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl`
- `eval/scripts/rerank_regression_eval.py` — read-only; the sidecar imports its helpers but does not modify it.
- `eval/scripts/llm_pregrade.py`
- `eval/scripts/merge_labels.py`
- `eval/scripts/compute_metrics.py`
- `docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md`
- `docs/superpowers/reports/rerank-regression-eval.md`
- `src/**` — no edits; no behavior change.

## Schema — `score_stage_top15.json`

```json
{
  "schema_version": "rerank-regression-score-stage-top15.v1",
  "ticket": "RERANK-REGRESSION-EVAL",
  "stage": "score",
  "run_id": "2026-05-19-1846-nogit",
  "generated_at": "<ISO8601 UTC>",
  "source_snapshot": "eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/full_set_pool_snapshot.json",
  "models": {
    "baseline": {"model_id": "BAAI/bge-reranker-v2-m3", "loader": "sentence_transformers.CrossEncoder"},
    "alt":      {"model_id": "Alibaba-NLP/gte-multilingual-reranker-base", "loader": "transformers.AutoModelForSequenceClassification"}
  },
  "scope": {
    "queries_total": 20,
    "modes": ["basic", "advanced", "hybrid"],
    "modes_with_rerank": ["advanced", "hybrid"]
  },
  "per_qid_top15": {
    "<qid>": {
      "baseline": {
        "<mode>": [
          {"rank": 0, "tmdb_id": 0, "movie_key": "string", "title": "string", "rerank_score": 0.0, "final_score": 0.0}
        ]
      },
      "alt": {
        "<mode>": [
          {"rank": 0, "tmdb_id": 0, "movie_key": "string", "title": "string", "rerank_score": 0.0, "final_score": 0.0}
        ]
      }
    }
  }
}
```

For `basic` mode (no rerank), `per_qid_top15[qid][model]["basic"]` MUST be identical to the snapshot's `modes.basic.baseline_top` for both `baseline` and `alt`, because basic mode does not invoke the reranker. The sidecar must assert this invariant.

For `advanced` and `hybrid`, `per_qid_top15[qid][model][mode]` is the top-15 list produced by `_build_ranked_top15(pool, scores, ...)` for the given model.

JSON output MUST be deterministic: keys sorted alphabetically at every level, `indent=2`, `\n` line endings, trailing newline.

## Current evidence
- `regression_comparison.json` reports `gate_verdict.value = gate_inconclusive`.
- Every baseline and alt mode has `queries_excluded_null = 20`.
- The score stage loads labels from `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`.
- Existing manifest contains 744 rows and 325 unique missing label keys, but `counts_by_model = {baseline: 563, alt: 181}` only because the snapshot lacks alt advanced/hybrid top-15. The 181 alt rows correspond to `basic` mode (where alt top = baseline top by invariant) and possibly a small number derived from per-query strict-hit fields; alt advanced/hybrid candidates ranked by alt reranker are NOT in the snapshot.
- `eval/scripts/rerank_regression_eval.py:stage_score` already computes `per_qid_top15` for both arms in-memory (lines 804–815) but only persists `per_query_strict_hit_at_5`. The sidecar reproduces this computation deterministically.

## Acceptance criteria
1. `score_stage_top15.json` exists, validates against the schema above, and is byte-identical across two consecutive runs on the same inputs.
2. `score_stage_top15.json` includes ranked top-15 lists for every `(qid, model, mode)` triple where `model ∈ {baseline, alt}` and `mode ∈ {basic, advanced, hybrid}` and `qid ∈ {q01..q20}` — i.e., 20 × 2 × 3 = 120 ranked lists.
3. For every qid, `per_qid_top15[qid]["baseline"]["basic"] == per_qid_top15[qid]["alt"]["basic"] == snapshot.modes.basic.baseline_top` (basic invariant).
4. For every qid, `per_qid_top15[qid]["baseline"]["advanced"]` and `per_qid_top15[qid]["baseline"]["hybrid"]` reproduce the snapshot's `modes.<mode>.baseline_top` ordering for the rank positions they share (top-5 baseline self-check semantics).
5. Missing-label manifest is regenerated deterministically; sort order `(qid, mode, model, rank, tmdb_id)`; rows include `qid`, `mode`, `model`, `rank`, `tmdb_id`, `movie_key`, `title`, `affects`, `source_artifact_path`, `source_top_field`. `source_top_field` for alt advanced/hybrid rows references `per_qid_top15.<qid>.alt.<mode>` in `score_stage_top15.json`.
6. After regeneration, manifest `counts_by_model` reflects real alt coverage: alt advanced ≈ baseline advanced and alt hybrid ≈ baseline hybrid in row order of magnitude (exact counts depend on label coverage; both should be non-zero and clearly larger than the current 0 alt advanced/hybrid contribution).
7. New test file passes without loading real reranker models (uses monkeypatch fixtures).
8. No edits to `src/*`; no edits to `eval/scripts/rerank_regression_eval.py`; no edits to existing test files.
9. No label is treated as human gold (Dependency #3 is deferred).
10. Score-stage rerun is NOT performed in this ticket (Dependency #4 deferred). Phase 5 remains blocked regardless of any future score result; a `gate_pass` only authorizes authoring a new Human-reviewed Phase 5 plan.

## Validation commands

For the alt top-15 capture ticket (Dependency #1 + #2):

```powershell
./venv/Scripts/python.exe -m pytest eval/tests/test_rerank_regression_eval.py eval/tests/test_compute_metrics.py eval/tests/test_merge_labels.py eval/tests/test_rerank_regression_persist_top15.py
./venv/Scripts/python.exe -m eval.scripts.rerank_regression_persist_top15 --run 2026-05-19-1846-nogit
./venv/Scripts/python.exe -c "import json; p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/score_stage_top15.json'; d=json.load(open(p,encoding='utf-8')); print(d['schema_version']); print(sorted(d['per_qid_top15'].keys())); print({arm:{m:len(d['per_qid_top15']['q01'][arm][m]) for m in d['per_qid_top15']['q01'][arm]} for arm in ('baseline','alt')})"
./venv/Scripts/python.exe -c "import json; p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest.json'; d=json.load(open(p,encoding='utf-8')); print(d['records_total'], d['unique_label_keys_total']); print(d['counts_by_model']); print(d['counts_by_mode'])"
```

For Dependency #4 (deferred — listed here for completeness):

```powershell
./venv/Scripts/python.exe -m eval.scripts.rerank_regression_eval --run 2026-05-19-1846-nogit --stage score
./venv/Scripts/python.exe -c "import json; p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json'; d=json.load(open(p,encoding='utf-8')); print(d['gate_verdict']['value']); print({k:v['queries_excluded_null'] for k,v in d['metrics_baseline_by_mode'].items()}); print({k:v['queries_excluded_null'] for k,v in d['metrics_alt_by_mode'].items()})"
```

## Dependencies
- Existing run artifacts for `2026-05-19-1846-nogit` (snapshot present).
- Local reranker model snapshots required by the sidecar's actual scoring run (baseline `BAAI/bge-reranker-v2-m3` + alt `Alibaba-NLP/gte-multilingual-reranker-base`).
- Separate authorization for any LLM/API/human judgment used to create new silver labels (Dependency #3, deferred).

## Risk level
Medium. The sidecar runs cross-encoder model inference (~45–90s on existing hardware). Risks:
- Numeric drift between baseline_self_check comparisons: sidecar must reproduce the same ordering as `regression_comparison.json:baseline_self_check` for q05/q10 in advanced/hybrid; deviations are a hard stop.
- Determinism: any non-deterministic kernel or BF16/FP16 reduction order could break the byte-identical-rerun acceptance criterion. Sidecar must pin the same dtype/device handling already used in `_alt_score_pairs`.

## Reviewer
Claude review required before commit. Human review optional. External LLM review optional.

## Hard-stop conditions
- Baseline self-check on q05/q10 in advanced/hybrid does not reproduce the snapshot baseline_top ordering.
- Re-running the sidecar on identical inputs produces a non-byte-identical artifact.
- Any modification appears in `git diff -- src/` or `git diff -- eval/scripts/rerank_regression_eval.py`.
- Any LLM/API call is made.
- Test suite regresses on previously-passing tests.

## Codex prompt (Dependency #1 + #2 only — this ticket)
Implement only Dependency #1 (alt top-15 capture sidecar) and Dependency #2 (manifest regeneration) for LABEL-EXTENSION on `RERANK-REGRESSION-EVAL`. Do not modify `src/*`, `eval/scripts/rerank_regression_eval.py`, or any existing test file. Do not perform Dependency #3 (silver labels) or Dependency #4 (score rerun + reports). Do not push.

Steps:

1. Create `eval/scripts/rerank_regression_persist_top15.py` that:
   - Loads `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/full_set_pool_snapshot.json`.
   - Imports `_baseline_score_pairs`, `_alt_score_pairs`, `_build_ranked_top15`, and any flattening helpers from `eval.scripts.rerank_regression_eval` (do not redefine them).
   - Re-scores captured advanced/hybrid pools with both arms.
   - Builds `per_qid_top15` exactly matching the schema in this plan.
   - Asserts the basic invariant (alt basic == baseline basic == snapshot basic baseline_top).
   - Asserts the baseline self-check on q05/q10 advanced/hybrid (top-5 ordering reproduces snapshot).
   - Writes the artifact atomically with deterministic JSON encoding (sorted keys, indent=2, trailing newline).
2. Create `eval/tests/test_rerank_regression_persist_top15.py` that uses `monkeypatch` to stub `_baseline_score_pairs` and `_alt_score_pairs` with deterministic synthetic scoring, builds a minimal in-memory snapshot, runs the sidecar, and validates schema + invariants + byte-identical re-run. Tests must NOT load real reranker models.
3. Run the sidecar once to produce `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/score_stage_top15.json`.
4. Regenerate `missing_label_manifest.json` and `missing_label_manifest_summary.txt` to include alt advanced/hybrid rows derived from `score_stage_top15.json`. Use a deterministic in-script regeneration (any helper logic lives inside the sidecar or a new tiny module under `eval/scripts/`; do not modify existing scripts). The regenerated manifest must remain sorted by `(qid, mode, model, rank, tmdb_id)` and conform to the existing `rerank-regression-missing-label-manifest.v1` schema with `generated_from` extended to list the new sidecar artifact.
5. Run validation commands listed above and report exit codes and key output lines.
6. Stop without performing Dependency #3 or #4. Confirm `git diff -- src/` is empty. Confirm `git diff -- eval/scripts/rerank_regression_eval.py` is empty. Report git status.

Final report from Codex must include: list of files changed, test results, sidecar run output excerpt, `score_stage_top15.json` size and per-arm/per-mode count summary, regenerated manifest counts, and a one-line restatement that Phase 5 remains blocked.
