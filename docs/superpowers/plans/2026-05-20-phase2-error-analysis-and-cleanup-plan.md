---
title: Phase 2 — Error analysis, label audit, hybrid diagnosis (with cleanup)
date: 2026-05-20
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one handoff at a time, human-approved)
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 03-six-phase-plan.md
  - 05-metrics-qc-and-labels.md
  - 08-prioritization-and-ticket-schema.md
  - 09-ai-handoff-and-conflict-protocol.md
parent_run: eval/runs/2026-05-19-1846-nogit
git_mode: no_git
---

# Phase 2 — Error Analysis, Label Audit, Hybrid Diagnosis (with Cleanup)

> **For agentic workers:** This plan is executed by **Codex CLI**, one handoff
> at a time, with explicit human approval per handoff. Claude Code Pro reviews
> each diff and the resulting validation log before the next handoff is
> dispatched. **No `src/*` edits in this plan.** No ranking, retrieval, BM25,
> RRF, or reranker changes. The plan adds read-only diagnostic tooling under
> `eval/` plus one small fix in `eval/scripts/_run_io.py`. Tickets use the
> 9-field Codex handoff format from `CLAUDE.md` (Codex handoff format §).

**Goal (one sentence):** Add error-analysis and hybrid-diagnostic tooling on
top of the Phase 1 baseline so the human can decide *which* observed failures
are real retrieval problems and *which* are silver-label artifacts — without
touching ranking — and fix the one harness bug (`latest_run()` shadowing) that
blocks reproducible reruns.

**Architecture:** All new code lives under `eval/scripts/` and `eval/tests/`.
Each new tool is read-only against a run directory and writes only into a
subfolder of that run (`eval/runs/<run_id>/analysis/`). The one mutating fix
is scoped to `eval/scripts/_run_io.py`. No `src/*` files are read for state
beyond what Phase 1 already reads (the new tools consume `candidates.jsonl`
and `silver_labels.jsonl` produced by `run_pipelines.py` and
`llm_pregrade.py`).

**Tech Stack:** Python 3.11+, stdlib only (`json`, `pathlib`, `argparse`,
`re`, `csv`, `dataclasses`, `collections`). Existing eval modules
(`eval.scripts._run_io`, `eval.scripts._schemas`). No new third-party
dependency.

---

## 0. Context and what this plan does NOT do

### 0.1 What the Phase 1 baseline showed (run `2026-05-19-1846-nogit`)

- 20/20 queries graded, 220/220 candidates pregraded, `parse_rate = 1.000`,
  zero null exclusions (silver covers every retrieved candidate).
- Headline ordering: **advanced ≥ basic > hybrid** on `strict_hit@5`
  (advanced 0.45, basic 0.45, hybrid 0.20). CIs are wide (half-widths
  0.15–0.18 on strict metrics at @5) — this is suggestive, not conclusive.
- Per-query inspection flagged four candidates for follow-up:
  - **q03** ("a trash robot falls in love in space") — looks like a real
    retrieval miss across multiple modes; the obvious answer should appear
    in top-5 for a low-vocab plot description.
  - **q08** ("multiverse family comedy about taxes, laundry, martial
    arts...") — same shape: low-/medium-vocab plot description; real
    retrieval miss is plausible.
  - **q12** ("a heist movie about folding cities and stolen dreams") — the
    description targets a real movie that may not be in the dataset; the
    "miss" is likely a silver-label cliff (grader unwilling to grade ≥ 2
    because no overview matches), not a ranking failure.
  - **q13** ("lonely astronaut debates a polite machine") — same shape as
    q12; likely silver-label conservatism on `2001: A Space Odyssey` rather
    than a retrieval failure.

### 0.2 Explicit gates

These are hard rules for every ticket in this plan and any follow-up:

1. **No ranking tuning based on q12 or q13** until a human has reviewed
   their silver labels and confirmed whether the grades are conservative.
   Treat them as *label-audit candidates*, not as retrieval bugs.
2. **q03 and q08 are the first real retrieval-debug targets.** Diagnostic
   work in this plan must produce per-query traces for these two queries
   before any wider analysis.
3. **No edits to `src/*`** in any ticket in this plan. All work goes under
   `eval/`. If a Codex handoff would require touching `src/*`, stop and
   surface the gap to Claude.
4. **No ablation runs, no full pipeline reruns, no ChromaDB
   re-ingestion.** All Phase 2 work in this plan reads from the existing
   `eval/runs/2026-05-19-1846-nogit/` artifacts.
5. **Codex CLI is the implementer.** Claude Code Pro plans and reviews.
   The human approves each ticket dispatch and each merge.

### 0.3 Not in scope for this plan (explicit deferrals)

The following are part of the broader Phase 2 spec
([05-metrics-qc-and-labels.md](../specs/accuracy-audit/05-metrics-qc-and-labels.md))
but are **deferred** to a later plan once the diagnostic tools below have
produced enough evidence to scope them properly:

- **Full Gradio review app (`review_app.py`)** — §6.7 in the spec. We do
  not need a full UI yet; the label audit in this plan produces a small,
  finite review sheet for q12/q13 (and any other manually selected
  queries) that the human can read in any editor.
- **`merge_labels.py` and `metrics.json`** — §7.6. Merged labels and the
  authoritative (non-provisional) metrics file wait until at least the
  q12/q13 audit closes.
- **`qc_analyze.py` and the 20% random QC sample** — §7.7–§7.9. The
  random QC sample is meaningful only after enough gold labels exist; we
  do not start that loop in this plan.
- **`build_review_sheet.py` auto-flag rules at full scope** — §6.7. The
  CX-07 ticket below produces a *targeted* review sheet for q12/q13 with
  a small auto-flag rule set, not the full flag set the spec describes.
- **Ablations (`ablate.py`) and Phase 3 code audit.**

These deferrals are intentional: until the human knows whether
q12/q13/hybrid signals are real, building the full QC pipeline would
optimize for the wrong inputs.

### 0.4 Caveats inherited from Phase 1

- The run artifacts are silver-only (`label_source: "silver_only"`,
  `provisional: true`). Nothing in this plan upgrades that status.
- `_run_io.latest_run()` currently picks `eval/runs/cx03-smoke-debug/`
  over `2026-05-19-1846-nogit/` because the alphabetical sort puts `c`
  after `2`. Ticket **CX-FIX-01** below fixes this; until it lands,
  every Codex command in this plan must pass `--run` explicitly.

---

## 1. Ticket inventory and sequencing

| ID | Title | Risk | Files-to-change count | Depends on |
|---|---|---|---|---|
| CX-FIX-01 | `latest_run()` ignores non-canonical run dirs | low | 2 | — |
| CX-06     | `error_report.py` — per-query × per-mode error report | low | 3 | CX-FIX-01 |
| CX-07     | `audit_silver_labels.py` — targeted review sheet for q12/q13 | low | 3 | CX-06 |
| CX-08     | `hybrid_stage_trace.py` — per-qid intermediate-stage dump | medium | 3 | CX-06 |
| CX-09     | q03/q08 retrieval-debug case study (markdown report only) | low | 1 | CX-06, CX-08 |

**Dispatch order:** CX-FIX-01 → CX-06 → (CX-07 and CX-08 in parallel only
if the human explicitly approves; otherwise serial in that order) → CX-09.

**Stop point for this plan:** after CX-09 lands and Claude has reviewed it,
the plan is complete. The next plan decides whether to (a) act on q03/q08
findings, (b) re-grade q12/q13, or (c) escalate the hybrid pipeline to a
ranking-changes plan.

---

## 2. Shared conventions for every ticket below

These conventions apply to every Codex handoff in this plan. They are stated
once here and referenced from each ticket.

### 2.1 Output convention

Each new analysis tool writes its outputs to
`eval/runs/<run_id>/analysis/<tool_name>/`. The harness already treats
`eval/runs/<run_id>/` as the single source of truth for a run, and adding a
sibling subfolder keeps analyses self-contained and discardable.

Tools must:

- Create the output folder via `Path.mkdir(parents=True, exist_ok=True)`.
- Write JSONL records with `utf-8`, `newline="\n"`, one record per line.
- Write summary JSON via `_run_io._atomic_write_json` so partial writes do
  not corrupt artifacts.
- Use `_run_io.latest_run()` only after CX-FIX-01 lands; before that, every
  CLI must require `--run`.

### 2.2 Validation convention

Every ticket's validation block runs three checks, in this order:

1. `python -m compileall eval/scripts` — must report `Listing ... OK`.
2. `python -m unittest discover -s eval/tests -v` — all tests pass; new
   tests included in the count.
3. The tool's own CLI smoke against the existing baseline run
   `2026-05-19-1846-nogit` — exact command listed per ticket.

No git commands appear in any validation block (no-git mode per
[Phase 1 plan §0](2026-05-19-phase1-eval-harness-plan.md)).

### 2.3 Test pattern

New unit tests follow the pattern in `eval/tests/test_run_io.py`: import the
module under test, swap `_run_io.PROJECT_ROOT` / `EVAL_DIR` / `RUNS_DIR` to a
`tempfile.TemporaryDirectory`, write small synthetic JSONL fixtures into the
temp run dir, call the function, assert on the result. Do **not** depend on
the real `eval/runs/2026-05-19-1846-nogit/` content from inside unit tests
— that artifact is the human's; tests must remain hermetic.

### 2.4 What "complete" means for each ticket

A ticket is complete when:

1. All files in "Files to change" exist with the expected content.
2. All unit tests in the ticket pass.
3. The CLI smoke against `2026-05-19-1846-nogit` runs and produces the
   declared artifacts.
4. Codex has reported the outputs back per `AGENTS.md` validation block
   (files changed, commands run, test counts, failures verbatim).
5. Claude Code Pro has reviewed the diff against the declared file list
   and the validation log.

---

## 3. Ticket CX-FIX-01 — `latest_run()` ignores non-canonical run dirs

### 1. Goal

When `eval/runs/current_run.txt` is absent, `_run_io.latest_run()` must
return the newest directory whose name matches the canonical timestamped
run-id pattern (`YYYY-MM-DD-HHMM` optionally followed by `-` or `_` and a
suffix), ignoring debug-named directories like `cx03-smoke-debug` so they
cannot shadow real runs under alphabetical sorting.

### 2. Files to change

- `eval/scripts/_run_io.py`
- `eval/tests/test_run_io.py`

### 3. Files to read but NOT change

- `eval/runs/2026-05-19-1846-nogit/run_manifest.json` (illustrative only —
  no test reads it).
- `eval/runs/cx03-smoke-debug/run_manifest.json` (illustrative only).
- `docs/superpowers/specs/accuracy-audit/04-phase1-eval-harness.md` §6.1
  for the directory-name convention.

### 4. Acceptance criteria

1. A new module-level regex constant exists in `_run_io.py`:
   ```python
   _RUN_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}([-_].*)?$")
   ```
   It matches `2026-05-19-1846-nogit` and
   `2026-05-19-1730-3680020-ablation-rrf_k_5`. It does NOT match
   `cx03-smoke-debug`, `current_run.txt`, or `analysis`.
2. `latest_run()` retains the `current_run.txt` precedence path unchanged.
3. When the pointer is absent, `latest_run()` scans `RUNS_DIR.iterdir()`
   and considers only directories whose name `_RUN_TIMESTAMP_RE.fullmatch`
   succeeds on.
4. If no timestamped directories exist, `latest_run()` raises
   `FileNotFoundError("no canonical eval runs found in eval/runs/ "
   "(expected directory names like YYYY-MM-DD-HHMM-*)")`.
5. Three new tests in `test_run_io.py` pass:
   - `test_latest_run_ignores_non_canonical_dirs` — creates one timestamp
     dir and one debug-named dir; asserts the timestamp dir is returned.
   - `test_latest_run_picks_newest_timestamped_dir` — creates two
     timestamp dirs differing only in `HHMM`; asserts the later one wins.
   - `test_latest_run_raises_when_no_canonical_dirs` — creates only
     `cx03-smoke-debug`; asserts `FileNotFoundError` with the exact
     message in criterion 4.
6. All existing tests in `test_run_io.py` still pass unchanged (no
   modifications to existing test bodies; the regex change MUST be
   backward compatible with the existing
   `test_write_config_snapshot_and_latest_run` fixture, which uses
   `2026-05-19-1530-nogit` and `2026-05-19-1531-nogit`).

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -c "from eval.scripts._run_io import latest_run; print(latest_run())"
```

Expected:

1. `Listing 'eval/scripts'... OK` (or equivalent — no failures).
2. All `eval/tests/*.py` tests pass; new test count is `existing + 3`.
3. The one-liner prints `2026-05-19-1846-nogit` (NOT `cx03-smoke-debug`).

### 6. Dependencies

None. This ticket is the prerequisite for every subsequent ticket in this
plan, because the new tools rely on `latest_run()` returning the real
baseline when `--run` is omitted.

### 7. Risk level

**Low.** Two-file change, isolated to a single helper. No production
behavior changes; only the harness-side `latest_run()` resolution.

### 8. Reviewer

Claude Code Pro reviews the diff against the declared file list. Human
gives final approval.

### 9. Codex prompt

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket CX-FIX-01 exactly as specified in
docs/superpowers/plans/2026-05-20-phase2-error-analysis-and-cleanup-plan.md
§3 ("Ticket CX-FIX-01 — latest_run() ignores non-canonical run dirs").

You may edit ONLY:
  - eval/scripts/_run_io.py
  - eval/tests/test_run_io.py

Do not edit any other file. Do not run pip installs. Do not run ablations.

Follow the acceptance criteria 1–6 exactly. After implementing, run the
three validation commands listed in §3 step 5 and report:
  - Files changed (exact paths)
  - Commands run (exact command lines)
  - Test results (pass count / fail count)
  - Any failures verbatim
  - Any assumptions you made beyond the ticket text
```

---

## 4. Ticket CX-06 — `error_report.py` per-query × per-mode error report

### 1. Goal

Produce a single, deterministic, machine-readable report that, for one
chosen run, lists every (qid, mode) pair with the top-5 candidates, their
silver grades, whether the pair hit at `hit@5` / `strict_hit@5`, and the
rank of the first relevant candidate. This is the foundational artifact
for every subsequent diagnostic ticket.

### 2. Files to change

- Create: `eval/scripts/error_report.py`
- Create: `eval/tests/test_error_report.py`
- Modify (one-line append to docstring index only):
  `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`
- `eval/scripts/_schemas.py`
- `eval/scripts/compute_metrics.py` (for the `_top_for_mode`,
  `_label_map`, `_group_candidates_by_qid`, `RELEVANCE`, `PRIMARY_K`,
  `TOP_KS`, `MODE_ORDER` definitions Codex must reuse verbatim — DO NOT
  duplicate the ranking logic; import from `compute_metrics`).
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl`,
  `silver_labels.jsonl`, `metrics_provisional.json` (smoke target only).

### 4. Acceptance criteria

1. `error_report.py` exposes a CLI:
   ```
   python -m eval.scripts.error_report --run <run_id> [--k 5]
   ```
   `--run` defaults to `_run_io.latest_run()`. `--k` defaults to 5 and
   must be one of `{5, 10, 15}` (reject otherwise with a clear
   `argparse` error).
2. The tool reads `candidates.jsonl` and `silver_labels.jsonl` from the
   run dir using the same schema validators as `compute_metrics.py`.
3. The tool writes two artifacts to
   `eval/runs/<run_id>/analysis/error_report/`:
   - `per_query_mode.jsonl` — one record per (qid, mode), with this
     exact shape (no extra keys):
     ```json
     {
       "qid": "q03",
       "mode": "hybrid",
       "k": 5,
       "top": [
         {"rank": 1, "tmdb_id": 12345, "title": "...", "year": 2008,
          "grade": 0, "confidence": "high"}
       ],
       "hit_at_k": 0,
       "strict_hit_at_k": 0,
       "first_relevant_rank": null,
       "first_perfect_rank": null,
       "null_grades_in_top_k": 0
     }
     ```
     - `hit_at_k`: 1 if any top-K candidate has grade ≥ 2, else 0; null
       if any top-K grade is null and no grade ≥ 2 has appeared yet
       (mirrors `_hit_at_k` in `compute_metrics.py`).
     - `strict_hit_at_k`: same with grade == 3.
     - `first_relevant_rank`: smallest 1-based rank where grade ≥ 2,
       or null if none.
     - `first_perfect_rank`: smallest 1-based rank where grade == 3,
       or null if none.
   - `summary.json` — small roll-up:
     ```json
     {
       "run_id": "2026-05-19-1846-nogit",
       "k": 5,
       "by_mode": {
         "basic":    {"miss_qids": [], "strict_miss_qids": []},
         "advanced": {"miss_qids": [], "strict_miss_qids": []},
         "hybrid":   {"miss_qids": [], "strict_miss_qids": []}
       },
       "any_mode_miss_qids": [],
       "all_modes_miss_qids": [],
       "hybrid_only_miss_qids": []
     }
     ```
     - `miss_qids`: qids with `hit_at_k == 0`.
     - `strict_miss_qids`: qids with `strict_hit_at_k == 0`.
     - `any_mode_miss_qids`: qids that miss in at least one mode (lenient).
     - `all_modes_miss_qids`: qids that miss in every mode (lenient).
     - `hybrid_only_miss_qids`: qids where hybrid misses (lenient) and
       both basic and advanced hit (lenient).
   - All qid lists are sorted.
4. `test_error_report.py` contains at least the following unit tests,
   each using a `tempfile.TemporaryDirectory` and a synthetic run dir of
   3 qids × 3 modes (you may reuse the fixture shape already used by
   `test_compute_metrics.py`):
   - `test_per_query_mode_record_shape` — for a known fixture, every
     output record has exactly the keys listed in criterion 3.
   - `test_first_relevant_rank_uses_grade_ge_2` — fixture has a grade-2
     candidate at rank 3 and grade-1 candidates above it; assert
     `first_relevant_rank == 3` and `first_perfect_rank is None`.
   - `test_summary_hybrid_only_miss_qids` — fixture where qid `q_b`
     hits in basic/advanced and misses in hybrid; assert
     `summary["hybrid_only_miss_qids"] == ["q_b"]`.
   - `test_summary_all_modes_miss_qids` — fixture where qid `q_a`
     misses in every mode; assert
     `summary["all_modes_miss_qids"] == ["q_a"]`.
   - `test_cli_rejects_invalid_k` — calling `main(["--run", "rid",
     "--k", "7"])` exits non-zero with an error message containing
     `"--k"`.
5. The tool's CLI smoke against `2026-05-19-1846-nogit` produces:
   - `eval/runs/2026-05-19-1846-nogit/analysis/error_report/per_query_mode.jsonl`
     with exactly 60 lines (20 qids × 3 modes).
   - `eval/runs/2026-05-19-1846-nogit/analysis/error_report/summary.json`
     whose `by_mode.hybrid.strict_miss_qids` is consistent with the
     `strict_hit_at_5 = 0.20` reported in `metrics_provisional.json`
     (16 of 20 qids miss strictly in hybrid).
6. **The tool is read-only against the run dir** outside of its own
   `analysis/error_report/` subfolder. It must not modify
   `run_manifest.json`, `candidates.jsonl`, `silver_labels.jsonl`, or
   `metrics_provisional.json`.

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.error_report --run 2026-05-19-1846-nogit --k 5
python -c "import json,pathlib; p=pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/error_report/summary.json'); print(json.loads(p.read_text())['by_mode']['hybrid']['strict_miss_qids'])"
```

Expected:

1. `compileall` passes.
2. All eval tests pass; new test count is `previous + 5`.
3. CLI prints output paths and exits 0; the two artifacts exist.
4. The one-liner prints a sorted list of 16 qids (matching
   `strict_hit@5 = 4/20` for hybrid in the baseline). The user will
   spot-check that the list is consistent with manual inspection of the
   run; Claude will verify the count.

### 6. Dependencies

CX-FIX-01 (so `latest_run()` works as documented and `--run` can be
omitted in follow-up tools).

### 7. Risk level

**Low.** Pure analysis. Reuses ranking logic from `compute_metrics.py` —
does not re-implement it.

### 8. Reviewer

Claude Code Pro. Specifically verifies the tool imports `_top_for_mode`
and `_label_map` from `compute_metrics` instead of duplicating them, and
that no new ranking logic is introduced.

### 9. Codex prompt

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket CX-06 exactly as specified in
docs/superpowers/plans/2026-05-20-phase2-error-analysis-and-cleanup-plan.md
§4 ("Ticket CX-06 — error_report.py per-query × per-mode error report").

You may edit ONLY:
  - eval/scripts/error_report.py        (create)
  - eval/tests/test_error_report.py     (create)
  - eval/README.md                      (append ONE line to its scripts
                                         table or scripts list — do not
                                         rewrite or reflow other content)

Do not edit any other file. Do not modify compute_metrics.py, _run_io.py,
or _schemas.py. Import from them.

You MUST reuse _top_for_mode, _label_map, _group_candidates_by_qid,
RELEVANCE, PRIMARY_K, TOP_KS, and MODE_ORDER from
eval.scripts.compute_metrics. Do not duplicate the ranking logic or the
hit/strict-hit predicates.

Acceptance criteria 1–6 are all required. Validation commands are in
§4 step 5 of the plan. Report back per AGENTS.md validation rules.
```

---

## 5. Ticket CX-07 — `audit_silver_labels.py` targeted review sheet for q12/q13

### 1. Goal

Produce a small, finite review sheet that lets the human re-grade exactly
the (query, candidate) pairs that drove the q12/q13 "misses" in the
Phase 1 baseline, plus any pair flagged by a tight set of auto-flag
rules. This ticket does **not** auto-merge gold labels into anything; the
output is a JSONL file with placeholder `gold_grade: null` rows for the
human to fill in.

### 2. Files to change

- Create: `eval/scripts/audit_silver_labels.py`
- Create: `eval/tests/test_audit_silver_labels.py`
- Modify (one-line append to scripts list only): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `_schemas.py`.
- `eval/scripts/error_report.py` (CX-06 output) — but the new tool does
  not import from it. It reads `summary.json` and `per_query_mode.jsonl`
  written by CX-06 as input.
- `eval/queries/v1.jsonl` (for the query string only).
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl`,
  `silver_labels.jsonl` (smoke target only).

### 4. Acceptance criteria

1. CLI:
   ```
   python -m eval.scripts.audit_silver_labels \
       --run <run_id> \
       [--qids q12,q13] \
       [--include-rules]
   ```
   - `--qids` is a comma-separated list of qids to include explicitly
     (default `q12,q13`).
   - `--include-rules` is a flag. When set, additionally include any
     (qid, tmdb_id) where ANY of:
     - the silver `confidence == "low"`, OR
     - the silver `grade == 1` AND the candidate appears in top-5 of any
       mode per `error_report/per_query_mode.jsonl`, OR
     - the silver `grade is None`.
   - The tool requires that `eval/runs/<run_id>/analysis/error_report/`
     exists; if not, exit non-zero with the message
     `error_report not found — run eval.scripts.error_report first`.
2. Output:
   - `eval/runs/<run_id>/analysis/audit_silver_labels/review_sheet.jsonl`
     — one record per (qid, tmdb_id) selected, exact shape:
     ```json
     {
       "qid": "q12",
       "tmdb_id": 12345,
       "query": "a heist movie about folding cities and stolen dreams",
       "title": "...",
       "year": 2008,
       "overview": "...",
       "genres": "...",
       "silver_grade": 1,
       "silver_confidence": "low",
       "silver_reason": "...",
       "in_top_5_of": ["basic", "advanced", "hybrid"],
       "flag_reasons": ["qid_in_audit_list", "silver_confidence_low"],
       "gold_grade": null,
       "gold_notes": null
     }
     ```
   - `eval/runs/<run_id>/analysis/audit_silver_labels/summary.json`:
     ```json
     {
       "run_id": "...",
       "qids_in_audit": ["q12", "q13"],
       "rules_applied": ["silver_confidence_low",
                         "silver_grade_1_in_top_5",
                         "silver_grade_null"],
       "rows_total": 0,
       "rows_by_qid": {"q12": 0, "q13": 0}
     }
     ```
     `rules_applied` is empty if `--include-rules` was not set.
3. The tool is idempotent: re-running it overwrites
   `review_sheet.jsonl` and `summary.json`. **It does not write to
   `silver_labels.jsonl`.** **It does not write a `gold_labels.jsonl`.**
4. `test_audit_silver_labels.py` includes at least:
   - `test_explicit_qids_only_with_no_rules` — fixture with q12 silver
     rows; assert review sheet contains exactly the q12 rows with
     `flag_reasons == ["qid_in_audit_list"]`.
   - `test_include_rules_adds_low_confidence_rows` — fixture with a
     non-q12 row at `confidence: low`; assert it appears with
     `flag_reasons` containing `"silver_confidence_low"`.
   - `test_missing_error_report_exits_nonzero` — fixture run dir lacks
     `analysis/error_report/`; assert exit code != 0 and stderr
     contains `error_report not found`.
   - `test_review_sheet_is_idempotent` — call twice, assert the file is
     byte-identical the second time.
   - `test_does_not_modify_silver_labels` — snapshot
     `silver_labels.jsonl` bytes before and after; assert equal.
5. Smoke against `2026-05-19-1846-nogit` (after CX-06 has run on the same
   run) produces a review sheet whose `summary.json.rows_total` is
   exactly the number of silver rows for q12 + q13 when `--include-rules`
   is NOT set. The exact integer is left to the implementer (do not
   hard-code it in the spec — the test asserts equality, not a magic
   number).

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.audit_silver_labels --run 2026-05-19-1846-nogit
python -c "import json,pathlib; p=pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/audit_silver_labels/summary.json'); print(json.loads(p.read_text()))"
```

Expected:

1. `compileall` passes.
2. All tests pass; new test count is `previous + 5`.
3. CLI prints output paths and exits 0.
4. The one-liner prints a summary with `qids_in_audit == ["q12", "q13"]`
   and `rules_applied == []`.

### 6. Dependencies

CX-FIX-01, CX-06.

### 7. Risk level

**Low.** Read-only against silver labels. The risk is mislabelling the
auto-flag rules; mitigated by tests 1–4 enumerating the rules.

### 8. Reviewer

Claude Code Pro. Specifically verifies that the tool does NOT write
`gold_labels.jsonl` and does NOT touch `silver_labels.jsonl`.

### 9. Codex prompt

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket CX-07 exactly as specified in
docs/superpowers/plans/2026-05-20-phase2-error-analysis-and-cleanup-plan.md
§5 ("Ticket CX-07 — audit_silver_labels.py targeted review sheet for q12/q13").

You may edit ONLY:
  - eval/scripts/audit_silver_labels.py    (create)
  - eval/tests/test_audit_silver_labels.py (create)
  - eval/README.md                          (append ONE line to scripts list)

This tool is read-only against silver_labels.jsonl and candidates.jsonl.
It MUST NOT write gold_labels.jsonl, MUST NOT modify silver_labels.jsonl,
and MUST NOT touch run_manifest.json. The review sheet is for the human
to fill in manually; this ticket does not implement any auto-merge.

Acceptance criteria 1–5 are required. Validation commands are in §5
step 5 of the plan. Report back per AGENTS.md validation rules.
```

---

## 6. Ticket CX-08 — `hybrid_stage_trace.py` per-qid intermediate-stage dump

### 1. Goal

For a single chosen qid, dump the intermediate-stage outputs of the
hybrid pipeline alongside the same stages for the advanced pipeline, so
the human (and Claude on review) can locate where hybrid loses signal
that advanced retains. The output is structured JSON; no code change in
`src/*`, no re-ingestion, no LLM re-call.

### 2. Files to change

- Create: `eval/scripts/hybrid_stage_trace.py`
- Create: `eval/tests/test_hybrid_stage_trace.py`
- Modify (one-line append to scripts list only): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `_schemas.py`,
  `eval/scripts/error_report.py` (for the rank shape).
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl` (smoke target).
- `src/pipelines/{advanced,hybrid}.py` (READ ONLY — for understanding
  the stages; the tool does NOT execute these pipelines).

### 4. Acceptance criteria

1. CLI:
   ```
   python -m eval.scripts.hybrid_stage_trace --run <run_id> --qid q03
   ```
   - Both `--run` (default `latest_run()`) and `--qid` (required) are
     parsed via `argparse`.
   - The qid must exist in `candidates.jsonl` for the run; otherwise
     exit non-zero with `qid <qid> not in run <run_id>`.
2. The tool reads `candidates.jsonl` for the qid and, for each candidate
   in that qid that has a non-empty `per_mode.hybrid` or
   `per_mode.advanced` block, emits one record. Output:
   `eval/runs/<run_id>/analysis/hybrid_stage_trace/<qid>.jsonl`, with the
   exact shape:
   ```json
   {
     "qid": "q03",
     "tmdb_id": 12345,
     "title": "...",
     "year": 2008,
     "silver_grade": 2,
     "silver_confidence": "medium",
     "advanced": {
       "rank": 4,
       "semantic_score": 0.81,
       "bm25_score": 7.2,
       "rrf_score": 0.029,
       "rerank_score": 4.1,
       "final_score": 4.31
     },
     "hybrid": {
       "rank": 12,
       "semantic_score": 0.83,
       "bm25_score": 7.2,
       "rrf_score": 0.031,
       "rerank_score": 4.2,
       "final_score": 4.42
     },
     "rank_delta_hybrid_minus_advanced": 8,
     "in_top_5_advanced": true,
     "in_top_5_hybrid": false
   }
   ```
   - Missing per-mode blocks are emitted as the key with value `null`
     and contribute `null` to `rank_delta_*` and `false` to
     `in_top_5_*`.
3. The tool writes a per-qid summary
   `eval/runs/<run_id>/analysis/hybrid_stage_trace/<qid>.summary.json`:
   ```json
   {
     "qid": "q03",
     "candidates_seen": 11,
     "in_top_5_advanced_count": 5,
     "in_top_5_hybrid_count": 5,
     "advanced_only_top_5_tmdb_ids": [],
     "hybrid_only_top_5_tmdb_ids": [],
     "advanced_top_5_tmdb_ids": [],
     "hybrid_top_5_tmdb_ids": []
   }
   ```
4. `test_hybrid_stage_trace.py` includes at least:
   - `test_trace_record_shape` — fixture with one qid, 6 candidates,
     mixed advanced/hybrid blocks; assert every output record has
     exactly the keys above.
   - `test_rank_delta_when_hybrid_only` — candidate has `per_mode.hybrid`
     and no `per_mode.advanced`; assert `advanced is None` and
     `rank_delta_hybrid_minus_advanced is None`.
   - `test_summary_advanced_only_top_5` — fixture where exactly one
     candidate is in advanced's top-5 but not hybrid's; assert
     `advanced_only_top_5_tmdb_ids` contains just that tmdb_id.
   - `test_unknown_qid_exits_nonzero` — fixture run dir has q03 only;
     `--qid q99` exits non-zero with the expected stderr.
5. **The tool does not re-execute any retrieval, BM25, RRF, or
   reranker code.** It only reads the per_mode scores already written
   to `candidates.jsonl` in the Phase 1 baseline.
6. Smoke against `2026-05-19-1846-nogit --qid q03` produces the two
   artifacts and exits 0. Same for `--qid q08`.

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hybrid_stage_trace --run 2026-05-19-1846-nogit --qid q03
python -m eval.scripts.hybrid_stage_trace --run 2026-05-19-1846-nogit --qid q08
ls eval/runs/2026-05-19-1846-nogit/analysis/hybrid_stage_trace/
```

Expected:

1. `compileall` passes.
2. All tests pass; new test count is `previous + 4`.
3. Both CLI invocations exit 0.
4. The directory listing shows `q03.jsonl`, `q03.summary.json`,
   `q08.jsonl`, `q08.summary.json`.

### 6. Dependencies

CX-FIX-01. (Independent of CX-06 and CX-07 by code, but should land
after CX-06 to avoid two tools writing into a missing
`analysis/` subtree simultaneously.)

### 7. Risk level

**Medium.** The risk is that Codex re-implements ranking logic or
imports from `src/pipelines` and accidentally executes a pipeline. The
acceptance criteria explicitly forbid both. Reviewer must confirm in the
diff.

### 8. Reviewer

Claude Code Pro. Two specific checks: (a) no `from src.pipelines import`
that calls `.run(...)`, and (b) no import of
`src.retrieval.{semantic,bm25,fusion,reranker}` at all.

### 9. Codex prompt

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket CX-08 exactly as specified in
docs/superpowers/plans/2026-05-20-phase2-error-analysis-and-cleanup-plan.md
§6 ("Ticket CX-08 — hybrid_stage_trace.py per-qid intermediate-stage dump").

You may edit ONLY:
  - eval/scripts/hybrid_stage_trace.py    (create)
  - eval/tests/test_hybrid_stage_trace.py (create)
  - eval/README.md                         (append ONE line to scripts list)

HARD CONSTRAINT: This tool MUST NOT import from src.pipelines,
src.retrieval.semantic, src.retrieval.bm25, src.retrieval.fusion,
src.retrieval.reranker, or src.llm. It reads per_mode scores from
candidates.jsonl only.

Acceptance criteria 1–6 are required. Validation commands are in §6
step 5 of the plan. Report back per AGENTS.md validation rules.
```

---

## 7. Ticket CX-09 — q03/q08 retrieval-debug case study (markdown only)

### 1. Goal

Combine the CX-06 and CX-08 outputs for q03 and q08 into a human-readable
markdown report that the human can read end-to-end in one sitting. This
is the artifact Claude will hand to the human as the basis for whatever
ranking-changes plan comes next. **This ticket writes no code.**

### 2. Files to change

- Create:
  `eval/runs/2026-05-19-1846-nogit/analysis/case_studies/q03_q08_retrieval_debug.md`

### 3. Files to read but NOT change

- `eval/runs/2026-05-19-1846-nogit/analysis/error_report/per_query_mode.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/error_report/summary.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_stage_trace/q03.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_stage_trace/q03.summary.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_stage_trace/q08.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_stage_trace/q08.summary.json`
- `eval/queries/v1.jsonl`

### 4. Acceptance criteria

The markdown file contains, in this order, with these exact section
headings:

1. `# Case study: q03 and q08 retrieval debug`
2. `## Context` — one short paragraph naming the parent run
   (`2026-05-19-1846-nogit`), the two qids, and the gate: "no ranking
   changes are proposed in this document."
3. `## q03 — "a trash robot falls in love in space"`
   - Subsection `### top-5 by mode` — three tables (basic, advanced,
     hybrid), each with columns `rank | tmdb_id | title (year) | silver_grade`.
     Populated from `per_query_mode.jsonl`.
   - Subsection `### hybrid vs advanced stage trace` — a table of every
     candidate seen for q03 from `q03.jsonl`, with columns:
     `tmdb_id | title | silver_grade | adv_rank | hyb_rank | adv_final | hyb_final | rank_delta`.
     Sorted by `min(adv_rank, hyb_rank)` ascending, with nulls last.
   - Subsection `### observed pattern` — at most 5 bullets, each
     directly attributable to a row in the tables above. No speculation
     about fixes.
4. `## q08 — "a multiverse family comedy about taxes, laundry, martial arts, ..."`
   — same four subsections, same shape, for q08.
5. `## What this report is NOT` — bullets:
   - "Not a fix proposal."
   - "Not authoritative — silver labels only."
   - "Not a recommendation to change RRF, BM25, or reranker weights."
6. `## Next step` — one sentence: "Hand to Claude for plan decision on
   whether to (a) trigger a label re-grade pass on q03/q08 candidates,
   or (b) open a ranking-changes plan with a paired-bootstrap eval gate."

### 5. Validation commands

```
test -f eval/runs/2026-05-19-1846-nogit/analysis/case_studies/q03_q08_retrieval_debug.md
grep -E "^## q03 — " eval/runs/2026-05-19-1846-nogit/analysis/case_studies/q03_q08_retrieval_debug.md
grep -E "^## q08 — " eval/runs/2026-05-19-1846-nogit/analysis/case_studies/q03_q08_retrieval_debug.md
grep -E "^## What this report is NOT" eval/runs/2026-05-19-1846-nogit/analysis/case_studies/q03_q08_retrieval_debug.md
```

Expected: file exists; all three section grep results return one matching
line each.

(On Windows where `test` and `grep` are unavailable, the human or Codex
substitutes `Test-Path` and `Select-String` respectively. The intent is
"the file exists and has these headings"; the implementer may use
whichever shell idiom matches the executing environment.)

### 6. Dependencies

CX-06 and CX-08 must have completed against
`eval/runs/2026-05-19-1846-nogit/` before this ticket can start. (CX-07
is NOT a dependency — the label-audit review sheet feeds the next plan,
not this report.)

### 7. Risk level

**Low.** Pure documentation; no code, no behavior change. Risk is that
the report drifts from the data; mitigated by criterion 3's
"directly attributable to a row in the tables above."

### 8. Reviewer

Claude Code Pro. Specifically verifies that every claim in
`### observed pattern` cites a tmdb_id present in the table immediately
above, and that no recommendation to change ranking appears anywhere in
the report.

### 9. Codex prompt

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

This ticket writes NO CODE. Implement ticket CX-09 exactly as specified
in docs/superpowers/plans/2026-05-20-phase2-error-analysis-and-cleanup-plan.md
§7 ("Ticket CX-09 — q03/q08 retrieval-debug case study").

You may edit ONLY:
  - eval/runs/2026-05-19-1846-nogit/analysis/case_studies/q03_q08_retrieval_debug.md
    (create)

Read the six listed JSON/JSONL artifacts and v1.jsonl. Produce the
markdown structure described in acceptance criteria 1–6 exactly.

DO NOT recommend any change to ranking, BM25, RRF, reranker, or
embedding behavior. DO NOT compare to or speculate about q12/q13. DO
NOT re-execute any pipeline.

Report back per AGENTS.md validation rules.
```

---

## 8. Self-review against this plan's own constraints

1. **Latest_run fix is isolated.** §3 (CX-FIX-01) touches exactly two
   files: `eval/scripts/_run_io.py` and `eval/tests/test_run_io.py`.
   Three new tests; no behavior change to existing tests. ✓
2. **Phase 2 spec covers error analysis, label audit, hybrid diagnosis.**
   §4 (CX-06) is the error-analysis tool; §5 (CX-07) is the label-audit
   tool; §6 (CX-08) is the hybrid-diagnosis tool; §7 (CX-09) is the
   first applied case study. ✓
3. **q12/q13 are not used to justify any ranking change.** §0.2 gate 1
   states the rule explicitly. CX-07 produces a review sheet whose
   `gold_grade` field is `null` until the human fills it in; nothing in
   CX-08 or CX-09 acts on q12/q13. CX-09 explicitly excludes q12/q13. ✓
4. **q03 and q08 are the first real retrieval-debug targets.** CX-08's
   smoke runs both qids; CX-09 produces the case-study markdown for
   exactly those two. ✓
5. **Codex codes, Claude reviews.** Every ticket §8 names Claude Code
   Pro as reviewer; every Codex prompt §9 names the file list and
   forbids out-of-scope edits. The plan owner field at the top of the
   document is Claude; the implementer field is Codex. ✓
6. **No-git mode honored.** No validation block contains a `git`
   command. ✓
7. **No `src/*` edits.** Every "Files to change" list is under `eval/`
   or `docs/`. Every Codex prompt restates this. ✓

---

## 9. Execution handoff

This plan is now complete and saved to
`docs/superpowers/plans/2026-05-20-phase2-error-analysis-and-cleanup-plan.md`.

Per CLAUDE.md (Autonomy boundaries): Claude does not dispatch Codex
automatically. The human approves each ticket before its Codex prompt is
sent. Suggested dispatch order:

1. Human approves CX-FIX-01 → Codex implements → Claude reviews diff
   and validation log → human merges.
2. Repeat for CX-06.
3. Repeat for CX-07 and CX-08 (serial unless human opts into parallel).
4. Repeat for CX-09.

When all five tickets have landed and Claude has signed off on the
CX-09 case study, this plan's stop point is reached. The next plan
decides whether the q03/q08 evidence justifies (a) a label re-grade
pass, (b) a hybrid ranking-changes plan, or (c) deferring while we
build out the full Phase 2 review app (`review_app.py` etc., currently
deferred per §0.3).
