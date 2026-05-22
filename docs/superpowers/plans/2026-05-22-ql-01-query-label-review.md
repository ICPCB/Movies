# QL-01 - Query/Label Review (basic-succeeds / hybrid-fails cluster)

Status: READY FOR CODEX - not yet implemented
Date: 2026-05-22
Owner: Codex automation
Mode: review/eval-only
Branch: `automation/cinematch-accuracy-audit-full`
Risk: low - read-only aggregation of existing artifacts into new docs plus one
isolated eval script; no `src/*`, no label/query mutation, no model calls.

---

## Goal

For q05, q07, and q10, aggregate existing run artifacts into one evidence
record per query and classify each query into exactly one of five buckets,
distinguishing whether the **hybrid intent expansion** degrades the query,
whether the **query wording** or the **silver pregrade label** is the problem,
or whether the defect is a **reranker/blend** mechanics issue that needs a
later eval. Produce a concise classification report. No product code, no
`src/*`, no label or query mutation, no model or network calls.

## Background - verified label provenance

Confirmed against `gold_labels.jsonl`, `silver_labels.jsonl`, and
`merge_labels.py` on 2026-05-22:

| Query | Target title | tmdb_id | `grade` (eval) | `label_source` | `gold_grade` | `silver_grade` |
|-------|--------------|---------|----------------|----------------|--------------|----------------|
| q05 | Thanatomorphose | 144204 | 3 | `silver` | `null` | 3 |
| q07 | My Babysitter's a Vampire | 63700 | 3 | `silver` | `null` | 3 |
| q10 | [REC] | 8329 | 3 | `silver` | `null` | 3 |

- `gold_labels.jsonl` is a genuine merged file: 45 human-gold rows + 175 silver
  rows = 220. `metrics.json` is non-provisional
  (`label_source: "merged_gold_over_silver"`).
- The human regrade pass covered **only q03, q08, q12, q13**
  (`metrics.json.label_provenance.regraded_queries`). q05/q07/q10 have **zero**
  human-gold rows - every row is `label_source: "silver"`.
- Per `merge_labels.py`, when no human regrade exists for a `(qid, tmdb_id)`
  the silver grade passes through verbatim; the eval-consumed `grade` field
  equals `silver_grade`.
- Silver grades were produced by an LLM pregrade (`silver_labels.jsonl` records
  `"model": "llama3.2"`, a `confidence`, and a free-text `reason`).

**Consequence:** the QL-01 cluster ran on silver/LLM-pregrade labels only.
There is no human gold to defer to. A `silver_label_issue` finding is a
recommendation to run an RG-style human regrade for that query, not a dispute
of an existing human gold grade.

## Resolved review questions

Two questions were raised when this plan was drafted; both are resolved here:

1. Bucket 2 is named `silver_label_issue` (not `gold_label_issue` /
   `label_issue`) because q05/q07/q10 carry silver/LLM-pregrade eval grades and
   no human-gold rows.
2. The deterministic-script / judgment-report split is retained: the script
   emits deterministic evidence plus a coarse lean; the report assigns the
   final five-way classification.

## Method and architecture

### Two-layer split - deterministic vs judgment

- **Script** (`ql_query_label_review.py`): does only what is deterministically
  computable from existing artifacts. It builds a structured `evidence` block
  per query and emits a coarse `rule_based_lean`. It must not import `src.*`
  and must make no model/network calls.
- **Report** (`ql-01-query-label-review.md`): assigns the final five-way
  `classification` per query - applying the wording-vs-label-vs-expansion
  judgment the script cannot - and cites the artifact evidence for every call.

### Five-way classification (report `classification`)

| Bucket | Meaning | Recommended follow-up |
|--------|---------|-----------------------|
| `query_wording_issue` | The original query text under-specifies or mis-points the intent. | Propose a query-wording revision ticket (edits `eval/queries/v1.jsonl`) - external-review gated. |
| `silver_label_issue` | The silver/LLM pregrade picked a wrong or weakly justified grade for the target or a competitor. | Propose an RG-style human regrade ticket for that query (`build_regrade_sheet` -> human grade -> `check_regrade_sheet` -> `merge_labels`) - external-review gated. |
| `hybrid_expansion_issue` | The hybrid intent-expansion step rewrites/expands the query so retrieval intent shifts away from the target. | Propose a hybrid-expansion diagnostic/eval ticket - not a `src/*` fix in QL-01. |
| `reranker_blend_issue_later_eval` | The target is retrieved into the hybrid pool but rerank/blend mechanics demote it; a true pipeline defect. | Defer to a decomposition-enriched eval ticket (the recurring HY-FIX blocker). |
| `inconclusive` | Available evidence cannot support any of the above. | Propose targeted additional instrumentation. |

### Script `rule_based_lean` (coarse, deterministic)

The script emits one of three values only - it does not attempt the full
five-way split:

- `reranker_blend_issue_later_eval` - confident pure-mechanics case.
- `needs_analyst_review` - requires the report's judgment.
- `inconclusive` - required evidence missing.

Rule heuristics, with a `rule_trace` string list recording which fired:

- **R1 -> `reranker_blend_issue_later_eval`:** in both deterministic arms
  (`pinned`, `no_llm`) the target is in the rerank pool and
  `loss_stage in {rerank_demoted, rerank_recovered_final_demoted}` (retrieval
  succeeded, ranking demoted it).
- **R2 -> `needs_analyst_review`:** R1 does not hold and the required
  query/label/expansion evidence is present - the report must split this into
  `query_wording_issue`, `silver_label_issue`, or `hybrid_expansion_issue`.
- **R3 -> `inconclusive`:** required evidence is missing or contradictory
  (for example deterministic-arm evidence absent for a qid).

The report must resolve every `needs_analyst_review` lean into a final
five-way bucket with cited rationale.

### Artifact schema contract - `ql-01-query-label-review.v1`

```
{
  "schema_version": "ql-01-query-label-review.v1",
  "run_id": "2026-05-19-1846-nogit",
  "generated_at": "<UTC ISO8601 Z>",
  "source_artifacts": { "<name>": "<run-relative path>", ... },
  "label_provenance_note": "<one-line statement that q05/q07/q10 eval grades
      are silver/LLM-pregrade and the merged gold file holds human gold only
      for q03/q08/q12/q13>",
  "queries": [
    {
      "qid": "q07",
      "query_text": "<from eval/queries/v1.jsonl>",
      "tags": { ... },
      "target": {
        "tmdb_id": 63700,
        "title": "<from hy_fix artifacts>",
        "grade_used_for_eval": 3,
        "label_source": "silver",
        "gold_grade": null,
        "silver_grade": 3,
        "silver_pregrade": {
          "model": "<silver_labels.model or null>",
          "confidence": "<silver_labels.confidence or null>",
          "reason": "<silver_labels.reason or null>",
          "ts": "<silver_labels.ts or null>"
        }
      },
      "evidence": {
        "consolidated_fix_category": "<from localization / hy_fix artifact>",
        "arms_agree": true,
        "deterministic_arms": { "pinned": { ... }, "no_llm": { ... } },
        "mode_comparison": { "basic": { ... }, "advanced": { ... }, "hybrid": { ... } },
        "target_retrieved_by_mode": { "basic": true, "advanced": null, "hybrid": false },
        "hybrid_top5": [
          { "rank": 0, "tmdb_id": 411354, "title": "...", "grade": 1, "label_source": "silver" }
        ],
        "hybrid_expansion_text": "<expanded/intent query text or null>",
        "hybrid_expansion_source": "<run-relative trace path or null>"
      },
      "rule_based_lean": "needs_analyst_review",
      "rule_trace": [ "R2: target retrieved in both arms; not a pure rerank/blend demotion" ]
    }
  ],
  "decision": {
    "status": "analyst_classification_required",
    "next_action": "complete_ql_01_report_classification",
    "external_review": "optional_non_blocking_for_ql_01; required_for_any_label_or_query_change_followup"
  }
}
```

The script must follow the structural conventions of
`eval/scripts/hy_fix_mixed_q05_q10.py`: module-level `SCHEMA_VERSION` and
`*_RELATIVE_PATH` constants, a `QIDS` tuple, a dedicated
`QueryLabelReviewError(ValueError)`, `run()` / `build_review()` /
`main(argv)` / `_load_inputs()` functions, `_run_io.run_dir(run_id)` for the
output path, `output_path.parent.mkdir(parents=True, exist_ok=True)`, and
`_run_io._atomic_write_json(...)` to write the artifact.

## Files to change

- Create `eval/scripts/ql_query_label_review.py` - deterministic evidence
  aggregator and coarse lean.
- Create `eval/tests/test_ql_query_label_review.py` - unit tests.
- Create `eval/runs/2026-05-19-1846-nogit/analysis/query_label_review/q05_q07_q10_review.json`
  - evidence artifact (written by the script).
- Create `docs/superpowers/reports/ql-01-query-label-review.md` - the concise
  five-way classification report.
- Update `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` - append one QL-01
  checkpoint entry (append-only).
- This plan file (`docs/superpowers/plans/2026-05-22-ql-01-query-label-review.md`)
  is committed with commit 1.

## Files to read but not change

- `eval/queries/v1.jsonl` - query wording and tags for q05/q07/q10.
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl` - merged labels:
  `grade`, `label_source`, `gold_grade`, `silver_grade`.
- `eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl` - silver pregrade:
  `grade`, `model`, `confidence`, `reason`, `ts`.
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl` - per-mode retrieval and
  top items (for `target_retrieved_by_mode` and `hybrid_top5`).
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json`
  - `consolidated_fix_category` cross-check.
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_reranker_scoring/q07_reranker_scoring_analysis.json`
  - q07 `deterministic_arms`, `mode_comparison`, `candidate_summary`.
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_mixed/q05_q10_mixed_analysis.json`
  - q05/q10 `deterministic_arms`, `mode_comparison`.
- `eval/runs/2026-05-19-1846-nogit/analysis/error_report/per_query_mode.gold.jsonl`
  - per-query/per-mode top lists with tmdb_ids.
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_trace.jsonl`
  - primary source for hybrid expanded/intent query text.
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_gap/trace.jsonl` and
  `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_live_trace/trace.jsonl`
  - fallback sources for hybrid expansion text.
- `eval/scripts/_run_io.py` - run-directory path helpers.
- `eval/scripts/hy_fix_mixed_q05_q10.py` - reference implementation pattern.
- `eval/scripts/_schemas.py` - schema conventions.

If none of the three named trace files carries the hybrid expanded/intent
query text, set `hybrid_expansion_text` and `hybrid_expansion_source` to
`null`; do not glob for other files.

## Files forbidden

- `src/**` - no reads required, no edits.
- `eval/queries/v1.jsonl`, `eval/queries/v1.candidate.jsonl` - read-only.
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`,
  `eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl`, and any other
  `*_labels.jsonl` - read-only; QL-01 recommends label changes, never makes
  them.
- `eval/scripts/_run_io.py`, `eval/scripts/_schemas.py` - read-only.
- Any other existing file under `eval/scripts/`, any existing analysis
  artifact, and any other run directory.

## Execution steps and commit plan

### Task 1 - evidence aggregator and tests

Commit message: `eval: add QL-01 query/label review evidence`

1. Write `eval/tests/test_ql_query_label_review.py` with the failing tests
   listed under "Required tests" below.
2. Run `python -m unittest eval.tests.test_ql_query_label_review -v` and
   confirm it fails (module not found).
3. Implement `eval/scripts/ql_query_label_review.py` per the schema contract
   and `rule_based_lean` heuristics above, following the
   `hy_fix_mixed_q05_q10.py` structural pattern.
4. Run `python -m compileall eval/scripts` and
   `python -m unittest discover -s eval/tests -v`; confirm all pass.
5. Run `python -m eval.scripts.ql_query_label_review --run 2026-05-19-1846-nogit`
   and confirm the artifact is written.
6. Commit this plan file, the script, the test file, and the JSON artifact.
   The artifact lives under `eval/runs/**` (gitignored) - stage it with
   `git add -f`.

### Task 2 - classification report and ledger

Commit message: `docs: record QL-01 query/label review`

1. Write `docs/superpowers/reports/ql-01-query-label-review.md` per "Required
   report contents" below. Resolve every `needs_analyst_review` lean into a
   final five-way bucket.
2. Append one QL-01 checkpoint to
   `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` with the full required
   field set (timestamp, branch, ticket id, status, files changed, artifacts,
   commands, validation results, commit hash, failures/blockers, assumptions,
   next action, external review note).
3. Re-run the full validation suite (see "Validation commands").
4. Commit the report and the ledger entry.

### Required tests

`eval/tests/test_ql_query_label_review.py` must cover:

1. Target extraction selects the grade-3 row per qid from `gold_labels.jsonl`,
   and `target.grade_used_for_eval` equals the row's `grade` field.
2. Provenance fields are copied correctly: for q05/q07/q10
   `label_source == "silver"`, `gold_grade is None`, and
   `silver_grade == grade_used_for_eval`.
3. `target.silver_pregrade` is populated (`model`, `confidence`, `reason`,
   `ts`) when the target tmdb_id is present in `silver_labels.jsonl`; fields
   are `null` when absent.
4. `rule_based_lean == "reranker_blend_issue_later_eval"` when both
   deterministic arms show a rerank/blend demotion (R1).
5. `rule_based_lean == "needs_analyst_review"` for the mixed/ambiguous case
   where R1 does not hold but evidence is present (R2).
6. `rule_based_lean == "inconclusive"` when required deterministic-arm
   evidence is missing for a qid (R3).
7. `build_review` output has `schema_version == "ql-01-query-label-review.v1"`,
   exactly the qids q05/q07/q10, a non-empty `label_provenance_note`, and a
   `decision` block.
8. A `QueryLabelReviewError` is raised when a required input file is missing.

Tests must be deterministic and offline - no model or network calls.

### Required report contents

`docs/superpowers/reports/ql-01-query-label-review.md` must contain:

1. An opening **label-provenance statement**: q05/q07/q10 ran on silver/LLM
   pregrade labels only; the merged `gold_labels.jsonl` holds human-gold rows
   only for q03/q08/q12/q13; therefore a `silver_label_issue` finding here
   means "recommend an RG-style human regrade", not "dispute an existing human
   gold grade".
2. A per-query section for q05, q07, and q10, each with: the final
   `classification` (exactly one of the five buckets), the cited evidence from
   the artifact, the rationale, and the recommended follow-up from the bucket
   table.
3. A summary table (qid, target, classification, follow-up).
4. An overall recommendation and a suggested next ticket.

## Acceptance criteria

1. `python -m eval.scripts.ql_query_label_review --run 2026-05-19-1846-nogit`
   writes `analysis/query_label_review/q05_q07_q10_review.json`.
2. The script imports only stdlib and `eval.scripts._run_io`; it does not
   import `src`, load models, or call Ollama or the network.
3. The artifact validates: `schema_version == "ql-01-query-label-review.v1"`,
   exactly the qids q05/q07/q10, each `target` carries `grade_used_for_eval`,
   `label_source`, `gold_grade`, `silver_grade`, and a `silver_pregrade`
   block, and each `rule_based_lean` is one of
   `reranker_blend_issue_later_eval`, `needs_analyst_review`, `inconclusive`.
4. The artifact carries a non-empty `label_provenance_note`.
5. All unit tests pass; total test count is at least the prior 171 plus the
   new QL-01 tests, with zero failures.
6. `docs/superpowers/reports/ql-01-query-label-review.md` assigns each of
   q05/q07/q10 exactly one of the five buckets, with cited evidence and a
   recommended follow-up; no query is left as `needs_analyst_review`.
7. The report opens with the label-provenance statement described above.
8. `git diff --name-only -- src/` prints nothing; no `*_labels.jsonl` and no
   `eval/queries/*` file is modified.
9. `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` has one QL-01 entry with
   the full required field set.

## Validation commands

```powershell
git status --short --branch
git log --oneline --decorate -8
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.ql_query_label_review --run 2026-05-19-1846-nogit
python -c "import json; d=json.load(open(r'eval/runs/2026-05-19-1846-nogit/analysis/query_label_review/q05_q07_q10_review.json', encoding='utf-8')); qs={q['qid'] for q in d['queries']}; assert d['schema_version']=='ql-01-query-label-review.v1', d['schema_version']; assert qs=={'q05','q07','q10'}, qs; assert d.get('label_provenance_note'); leans={'reranker_blend_issue_later_eval','needs_analyst_review','inconclusive'}; assert all(q['rule_based_lean'] in leans for q in d['queries']); assert all(set(q['target'])>={'grade_used_for_eval','label_source','gold_grade','silver_grade','silver_pregrade'} for q in d['queries']); print('QL-01 artifact ok')"
git diff --name-only -- src/
```

## Dependencies

- Parent run `eval/runs/2026-05-19-1846-nogit` with all artifacts listed under
  "Files to read but not change" - verified present on 2026-05-22.
- `eval/scripts/_run_io.py` run-directory helpers.
- No external data, no compute budget, no credentials.

## Stop conditions

- Stop if any required input file under "Files to read but not change" is
  missing or unparseable.
- Stop before any `src/*` edit.
- Stop before any model, network, or Ollama call.
- Stop if a classification would require editing a label or query file - that
  is the QL-01 follow-up ticket and is external-review gated; record the
  recommendation instead.
- Stop if a classification would require running a new eval or model call -
  record it as `reranker_blend_issue_later_eval` instead of running it.
- Stop if validation fails and cannot be fixed within this ticket's allowed
  files.

## Reviewer

QL-01 itself is review/eval-only with no mutation: Codex self-review is
sufficient on this automation branch, marked SELF-REVIEWED in the ledger.
External review (optional, non-blocking) is recommended for any follow-up
ticket that would actually change a query wording or a label, including any
RG-style human regrade of q05/q07/q10.

## Codex prompt

> Implement ticket QL-01 per
> `docs/superpowers/plans/2026-05-22-ql-01-query-label-review.md`. Work TDD in
> two commits: Task 1 `eval: add QL-01 query/label review evidence`, Task 2
> `docs: record QL-01 query/label review`. Create only the files in "Files to
> change"; never touch `src/*`, `eval/queries/*`, or any `*_labels.jsonl`. The
> script aggregates existing run artifacts only - no `src` import, no
> model/network calls - and follows the structural pattern of
> `eval/scripts/hy_fix_mixed_q05_q10.py`. Run every command in "Validation
> commands" and paste the output. In the report, resolve every
> `needs_analyst_review` lean into a final five-way bucket with cited
> evidence, and open with the label-provenance statement. Append one QL-01
> ledger entry. Stop and report if any "Stop conditions" item triggers.
