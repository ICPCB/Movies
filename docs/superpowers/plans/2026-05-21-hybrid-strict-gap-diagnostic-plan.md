---
title: HX-01 — Hybrid strict-ranking gap diagnostic trace
date: 2026-05-21
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one tooling ticket, human-approved before dispatch)
human: approves dispatch (Gate A); accepts the diagnosis and makes the fix/no-fix decision (Gate E)
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 05-metrics-qc-and-labels.md
parent_run: eval/runs/2026-05-19-1846-nogit
parent_plan: docs/superpowers/plans/2026-05-21-cx10-gold-error-report-plan.md
git_mode: no_git
status: COMPLETE (2026-05-21) — HX-01 implemented by Codex, reviewed at Gate D, accepted at Gate E. diagnosis.json accepted with disclosed caveats; Gate E chose option (1) deeper analysis — no fix dispatched. Plan stop point reached. See §7.
---

# HX-01 — Hybrid Strict-Ranking Gap: Diagnostic Trace

> **For agentic workers:** This plan is executed by **Codex CLI** for one
> tooling ticket (HX-01), with explicit human approval before the Codex
> prompt is sent. Claude Code Pro reviews the diff and validation log.
> **This plan is analysis-only. No `src/*` edits. No `app.py` /
> recommender-runtime edits. No ranking, retrieval, BM25, RRF, reranker,
> or embedding change. No pipeline re-run.** It adds one read-only
> diagnostic tool under `eval/` that consumes existing
> `2026-05-19-1846-nogit` artifacts. The ticket uses the 9-field Codex
> handoff format from `CLAUDE.md`.

**This plan is the gated follow-on to CX-10** (`2026-05-21-cx10-gold-error-
report-plan.md`). CX-10 §7.3 recorded a gold-confirmed finding: hybrid
strict-misses 15 of 20 queries vs 10 for basic and advanced
(`strict_hit@5` 0.25 vs 0.50). This plan produces the evidence needed to
**decide** whether the next work item is **(1) analysis-only** (accept the
gap as characterized, or commission a deeper human-run trace) or **(2) a
narrowly-scoped hybrid ranking fix** — without making any ranking change
itself.

**Goal (one sentence):** Build one Codex tool, `hybrid_gap_trace.py`, that
partitions the 15 hybrid strict-miss queries and, for the subset where a
gold grade-3 candidate provably exists and is top-5-rankable, localizes the
hybrid pipeline stage at which that perfect candidate loses its top-5 rank
— producing `diagnosis.json`, the evidence base for the Gate E fix/no-fix
decision — without touching `src/*`, without re-running any pipeline, and
without changing any ranking behavior.

**Architecture:** A single deterministic, read-only tool under
`eval/scripts/`. It consumes the CX-10 outputs (`summary.gold.json`,
`per_query_mode.gold.jsonl`), `gold_labels.jsonl`, `candidates.jsonl`, and
`metrics.json`; it **re-sorts the per-stage scores already persisted in
`candidates.jsonl`** to reconstruct, for each perfect candidate, its rank at
each pipeline stage. It writes outputs only into
`eval/runs/<run_id>/analysis/hybrid_gap/`.

**Tech stack:** Python 3.11+, stdlib only (`json`, `pathlib`, `argparse`,
`sys`). Existing eval modules (`eval.scripts._run_io`, `compute_metrics`,
`merge_labels`, `error_report`). No new dependency.

---

## 0. Context and scope

### 0.1 Evidence

All figures below are read directly from the accepted authoritative
artifacts in `eval/runs/2026-05-19-1846-nogit/` and verified for this plan.

- **`metrics.json`** (`merged_gold_over_silver`, `provisional: false`) —
  `strict_hit@5`: basic **0.50**, advanced **0.50**, hybrid **0.25**.
- **`analysis/error_report/summary.gold.json`** — `strict_miss_qids`
  counts: basic **10**, advanced **10**, hybrid **15** (of 20 queries).
- **Set arithmetic on the three `strict_miss_qids` lists** partitions the
  15 hybrid strict-miss queries:
  - **Hybrid uniquely strict-misses (3): `q04`, `q10`, `q18`** — both
    basic *and* advanced strict-hit them. The sharpest signal: a gold
    grade-3 candidate provably exists *and* is top-5-rankable, yet hybrid
    ranks it out of the top 5.
  - **Exactly one other mode strict-hits (5):** advanced-only hits
    `q03`, `q08`; basic-only hits `q05`, `q06`, `q07`.
  - **All three modes strict-miss (7):** `q02`, `q09`, `q13`, `q14`,
    `q16`, `q17`, `q19` — not hybrid-specific.
- **Verified in `gold_labels.jsonl`:**
  - `q12` carries a gold grade-3 label (Inception, tmdb 27205); it is
    **resolved** and absent from every strict-miss list.
  - **`q13` has NO gold grade-3 label** (12 candidates re-graded, best gold
    grade is 2). It strict-misses all three modes **by construction** — a
    "no perfect answer in the pool" query, **not** a retrieval or ranking
    bug.
  - `q03` gold grade-3 = tmdb 10681; `q08` gold grade-3 = tmdb 545611.
- **`hybrid_only_miss_qids` is `[]`** (lenient) in both the silver and gold
  reports — the deficit is **purely strict** (perfect-match ranking), not
  lenient retrieval coverage.

**Implication for scope.** The diagnostic target is the **hybrid-attributable**
subset — queries where a gold grade-3 candidate exists *and* at least one
other mode places it in the top 5 (set arithmetic predicts ≤ 8:
`q03 q04 q05 q06 q07 q08 q10 q18`). HX-01 confirms membership against actual
grade-3 presence and actual ranks rather than trusting set arithmetic
alone. `q13` lands in `no_perfect_candidate`; the all-three-miss remainder
lands in `shared_miss` — neither is a hybrid-ranking target.

### 0.2 Explicit gates (hard rules for the ticket and every step)

1. **Analysis-only. No ranking change of any kind.** No edit to retrieval,
   BM25, RRF, fusion, reranker, embedding, or any `src/*` / `app.py` /
   recommender-runtime code. If the diagnosis warrants a fix, that is a
   **separate, separately-gated plan** — never this one.
2. **No pipeline re-run.** `diagnosis.json` is computed purely by
   re-sorting the per-stage scores **already persisted** in
   `candidates.jsonl`. No retrieval, BM25, RRF, reranker, embedding, or LLM
   call is executed.
3. **No `src/*` edits.** All tooling lives under `eval/`.
4. **Imported modules are libraries, not edited.** `compute_metrics.py`,
   `merge_labels.py`, `error_report.py`, `_run_io.py`, `_schemas.py` are
   imported; never modified.
5. **Read-only on every existing artifact.** The tool's only writes are the
   two new files under `analysis/hybrid_gap/`.
6. **q12 / q13 are not fix targets.** q12 is resolved; q13 has no grade-3
   and is a structural miss (§0.1). Neither is treated as a ranking bug.
7. **Codex implements; Claude reviews; the human approves each gate.**

### 0.3 Honest caveats

- **Stage localization is a reconstruction, not live instrumentation.**
  HX-01 ranks each perfect candidate by the per-stage scores
  `candidates.jsonl` already stores (`semantic_score`, `bm25_score`,
  `rrf_score`, `rerank_score`, `final_score`). This localizes the demotion
  to a stage *as represented in `candidates.jsonl`* — a strong diagnostic
  signal, but not a substitute for instrumenting the live `src/` pipeline.
  If `diagnosis.json` is ambiguous (demotions spread across stages, or
  `final` dominates with no single upstream stage), the Gate E decision may
  pick option (1): a deeper, **human-run** instrumented pipeline pass —
  which is out of scope here.
- **`basic` carries only `semantic_score` and `final_score`.** When the
  reference mode is `basic`, only those two stages are comparable; the tool
  records the missing stages as `null` rather than failing.
- **This plan makes no fix and pre-commits to no fix.** Its sole product is
  evidence for a human decision (§4 Gate E).

### 0.4 Non-goals (explicit deferrals)

- **Any ranking / RRF / BM25 / reranker / fusion / embedding change**, and
  any `src/*` or `app.py` edit. A fix, if chosen at Gate E, is its own
  separately-gated plan with a paired-bootstrap eval gate.
- **Re-running any retrieval or pipeline stage**; **instrumenting the live
  `src/` pipeline** (a possible Gate E option-1 follow-on, human-run).
- **Editing `hybrid_stage_trace.py` (CX-08) or `error_report.py` (CX-10).**
- **q12** (resolved) and **q13** (no grade-3 — structural miss); the
  `shared_miss` set is reported for completeness but is not a hybrid target.
- A markdown narrative report — the decision is made from `diagnosis.json`
  at Gate E; no separate report ticket.
- Any change to `metrics.json`, `summary.gold.json`, or other run
  artifacts.

---

## 1. Ticket inventory and sequencing

| ID | Title | Type | Risk | Files-to-change | Depends on |
|---|---|---|---|---|---|
| HX-01 | `hybrid_gap_trace.py` — partition the hybrid strict-miss set; localize the demoting pipeline stage for each hybrid-attributable perfect candidate | Codex | low | 3 | CX-10 (`summary.gold.json`, `per_query_mode.gold.jsonl`) |

**Dispatch order (human-gated):** Gate A (approve dispatch) → Codex
implements HX-01 → Gate D (Claude review) → Gate E (human accept +
fix/no-fix decision). One ticket; no parallel work.

**Stop point for this plan:** after `hybrid_gap_trace.py` is reviewed and
the human has made the Gate E decision. **No fix is implemented by this
plan.**

---

## 2. Shared conventions

### 2.1 Allowed files (HX-01 may create/modify only these three)

- Create: `eval/scripts/hybrid_gap_trace.py`
- Create: `eval/tests/test_hybrid_gap_trace.py`
- Modify (one line — add `hybrid_gap_trace.py` to the `scripts/` block of
  the Layout fence): `eval/README.md`

### 2.2 Inputs (read-only — the tool must never write these)

`eval/runs/<run_id>/`: `candidates.jsonl`, `gold_labels.jsonl`,
`metrics.json`, `analysis/error_report/summary.gold.json`,
`analysis/error_report/per_query_mode.gold.jsonl`. Modules
`eval.scripts._run_io`, `compute_metrics`, `merge_labels`, `error_report`
(imported, not changed).

### 2.3 Forbidden files (the tool must never create or modify any of these)

Anything under `src/`; `app.py` and any recommender-runtime module;
`candidates.jsonl`; `gold_labels.jsonl`; `silver_labels.jsonl`;
`metrics.json`; `metrics_provisional.json`; `run_manifest.json`;
`config_snapshot.json`; `analysis/error_report/*`;
`analysis/hybrid_stage_trace/*`; anything under `analysis/regrade/`; the
CX-09 file `analysis/case_studies/q03_q08_retrieval_debug.md`;
`compute_metrics.py`; `merge_labels.py`; `error_report.py`; `_run_io.py`;
`_schemas.py`. The tool's **only** writes are
`analysis/hybrid_gap/trace.jsonl` and `analysis/hybrid_gap/diagnosis.json`.

### 2.4 Overwrite / idempotency policy

Both outputs are **derived** artifacts. `hybrid_gap_trace.py` overwrites
its own two outputs atomically on every run and is **deterministic**: same
inputs → byte-identical `trace.jsonl` and `diagnosis.json`. All sorts use a
stable tie-break (score descending, then `tmdb_id` ascending).

### 2.5 Test pattern

`test_hybrid_gap_trace.py` follows `eval/tests/test_error_report.py`: swap
`_run_io.PROJECT_ROOT` / `EVAL_DIR` / `RUNS_DIR` to a
`tempfile.TemporaryDirectory`, write small synthetic `candidates.jsonl` /
`gold_labels.jsonl` / `summary.gold.json` / `per_query_mode.gold.jsonl` /
`metrics.json` fixtures, call the function, assert on the result. Tests are
hermetic — they never depend on the real `2026-05-19-1846-nogit` content.

### 2.6 Validation convention

The validation block runs, in order: `compileall` → `unittest discover` →
the tool's own CLI smoke against `2026-05-19-1846-nogit` → a one-liner
cross-check on `diagnosis.json`. No git commands appear in any validation
block (no-git mode).

---

## 3. Ticket HX-01 — `hybrid_gap_trace.py`

### 1. Goal

Partition the 15 hybrid strict-miss queries into `hybrid_attributable`,
`shared_miss`, and `no_perfect_candidate`; and for each
`hybrid_attributable` query, localize the hybrid pipeline stage at which the
gold grade-3 candidate loses its top-5 rank — writing `trace.jsonl` and
`diagnosis.json`. Analysis-only: the tool only re-sorts scores already
present in `candidates.jsonl`.

### 2. Files to change

- Create: `eval/scripts/hybrid_gap_trace.py`
- Create: `eval/tests/test_hybrid_gap_trace.py`
- Modify (one line): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `compute_metrics.py`, `merge_labels.py`,
  `error_report.py`.
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl`, `gold_labels.jsonl`,
  `metrics.json`, `analysis/error_report/summary.gold.json`,
  `analysis/error_report/per_query_mode.gold.jsonl` (smoke target only).

### 4. Acceptance criteria

1. **CLI:** `python -m eval.scripts.hybrid_gap_trace --run <run_id>`.
   `--run` defaults to `_run_io.latest_run()`.

2. **Preconditions — exit non-zero, write nothing, if any fail:** each of
   `candidates.jsonl`, `gold_labels.jsonl`, `metrics.json`,
   `analysis/error_report/summary.gold.json`, and
   `analysis/error_report/per_query_mode.gold.jsonl` must exist. Otherwise
   raise a `HybridGapError` (a `ValueError` subclass) naming the missing
   file; `main()` catches it, prints to `stderr`, returns non-zero.

3. **Inputs and definitions:**
   - `gold_labels.jsonl` is loaded via the existing
     `error_report._load_gold_labels` (do **not** route gold rows through
     the silver schema validator). `perfect_ids(qid)` = the set of
     `tmdb_id` whose gold `grade == 3` for that `qid`.
   - From `summary.gold.json`: `hybrid_strict_miss` =
     `by_mode.hybrid.strict_miss_qids`; `basic_strict_miss`,
     `advanced_strict_miss` likewise.
   - Cross-check: `len(hybrid_strict_miss)` must equal
     `round((1 - metrics.by_mode.hybrid.strict_hit_at_5) * metrics.queries_total)`.
     On mismatch, raise `HybridGapError`.
   - "In top-5 of mode `m`" for a candidate = it has a `per_mode[m]` block
     and `per_mode[m].rank < 5` (ranks in `candidates.jsonl` are 0-indexed).

4. **Partition** — every qid in `hybrid_strict_miss` is placed in exactly
   one bucket:
   - `no_perfect_candidate` — `perfect_ids(qid)` is empty.
   - `hybrid_attributable` — at least one `perfect_id` is in the top-5 of
     `basic` and/or `advanced`, but no `perfect_id` is in the top-5 of
     `hybrid`.
   - `shared_miss` — at least one `perfect_id` exists, but none is in the
     top-5 of any of the three modes.

5. **Stage trace (for each `hybrid_attributable` qid):**
   - Diagnostic target = the `perfect_id` in the top-5 of the most modes
     (tie-break: smallest `tmdb_id`). Reference mode = a mode that places
     it in top-5, preferring `advanced`, else `basic`.
   - Stage score fields, in pipeline order:
     `["semantic_score", "bm25_score", "rrf_score", "rerank_score",
     "final_score"]`. For mode `m` and stage field `s`,
     `rank_by(m, s, cand)` = the 0-indexed position of `cand` when all
     candidates that have `per_mode[m]` with a non-null `s` are sorted by
     `s` descending, ties broken by `tmdb_id` ascending. A stage absent for
     a mode (e.g. `bm25_score` for `basic`) → `null`.
   - Internal consistency: `rank_by(m, "final_score", cand)` must equal the
     stored `per_mode[m].rank`; on mismatch, raise `HybridGapError`.
   - `demoting_stage` (for the target in `hybrid`) = the first stage, in
     pipeline order, whose `rank_by("hybrid", stage, target) >= 5`. If the
     target has no `per_mode.hybrid` block → `"not_retrieved_by_hybrid"`.
     If no stage crosses out → `"none"` (defensive; not expected).

6. **Output `analysis/hybrid_gap/trace.jsonl`** — one record per
   `hybrid_attributable` qid, qids sorted, exact keys:
   ```json
   {"qid": "q04", "perfect_tmdb_id": 12345, "title": "...",
    "gold_grade": 3, "reference_mode": "advanced",
    "stage_ranks": {
      "hybrid":   {"semantic_score": 2, "bm25_score": 3,
                   "rrf_score": 4, "rerank_score": 9, "final_score": 9},
      "advanced": {"semantic_score": 2, "bm25_score": 1,
                   "rrf_score": 1, "rerank_score": 2, "final_score": 2}},
    "demoting_stage": "rerank_score"}
   ```

7. **Output `analysis/hybrid_gap/diagnosis.json`** — exact envelope:
   ```json
   {"run_id": "2026-05-19-1846-nogit",
    "labels_file": "gold_labels.jsonl",
    "hybrid_strict_miss_total": 15,
    "partition": {
      "hybrid_attributable": ["..."],
      "shared_miss": ["..."],
      "no_perfect_candidate": ["..."]},
    "demoting_stage_counts": {
      "semantic_score": 0, "bm25_score": 0, "rrf_score": 0,
      "rerank_score": 0, "final_score": 0,
      "not_retrieved_by_hybrid": 0, "none": 0}}
   ```
   The three partition lists are sorted, pairwise disjoint, and their
   lengths sum to `hybrid_strict_miss_total`. `demoting_stage_counts` sums
   to `len(partition.hybrid_attributable)`.

8. **Writes nothing else.** The tool must not modify any file in §2.3;
   `analysis/hybrid_gap/` is created with `mkdir(parents=True,
   exist_ok=True)`; JSON via `_run_io._atomic_write_json`.

9. **Idempotent & deterministic.** A second invocation produces
   byte-identical `trace.jsonl` and `diagnosis.json`.

10. **CLI output.** On success, print `run_id=`, the two output paths, the
    three partition sizes, and the dominant `demoting_stage`.

11. `test_hybrid_gap_trace.py` includes at least:
    - `test_partition_no_perfect_candidate` — a strict-miss qid with no
      gold grade-3 → `no_perfect_candidate`.
    - `test_partition_hybrid_attributable` — a grade-3 in top-5 of advanced
      but not hybrid → `hybrid_attributable`.
    - `test_partition_shared_miss` — a grade-3 that exists but is in no
      mode's top-5 → `shared_miss`.
    - `test_demoting_stage_localization` — a target in top-5 of hybrid by
      `semantic_score`/`rrf_score` but rank ≥ 5 by `rerank_score` →
      `demoting_stage == "rerank_score"`.
    - `test_not_retrieved_by_hybrid` — a grade-3 with no `per_mode.hybrid`
      block → `demoting_stage == "not_retrieved_by_hybrid"`.
    - `test_missing_summary_gold_exits_nonzero` — precondition failure →
      non-zero exit, nothing written.
    - `test_idempotent_rerun_byte_identical` — two runs → both outputs
      byte-identical.

### 5. Validation commands

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hybrid_gap_trace --run 2026-05-19-1846-nogit
python -c "import json,pathlib; d=json.loads(pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/hybrid_gap/diagnosis.json').read_text(encoding='utf-8')); p=d['partition']; allq=p['hybrid_attributable']+p['shared_miss']+p['no_perfect_candidate']; assert len(allq)==d['hybrid_strict_miss_total']==15 and len(set(allq))==15, 'partition not disjoint/complete'; assert 'q13' in p['no_perfect_candidate'], 'q13 must be no_perfect_candidate'; assert sum(d['demoting_stage_counts'].values())==len(p['hybrid_attributable']); print('partition ok', {k:len(v) for k,v in p.items()}); print('demoting_stage_counts', d['demoting_stage_counts'])"
```

Expected:

1. `compileall` reports `Listing ... OK`.
2. All tests pass; new test count is `previous + N` (baseline is **96**;
   HX-01 adds at least 7 → expect **≥ 103**).
3. The CLI smoke exits 0 and writes `analysis/hybrid_gap/trace.jsonl` and
   `diagnosis.json`.
4. The one-liner asserts the partition is disjoint and complete (sums to
   15), confirms `q13 ∈ no_perfect_candidate`, and prints the partition
   sizes and `demoting_stage_counts`. (The exact partition membership and
   stage counts are the **diagnostic result** — they are not pre-asserted
   here; Claude reviews them at Gate D and the human decides at Gate E.)

### 6. Dependencies

CX-10 — `analysis/error_report/summary.gold.json` and
`per_query_mode.gold.jsonl` must exist (satisfied, accepted at CX-10 Gate
E). ML-01 — `gold_labels.jsonl` and `metrics.json` (satisfied). The run's
`candidates.jsonl` already exists.

### 7. Risk level

**Low.** Three-file change, a new read-only tool. The real risks are (a)
the tool accidentally writing outside `analysis/hybrid_gap/`, or (b)
re-implementing or invoking ranking logic instead of re-sorting stored
scores. Criteria 2/5/8, the §2.3 forbidden list, atomic writes, and the
hermetic tests forbid both. The diagnostic is deterministic sorting over
data already in `candidates.jsonl`.

### 8. Reviewer

Claude Code Pro. Specifically verifies: the diff touches exactly the 3
files in criterion 2; the tool imports no `src/` module and executes no
retrieval/BM25/RRF/reranker/embedding/LLM code; `diagnosis.json`'s
partition is disjoint, covers all 15, and places `q13` in
`no_perfect_candidate`; `rank_by(..., "final_score", ...)` matches the
stored ranks; the tool's only writes are the two `analysis/hybrid_gap/`
files. Claude then summarizes `diagnosis.json` and recommends the Gate E
option (1 or 2); the human decides.

### 9. Codex prompt (planning artifact — NOT dispatched by this plan)

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket HX-01 exactly as specified in
docs/superpowers/plans/2026-05-21-hybrid-strict-gap-diagnostic-plan.md
section 3 ("Ticket HX-01 -- hybrid_gap_trace.py").

You may edit ONLY:
  - eval/scripts/hybrid_gap_trace.py       (create)
  - eval/tests/test_hybrid_gap_trace.py    (create)
  - eval/README.md                         (add ONE line: hybrid_gap_trace.py
                                            in the scripts/ block of the
                                            Layout fence)

Do not edit any other file. No src/* edits. No app.py / recommender-runtime
edits. Do not run pip installs. Do not run any git command.

HARD CONSTRAINTS:
  - This tool is ANALYSIS-ONLY. It MUST NOT change, re-implement, or invoke
    any ranking / retrieval / BM25 / RRF / fusion / reranker / embedding /
    LLM logic. It MUST NOT import from src.* at all. It MUST NOT re-run any
    pipeline stage.
  - diagnosis.json and trace.jsonl are computed PURELY by re-sorting the
    per-stage scores already stored in candidates.jsonl.
  - The tool's ONLY writes are eval/runs/<run_id>/analysis/hybrid_gap/
    trace.jsonl and diagnosis.json. It MUST NOT modify candidates.jsonl,
    gold_labels.jsonl, silver_labels.jsonl, metrics.json, summary.gold.json,
    per_query_mode.gold.jsonl, run_manifest.json, anything under
    analysis/regrade/ or analysis/error_report/, or anything under src/.
  - compute_metrics.py, merge_labels.py, error_report.py, _run_io.py and
    _schemas.py are IMPORTED as libraries and MUST NOT be edited. Load gold
    labels via error_report._load_gold_labels.
  - If any required input file is missing, exit non-zero and write nothing.

Acceptance criteria 1-11 in section 3 are all required. Run the validation
commands in section 3 step 5. Report back per AGENTS.md validation rules
(files changed, commands run, test counts, failures verbatim, the one-liner
stdout, and any assumptions).
```

---

## 4. Human approval gates

| Gate | When | Who | What |
|---|---|---|---|
| **A — Dispatch approval** | Before the HX-01 Codex prompt is sent | Human | Approves the specific HX-01 handoff. Per `CLAUDE.md`, Claude does **not** auto-dispatch Codex. **This plan stops here until Gate A is given.** |
| **D — Claude review** | After Codex finishes | Claude | Reviews the 3-file diff vs the allowed list, the validation log, and `diagnosis.json` (partition disjoint/complete; `q13 ∈ no_perfect_candidate`; final-stage rank consistency). Reports matches / deviations / blockers, then summarizes `diagnosis.json` and recommends a Gate E option. |
| **E — Human accept + decision** | After Gate D | Human | Accepts the diagnosis, then **decides the next work item**, choosing exactly one: **(1) analysis-only** — accept the gap as characterized, optionally commission a deeper human-run live-pipeline instrumentation pass (separate plan); or **(2) a narrowly-scoped hybrid ranking-fix plan** — separate and separately-gated, scoped by `diagnosis.json` to the dominant demoting stage and gated on a paired-bootstrap eval showing no regression. This plan pre-commits to neither. |

Gates B and C from ML-01 do not apply — there is no human-run merge step
and no provisional flag.

---

## 5. Self-review against this plan's own constraints

1. **Analysis-only; no ranking change** — §0.2 gates 1–2, §0.4 non-goals,
   §3 criteria 5/7, and the Codex prompt all forbid any ranking/retrieval
   change and any pipeline re-run. ✓
2. **Decides between (1) analysis-only and (2) a narrow fix** — §4 Gate E
   states the decision explicitly; `diagnosis.json` (§3.7) is the evidence
   for it; this plan implements neither option. ✓
3. **Findings preserved (corrected)** — §0.1: q12 resolved; **q13 has no
   grade-3 and is a structural miss, not a bug**; q03/q08 are genuine
   targets; hybrid strict-miss 15 vs 10/10; `hybrid_only_miss_qids` empty
   → strict/perfect-match ranking, not lenient coverage. ✓
4. **No `src/*` / `app.py` / recommender edits** — every "Files to change"
   entry is under `eval/`. ✓
5. **No git commands** — none in any validation block (no-git mode). ✓
6. **Imported modules not edited** — §2.3 forbidden list + the Codex
   prompt. ✓
7. **goal / evidence / allowed files / forbidden files / non-goals /
   validation commands / Codex-ready handoff / stop-for-Gate-A** — all
   present (goal §3.1; evidence §0.1; allowed §2.1/§3.2; forbidden §2.3;
   non-goals §0.4; validation §3.5; handoff §3 + §3.9; Gate A §4 + the
   `status` field). ✓
8. **Planning only** — no Codex dispatched, no code implemented; the §3.9
   prompt is plan text, not an invocation. ✓

---

## 6. Execution handoff

Per `CLAUDE.md` autonomy boundaries, Claude does not dispatch Codex
automatically. Suggested order once this plan is approved:

1. **Gate A** — human approves the HX-01 handoff → Codex implements
   `hybrid_gap_trace.py` → **Gate D** Claude reviews the diff, the
   validation log, and `diagnosis.json`.
2. **Gate E** — human accepts the diagnosis and decides: (1) analysis-only,
   or (2) commission a separate narrowly-scoped hybrid ranking-fix plan.

When the Gate E decision is made, this plan's stop point is reached. **No
ranking fix is implemented by this plan.** If option (2) is chosen, the fix
is a new, separately-gated plan scoped by `diagnosis.json`.

---

## 7. Completion record (2026-05-21)

HX-01 is **complete**. The §1 stop point is reached.

### 7.1 Ticket outcome

- **HX-01** — `hybrid_gap_trace.py`, implemented by Codex CLI (dispatch
  exit 0), reviewed by Claude Code Pro, accepted by the human. Status:
  **complete.**
- Files changed (exactly the 3 approved): `eval/scripts/hybrid_gap_trace.py`,
  `eval/tests/test_hybrid_gap_trace.py`, `eval/README.md`.
- New artifacts under `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_gap/`:
  `trace.jsonl` (8 records) and `diagnosis.json`.
- Tests: **96 → 103**, all passing (independently re-run at Gate D).
- **One disclosed, accepted deviation:** the plan's §3 criterion 5 required
  `rank_by(final_score)` to equal the stored `rank` exactly. That is
  infeasible — `candidates.jsonl` is the **220-row labeled subset**, not
  full ranked lists (each mode's stored ranks run 0–14 with gaps where a
  top-15 item was unlabeled). Codex correctly used the **stored** rank for
  the final stage with a monotonic-order consistency check, and disclosed
  it. The plan's spec was wrong, not the implementation.

### 7.2 Gate outcomes

| Gate | Outcome |
|---|---|
| **A — Dispatch** | Approved 2026-05-21; Codex implemented HX-01 (exit 0). |
| **D — Claude review** | matches spec / one accepted+disclosed deviation / no code blockers. 3-file scope verified; no `src/*` touched; `q13 ∈ no_perfect_candidate`; 103 tests pass. Three interpretation caveats recorded (§7.3). |
| **E — Human accept + decision** | **Approved 2026-05-21.** `diagnosis.json` accepted as useful and complete with the disclosed caveats. **Decision: option (1) — deeper analysis. No narrow-fix plan dispatched.** |

### 7.3 Diagnosis result and caveats (preserved)

**Caveats under which the diagnosis is accepted:**

- `candidates.jsonl` is the 220-row **labeled subset** — sparse, not a full
  ranked-list trace.
- `not_retrieved_by_hybrid` means **absent from hybrid's top-15 / no
  `per_mode.hybrid` block** (ranked ≥ 15 *or* unretrieved —
  indistinguishable from this data), not literally "not retrieved."
- Non-final stage ranks are positions within the labeled pool —
  **directional, not definitive** full-pipeline ranks.

**Findings:**

- Partition of the 15 hybrid strict-miss queries: `hybrid_attributable` 8,
  `shared_miss` 0, `no_perfect_candidate` 7.
- **q13 is `no_perfect_candidate`** — a structural strict miss (no gold
  grade-3), **not** a retrieval or ranking bug. 7 of the 15 have no
  grade-3, so strict-hit has a hard ceiling of 13/20.
- **The hybrid strict gap splits into ≥ 2 mechanisms:**
  1. The perfect candidate is **absent from hybrid's top-15** in **5/8**
     `hybrid_attributable` cases (q04, q05, q07, q08, q18) while basic
     and/or advanced rank it top-5.
  2. The **reranker recovers** the perfect candidate but **`final_score`
     re-demotes** it in **3/8** cases (q03, q06, q10).
- **RRF and the reranker are not the primary culprit** — `rrf` and
  `rerank` demoting counts are 0; the reranker appears to *recover* the
  perfect candidate in several cases (q03 → rerank rank 1, q06 → 2).

### 7.4 Gate E decision and next step

- **Decision: option (1) — deeper analysis. No fix plan dispatched.**
- The remaining investigation needs a **live / full hybrid pipeline trace
  with true ranked lists** (not the 220-row labeled subset) to (i) resolve,
  for the 5 "absent from hybrid top-15" cases, whether the perfect movie is
  unretrieved vs ranked-low, and (ii) confirm the `final_score`-vs-reranker
  interaction for the 3 retrieved cases. Per `CLAUDE.md`, such a trace
  requires running / instrumenting the pipeline — it is **human-run** and
  would be its own separately-gated plan. It is **not drafted or dispatched
  here.**
- **No ranking fix is implemented or dispatched by this plan.**
