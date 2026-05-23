# LABEL-EXTENSION — Rerank Regression Null-Metric Resolution

## Goal
Resolve the `RERANK-REGRESSION-EVAL` `gate_inconclusive` verdict by extending labels for every unlabeled candidate that appears in score-stage top-15 candidate sets, then rerun score-stage metrics to obtain a real `gate_pass` or `gate_fail`.

## Revision history
- 2026-05-23 (v1): initial plan committed at 62a53d4.
- 2026-05-23 (v2): resolved Dependency #1 (alt advanced/hybrid top-15 capture) by specifying a sidecar persistence script. `eval/scripts/rerank_regression_eval.py` remains under "Files to read but not change"; the new sidecar produces a separate artifact that the manifest builder consumes. Added explicit schema, files, tests, and acceptance criteria for the sidecar.
- 2026-05-23 (v3): resolved Dependency #3 ambiguity by narrowing scope to a deterministic, fully-offline **human-review queue** builder. No silver-label generation, no LLM/API calls, no modification of `gold_labels.jsonl` or `silver_labels.jsonl`. Added explicit standalone-sidecar spec, schema, allowed files, acceptance criteria, validation commands, hard-stop conditions, and Codex prompt for the queue ticket. Silver-label generation remains DEFERRED to a separate, future, separately-authorized ticket.

## Files to change

### Dependency #1 — alt advanced/hybrid top-15 capture (sidecar)
- `eval/scripts/rerank_regression_persist_top15.py` — NEW. Imports public helpers from `eval.scripts.rerank_regression_eval` (`_baseline_score_pairs`, `_alt_score_pairs`, `_build_ranked_top15`, `_flatten_pairs`, model constants). Loads `full_set_pool_snapshot.json`, re-scores captured pools with baseline (`BAAI/bge-reranker-v2-m3`) and alt (`Alibaba-NLP/gte-multilingual-reranker-base`), and writes a NEW artifact (see below). Atomic write. No mutation of any existing artifact. Does NOT call the orchestrator script's main entry point.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/score_stage_top15.json` — NEW artifact. Persists per-query, per-mode, per-arm ranked top-15 records produced during score stage (see schema below).
- `eval/tests/test_rerank_regression_persist_top15.py` — NEW. Tests must NOT load real reranker models. Use fixtures with stubbed `_baseline_score_pairs` / `_alt_score_pairs` (via `monkeypatch`) returning deterministic synthetic scores, and a tiny in-memory snapshot. Tests assert: deterministic ordering, schema conformance, atomic write behavior, and that re-running the script on identical inputs produces a byte-identical artifact.

### Dependency #2 — manifest regeneration (deterministic)
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest.json` — regenerated to include alt advanced/hybrid rows derived from `score_stage_top15.json`. Sort order remains `(qid, mode, model, rank, tmdb_id)` ascending. Schema version stays `rerank-regression-missing-label-manifest.v1`. `generated_from` list extended to include `score_stage_top15.json`.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest_summary.txt` — regenerated counts to reflect new rows.

### Dependency #3 — human-review queue (this ticket; fully offline)
This ticket builds a deterministic offline queue of the unique missing label keys so a human reviewer can grade them later. It does NOT generate silver labels, does NOT call any LLM/API, and does NOT modify `gold_labels.jsonl` or `silver_labels.jsonl`. Silver-label generation is split out to Dependency #3b (deferred, separately-authorized).

- `eval/scripts/rerank_regression_build_review_queue.py` — NEW standalone sidecar. Reads ONLY: `missing_label_manifest.json`, `score_stage_top15.json`, `full_set_pool_snapshot.json`. Writes the three queue artifacts below. MUST NOT import from `eval.scripts.llm_pregrade`, `eval.scripts.merge_labels`, `eval.scripts.rerank_regression_persist_top15`, or `eval.scripts.rerank_regression_eval`. MUST NOT make any network/API call. MUST NOT load any model. Pure dict/list/string transformation only.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.jsonl` — NEW. One JSONL row per unique missing label key (qid, tmdb_id). Schema below. Deterministic order.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv` — NEW. Same rows in CSV form for spreadsheet/human grading. Same row order as the JSONL. UTF-8, `\n` line endings, RFC 4180 quoting.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue_summary.txt` — NEW. Deterministic counts summary.
- `eval/tests/test_rerank_regression_build_review_queue.py` — NEW. Tests use tiny fixture inputs only; must NOT load any reranker model and must NOT touch network. Assert: schema conformance, deterministic ordering, byte-identical rerun on JSONL/CSV/summary, atomic-write rollback on failure, no rows for keys already labeled in `gold_labels.jsonl` fixture.

### Dependency #3b — silver label generation (DEFERRED to a future, separately-authorized ticket; do not perform now)
- `eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl` — only if silver label generation is separately authorized in its own ticket.
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl` — only as a derived merge/update artifact after silver labels are extended. Existing schema already separates provenance via `label_source` / `silver_grade` / `gold_grade` / `gold_notes` and MUST be preserved.

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

## Schema — `missing_label_review_queue.jsonl` (Dependency #3)

One JSONL row per unique missing label key. A "unique missing label key" is a `(qid, tmdb_id)` pair that appears in `missing_label_manifest.json:missing_labels` AND is not already present in `gold_labels.jsonl`. Sort order: `(qid, tmdb_id)` ascending. Row fields (alphabetical within each row when serialized):

```json
{
  "queue_position": 0,
  "qid": "q01",
  "query_text": "string from snapshot.queries[].query",
  "tmdb_id": 1234,
  "movie_key": "string",
  "title": "string",
  "modes_affected": ["advanced", "hybrid"],
  "models_affected": ["alt", "baseline"],
  "ranks_observed": [
    {"mode": "advanced", "model": "alt", "rank": 3},
    {"mode": "hybrid",   "model": "baseline", "rank": 7}
  ],
  "document_text_excerpt": "first 500 chars of pool entry document_text, or empty string if absent",
  "source_artifact_paths": [
    "eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest.json",
    "eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/score_stage_top15.json"
  ],
  "source_top_fields": [
    "per_qid_top15.q01.alt.advanced",
    "per_qid_top15.q01.baseline.hybrid"
  ],
  "grade": null,
  "grader_notes": null
}
```

Field semantics:
- `queue_position` is the zero-based row index after sorting, useful for human reviewer progress tracking.
- `modes_affected`, `models_affected`, `ranks_observed` deduplicate per-row entries from the manifest. `ranks_observed` lists every `(mode, model, rank)` triple observed for this key, sorted by `(mode, model, rank)` ascending.
- `document_text_excerpt` is read from `full_set_pool_snapshot.json:queries[].modes[].pool[]` and truncated to the first 500 characters (after `\n` → space normalization) for grading reference. Empty string if the key is not in any captured pool.
- `source_top_fields` mirrors the manifest's `source_top_field` values for this key, deduplicated and sorted.
- `grade` and `grader_notes` are ALWAYS `null` at generation time. They exist as stable placeholders for downstream human-grading tooling. The sidecar MUST NOT populate them.

CSV form: same fields, header row, list-typed fields encoded as `|`-joined strings (e.g., `advanced|hybrid`, `alt|baseline`), `ranks_observed` encoded as `mode:model:rank` triples joined by `|` (e.g., `advanced:alt:3|hybrid:baseline:7`). `source_artifact_paths` and `source_top_fields` encoded the same way.

JSONL output MUST be deterministic: each row serialized with `json.dumps(row, sort_keys=True, ensure_ascii=False)`, `\n` line ending per row, trailing newline. CSV output MUST be byte-identical across reruns on identical inputs.

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
9. No label is treated as human gold. Dependency #3 (this ticket scope) builds an offline review queue only; Dependency #3b (silver-label generation) remains deferred.
10. Score-stage rerun is NOT performed in this ticket (Dependency #4 deferred). Phase 5 remains blocked regardless of any future score result; a `gate_pass` only authorizes authoring a new Human-reviewed Phase 5 plan.

### Acceptance criteria — Dependency #3 (human-review queue)

11. `missing_label_review_queue.jsonl`, `missing_label_review_queue.csv`, and `missing_label_review_queue_summary.txt` exist under `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/` and are byte-identical across two consecutive sidecar runs on identical inputs.
12. JSONL row count equals the count of unique `(qid, tmdb_id)` keys in `missing_label_manifest.json:missing_labels` MINUS keys already present in `gold_labels.jsonl`. This count MUST equal the manifest's `unique_label_keys_total` minus any pre-existing gold-label overlap.
13. JSONL row order is strictly ascending by `(qid, tmdb_id)`. `queue_position` matches the row index. Within each row, JSON keys are sorted alphabetically.
14. CSV row order matches JSONL row order one-to-one (excluding the CSV header). CSV header order is alphabetical.
15. Every row carries non-null `qid`, `tmdb_id`, `movie_key`, `title`, `modes_affected` (non-empty list), `models_affected` (non-empty list), `ranks_observed` (non-empty list), `source_artifact_paths` (length 2 or 3), and `source_top_fields` (non-empty list). `grade` and `grader_notes` are ALWAYS `null` in the generated artifact.
16. `document_text_excerpt` is sourced only from `full_set_pool_snapshot.json` pool entries; if the key does not appear in any captured pool, the field is the empty string `""` (never `null`).
17. `missing_label_review_queue_summary.txt` reports deterministic counts: `total_rows`, `counts_by_qid`, `counts_by_mode`, `counts_by_model`, `rows_with_excerpt`, `rows_without_excerpt`. Identical across reruns.
18. Sidecar makes NO network call and loads NO model. Static analysis: `git diff -- eval/scripts/rerank_regression_build_review_queue.py` shows zero imports from `eval.scripts.rerank_regression_eval`, `eval.scripts.rerank_regression_persist_top15`, `eval.scripts.llm_pregrade`, `eval.scripts.merge_labels`, `requests`, `httpx`, `openai`, `anthropic`, `torch`, `transformers`, or `sentence_transformers`.
19. New test file `eval/tests/test_rerank_regression_build_review_queue.py` passes and validates: schema conformance on tiny fixtures, sort/order determinism, byte-identical rerun, exclusion of keys already in gold-label fixture, atomic-write rollback on simulated `Path.replace` failure.
20. No edits to `src/*`. No edits to `eval/scripts/rerank_regression_eval.py`, `eval/scripts/rerank_regression_persist_top15.py`, `eval/scripts/llm_pregrade.py`, `eval/scripts/merge_labels.py`, or any existing test file. No edits to `gold_labels.jsonl` or `silver_labels.jsonl`. No edits to the Dep #1+#2 artifacts (`score_stage_top15.json`, `missing_label_manifest.json`, `missing_label_manifest_summary.txt`).

## Validation commands

For the alt top-15 capture ticket (Dependency #1 + #2):

```powershell
./venv/Scripts/python.exe -m pytest eval/tests/test_rerank_regression_eval.py eval/tests/test_compute_metrics.py eval/tests/test_merge_labels.py eval/tests/test_rerank_regression_persist_top15.py
./venv/Scripts/python.exe -m eval.scripts.rerank_regression_persist_top15 --run 2026-05-19-1846-nogit
./venv/Scripts/python.exe -c "import json; p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/score_stage_top15.json'; d=json.load(open(p,encoding='utf-8')); print(d['schema_version']); print(sorted(d['per_qid_top15'].keys())); print({arm:{m:len(d['per_qid_top15']['q01'][arm][m]) for m in d['per_qid_top15']['q01'][arm]} for arm in ('baseline','alt')})"
./venv/Scripts/python.exe -c "import json; p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest.json'; d=json.load(open(p,encoding='utf-8')); print(d['records_total'], d['unique_label_keys_total']); print(d['counts_by_model']); print(d['counts_by_mode'])"
```

For the human-review queue ticket (Dependency #3):

```powershell
./venv/Scripts/python.exe -m pytest eval/tests/test_rerank_regression_build_review_queue.py
./venv/Scripts/python.exe -m eval.scripts.rerank_regression_build_review_queue --run 2026-05-19-1846-nogit
./venv/Scripts/python.exe -c "import json,collections; p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.jsonl'; rows=[json.loads(l) for l in open(p,encoding='utf-8')]; print('rows', len(rows)); print('qids', sorted({r['qid'] for r in rows})); print('null_grades', sum(1 for r in rows if r['grade'] is None and r['grader_notes'] is None)); print('first_position', rows[0]['queue_position'], 'last_position', rows[-1]['queue_position'])"
./venv/Scripts/python.exe -c "p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv'; data=open(p,encoding='utf-8').read(); print('bytes',len(data)); print('header',data.splitlines()[0])"
./venv/Scripts/python.exe -c "p='eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue_summary.txt'; print(open(p,encoding='utf-8').read())"
# Byte-identical rerun check (Linux/macOS would use sha256sum; on Windows use Get-FileHash)
./venv/Scripts/python.exe -m eval.scripts.rerank_regression_build_review_queue --run 2026-05-19-1846-nogit
# Then compare hashes of all three queue artifacts before/after the second run.
git diff --name-only -- src/
git diff --name-only -- eval/scripts/rerank_regression_eval.py
git diff --name-only -- eval/scripts/rerank_regression_persist_top15.py
git diff --name-only -- eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl
git status --short
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

### For Dependency #1 + #2 (already implemented at commit 5edfe66)
- Baseline self-check on q05/q10 in advanced/hybrid does not reproduce the snapshot baseline_top ordering.
- Re-running the sidecar on identical inputs produces a non-byte-identical artifact.
- Any modification appears in `git diff -- src/` or `git diff -- eval/scripts/rerank_regression_eval.py`.
- Any LLM/API call is made.
- Test suite regresses on previously-passing tests.

### For Dependency #3 (this ticket — human-review queue)
- Any import in `eval/scripts/rerank_regression_build_review_queue.py` of `eval.scripts.rerank_regression_eval`, `eval.scripts.rerank_regression_persist_top15`, `eval.scripts.llm_pregrade`, `eval.scripts.merge_labels`, `requests`, `httpx`, `openai`, `anthropic`, `torch`, `transformers`, or `sentence_transformers`.
- Any network call, any model load, any external process spawn.
- Any change to `gold_labels.jsonl` or `silver_labels.jsonl`.
- Any change to the Dep #1+#2 artifacts (`score_stage_top15.json`, `missing_label_manifest.json`, `missing_label_manifest_summary.txt`) or to `eval/scripts/rerank_regression_persist_top15.py` or `eval/tests/test_rerank_regression_persist_top15.py`.
- Any non-null `grade` or `grader_notes` value in generated queue rows.
- Re-running the queue sidecar on identical inputs produces a non-byte-identical artifact (JSONL, CSV, or summary).
- Queue row count diverges from the expected `unique_label_keys_total` minus pre-existing gold overlap.
- Any modification appears in `git diff -- src/` or in any existing test file.

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

## Codex prompt (Dependency #3 only — human-review queue ticket)

Implement only Dependency #3 (human-review queue builder) for LABEL-EXTENSION on `RERANK-REGRESSION-EVAL`. Do not perform Dependency #3b (silver labels), Dependency #4 (score rerun + reports), or any rework of Dependency #1+#2. Do not push.

Hard constraints (every one is a hard-stop):
- Do not modify `src/*`.
- Do not modify `eval/scripts/rerank_regression_eval.py`, `eval/scripts/rerank_regression_persist_top15.py`, `eval/scripts/llm_pregrade.py`, `eval/scripts/merge_labels.py`, or any existing test file.
- Do not modify `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl` or `silver_labels.jsonl`.
- Do not modify the Dep #1+#2 artifacts (`score_stage_top15.json`, `missing_label_manifest.json`, `missing_label_manifest_summary.txt`).
- Do not make any network call, do not load any model, do not spawn any external process.
- Do not import `eval.scripts.rerank_regression_eval`, `eval.scripts.rerank_regression_persist_top15`, `eval.scripts.llm_pregrade`, `eval.scripts.merge_labels`, `requests`, `httpx`, `openai`, `anthropic`, `torch`, `transformers`, or `sentence_transformers`.
- Do not populate `grade` or `grader_notes` — they must be `null` in every generated row.
- Do not rerun or unblock Phase 5.
- Leave Codex transcripts and graphify output untracked.

Allowed files to create for this ticket only:
1. NEW `eval/scripts/rerank_regression_build_review_queue.py`
2. NEW `eval/tests/test_rerank_regression_build_review_queue.py`
3. NEW `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.jsonl`
4. NEW `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv`
5. NEW `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue_summary.txt`

Read but do not change:
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_manifest.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/score_stage_top15.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/full_set_pool_snapshot.json`
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`
- `docs/superpowers/plans/2026-05-23-label-extension-rerank-regression.md`
- `src/**`

Implementation steps:

1. Create `eval/scripts/rerank_regression_build_review_queue.py`:
   - CLI entry: `python -m eval.scripts.rerank_regression_build_review_queue --run 2026-05-19-1846-nogit`.
   - Stdlib only (json, csv, pathlib, argparse, dataclasses, typing). No third-party imports.
   - Resolve run-relative paths from the `--run` argument.
   - Load: manifest JSON, score_stage_top15 JSON, full_set_pool_snapshot JSON, gold_labels JSONL.
   - Build the set of pre-existing gold-label keys: `{(row["qid"], int(row["tmdb_id"])) for row in gold_labels.jsonl}`. Treat a row as "already labeled" only when it has a non-null `gold_grade` field; if the file uses a different shape, fall back to presence of any `grade` field. (The existing schema separates `silver_grade` from `gold_grade`; rows with only `silver_grade` are NOT counted as gold and DO appear in the queue.)
   - Build per-key aggregation from manifest rows: for each unique `(qid, tmdb_id)` collect `modes_affected`, `models_affected`, `ranks_observed`, and `source_top_fields`. Look up `movie_key`, `title`, `query_text` from the manifest/snapshot. Look up `document_text_excerpt` from the snapshot pool (advanced+hybrid pools); first match wins; truncate to 500 chars after `\n`→space normalization; empty string if not found.
   - Filter out keys already in the gold-labeled set.
   - Sort rows by `(qid, tmdb_id)` ascending; assign `queue_position` as zero-based index.
   - Write atomically:
     - JSONL: each line is `json.dumps(row, sort_keys=True, ensure_ascii=False)`, then `\n`. Trailing newline after last row.
     - CSV: alphabetical header; list-typed fields joined with `|`; `ranks_observed` encoded as `mode:model:rank` triples joined with `|`. UTF-8, `\n` line endings, RFC 4180 quoting via the stdlib `csv` module with `lineterminator="\n"`.
     - Summary: deterministic text with `total_rows=N`, `counts_by_qid=...`, `counts_by_mode=...`, `counts_by_model=...`, `rows_with_excerpt=N`, `rows_without_excerpt=N`. Sort all dict outputs by key.
   - Atomic write helper writes to `.tmp` then `Path.replace`. On failure, leave any existing target file unchanged.
   - No print statements except a final one-line summary on stdout.

2. Create `eval/tests/test_rerank_regression_build_review_queue.py`:
   - Use tiny in-memory fixtures for manifest, snapshot, score-top15, gold labels.
   - Tests:
     a. Schema conformance: every generated row has required keys with correct types; `grade` and `grader_notes` are always `null`.
     b. Deterministic ordering: row order matches `(qid, tmdb_id)` ascending; `queue_position` matches index.
     c. Byte-identical rerun: JSONL, CSV, and summary bytes are identical across two consecutive runs.
     d. Gold exclusion: keys present in gold-label fixture with non-null `gold_grade` do NOT appear in the queue.
     e. Atomic-write rollback: monkeypatch `Path.replace` to raise; existing target file content is preserved.
     f. (Optional but recommended) Empty pool fallback: a key not found in any pool produces `document_text_excerpt == ""` (string, not null).

3. Run the sidecar once to produce the three queue artifacts.

4. Run validation commands listed under "For the human-review queue ticket (Dependency #3)" in this plan. Capture exit codes and key stdout lines.

5. Confirm:
   - `git diff -- src/` is empty.
   - `git diff -- eval/scripts/rerank_regression_eval.py` is empty.
   - `git diff -- eval/scripts/rerank_regression_persist_top15.py` is empty.
   - `git diff -- eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl` is empty.
   - No tracked changes outside the five NEW files listed above.

Final Codex report must include:
- Files changed.
- Test results and command exit codes.
- Sidecar stdout summary line.
- JSONL row count and the first three plus last three `queue_position` values.
- Counts from the summary file.
- Byte-identical rerun confirmation (hash of each artifact before/after second run).
- Confirmation that `grade` and `grader_notes` are `null` on every row.
- Confirmation that all hard-stop conditions are clean.
- Confirmation that Phase 5 remains BLOCKED.
