---
title: CX-10 — Authoritative error report on gold_labels.jsonl
date: 2026-05-21
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one tooling ticket, human-approved before dispatch)
human: approves dispatch (Gate A); accepts the authoritative gold miss breakdown (Gate E)
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 05-metrics-qc-and-labels.md
parent_run: eval/runs/2026-05-19-1846-nogit
parent_plan: docs/superpowers/plans/2026-05-21-label-merge-and-authoritative-metrics-plan.md
git_mode: no_git
status: COMPLETE (2026-05-21) — CX-10 implemented by Codex, reviewed at Gate D, accepted at Gate E. summary.gold.json is the authoritative per-query/per-mode miss breakdown for the merged_gold_over_silver baseline. Plan stop point reached. See §7.
---

# CX-10 — Authoritative Error Report on `gold_labels.jsonl`

> **For agentic workers:** This plan is executed by **Codex CLI** for one
> tooling ticket (CX-10), with explicit human approval before the Codex prompt
> is sent. Claude Code Pro reviews the diff and validation log. **No `src/*`
> edits. No `app.py` / recommender runtime edits. No ranking, retrieval, BM25,
> RRF, reranker, embedding, or pipeline change or re-run.** All work is
> read-only consumption of existing `2026-05-19-1846-nogit` artifacts plus a
> new pair of derived `analysis/` outputs. The ticket uses the 9-field Codex
> handoff format from `CLAUDE.md`.

**This plan is the gated follow-on to ML-01** (`2026-05-21-label-merge-and-
authoritative-metrics-plan.md`). ML-01 produced the authoritative
`merged_gold_over_silver` baseline — `gold_labels.jsonl` and `metrics.json`
(`provisional: false`) — accepted at Gates C + E. But the per-query error
report from **CX-06** (`error_report.py`, owned by
`2026-05-20-phase2-error-analysis-and-cleanup-plan.md` §4) still reads the
**silver** labels. Its per-query / per-mode miss lists therefore no longer
match the authoritative `metrics.json`. CX-10 closes that gap.

**Goal (one sentence):** Extend `error_report.py` with a `--labels
{silver,gold}` selector so it can recompute the per-query × per-mode error
report from `gold_labels.jsonl`, writing a new `per_query_mode.gold.jsonl` +
`summary.gold.json` pair whose miss lists are provably consistent with the
authoritative `metrics.json` — without touching `src/*`, without re-running
any pipeline, and without disturbing the existing silver baseline files.

**Architecture:** A backward-compatible extension of one existing tool,
`eval/scripts/error_report.py`. It (1) adds a `--labels` argument
(default `silver` — unchanged behavior), (2) in `gold` mode loads
`gold_labels.jsonl` for the merged `grade` and keeps `silver_labels.jsonl`
only for the per-candidate `confidence` annotation, (3) reuses the existing
`compute_metrics` ranking/metric helpers unchanged, and (4) writes a
gold-suffixed output pair alongside — never overwriting — the silver files.
No metric formula changes; `compute_metrics.py` is imported, never edited.

**Tech stack:** Python 3.11+, stdlib only (`json`, `pathlib`, `argparse`,
`sys`). Existing eval modules (`eval.scripts._run_io`, `compute_metrics`,
`merge_labels`). No new dependency.

---

## 0. Context and scope

### 0.1 Inputs this plan starts from

All inputs already exist in `eval/runs/2026-05-19-1846-nogit/`:

- **`gold_labels.jsonl`** — ML-01 output. 220 rows, 45 `label_source:
  "gold"` / 175 `"silver"`. Row schema is the 7-key
  `merge_labels.GOLD_LABEL_KEYS` tuple: `qid`, `tmdb_id`, `grade`,
  `label_source`, `silver_grade`, `gold_grade`, `gold_notes`. The merged
  effective grade is `grade`.
- **`metrics.json`** — ML-01 output, `provisional: false`,
  `label_source: "merged_gold_over_silver"`. The authoritative baseline.
  Read by CX-10's **validation only** (cross-check) — never by the tool.
- **`silver_labels.jsonl`** — 220 silver rows; carries the per-row
  `confidence` field that `gold_labels.jsonl` does **not**.
- **`candidates.jsonl`** — the per-mode ranked candidate pool (unchanged).
- **`analysis/error_report/per_query_mode.jsonl` + `summary.json`** —
  CX-06's existing **silver** error report. Read for comparison only;
  **never modified or moved** (the CX-09 case study depends on these paths).
- The tool under change: `eval/scripts/error_report.py`; its test
  `eval/tests/test_error_report.py`; the imported modules
  `eval.scripts._run_io`, `compute_metrics`, `merge_labels`.

### 0.2 Explicit gates (hard rules for the ticket and every step)

1. **No `src/*` edits, no `app.py` / recommender-runtime edits.** All tooling
   lives in `eval/`.
2. **No ranking / retrieval / BM25 / RRF / reranker / embedding / pipeline
   change, and no re-run of any of them.** The gold report is recomputed
   purely from existing `candidates.jsonl` ranks plus the merged labels —
   the same arithmetic CX-06 and `metrics.json` already used.
3. **`compute_metrics.py` and `merge_labels.py` are reused as libraries, not
   edited.** `error_report.py` imports the ranking/metric helpers and the
   `GOLD_LABEL_KEYS` schema contract; it owns its own output envelope.
4. **The silver baseline is not disturbed.** Silver-mode `per_query_mode.jsonl`
   stays byte-identical; the tool's only new writes are
   `per_query_mode.gold.jsonl` and `summary.gold.json`.
5. **Read-only on every existing run artifact** except the tool's own
   `analysis/error_report/` outputs.
6. **Codex implements; Claude reviews; the human approves each gate.**

### 0.3 Honest caveats

- **`confidence` stays a silver-grader field.** `gold_labels.jsonl` has no
  per-row `confidence`. In `gold` mode the `top[]` rows therefore keep
  reporting the **silver pre-grader** `confidence` (joined from
  `silver_labels.jsonl`); only `grade` reflects the gold merge. The
  `per_query_mode.*` record schema is unchanged from CX-06. A reviewer
  reading `per_query_mode.gold.jsonl` must read `confidence` as
  "silver-grader confidence", not "gold confidence". This is documented in
  the tool and in §3 acceptance criterion 3.
- **`summary.json` gains two additive envelope keys.** Both modes now write
  `label_source` and `labels_file` into the summary envelope. The next
  silver-mode run therefore adds those two keys to `summary.json`. This is
  an intentional, additive, idempotent change to `error_report.py`'s **own
  derived output** — not a modification of a frozen input. The silver
  `per_query_mode.jsonl` record schema is unchanged, so the CX-09 case
  study (which reads `by_mode` and the miss lists, not a strict key set) is
  unaffected.
- **No Gate B / Gate C.** ML-01's inputs (`gold_labels.jsonl`,
  `candidates.jsonl`, `metrics.json`) are already frozen and human-accepted
  at ML-01 Gate E. CX-10 has no provisional flag and no human-run step, so
  only Gates **A / D / E** apply (§4).

### 0.4 Not in scope for this plan (explicit deferrals)

- Re-pointing `hybrid_stage_trace.py` at gold labels — its `silver_grade`
  annotation is cosmetically stale but its rank deltas come from
  `candidates.jsonl` and are label-independent. Separate minor ticket.
- Regenerating the CX-09 `analysis/case_studies/q03_q08_retrieval_debug.md`
  with gold numbers.
- Adding per-`top[]`-row gold/silver provenance — would change the
  per-record schema and the CX-06 strict key-set test; deferred.
- `--labels` values beyond `silver` / `gold`.
- Any ranking / retrieval change. A future, separately-gated
  ranking-changes plan would *consume* `summary.gold.json` as its scoping
  input; CX-10 only produces it.

---

## 1. Ticket inventory and sequencing

| ID | Title | Type | Risk | Files-to-change | Depends on |
|---|---|---|---|---|---|
| CX-10 | `error_report.py` — `--labels {silver,gold}`; write authoritative `per_query_mode.gold.jsonl` + `summary.gold.json` | Codex | low | 3 | ML-01 (`gold_labels.jsonl` accepted at Gate E) |

**Dispatch order (human-gated):** Gate A (approve dispatch) → Codex
implements CX-10 → Gate D (Claude review) → Gate E (human accept). One
ticket; no parallel work.

**Stop point for this plan:** after `error_report.py` is reviewed and the
human has accepted `summary.gold.json` as the authoritative per-query /
per-mode miss breakdown.

---

## 2. Shared conventions

### 2.1 Outputs (written only — and only when CX-10 runs post-approval)

`error_report.py` writes one pair of files per invocation, into the existing
`eval/runs/<run_id>/analysis/error_report/` folder:

- `--labels silver` (default) → `per_query_mode.jsonl` + `summary.json`
  (**unchanged CX-06 paths and behavior**).
- `--labels gold` → `per_query_mode.gold.jsonl` + `summary.gold.json`
  (**new**, siblings of the silver pair; the `.gold.` infix keeps the
  gold/silver pair side by side and leaves the CX-09-referenced silver
  paths byte-identical).

JSONL written `utf-8`, `newline="\n"`, one record per line (existing
`_write_jsonl`); summary JSON via `_run_io._atomic_write_json` (existing).

### 2.2 Inputs (read-only — the tool must never write these)

`candidates.jsonl`, `silver_labels.jsonl`, `gold_labels.jsonl`, and the
modules `eval.scripts._run_io`, `compute_metrics`, `merge_labels` (imported,
not changed). `metrics.json` is read by **validation commands only**, never
by the tool.

### 2.3 Forbidden files (the tool must never create or modify any of these)

Anything under `src/`; `app.py` and any recommender-runtime module;
`candidates.jsonl`; `silver_labels.jsonl`; `gold_labels.jsonl`;
`metrics.json`; `metrics_provisional.json`; `run_manifest.json`;
`config_snapshot.json`; anything under `analysis/regrade/`; the existing
silver `analysis/error_report/per_query_mode.jsonl`; the CX-09
`analysis/case_studies/q03_q08_retrieval_debug.md`; `compute_metrics.py`;
`merge_labels.py`; `_run_io.py`; `_schemas.py`. (The silver `summary.json`
is the tool's own derived output and may gain the two additive envelope
keys of §0.3 on a silver-mode run; it is otherwise unchanged.)

### 2.4 Overwrite / idempotency policy

Both output pairs are **derived** artifacts — fully reproducible from the
inputs. `error_report.py` overwrites its own outputs atomically on every run
and is **deterministic**: same inputs + same `--labels` → byte-identical
output pair.

### 2.5 Test pattern

`test_error_report.py` already swaps `_run_io.PROJECT_ROOT` / `EVAL_DIR` /
`RUNS_DIR` to a `tempfile.TemporaryDirectory` and writes synthetic
`candidates.jsonl` / `silver_labels.jsonl` fixtures. CX-10 extends the
`_temporary_run` helper to optionally also write a `gold_labels.jsonl`
fixture, and adds a `_gold(...)` row factory. Tests stay hermetic — they
never depend on the real `eval/runs/2026-05-19-1846-nogit/` content.

### 2.6 Validation convention

The validation block runs, in order: `compileall` → `unittest discover` →
the tool's own CLI smoke (`--labels gold` and `--labels silver`) against
`2026-05-19-1846-nogit`, then two cross-check one-liners. No git commands
appear in any validation block (no-git mode).

---

## 3. Ticket CX-10 — `error_report.py --labels {silver,gold}`

### 1. Goal

Add a `--labels {silver,gold}` selector to `error_report.py` so it can
recompute the per-query × per-mode error report from `gold_labels.jsonl`,
writing `per_query_mode.gold.jsonl` + `summary.gold.json` whose miss lists
are provably consistent with the authoritative `metrics.json` — reusing the
existing `compute_metrics` engine unchanged and leaving the silver baseline
files byte-identical.

### 2. Files to change

- Modify: `eval/scripts/error_report.py`
- Modify: `eval/tests/test_error_report.py`
- Modify (one line — add `error_report.py` to the `scripts/` block of the
  Layout fence, which currently omits it): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `compute_metrics.py`, `merge_labels.py`.
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`,
  `silver_labels.jsonl`, `candidates.jsonl`, `metrics.json` (smoke /
  validation target only).

### 4. Acceptance criteria

1. **CLI:** `python -m eval.scripts.error_report --run <run_id> [--k 5]
   [--labels {silver,gold}]`. `--run` defaults to `_run_io.latest_run()`;
   `--k` keeps its existing `{5,10,15}` choices and default `5`;
   `--labels` defaults to `"silver"`. Existing invocations
   (`--run ... --k ...` with no `--labels`) behave exactly as before.

2. **`run()` / `build_report()` signatures:**
   - `run(*, run_id=None, k=PRIMARY_K, labels="silver")` — the new `labels`
     keyword defaults to `"silver"` so existing callers and tests that call
     `error_report.run(run_id=..., k=...)` are unaffected.
   - `build_report` is split so grade and confidence come from separate
     inputs: `build_report(*, run_id, candidates, grade_labels,
     confidence_labels, k=PRIMARY_K, label_source, labels_file)`. It calls
     `_label_map(grade_labels)` and `_silver_confidence_map(confidence_labels)`.
     (No external module imports `build_report`; the signature change is
     internal.)

3. **Per-record schema is unchanged.** `per_query_mode.jsonl` and
   `per_query_mode.gold.jsonl` records carry exactly the existing 9
   `_REPORT_KEYS`; each `top[]` row carries exactly the existing 6 keys
   (`rank`, `tmdb_id`, `title`, `year`, `grade`, `confidence`). In `gold`
   mode `grade` is the merged gold-over-silver grade and `confidence` is the
   **silver** pre-grader confidence (§0.3). Add a module-level comment in
   `error_report.py` stating this `confidence` semantics explicitly.

4. **`silver` mode (default):**
   - Loads `silver_labels.jsonl` via `compute_metrics._load_silver_labels`
     and uses it for both `grade_labels` and `confidence_labels`.
   - Writes `analysis/error_report/per_query_mode.jsonl` +
     `summary.json`. `per_query_mode.jsonl` is **byte-identical** to the
     pre-CX-10 output.

5. **`gold` mode:**
   - Loads `gold_labels.jsonl` from the run root for `grade_labels`, and
     `silver_labels.jsonl` for `confidence_labels`.
   - `gold_labels.jsonl` is loaded by a **new** `_load_gold_labels(path)`
     helper — it must **not** route gold rows through
     `compute_metrics._load_silver_labels` /
     `_schemas.validate_silver_record` (gold rows lack the silver schema's
     `confidence`/`reason`/`model`/`ts` keys and would be rejected).
     `_load_gold_labels` reads the JSONL and validates each row's key set
     equals `merge_labels.GOLD_LABEL_KEYS` and that `grade` is an integer
     in `{0,1,2,3}` or `null`.
   - **Precondition:** if `gold_labels.jsonl` is absent, raise a new
     `ErrorReportError` (a `ValueError` subclass) with the message
     `gold_labels.jsonl not found in run <run_id> — run
     eval.scripts.merge_labels first`; `main()` catches it, prints to
     `stderr`, and returns a non-zero exit code. Nothing is written.
   - Writes `analysis/error_report/per_query_mode.gold.jsonl` +
     `summary.gold.json`. Does **not** create or modify the silver pair.
   - Result for this run: `per_query_mode.gold.jsonl` has **60 records**
     (20 qids × 3 modes).

6. **Summary envelope.** `summary.json` / `summary.gold.json` keep their
   existing keys (`run_id`, `k`, `by_mode`, `any_mode_miss_qids`,
   `all_modes_miss_qids`, `hybrid_only_miss_qids`) and gain two additive
   keys:
   - `label_source`: `"silver"` in silver mode, `"merged_gold_over_silver"`
     in gold mode.
   - `labels_file`: `"silver_labels.jsonl"` or `"gold_labels.jsonl"`.

7. **Authoritative consistency.** For `2026-05-19-1846-nogit`,
   `summary.gold.json` miss counts match `metrics.json` exactly:
   for each mode, `len(by_mode[mode]["strict_miss_qids"]) == round((1 -
   metrics.by_mode[mode].strict_hit_at_5) * 20)` and likewise for
   `miss_qids` vs `hit_at_5`. Expected: `strict_miss_qids` counts
   **basic 10 / advanced 10 / hybrid 15**; `miss_qids` counts
   **basic 2 / advanced 0 / hybrid 1**.

8. **Writes nothing else.** The tool must not modify any file in §2.3.

9. **Idempotent & deterministic.** A second invocation with the same
   `--labels` produces a byte-identical output pair (§2.4).

10. **CLI output.** On success, print `run_id=`, the two output paths, and
    the `label_source`. On the gold-missing precondition failure, print the
    error to `stderr` and return non-zero.

11. `test_error_report.py` keeps its 5 existing tests passing and adds at
    least these 6 (extend `_temporary_run` to optionally write
    `gold_labels.jsonl`; add a `_gold(...)` row factory):
    - `test_gold_mode_writes_gold_suffixed_artifacts` — `--labels gold`
      writes `per_query_mode.gold.jsonl` + `summary.gold.json` and does
      **not** create `per_query_mode.jsonl` / `summary.json`.
    - `test_gold_mode_missing_gold_labels_exits_nonzero` — run dir has no
      `gold_labels.jsonl`; `main([..., "--labels", "gold"])` exits
      non-zero, `stderr` contains `gold_labels.jsonl`, neither output
      written.
    - `test_gold_grade_overrides_silver_in_miss_lists` — a fixture where a
      gold override flips a query's `strict_hit_at_k`; assert
      `summary.gold.json` miss lists differ from the silver `summary.json`
      for that qid (proves gold actually feeds the math).
    - `test_summary_envelope_records_label_source` — silver summary has
      `label_source == "silver"` / `labels_file == "silver_labels.jsonl"`;
      gold summary has `label_source == "merged_gold_over_silver"` /
      `labels_file == "gold_labels.jsonl"`.
    - `test_gold_mode_confidence_comes_from_silver` — a gold-overridden
      candidate's `top[]` row `confidence` equals the silver `confidence`
      for that `(qid, tmdb_id)`, not `null`.
    - `test_silver_mode_per_query_schema_unchanged` — silver-mode
      `per_query_mode.jsonl` records have exactly the 9 `_REPORT_KEYS` and
      each `top[]` row exactly the 6 keys (back-compat guard).

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.error_report --run 2026-05-19-1846-nogit --k 5 --labels gold
python -m eval.scripts.error_report --run 2026-05-19-1846-nogit --k 5 --labels silver
python -c "import json,pathlib; b=pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/error_report'); rows=[json.loads(l) for l in (b/'per_query_mode.gold.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]; s=json.loads((b/'summary.gold.json').read_text(encoding='utf-8')); print(len(rows), s['label_source'], s['labels_file'])"
python -c "import json,pathlib; b=pathlib.Path('eval/runs/2026-05-19-1846-nogit'); s=json.loads((b/'analysis/error_report/summary.gold.json').read_text(encoding='utf-8'))['by_mode']; m=json.loads((b/'metrics.json').read_text(encoding='utf-8'))['by_mode']; [print(mode,'strict_miss',len(s[mode]['strict_miss_qids']),'miss',len(s[mode]['miss_qids'])) for mode in ('basic','advanced','hybrid')]; assert all(len(s[mode]['strict_miss_qids'])==round((1-m[mode]['strict_hit_at_5'])*20) and len(s[mode]['miss_qids'])==round((1-m[mode]['hit_at_5'])*20) for mode in ('basic','advanced','hybrid')); print('summary.gold.json consistent with metrics.json')"
```

Expected:

1. `compileall` reports `Listing ... OK`.
2. All tests pass; new test count is `previous + N` (baseline is **90**;
   CX-10 adds at least 6 → expect **≥ 96**).
3. Both CLI invocations exit 0; the gold run writes the `.gold.` pair, the
   silver run leaves `per_query_mode.jsonl` byte-identical.
4. The first one-liner prints `60 merged_gold_over_silver gold_labels.jsonl`.
5. The second one-liner prints `basic strict_miss 10 miss 2`,
   `advanced strict_miss 10 miss 0`, `hybrid strict_miss 15 miss 1`, then
   `summary.gold.json consistent with metrics.json`.

### 6. Dependencies

ML-01 — `gold_labels.jsonl` and `metrics.json` for `2026-05-19-1846-nogit`
must exist and be the Gate-E-accepted authoritative artifacts (satisfied).
CX-06 — `error_report.py` and its test must exist (satisfied).

### 7. Risk level

**Low.** Three-file change, additive and backward-compatible. The real
risks are (a) moving or clobbering the silver baseline files the CX-09 case
study depends on, or (b) routing gold rows through the silver schema
validator and crashing. Criterion 4 (silver byte-identical), criterion 5
(separate `_load_gold_labels`, no `_schemas.validate_silver_record`), the
§2.3 forbidden list, atomic writes, and
`test_gold_mode_writes_gold_suffixed_artifacts` /
`test_silver_mode_per_query_schema_unchanged` forbid both. The recompute
itself is the same deterministic arithmetic CX-06 and `metrics.json`
already use.

### 8. Reviewer

Claude Code Pro. Specifically verifies: the diff touches exactly the 3
files in criterion 2; `_load_gold_labels` does **not** call
`_schemas.validate_silver_record` / `_load_silver_labels` on gold rows; the
silver `per_query_mode.jsonl` is byte-identical pre/post; `summary.gold.json`
strict-miss counts are 10 / 10 / 15 and trace to `metrics.json`; no
`compute_metrics.py` / `merge_labels.py` / `_run_io.py` / `_schemas.py`
edits; no `src/*` or `app.py` edits.

### 9. Codex prompt (planning artifact — NOT dispatched by this plan)

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket CX-10 exactly as specified in
docs/superpowers/plans/2026-05-21-cx10-gold-error-report-plan.md
section 3 ("Ticket CX-10 -- error_report.py --labels {silver,gold}").

You may edit ONLY:
  - eval/scripts/error_report.py       (modify)
  - eval/tests/test_error_report.py    (modify)
  - eval/README.md                     (add ONE line: error_report.py in
                                        the scripts/ block of the Layout fence)

Do not edit any other file. No src/* edits. No app.py / recommender-runtime
edits. Do not run pip installs. Do not run any pipeline, retrieval, BM25,
RRF, reranker, or embedding code.

HARD CONSTRAINTS:
  - --labels defaults to "silver"; silver-mode behavior and the silver
    output paths (analysis/error_report/per_query_mode.jsonl + summary.json)
    are UNCHANGED. per_query_mode.jsonl must be byte-identical to before.
  - gold mode writes ONLY analysis/error_report/per_query_mode.gold.jsonl
    and summary.gold.json. It must not create or modify the silver pair.
  - gold_labels.jsonl must be loaded by a new _load_gold_labels() helper
    that validates rows against merge_labels.GOLD_LABEL_KEYS. Do NOT pass
    gold rows through compute_metrics._load_silver_labels or
    _schemas.validate_silver_record.
  - compute_metrics.py and merge_labels.py are IMPORTED as libraries and
    MUST NOT be edited. Reuse the existing ranking/metric helpers.
  - The report is recomputed purely from existing candidates.jsonl ranks
    plus the merged labels. Do NOT re-run retrieval or any pipeline.
  - If gold_labels.jsonl is missing, exit non-zero and write nothing.

Acceptance criteria 1-11 in section 3 are all required. Run the validation
commands in section 3 step 5. Report back per AGENTS.md validation rules
(files changed, commands run, test counts, failures verbatim, assumptions).
```

---

## 4. Human approval gates

| Gate | When | Who | What |
|---|---|---|---|
| **A — Dispatch approval** | Before the CX-10 Codex prompt is sent | Human | Approves the specific CX-10 handoff. Per `CLAUDE.md`, Claude does **not** auto-dispatch Codex. **This plan stops here until Gate A is given.** |
| **D — Claude review** | After Codex finishes | Claude | Reviews the 3-file diff vs the allowed list, the validation log, the silver `per_query_mode.jsonl` byte-identity, and the `summary.gold.json` miss counts vs `metrics.json`. Reports matches / deviations / blockers. |
| **E — Human accept** | After Gate D | Human | Accepts `summary.gold.json` as the authoritative per-query / per-mode miss breakdown. Only then is it the scoping input for any subsequent ranking-changes plan. |

Gates B and C from ML-01 do not apply here — see §0.3.

---

## 5. Self-review against this plan's own constraints

1. **Goal is the authoritative miss breakdown** — §3 criteria 5 + 7;
   `summary.gold.json` cross-checked against `metrics.json`. ✓
2. **`error_report.py` extended, not yet** — this plan only *specifies* the
   change; nothing is written until CX-10 runs post-approval. ✓
3. **No `src/*` / `app.py` / recommender edits** — every "Files to change"
   entry is `eval/scripts/error_report.py`, `eval/tests/test_error_report.py`,
   or `eval/README.md`. ✓
4. **No git commands** — none in any validation block (no-git mode). ✓
5. **No ranking / retrieval / pipeline change or re-run** — the report is
   pure arithmetic over existing `candidates.jsonl` ranks;
   `compute_metrics.py` is imported unchanged. ✓
6. **Silver baseline untouched** — §2.1 / §3 criterion 4 keep
   `per_query_mode.jsonl` byte-identical; gold writes a separate `.gold.`
   pair; `test_silver_mode_per_query_schema_unchanged` guards it. ✓
7. **`compute_metrics.py` / `merge_labels.py` reused, not edited** — §2.2,
   §2.3, §3 criterion 5, and the Codex prompt forbid edits. ✓
8. **Inputs / outputs / allowed / forbidden / overwrite policy / schema /
   validation / tests / gates** — all present (§2, §3, §4). ✓
9. **Planning only** — no Codex dispatched, no code implemented; the §3.9
   prompt is plan text, not an invocation. ✓

---

## 6. Execution handoff

Per `CLAUDE.md` autonomy boundaries, Claude does not dispatch Codex
automatically. Suggested order once this plan is approved:

1. **Gate A** — human approves the CX-10 handoff → Codex implements
   `error_report.py` → **Gate D** Claude reviews the diff and validation log.
2. **Gate E** — human accepts `summary.gold.json` as the authoritative
   per-query / per-mode miss breakdown.

When `summary.gold.json` is accepted, this plan's stop point is reached. It
then becomes the scoping input for the next decision — whether the
gold-confirmed hybrid `strict_hit@5` gap (0.25 vs 0.50) justifies a hybrid
ranking-changes plan — which would be its own separately-gated plan.

---

## 7. Completion record (2026-05-21)

CX-10 is **complete**. The §1 stop point is reached.

### 7.1 Ticket outcome

- **CX-10** — `error_report.py` extended with `--labels {silver,gold}`,
  implemented by Codex CLI (dispatch exit 0), reviewed by Claude Code Pro,
  accepted by the human. Status: **complete.**
- Files changed (exactly the 3 approved): `eval/scripts/error_report.py`,
  `eval/tests/test_error_report.py`, `eval/README.md`.
- New artifacts under `eval/runs/2026-05-19-1846-nogit/analysis/error_report/`:
  - `per_query_mode.gold.jsonl` — 60 records (20 qids × 3 modes).
  - `summary.gold.json` — `label_source: "merged_gold_over_silver"`.
- The silver `per_query_mode.jsonl` is byte-identical; the silver
  `summary.json` gained the two additive envelope keys (`label_source`,
  `labels_file`) per §0.3.
- Tests: **90 → 96**, all passing (independently re-run at Gate D).

### 7.2 Gate outcomes

| Gate | Outcome |
|---|---|
| **A — Dispatch** | Approved 2026-05-21; Codex implemented CX-10 (exit 0). |
| **D — Claude review** | matches spec / no deviations / no blockers. 3-file scope verified; `_load_gold_labels` does not route gold rows through the silver schema validator; `summary.gold.json` cross-checked against `metrics.json`. |
| **E — Human accept** | **Approved 2026-05-21.** `analysis/error_report/summary.gold.json` is the authoritative per-query / per-mode miss breakdown for the `merged_gold_over_silver` baseline. |

### 7.3 Authoritative finding (preserved)

From `summary.gold.json` and `gold_labels.jsonl` vs the silver baseline
(corrected 2026-05-21 — an earlier summary wrongly said q13 also drops out
of every strict-miss list):

- **q12 was a silver-label artifact, fully resolved.** It carries a gold
  grade-3 label (Inception, tmdb 27205) and now strict-hits all three
  modes — it drops out of every `strict_miss_qids` list. Not a retrieval
  failure.
- **q13 was re-graded but is not a strict miss to "fix".** All 12 of its
  candidates were human re-graded; the best gold grade is **2** — q13 has
  **no grade-3 candidate**, so it strict-misses all three modes *by
  construction*. The re-grade resolved only its **lenient** miss (it now
  lenient-hits everywhere). q13 is a "no perfect answer in the pool" query
  — **not** a retrieval or ranking bug.
- **q03 and q08 remain genuine retrieval-debug targets.** Both carry a gold
  grade-3 label; `advanced` strict-hits them, `basic` and `hybrid`
  strict-miss them.
- **Gold-confirmed hybrid strict-ranking gap** — `strict_miss_qids` counts:

  | mode | strict-miss | `strict_hit@5` |
  |---|---|---|
  | basic | 10 | 0.50 |
  | advanced | 10 | 0.50 |
  | hybrid | **15** | **0.25** |

  `hybrid_only_miss_qids` is `[]` (lenient) — the deficit is **purely
  strict** (perfect-match ranking), not lenient retrieval.

### 7.4 Next step (not in scope for this plan)

A **separate, separately-gated scoped plan** should decide whether to
investigate / fix the gold-confirmed hybrid strict-ranking gap (§7.3),
consuming `summary.gold.json` as its scoping input. Per `CLAUDE.md` it is
not drafted or dispatched here. **No further implementation dispatched.**
