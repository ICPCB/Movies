---
title: Gated label merge — gold_labels.jsonl + authoritative metrics.json
date: 2026-05-21
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one tooling ticket, human-approved before dispatch)
human: approves dispatch; approves the provisional:false sign-off; runs the merge
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 05-metrics-qc-and-labels.md
parent_run: eval/runs/2026-05-19-1846-nogit
parent_plan: docs/superpowers/plans/2026-05-20-label-regrade-pass-plan.md
git_mode: no_git
status: COMPLETE (2026-05-21) — ML-01 implemented by Codex, reviewed at Gate D, accepted at Gates C + E. metrics.json is the authoritative merged_gold_over_silver re-baseline (45 human gold + 175 retained silver = 220; explicitly not a fully human-gold benchmark). Plan stop point reached. See §7.
---

# Label Merge — `gold_labels.jsonl` + Authoritative `metrics.json`

> **For agentic workers:** This plan is executed by **Codex CLI** for one
> tooling ticket (ML-01), with explicit human approval before the Codex prompt
> is sent. Claude Code Pro reviews the diff and validation log. **No `src/*`
> edits. No git commands. No ranking, retrieval, BM25, RRF, reranker,
> embedding, or pipeline change or re-run.** All work is read-only consumption
> of existing `2026-05-19-1846-nogit` artifacts plus two new derived outputs.
> The ticket uses the 9-field Codex handoff format from `CLAUDE.md`.

**This plan is the gated follow-on selected by the §6 decision of the
parent plan** (`2026-05-20-label-regrade-pass-plan.md`). RG-02 reported
`complete: true`; the agreement summary showed Outcome 1 (silver-label
artifact, q12/Inception) dominant and no Outcome 2(a) ranking signal. The
chosen next step is therefore the **label merge**, not a ranking-changes
plan.

**Goal (one sentence):** Build one Codex tool, `merge_labels.py`, that merges
the 45 human gold grades (from the RG-02-validated re-grade sheet) over the
220 silver labels to produce `gold_labels.jsonl`, then recomputes an
authoritative `metrics.json` with `provisional: false` — without touching
`src/*`, without re-running any retrieval/ranking pipeline, and without
altering any silver or re-grade artifact.

**Architecture:** A single deterministic tool under `eval/scripts/`.
It (1) gates on RG-02's `regrade_check.json` (`complete: true`), (2) merges
gold-over-silver into `eval/runs/<run_id>/gold_labels.jsonl`, then (3) reuses
the existing `compute_metrics.compute_metrics()` math engine as a **library
call** — passing the merged labels in place of silver — and writes
`eval/runs/<run_id>/metrics.json` with the authoritative envelope. No metric
formula changes; `compute_metrics.py` is imported, never edited.

**Tech stack:** Python 3.11+, stdlib only (`json`, `pathlib`, `argparse`,
`dataclasses`, `collections`). Existing eval modules
(`eval.scripts._run_io`, `_schemas`, `compute_metrics`,
`check_regrade_sheet`). No new dependency.

---

## 0. Context and scope

### 0.1 Inputs this plan starts from

All inputs already exist in `eval/runs/2026-05-19-1846-nogit/`:

- **`analysis/regrade/regrade_sheet.jsonl`** — 45 rows, every `gold_grade`
  filled (0–3) and validated by RG-02. Batches: q12 (10), q13 (12),
  q03 (9), q08 (14).
- **`analysis/regrade/regrade_check.json`** — RG-02 output;
  `complete: true`, 45/45 filled. The merge precondition.
- **`analysis/regrade/regrade_manifest.json`** — RG-01's
  `silver_grade_snapshot` (45 entries), used to cross-check the sheet.
- **`silver_labels.jsonl`** — 220 silver rows, **0 null grades** (verified).
- **`candidates.jsonl`** — the per-mode ranked candidate pool (unchanged).
- **`metrics_provisional.json`** — Phase 1 provisional metrics
  (`provisional: true`, `queries_excluded_null: 0` for all modes). Read for
  comparison only; **never modified**.
- `eval/queries/v1.jsonl` — query tag records for the `by_axis` breakdown.

### 0.2 Explicit gates (hard rules for the ticket and every step)

1. **Gold overrides silver, nothing else changes.** The merge replaces a
   silver grade with the human gold grade **only** for the 45 re-graded
   `(qid, tmdb_id)` pairs. All other 175 labels pass through unchanged.
2. **No `src/*` edits.** All tooling lives under `eval/`.
3. **No ranking / retrieval / BM25 / RRF / reranker / embedding / pipeline
   change, and no re-run of any of them.** `metrics.json` is recomputed
   purely from existing `candidates.jsonl` ranks plus the merged labels —
   the same arithmetic `metrics_provisional.json` already used.
4. **`compute_metrics.py` is reused as a library, not edited.** The merge
   tool imports `compute_metrics.compute_metrics()` and owns the output
   envelope itself.
5. **Read-only on every existing artifact.** The tool's only writes are the
   two new files `gold_labels.jsonl` and `metrics.json`.
6. **Codex implements; Claude reviews; the human approves each gate.**

### 0.3 Honest caveat on `provisional: false`

Spec §7.6 says `metrics.json` (`provisional: false`) is computed from
"merged labels (gold overrides silver) **+ QC validated**". This plan
delivers the merge, but the random-20% QC loop (spec §7.7–7.9) was
**deliberately deferred** by the parent plan (its §0.4). So:

- Only **45 of 220** `(qid, tmdb_id)` pairs carry a human gold label; the
  remaining **175 stay silver**.
- `metrics.json` is marked `provisional: false` **per explicit human
  direction** (the §6 decision), and carries a `label_provenance` block that
  makes the partial gold coverage machine-visible and honest.
- This is formalized as **Gate C** below — the human reaffirms the
  `provisional: false` sign-off at review time.

### 0.4 Null-label policy (spec §7.2) — verified not triggered

Spec §7.2 says final metrics must **block** any (mode, query) whose top-5
contains a `null` label. For this run that is moot: `silver_labels.jsonl` has
**0 null grades** and all 45 gold grades are integers, so the merged label
set has **no nulls**. `merge_labels.py` still checks defensively — if a
merged label feeding any top-5 slot is `null`, it **exits non-zero** (it does
not silently exclude). For `2026-05-19-1846-nogit` this check is a verified
no-op.

### 0.5 Not in scope for this plan (explicit deferrals)

- The Gradio `review_app.py` (spec §6.7).
- `qc_analyze.py`, the 20% random QC sample, and the adaptive-expansion loop
  (spec §7.7–7.9).
- Any ablation or ranking-changes plan, and any paired-bootstrap ablation.
- Editing `compute_metrics.py`, `check_regrade_sheet.py`, or
  `build_regrade_sheet.py` — all three are imported unchanged.
- Re-running retrieval, embedding, or any pipeline stage.

---

## 1. Ticket inventory and sequencing

| ID | Title | Type | Risk | Files-to-change | Depends on |
|---|---|---|---|---|---|
| ML-01 | `merge_labels.py` — merge gold over silver, write `gold_labels.jsonl` + authoritative `metrics.json` | Codex | low-med | 3 | RG-02 (`regrade_check.json` `complete: true`) |

**Dispatch order (human-gated):** Gate A (approve dispatch) → Codex
implements ML-01 → Gate D (Claude review) → Gate B (freeze inputs, RG-02 fresh)
→ human runs the merge → Gate C (`provisional:false` sign-off) → Gate E
(human accept). One ticket; no parallel work.

**Stop point for this plan:** after `merge_labels.py` is reviewed and the
human has accepted `metrics.json` as the authoritative re-baseline.

---

## 2. Shared conventions

### 2.1 Inputs (read-only — the tool must never write these)

`analysis/regrade/regrade_sheet.jsonl`, `analysis/regrade/regrade_check.json`,
`analysis/regrade/regrade_manifest.json`, `silver_labels.jsonl`,
`candidates.jsonl`, `metrics_provisional.json`, `eval/queries/v1.jsonl`, and
the modules `eval.scripts._run_io`, `_schemas`, `compute_metrics`,
`check_regrade_sheet` (imported, not changed).

### 2.2 Outputs (written only — and only when ML-01 runs post-approval)

- `eval/runs/<run_id>/gold_labels.jsonl`
- `eval/runs/<run_id>/metrics.json`

Both sit at the run root, siblings of `silver_labels.jsonl` /
`metrics_provisional.json`. Written with `utf-8`, `newline="\n"`; JSON via
`_run_io._atomic_write_json`.

### 2.3 Forbidden files (the tool must never create or modify any of these)

Anything under `src/`; `silver_labels.jsonl`; `candidates.jsonl`;
`metrics_provisional.json`; `analysis/regrade/regrade_sheet.jsonl`;
`analysis/regrade/regrade_manifest.json`;
`analysis/regrade/regrade_check.json`; anything else under `analysis/`;
`eval/queries/v1.jsonl`; `compute_metrics.py`; `check_regrade_sheet.py`;
`build_regrade_sheet.py`; `run_manifest.json`; `config_snapshot.json`.

### 2.4 Overwrite / idempotency policy

`gold_labels.jsonl` and `metrics.json` are **derived** artifacts — fully
reproducible from the inputs. So `merge_labels.py` is **idempotent**:

- It **overwrites its own two outputs** atomically on every run (no
  refuse-to-overwrite — unlike RG-01, these are not human-owned).
- It is **deterministic**: same inputs → byte-identical `gold_labels.jsonl`
  and `metrics.json` (bootstrap fixed at `seed=42`, `B=1000`, matching the
  provisional run).
- It writes **nothing** until all preconditions in §3 criterion 3 pass; a
  failed precondition exits non-zero having written nothing.

### 2.5 Test pattern

`test_merge_labels.py` follows `eval/tests/test_check_regrade_sheet.py`:
swap `_run_io.PROJECT_ROOT` / `EVAL_DIR` / `RUNS_DIR` to a
`tempfile.TemporaryDirectory`, write small synthetic fixtures, assert on the
result. Tests are hermetic — never depend on the real
`eval/runs/2026-05-19-1846-nogit/` content.

### 2.6 Validation convention

Every validation block runs, in order: `compileall` → `unittest discover` →
the tool's own CLI smoke against `2026-05-19-1846-nogit`. No git commands
appear in any validation block (no-git mode).

---

## 3. Ticket ML-01 — `merge_labels.py`

### 1. Goal

Merge the 45 human gold grades over the 220 silver labels into
`gold_labels.jsonl`, then recompute an authoritative `metrics.json`
(`provisional: false`) from the merged labels — reusing the existing
`compute_metrics` math engine unchanged.

### 2. Files to change

- Create: `eval/scripts/merge_labels.py`
- Create: `eval/tests/test_merge_labels.py`
- Modify (one-line append to the scripts list only): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `_schemas.py`, `compute_metrics.py`,
  `check_regrade_sheet.py`.
- `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_sheet.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_check.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_manifest.json`
- `eval/runs/2026-05-19-1846-nogit/silver_labels.jsonl`
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl`
- `eval/queries/v1.jsonl`

### 4. Acceptance criteria

1. **CLI:** `python -m eval.scripts.merge_labels --run <run_id>`
   (`--run` defaults to `_run_io.latest_run()`).

2. **Preconditions — exit non-zero, write nothing, if any fail:**
   - `regrade_check.json` exists, its `run_id` matches `--run`, and
     `complete` is `true`. Else:
     `regrade_check.json missing or complete:false — run RG-02 first`.
   - `regrade_check.json` is **not stale**: its mtime is `>=` the mtime of
     `regrade_sheet.jsonl`. Else:
     `regrade_check.json is stale — re-run RG-02`.
   - Every `regrade_sheet.jsonl` row has an integer `gold_grade` in
     `{0,1,2,3}` and its row count equals `regrade_manifest.rows_total`.
   - No merged label that feeds a top-5 slot is `null` (spec §7.2). Else
     exit non-zero naming the `(qid, mode, tmdb_id)`.

3. **Gold-over-silver merge → `gold_labels.jsonl`:**
   - Build `gold_map = {(qid, tmdb_id): (gold_grade, gold_notes)}` from the
     45 re-grade rows.
   - For each `silver_labels.jsonl` row, **in original file order**, emit one
     `gold_labels.jsonl` row:
     - if `(qid, tmdb_id) ∈ gold_map` → `grade = gold_grade`,
       `label_source = "gold"`, `gold_grade = <gold>`,
       `gold_notes = <notes>`, `silver_grade = <silver row's grade>`;
     - else → `grade = <silver grade>`, `label_source = "silver"`,
       `gold_grade = null`, `gold_notes = null`,
       `silver_grade = <silver grade>`.
   - For any `gold_map` key **absent** from `silver_labels.jsonl`, append a
     gold-only row (`silver_grade = null`, `label_source = "gold"`), sorted
     by `(qid, tmdb_id)`. *(For `2026-05-19-1846-nogit` this set is empty —
     all 45 re-graded pairs have silver predecessors per the manifest
     snapshot — but the tool must handle the general case.)*
   - **Row schema** (exactly these 7 keys):
     ```json
     {"qid": "q12", "tmdb_id": 27205, "grade": 3,
      "label_source": "gold", "silver_grade": 1, "gold_grade": 3,
      "gold_notes": "..."}
     ```
     Invariants: `label_source == "gold"` ⇒ `grade == gold_grade` and
     `gold_grade` is non-null; `label_source == "silver"` ⇒
     `grade == silver_grade` and `gold_grade is null`.
   - Result for this run: **220 rows, exactly 45 with `label_source:
     "gold"`**, 175 with `"silver"`.

4. **Authoritative recompute → `metrics.json`:**
   - Load `candidates.jsonl` and `eval/queries/v1.jsonl` via
     `compute_metrics._load_candidates` / `_load_queries`.
   - Call `compute_metrics.compute_metrics(run_id=<run_id>,
     candidates=<candidates>, silver_labels=<merged gold rows>,
     query_records=<queries>, bootstrap_b=1000, seed=42)`. The
     `silver_labels` parameter name is historical — the function consumes
     only `qid` / `tmdb_id` / `grade`, which the merged rows provide.
   - Take the returned dict and write `metrics.json` with these envelope
     overrides (everything else — `run_id`, `queries_total`, `by_mode`,
     `by_axis`, `bootstrap` — passes through unchanged):
     - `provisional`: `false`
     - `label_source`: `"merged_gold_over_silver"`
     - add `label_provenance`:
       ```json
       {"gold": 45, "silver": 175, "total": 220,
        "regraded_queries": ["q03", "q08", "q12", "q13"]}
       ```
     - add `built_from`:
       ```json
       {"silver_labels": "silver_labels.jsonl",
        "gold_labels": "gold_labels.jsonl",
        "regrade_sheet": "analysis/regrade/regrade_sheet.jsonl"}
       ```
   - Write via `_run_io._atomic_write_json` to
     `eval/runs/<run_id>/metrics.json`.

5. **Writes nothing else.** The tool must not modify any file in §2.3, must
   not create `metrics_provisional.json` or any file under `analysis/`, and
   must not merge anything beyond the 45 gold grades.

6. **Idempotent & deterministic.** A second invocation produces
   byte-identical `gold_labels.jsonl` and `metrics.json` (§2.4).

7. **CLI output.** On success, print the two output paths plus a one-line
   summary: `merged 45 gold over 220 silver; metrics.json provisional=false`.

8. `test_merge_labels.py` includes at least:
   - `test_gold_overrides_silver_for_regraded_pairs` — a re-graded pair's
     `gold_labels.jsonl` row has `grade == gold_grade`,
     `label_source == "gold"`.
   - `test_silver_passthrough_for_unregraded_pairs` — a non-re-graded pair
     keeps its silver grade, `label_source == "silver"`, `gold_grade null`.
   - `test_gold_only_pair_absent_from_silver_is_added` — a gold pair with no
     silver row becomes a new row with `silver_grade null`.
   - `test_metrics_json_envelope` — `metrics.json` has `provisional: false`,
     `label_source: "merged_gold_over_silver"`, and a correct
     `label_provenance` count block.
   - `test_gold_grades_change_metrics` — a fixture where a gold override
     flips a `hit@5`; `metrics.json` differs from a silver-only
     `compute_metrics` baseline (proves gold actually feeds the math).
   - `test_refuses_when_regrade_incomplete` — `regrade_check.json`
     `complete: false` → exit non-zero, neither output written.
   - `test_refuses_when_regrade_check_stale` — `regrade_check.json` older
     than `regrade_sheet.jsonl` → exit non-zero, neither output written.
   - `test_idempotent_rerun_byte_identical` — two runs → both outputs
     byte-identical.
   - `test_does_not_modify_silver_or_sheet` — `silver_labels.jsonl` and
     `regrade_sheet.jsonl` byte-identical before/after.
   - `test_null_in_top5_exits_nonzero` — a merged `null` in a top-5 slot →
     exit non-zero (spec §7.2).

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.merge_labels --run 2026-05-19-1846-nogit
python -c "import json; d=json.load(open('eval/runs/2026-05-19-1846-nogit/metrics.json',encoding='utf-8')); assert d['provisional'] is False and d['label_source']=='merged_gold_over_silver'; print('ok', d['label_provenance'])"
python -c "import json,pathlib; rows=[json.loads(l) for l in pathlib.Path('eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]; print(len(rows), sum(r['label_source']=='gold' for r in rows))"
```

Expected:

1. `compileall` reports `Listing ... OK`.
2. All tests pass; new test count is `previous + N` (baseline is **80**;
   ML-01 adds at least 10 → expect **≥ 90**).
3. The CLI smoke exits 0 and writes both artifacts.
4. The first one-liner prints `ok {'gold': 45, 'silver': 175, 'total': 220,
   'regraded_queries': ['q03', 'q08', 'q12', 'q13']}`.
5. The second one-liner prints `220 45`.

### 6. Dependencies

RG-02 — `regrade_check.json` must report `complete: true` for
`2026-05-19-1846-nogit` (satisfied; re-run fresh at Gate B). RG-01's
`regrade_sheet.jsonl` / `regrade_manifest.json` and the run's
`silver_labels.jsonl` / `candidates.jsonl` all already exist.

### 7. Risk level

**Low-medium.** The real risks are (a) clobbering `silver_labels.jsonl` or
`metrics_provisional.json`, or (b) emitting `metrics.json` with the wrong
`provisional` flag. Criteria 2/5, the §2.3 forbidden list, atomic writes,
and `test_does_not_modify_silver_or_sheet` / `test_metrics_json_envelope`
forbid both. The merge itself is a deterministic dictionary lookup.

### 8. Reviewer

Claude Code Pro. Specifically verifies: the diff touches exactly the 3 files
in criterion 2; `gold_labels.jsonl` has 220 rows / 45 `"gold"`;
`metrics.json` is `provisional: false` with the correct `label_provenance`;
`silver_labels.jsonl`, `metrics_provisional.json`, and every
`analysis/regrade/` file are byte-unchanged; the metric movements vs
`metrics_provisional.json` trace to the RG-02 `threshold_crossings`.

### 9. Codex prompt (planning artifact — NOT dispatched by this plan)

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket ML-01 exactly as specified in
docs/superpowers/plans/2026-05-21-label-merge-and-authoritative-metrics-plan.md
section 3 ("Ticket ML-01 -- merge_labels.py").

You may edit ONLY:
  - eval/scripts/merge_labels.py        (create)
  - eval/tests/test_merge_labels.py     (create)
  - eval/README.md                      (append ONE line to the scripts list)

Do not edit any other file. No src/* edits. Do not run pip installs.

HARD CONSTRAINTS:
  - The tool's ONLY writes are eval/runs/<run_id>/gold_labels.jsonl and
    eval/runs/<run_id>/metrics.json. It MUST NOT modify silver_labels.jsonl,
    candidates.jsonl, metrics_provisional.json, run_manifest.json, any file
    under analysis/, or anything under src/.
  - compute_metrics.py, check_regrade_sheet.py and build_regrade_sheet.py are
    IMPORTED as libraries and MUST NOT be edited.
  - metrics.json must be recomputed purely from existing candidates.jsonl
    ranks plus the merged labels. Do NOT re-run retrieval, BM25, RRF,
    reranker, embedding, LLM, or any pipeline.
  - If regrade_check.json is missing, complete:false, or stale relative to
    regrade_sheet.jsonl, exit non-zero and write nothing.

Acceptance criteria 1-8 in section 3 are all required. Run the validation
commands in section 3 step 5. Report back per AGENTS.md validation rules
(files changed, commands run, test counts, failures verbatim, assumptions).
```

---

## 4. Human approval gates

| Gate | When | Who | What |
|---|---|---|---|
| **A — Dispatch approval** | Before the ML-01 Codex prompt is sent | Human | Approves the specific ML-01 handoff. Per `CLAUDE.md`, Claude does **not** auto-dispatch Codex. |
| **B — Inputs frozen** | Before `merge_labels.py` is *run* | Human | RG-02 is re-run fresh; `regrade_check.json` shows `complete: true`; human confirms the 45 gold grades are final and `regrade_sheet.jsonl` will not be edited again. |
| **C — `provisional:false` sign-off** | Before `metrics.json` is accepted | Human | Reaffirms `metrics.json` may carry `provisional: false` and be treated as authoritative (spec §7.6) even though only 45/220 pairs are human-gold and the §7.7–7.9 random-QC loop was deferred (§0.3). The `label_provenance` block keeps this visible. |
| **D — Claude review** | After Codex finishes | Claude | Reviews the 3-file diff vs the allowed list, the validation log, the `gold_labels.jsonl` override count (expect 45), and the `metrics.json` delta vs `metrics_provisional.json`. Reports matches / deviations / blockers. |
| **E — Human accept** | After Gate D | Human | Accepts the reviewed result. Only then is `metrics.json` the authoritative re-baseline. |

---

## 5. Self-review against this plan's own constraints

1. **Gold overrides silver** — §3 criterion 3; exactly the 45 re-graded
   pairs, 175 pass through. ✓
2. **`gold_labels.jsonl` produced, not yet** — this plan only *specifies*
   the tool; nothing is written until ML-01 runs post-approval. ✓
3. **Authoritative `metrics.json`, `provisional: false`** — §3 criterion 4,
   with an honest `label_provenance` caveat and Gate C. ✓
4. **No `src/*` edits** — every "Files to change" entry is under `eval/`. ✓
5. **No git commands** — none in any validation block (no-git mode). ✓
6. **No ranking / retrieval / pipeline change or re-run** — `metrics.json`
   is pure arithmetic over existing `candidates.jsonl` ranks;
   `compute_metrics.py` is imported unchanged. ✓
7. **`silver_labels.jsonl` / `regrade_sheet.jsonl` untouched** — §2.3
   forbidden list + `test_does_not_modify_silver_or_sheet`. ✓
8. **Inputs / outputs / allowed / forbidden / overwrite policy / merge
   semantics / metrics recompute / validation / tests / gates** — all
   present (§2, §3, §4). ✓
9. **Planning only** — no Codex dispatched, no code implemented; the §3.9
   prompt is plan text, not an invocation. ✓

---

## 6. Execution handoff

Per `CLAUDE.md` autonomy boundaries, Claude does not dispatch Codex
automatically. Suggested order once this plan is approved:

1. **Gate A** — human approves the ML-01 handoff → Codex implements
   `merge_labels.py` → **Gate D** Claude reviews the diff and validation log.
2. **Gate B** — human re-runs RG-02, confirms `regrade_check.json`
   `complete: true`, freezes `regrade_sheet.jsonl`.
3. Human runs `python -m eval.scripts.merge_labels --run 2026-05-19-1846-nogit`.
4. **Gate C** — human signs off on `provisional: false`.
5. **Gate E** — human accepts `metrics.json` as the authoritative
   re-baseline.

When `metrics.json` is accepted, this plan's stop point is reached.
`metrics.json` then becomes the authoritative input for any subsequent
fix-prioritization, ablation, or re-baseline work (spec §7.6) — each of
which would be its own separately-gated plan.
