---
title: Targeted human label re-grade pass — q12/q13 and q03/q08 gold labels
date: 2026-05-20
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (tooling tickets, one handoff at a time, human-approved)
human: fills gold labels; approves each dispatch and any merge
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 05-metrics-qc-and-labels.md
  - 08-prioritization-and-ticket-schema.md
parent_run: eval/runs/2026-05-19-1846-nogit
parent_plan: docs/superpowers/plans/2026-05-20-phase2-error-analysis-and-cleanup-plan.md
git_mode: no_git
---

# Label Re-grade Pass — Targeted Human Gold Labels (Phase 2 follow-on)

> **For agentic workers:** This plan is executed by **Codex CLI** for the two
> tooling tickets (RG-01, RG-02), one handoff at a time, with explicit human
> approval per handoff. The middle step (H-1) is **human-run** — the human
> fills gold labels by hand. Claude Code Pro reviews each diff and validation
> log. **No `src/*` edits. No ranking, retrieval, BM25, RRF, reranker,
> embedding, or pipeline change or re-run. No label merge.** All work is
> read-only diagnostic/QC tooling under `eval/` plus a human grading step.
> Tickets use the 9-field Codex handoff format from `CLAUDE.md`.

**Goal (one sentence):** Produce human gold labels for the specific
(query, candidate) pairs that drove the q12/q13 and q03/q08 signals in the
Phase 1 baseline, so the human can tell apart a *silver-label artifact* from a
*real retrieval/ranking miss* — without merging labels, without touching
`src/*`, and without changing ranking.

**Architecture:** Two small Codex-built tools under `eval/scripts/` bracket a
human grading step. RG-01 assembles a single frozen re-grade sheet; the human
fills it; RG-02 validates the filled sheet and reports silver-vs-gold
agreement. All outputs live in a new `eval/runs/<run_id>/analysis/regrade/`
subfolder, deliberately separate from `analysis/audit_silver_labels/` (which
CX-07's idempotent tool overwrites). Nothing in this plan reads `src/*` for
state; the tools consume only Phase 1 / Phase 2 artifacts.

**Tech stack:** Python 3.11+, stdlib only (`json`, `pathlib`, `argparse`,
`csv`, `dataclasses`, `collections`). Existing eval modules
(`eval.scripts._run_io`, `eval.scripts._schemas`). No new dependency.

---

## 0. Context and scope

### 0.1 Inputs this plan starts from

All inputs already exist in `eval/runs/2026-05-19-1846-nogit/`:

- **`analysis/audit_silver_labels/review_sheet.jsonl`** (CX-07 output) —
  **22 rows**, q12: 10, q13: 12. Each row already carries `gold_grade: null`
  and `gold_notes: null` stubs plus the full silver context (`silver_grade`,
  `silver_confidence`, `silver_reason`, `in_top_5_of`, `flag_reasons`).
- **`analysis/error_report/per_query_mode.jsonl`** (CX-06) — per-(qid, mode)
  top-5 records; the source for the q03/q08 batch.
- **`analysis/hybrid_stage_trace/{q03,q08}.*`** (CX-08) and
  **`analysis/case_studies/q03_q08_retrieval_debug.md`** (CX-09) — context
  for the q03/q08 candidates.
- `candidates.jsonl`, `silver_labels.jsonl`, `eval/queries/v1.jsonl` — for
  `overview` / `genres` / `silver_reason` / query text.

### 0.2 Explicit gates

These are hard rules for every ticket and step in this plan:

1. **No label merge in this plan.** This plan produces *filled gold grades
   inside a review sheet*. Merging gold over silver into `gold_labels.jsonl`
   and recomputing the authoritative `metrics.json` (spec §7.6) is a
   **separate, explicitly-gated** step (see §6) — not dispatched here unless
   the human approves it after seeing the results.
2. **No `src/*` edits.** All tooling lives under `eval/`. If a handoff would
   require touching `src/*`, stop and surface the gap to Claude.
3. **No ranking / retrieval / BM25 / RRF / reranker / embedding / pipeline
   change**, and no re-run of any of them. This plan reads only existing
   `2026-05-19-1846-nogit` artifacts.
4. **Grade relevance, not rank.** The human grades from metadata only
   (spec §6.6 standard); ranking position must not influence a grade —
   otherwise the silver-vs-gold comparison is circular.
5. **Codex implements tooling; the human fills labels; Claude reviews.**
   Each ticket dispatch is human-approved.

### 0.3 Honest caveat on q13

The q13 review sheet contains 12 retrieved candidates — but **not** the
canonical answer (`2001: A Space Odyssey` / HAL). A re-grade only re-grades
*retrieved* candidates. So a legitimate outcome for q13 is "every retrieved
candidate genuinely grades ≤ 1" — which is **not** a label artifact; it is a
real retrieval / corpus-coverage miss. The decision logic (§6) treats that as
a first-class result, not a failure of the pass.

### 0.4 Not in scope for this plan (explicit deferrals)

- `merge_labels.py` + authoritative `metrics.json` (spec §7.6) — gated; see §6.
- The 20% random QC sample, `qc_analyze.py`, and the adaptive-expansion loop
  (spec §7.7–7.9). This plan is a *targeted* re-grade of named queries, not
  the random QC sample.
- The Gradio `review_app.py` (spec §6.7). The raw-JSONL fallback UX is used.
- Any ablation or ranking-changes plan.

### 0.5 Caveats inherited from Phase 1 / Phase 2

- The run is silver-only (`label_source: "silver_only"`, `provisional: true`).
  This plan does **not** upgrade that status — that is the gated merge (§6).
- `metrics_provisional.json` stays provisional and never drives a decision
  while provisional (spec §7.6).

---

## 1. Ticket inventory and sequencing

| ID | Title | Type | Risk | Files-to-change | Depends on |
|---|---|---|---|---|---|
| RG-01 | `build_regrade_sheet.py` — assemble the combined frozen re-grade sheet | Codex | low-med | 3 | CX-06, CX-07 |
| H-1   | Human fills `gold_grade` / `gold_notes` | Human | — | 1 (the sheet) | RG-01 |
| RG-02 | `check_regrade_sheet.py` — post-fill validation + agreement report | Codex | low | 3 | H-1 |

**Dispatch order (each human-gated):** RG-01 → Claude review → **H-1 (human
grading)** → RG-02 → Claude review → §6 decision. Strictly serial; no parallel
work.

**Stop point for this plan:** after RG-02 reports `complete: true` and Claude
has reported the agreement summary, this plan is complete. The §6 decision
selects the next plan (label-merge plan, ranking-changes plan, or neither).

---

## 2. Shared conventions for every ticket below

### 2.1 Output convention

New tools write outputs to a **new** subfolder
`eval/runs/<run_id>/analysis/regrade/`, deliberately separate from
`analysis/audit_silver_labels/` — CX-07's tool is idempotent and overwrites
its own `review_sheet.jsonl`, so the human-owned re-grade sheet must not live
there. Tools must:

- Create the output folder via `Path.mkdir(parents=True, exist_ok=True)`.
- Write JSONL with `utf-8`, `newline="\n"`, one record per line.
- Write summary JSON via `_run_io._atomic_write_json`.
- Default `--run` to `_run_io.latest_run()`.

### 2.2 Grade scale (spec §6.6)

```
3 = perfect match  (the query clearly describes this exact movie)
2 = good match     (most of the query's themes / plot elements present)
1 = related        (some shared themes / genre but not a strong match)
0 = irrelevant     (no meaningful connection)
```

Hit predicates (spec §7.3): `hit@5` = any top-5 grade ≥ 2;
`strict_hit@5` = any top-5 grade == 3.

### 2.3 Validation convention

Every ticket's validation block runs, in order:

1. `python -m compileall eval/scripts` — must report `Listing ... OK`.
2. `python -m unittest discover -s eval/tests -v` — all tests pass; new
   tests included in the count.
3. The tool's own CLI smoke against `2026-05-19-1846-nogit`.

No git commands appear in any validation block (no-git mode).

### 2.4 Test pattern

New unit tests follow `eval/tests/test_run_io.py`: import the module under
test, swap `_run_io.PROJECT_ROOT` / `EVAL_DIR` / `RUNS_DIR` to a
`tempfile.TemporaryDirectory`, write small synthetic fixtures, assert on the
result. Tests must remain hermetic — never depend on the real
`eval/runs/2026-05-19-1846-nogit/` content.

### 2.5 What "complete" means for each ticket

1. All files in "Files to change" exist with the expected content.
2. All unit tests in the ticket pass.
3. The CLI smoke against `2026-05-19-1846-nogit` runs and produces the
   declared artifacts.
4. Codex has reported outputs back per `AGENTS.md` validation rules.
5. Claude Code Pro has reviewed the diff against the declared file list and
   the validation log.

---

## 3. Ticket RG-01 — `build_regrade_sheet.py`

### 1. Goal

Assemble one combined, **frozen, human-owned** re-grade sheet: batch 1 = the
22 CX-07 q12/q13 rows carried over verbatim; batch 2 = the q03/q08 candidates
(the distinct union of each query's top-5 across basic/advanced/hybrid). Write
it once to a path that no idempotent tool overwrites.

### 2. Files to change

- Create: `eval/scripts/build_regrade_sheet.py`
- Create: `eval/tests/test_build_regrade_sheet.py`
- Modify (one-line append to scripts list only): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `_schemas.py`.
- `eval/runs/2026-05-19-1846-nogit/analysis/audit_silver_labels/review_sheet.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/error_report/per_query_mode.jsonl`
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl`, `silver_labels.jsonl`
- `eval/queries/v1.jsonl`

### 4. Acceptance criteria

1. CLI: `python -m eval.scripts.build_regrade_sheet --run <run_id>`
   (`--run` defaults to `_run_io.latest_run()`).
2. **Batch 1** = every row of `audit_silver_labels/review_sheet.jsonl`
   carried over with all existing keys preserved unchanged, plus two added
   keys `batch: 1` and `batch_purpose: "label_artifact_audit"`.
3. **Batch 2** = for `q03` and `q08`, the **distinct union of `tmdb_id`s
   appearing in any mode's top-5** in `per_query_mode.jsonl`. Each batch-2
   row has the **same key set as a batch-1 row** —
   `qid, tmdb_id, query, title, year, overview, genres, silver_grade,
   silver_confidence, silver_reason, in_top_5_of, flag_reasons, gold_grade,
   gold_notes` — plus `batch: 2` and
   `batch_purpose: "retrieval_miss_audit"`. Field sources:
   - `title, year, silver_grade, silver_confidence` — from
     `per_query_mode.jsonl` top records.
   - `overview, genres` — from `candidates.jsonl`.
   - `silver_reason` — from `silver_labels.jsonl` (null if the pair has no
     silver row).
   - `query` — from `eval/queries/v1.jsonl`.
   - `in_top_5_of` — sorted list of modes whose top-5 contain the id.
   - `flag_reasons` — `["regrade_q03_q08"]` plus one `"top_5_<mode>"` entry
     per mode in `in_top_5_of`.
   - `gold_grade`, `gold_notes` — `null`.
4. Output artifacts in `eval/runs/<run_id>/analysis/regrade/`:
   - `regrade_sheet.jsonl` — batch-1 rows first, then batch-2; stable sort by
     `(batch, qid, tmdb_id)`.
   - `regrade_manifest.json`:
     ```json
     {
       "run_id": "2026-05-19-1846-nogit",
       "built_from": {
         "q12_q13_sheet": "analysis/audit_silver_labels/review_sheet.jsonl",
         "q03_q08_source": "analysis/error_report/per_query_mode.jsonl"
       },
       "rows_total": 0,
       "rows_by_batch": {"1": 0, "2": 0},
       "rows_by_qid": {"q12": 0, "q13": 0, "q03": 0, "q08": 0},
       "silver_grade_snapshot": {"<qid>:<tmdb_id>": 0}
     }
     ```
     `silver_grade_snapshot` records each row's `silver_grade` (value or
     `null`) keyed by `"<qid>:<tmdb_id>"`, so RG-02 can prove the human did
     not alter silver fields.
5. **Refuses to overwrite.** If `analysis/regrade/regrade_sheet.jsonl`
   already exists, exit non-zero with the message
   `regrade_sheet.jsonl already exists — delete it manually to rebuild` and
   write nothing. There is no `--force` flag (this protects in-progress
   human edits).
6. **Writes nothing else.** The tool must not modify `silver_labels.jsonl`,
   `candidates.jsonl`, the `analysis/audit_silver_labels/` folder, or any
   metrics file; it must not create `gold_labels.jsonl`; it must not merge
   labels.
7. `test_build_regrade_sheet.py` includes at least:
   - `test_batch1_rows_carried_verbatim` — every non-added key of a batch-1
     row equals the source CX-07 row.
   - `test_batch2_is_top5_union` — batch-2 tmdb_ids equal the distinct
     union of the fixture's per-mode top-5 for q03/q08.
   - `test_row_keysets_match_across_batches` — every row, both batches, has
     exactly the 16-key set in criterion 3.
   - `test_refuses_to_overwrite_existing_sheet` — second invocation exits
     non-zero and leaves the existing sheet byte-identical.
   - `test_manifest_counts_and_snapshot` — `rows_total` / `rows_by_batch` /
     `rows_by_qid` are consistent, and `silver_grade_snapshot` has one entry
     per row.

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.build_regrade_sheet --run 2026-05-19-1846-nogit
python -c "import json,pathlib; rows=[json.loads(l) for l in pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_sheet.jsonl').read_text(encoding='utf-8').splitlines()]; print(len(rows), sum(r['batch']==1 for r in rows), sum(r['batch']==2 for r in rows))"
```

Expected:

1. `compileall` passes.
2. All tests pass; new test count is `previous + 5`.
3. CLI prints output paths and exits 0; both artifacts exist.
4. The one-liner prints `<total> 22 <batch2-count>` — batch-1 count is 22;
   `<total>` equals `regrade_manifest.json.rows_total`. The exact batch-2 and
   total counts are left to the implementer; the test asserts internal
   consistency, not a magic number.

### 6. Dependencies

CX-06 (`error_report` output) and CX-07 (`audit_silver_labels` output) —
both complete in `eval/runs/2026-05-19-1846-nogit/`.

### 7. Risk level

**Low-medium.** The one real risk is clobbering the CX-07 sheet or emitting
gold / merge artifacts. Criteria 5–6 and the tests forbid both; the output
folder is a fresh sibling subtree.

### 8. Reviewer

Claude Code Pro. Specifically verifies: the refuse-to-overwrite path works;
batch-1 rows are byte-faithful aside from the two added keys; nothing is
written outside `analysis/regrade/`; no `gold_labels.jsonl` is created.

### 9. Codex prompt

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket RG-01 exactly as specified in
docs/superpowers/plans/2026-05-20-label-regrade-pass-plan.md
section 3 ("Ticket RG-01 -- build_regrade_sheet.py").

You may edit ONLY:
  - eval/scripts/build_regrade_sheet.py     (create)
  - eval/tests/test_build_regrade_sheet.py  (create)
  - eval/README.md                          (append ONE line to the scripts
                                             list -- do not reflow other
                                             content)

Do not edit any other file. No src/* edits. Do not run pip installs.

HARD CONSTRAINTS:
  - Output goes ONLY to eval/runs/<run_id>/analysis/regrade/. The tool MUST
    NOT modify silver_labels.jsonl, candidates.jsonl, the
    analysis/audit_silver_labels/ folder, or any metrics file.
  - The tool MUST NOT create gold_labels.jsonl and MUST NOT merge labels.
  - If analysis/regrade/regrade_sheet.jsonl already exists, exit non-zero
    and write nothing. There is no --force flag.
  - Do not re-execute retrieval, BM25, RRF, reranker, LLM, or pipelines.

Acceptance criteria 1-7 in section 3 are all required. Run the validation
commands in section 3 step 5. Report back per AGENTS.md validation rules
(files changed, commands run, test counts, failures verbatim, assumptions).
```

---

## 4. Step H-1 — Human re-grade protocol

This step is **human-run**. No agent edits the sheet.

The human opens `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_sheet.jsonl`
in any text editor (spec §6.7 raw-JSONL fallback UX) and, for each row:

- **`gold_grade`** — assign **0 / 1 / 2 / 3** using the §2.2 (spec §6.6)
  rubric, graded **strictly from the `overview` / `genres` / `title` shown**,
  exactly as the silver grader was instructed. No `null` in gold — a
  deliberate pass resolves every row to a grade.
- **`gold_notes`** — **required** (one sentence, stating why) whenever
  `gold_grade != silver_grade`. For an unchanged grade a short
  `"confirms silver"` is encouraged but optional.
- **Order:** finish all **batch 1 (q12/q13)** rows first, then **batch 2
  (q03/q08)**. Stopping after batch 1 is allowed — RG-02 reports per-batch
  completion and the human can resume later.
- **Do not** edit any field other than `gold_grade` / `gold_notes`; do not
  add, remove, or reorder rows.
- **Do not** consult ranking position while grading (gate 0.2.4) — grade
  relevance to the query, not where the pipeline placed the candidate.

Output of this step: the same `regrade_sheet.jsonl`, with `gold_grade` /
`gold_notes` filled in.

---

## 5. Ticket RG-02 — `check_regrade_sheet.py`

### 1. Goal

Validate the human-filled re-grade sheet for integrity and completeness, and
emit a silver-vs-gold agreement report — **without merging anything**.

### 2. Files to change

- Create: `eval/scripts/check_regrade_sheet.py`
- Create: `eval/tests/test_check_regrade_sheet.py`
- Modify (one-line append to scripts list only): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `_schemas.py`.
- `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_sheet.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_manifest.json`

### 4. Acceptance criteria

1. CLI: `python -m eval.scripts.check_regrade_sheet --run <run_id>`
   (`--run` defaults to `_run_io.latest_run()`).
2. **Structural checks** — any failure exits non-zero with a message naming
   the offending row:
   - every row in `regrade_manifest.json` is still present; none added,
     removed, or reordered;
   - every non-gold field is byte-identical to RG-01's output;
   - each row's `silver_grade` equals `regrade_manifest.silver_grade_snapshot`;
   - each non-null `gold_grade` is in `{0, 1, 2, 3}`;
   - `gold_notes` is a non-empty string wherever `gold_grade != silver_grade`.
3. **Completeness is a status, not an error.** A structurally valid but
   partly-blank sheet (any `gold_grade` still `null`) exits **0** with
   `complete: false`.
4. Output `eval/runs/<run_id>/analysis/regrade/regrade_check.json`:
   ```json
   {
     "run_id": "2026-05-19-1846-nogit",
     "complete": false,
     "rows_total": 0,
     "rows_filled": 0,
     "pending_by_batch": {"1": 0, "2": 0},
     "agreement": {
       "exact": null,
       "within_1": null,
       "disagree_ge1_count": 0,
       "disagree_ge2_count": 0
     },
     "threshold_crossings": [
       {"qid": "q12", "tmdb_id": 27205, "silver_grade": 1, "gold_grade": 3,
        "crossing": "silver<2->gold>=2; silver<3->gold==3"}
     ],
     "by_qid": {
       "q12": {"filled": 0, "changed": 0},
       "q13": {"filled": 0, "changed": 0},
       "q03": {"filled": 0, "changed": 0},
       "q08": {"filled": 0, "changed": 0}
     }
   }
   ```
   - `agreement.exact` = fraction of filled rows with `gold_grade ==
     silver_grade`; `agreement.within_1` = fraction with
     `abs(gold_grade - silver_grade) <= 1`; `disagree_ge1_count` /
     `disagree_ge2_count` = counts with absolute difference ≥ 1 / ≥ 2.
     All four populate only when `complete: true` (else `null` / `0`).
   - `threshold_crossings` lists every **filled** row where the gold grade
     crosses a hit boundary — `silver < 2` ↔ `gold >= 2`, or `silver < 3`
     ↔ `gold == 3` — i.e. the rows that change a `hit@5` / `strict_hit@5`
     verdict. (`silver_grade == null` counts as below every threshold.)
   - `by_qid.<qid>.changed` = count of filled rows with
     `gold_grade != silver_grade`.
5. **Read-only on labels.** The tool must not write `gold_labels.jsonl`,
   must not modify `silver_labels.jsonl` or `regrade_sheet.jsonl`, and must
   not write any metrics file. It must not merge labels. Its only output is
   `regrade_check.json`.
6. `test_check_regrade_sheet.py` includes at least:
   - `test_detects_tampered_silver_field` — a row whose `silver_grade` was
     changed vs the manifest snapshot → exit non-zero.
   - `test_detects_added_or_removed_row` — row count differs from the
     manifest → exit non-zero.
   - `test_missing_note_on_changed_grade_fails` — a row with
     `gold_grade != silver_grade` and empty `gold_notes` → exit non-zero.
   - `test_incomplete_sheet_exits_zero_status_false` — a structurally valid
     sheet with a `null` `gold_grade` → exit 0, `complete: false`.
   - `test_agreement_and_threshold_crossings_on_complete_fixture` — a fully
     filled fixture → `agreement` populated and `threshold_crossings`
     contains exactly the boundary-crossing rows.

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.check_regrade_sheet --run 2026-05-19-1846-nogit
```

Expected:

1. `compileall` passes.
2. All tests pass; new test count is `previous + 5`.
3. The CLI smoke runs against the **as-yet-unfilled** real sheet, exits 0,
   and `regrade_check.json` reports `complete: false` with the pending
   counts. The authoritative validation pass runs again after H-1 is done.

### 6. Dependencies

RG-01 (produces `regrade_sheet.jsonl` + `regrade_manifest.json`) and H-1
(human fills the sheet). RG-02's *implementation* can be reviewed before H-1
finishes; its *decision-bearing run* happens after H-1.

### 7. Risk level

**Low.** Pure read / validate. The risk is a check that fails to catch
tampering; mitigated by tests in criterion 6.

### 8. Reviewer

Claude Code Pro. Specifically verifies: no `gold_labels.jsonl` is written;
`silver_labels.jsonl` and `regrade_sheet.jsonl` are untouched; no merge; the
structural-tampering checks actually fail on the negative-test fixtures.

### 9. Codex prompt

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket RG-02 exactly as specified in
docs/superpowers/plans/2026-05-20-label-regrade-pass-plan.md
section 5 ("Ticket RG-02 -- check_regrade_sheet.py").

You may edit ONLY:
  - eval/scripts/check_regrade_sheet.py     (create)
  - eval/tests/test_check_regrade_sheet.py  (create)
  - eval/README.md                          (append ONE line to the scripts
                                             list)

Do not edit any other file. No src/* edits. Do not run pip installs.

HARD CONSTRAINTS:
  - The tool is read-only on labels. It MUST NOT write gold_labels.jsonl,
    MUST NOT modify silver_labels.jsonl or regrade_sheet.jsonl, and MUST NOT
    write any metrics file. It MUST NOT merge labels.
  - Its only output is
    eval/runs/<run_id>/analysis/regrade/regrade_check.json.
  - Do not re-execute retrieval, BM25, RRF, reranker, LLM, or pipelines.

Acceptance criteria 1-6 in section 5 are all required. Run the validation
commands in section 5 step 5; the CLI smoke runs against the as-yet-unfilled
sheet and must exit 0 with complete:false. Report back per AGENTS.md
validation rules (files changed, commands run, test counts, failures
verbatim, assumptions).
```

---

## 6. What decision becomes possible after the re-grade

Once RG-02 reports `complete: true`, `regrade_check.json` answers — per
query — whether each observed "miss" was a silver-label artifact or a real
retrieval / ranking miss.

| Outcome | Evidence in `regrade_check.json` | Meaning |
|---|---|---|
| **1. Silver artifact confirmed** | `threshold_crossings` rows where `silver < 2` but `gold >= 2` (especially q12 — e.g. Inception, currently silver 1 / low) | The "miss" was grader conservatism, **not** retrieval. The fix is label correction, not ranking. |
| **2. Real retrieval / ranking miss confirmed** | (a) q03/q08 rows where gold **confirms** a high grade (e.g. WALL·E, EEAAO at grade 3) that the pipeline ranked outside top-5; or (b) a query where **no** retrieved candidate earns `gold >= 2` (true coverage miss — the likely q13 shape, §0.3) | The pipeline genuinely failed. The fix lives in retrieval / ranking or corpus coverage. |
| **3. Ranking-changes plan justified?** | Outcome 2(a) holding for q03/q08 — gold-confirmed strong positives that **hybrid** demotes relative to **advanced** | If yes → open a ranking-changes plan, **gated by a paired-bootstrap eval** (spec §7.4). If outcome 1 dominates → no ranking plan; correct labels and re-baseline instead. |

**Gated follow-on (NOT in this plan).** If the human decides to act on the
results, the next step is `merge_labels.py` → `gold_labels.jsonl` (gold
overrides silver) → authoritative `metrics.json` with `provisional: false`
(spec §7.6). That merge requires explicit human approval and is a separate
plan. Nothing in RG-01 or RG-02 performs or prepares the merge.

---

## 7. Self-review against this plan's own constraints

1. **Starts from the CX-07 sheet** — §0.1; RG-01 criterion 2 carries the 22
   rows over verbatim. ✓
2. **q12/q13 first** — they are batch 1; the H-1 protocol orders batch 1
   before batch 2; RG-02 reports per-batch completion. ✓
3. **q03/q08 included as a second batch** — RG-01 criterion 3. ✓
4. **Defines how the human fills `gold_grade` / `gold_notes`** — §4 protocol
   plus the §2.2 rubric. ✓
5. **No label merge unless approved** — §0.2 gate 1; §6 gated follow-on;
   RG-01 and RG-02 are both forbidden from writing `gold_labels.jsonl` or
   merging. ✓
6. **No `src/*` edits** — every "Files to change" entry is under `eval/`. ✓
7. **No ranking / retrieval / BM25 / RRF / reranker / embedding / pipeline
   change or re-run** — the tools read existing artifacts only; every Codex
   prompt restates this. ✓
8. **States validation after the human labels are filled** — RG-02 (§5),
   re-run after H-1. ✓
9. **Explains the post-re-grade decision** — §6, three outcomes. ✓
10. **No-git mode honored** — no `git` command in any validation block. ✓

---

## 8. Execution handoff

Per `CLAUDE.md` autonomy boundaries, Claude does not dispatch Codex
automatically. The human approves each ticket before its Codex prompt is
sent. Suggested order:

1. Human approves RG-01 → Codex implements → Claude reviews diff and
   validation log → human accepts.
2. **H-1:** human fills `gold_grade` / `gold_notes` in `regrade_sheet.jsonl`.
3. Human approves RG-02 → Codex implements → Claude reviews → human accepts.
4. Human runs RG-02 against the filled sheet → Claude reports the agreement
   summary and the `threshold_crossings`.

When RG-02 reports `complete: true` and Claude has summarized the result,
this plan's stop point is reached. The §6 decision selects the next plan:
a gated label-merge plan, a ranking-changes plan, or neither.
