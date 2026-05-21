---
title: Phase 1 — Eval harness scaffold (implementation plan)
date: 2026-05-19
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one handoff at a time, human-approved)
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - README.md
  - 00-purpose-goals-and-rules.md
  - 03-six-phase-plan.md
  - 04-phase1-eval-harness.md
  - 05-metrics-qc-and-labels.md
  - 09-ai-handoff-and-conflict-protocol.md
  - 10-validation-done-risks.md
git_mode: no_git
---

# Phase 1 — Eval Harness Scaffold Implementation Plan

> **For agentic workers:** This plan is executed by **Codex CLI**, one handoff at a
> time, with explicit human approval per handoff. Claude Code Pro reviews each
> diff and the resulting validation log before the next handoff is dispatched.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal (one sentence):** Stand up the read-only eval harness under `eval/` that can
produce `metrics_provisional.json` for a user-approved 20-query v1 set against the
three existing pipelines, without changing any retrieval or ranking behavior.

**Architecture:** New code lives entirely under `eval/` (scripts + per-run output
directories). Scripts import from `src.*` but never edit it. Each run is fully
self-contained in its own `eval/runs/<run_id>/` directory; multiple runs coexist
without interference. State for resume/idempotency lives in JSONL artifacts on disk.

**Tech Stack:** Python 3.11+ (already required by the repo), stdlib `json`,
`pathlib`, `argparse`, `random`, `statistics`, `math`; existing project modules
(`src.pipelines.{basic,advanced,hybrid}`, `src.llm.langchain_ollama`,
`src.config`). No new third-party dependency is introduced in Phase 1 unless a
Codex handoff explicitly justifies it and Claude approves first.

---

## 0. Status of git in this plan

Per the human's direction on 2026-05-19, the project directory **no longer has a
`.git` folder**. This plan runs in **no-git mode**:

- No handoff runs `git status`, `git rev-parse`, `git diff`, or `git commit`.
- `run_manifest.json` records `git_sha: null`, `git_dirty: null`,
  `git_mode: "no_git"` (see §2 schema).
- Conflict-avoidance branch locking from
  [09 §13](../specs/accuracy-audit/09-ai-handoff-and-conflict-protocol.md) is
  **deferred** until git is restored. In the interim, "one Codex handoff at a
  time, files-to-change declared upfront, Claude reviews diff against the
  declared list" is the substitute for branch locks.
- Validation gates that quote git in
  [10 §14](../specs/accuracy-audit/10-validation-done-risks.md) are honored
  in spirit (compile + smoke + harness run), not in form.

When git is restored, a follow-up plan will add the manifest fields, branch
naming, and STATUS.md tracking back in. No script code needs to change at that
point — the manifest builder will simply start filling `git_sha`/`git_dirty`
with real values.

---

## 1. Phase 1 goal

From [03 §5](../specs/accuracy-audit/03-six-phase-plan.md):

> Phase 1 — Eval harness scaffold (no code fixes)
> 1.1 Build `eval/` directory + harness scripts
> 1.2 Generate v1 query set (20 queries, 5-axis diversity, vocab-mismatch bias)
> 1.3 User reviews and approves the 20 queries
> 1.4 Run all 3 pipelines, build per-query top-8 union (soft cap, hard max 15)
> 1.5 LLM pre-grades all (query, candidate) pairs → silver labels
> 1.6 Compute baseline `metrics_provisional.json` (silver only, `provisional: true`)

**Out of scope (do not start until Phase 1 lands and is approved):**

- Phase 2 (`build_review_sheet.py`, `review_app.py`, `merge_labels.py`,
  `qc_analyze.py`, gold labels, QC, expansion).
- Phase 3 (code audit, `findings.md`).
- Phase 4 (ablations, `ablate.py`, `ablation_summary.md`).
- Phase 5 (fix tickets, ChromaDB re-ingestion decision).
- Any change to `src/*` (no retrieval/ranking/embedding/reranker edits).
- ChromaDB re-ingestion.

**Phase 1 stop point:** after the human runs the v1 baseline end-to-end once and
confirms `metrics_provisional.json` exists, is well-formed, and reports the
expected mode coverage. No interpretation, no comparison, no follow-on work
inside Phase 1.

---

## 2. Shared schemas / contracts

These are the **single source of truth** for every Phase 1 handoff. Each Codex
handoff that produces or consumes a JSONL/JSON artifact must match these
exactly. Any deviation = stop and escalate to Claude Code Pro.

### 2.1 `eval/queries/v1.jsonl` (one record per line)

```json
{
  "qid": "q01",
  "query": "a mind-bending movie about dreams, memory, and reality",
  "tags": {
    "era": "2000-2015",
    "genre": ["sf", "thriller"],
    "vocab_distance": "high",
    "length": "short",
    "specificity": "medium",
    "ambiguity": "low"
  },
  "notes": "vocab-mismatch axis: 'mind-bending' rarely appears in TMDB overviews"
}
```

**Enums (closed sets — anything else = schema error):**

- `qid`: `"q01" … "q20"` (zero-padded, ordered).
- `tags.era`: `"pre-1980" | "1980-2000" | "2000-2015" | "2015+"`.
- `tags.genre`: list of at least one of
  `"drama" | "thriller" | "sf" | "animation" | "horror" | "comedy" | "action" | "romance" | "documentary" | "other"`.
- `tags.vocab_distance`: `"low" | "medium" | "high"`.
- `tags.length`: `"short" | "medium" | "long"` (≤8 words / 9–20 / >20).
- `tags.specificity`: `"low" | "medium" | "high"`.
- `tags.ambiguity`: `"low" | "medium" | "high"` (low = one clear answer;
  high = many plausible answers).
- `notes`: free text, ≤200 chars; required (may be `""` after human review).

**Diversity targets** (over the 20 queries; from [04 §6.4](../specs/accuracy-audit/04-phase1-eval-harness.md#64-query-generation-strategy)):

| Axis            | Target distribution                                              |
|-----------------|------------------------------------------------------------------|
| era             | 4 pre-1980 · 5 1980-2000 · 6 2000-2015 · 5 2015+                 |
| genre           | ≥2 each from drama, thriller, sf, animation, horror, comedy     |
| vocab_distance  | 8 high · 8 medium · 4 low                                        |
| length          | 8 short (≤8 words) · 8 medium · 4 long                           |
| ambiguity       | 4 one-clear (low) · 12 small-set (medium) · 4 many-plausible (high) |

### 2.2 `eval/runs/<run_id>/candidates.jsonl` (one record per line)

```json
{
  "qid": "q01",
  "tmdb_id": 27205,
  "movie_key": "title:inception|year:2010",
  "title": "Inception",
  "year": 2010,
  "overview": "...",
  "genres": "...",
  "keywords": "...",
  "tagline": "...",
  "per_mode": {
    "basic":    {"rank": 0,  "semantic_score": 0.83, "final_score": 0.83},
    "advanced": {"rank": 2,  "semantic_score": 0.81, "bm25_score": 7.2,
                 "rrf_score": 0.029, "rerank_score": 4.1, "final_score": 4.31},
    "hybrid":   {"rank": 0,  "semantic_score": 0.83, "bm25_score": 7.2,
                 "rrf_score": 0.031, "rerank_score": 4.2, "final_score": 4.42}
  },
  "in_top_k_of": ["basic", "hybrid"],
  "source": "union"
}
```

Rules ([04 §6.5](../specs/accuracy-audit/04-phase1-eval-harness.md#65-candidate-union-construction-run_pipelinespy)):

- Primary dedup key: `tmdb_id` (int). Secondary: `movie_key` (string).
- Each pipeline runs with `top_k=15`.
- Union per query is **dedup → sort by best rank across modes → soft cap 8 →
  hard max 15**, with **top-5 of any mode always retained**.
- `per_mode` only contains modes in which this candidate appeared in that
  mode's top-15. Missing modes = key omitted (NOT set to `null`).
- `rank` is **0-based** wherever it appears in JSONL artifacts (see
  [05 §7.3](../specs/accuracy-audit/05-metrics-qc-and-labels.md#73-metric-formulas)).
- On `tmdb_id` collision with different `movie_key`, emit a `dedup_bug`
  warning (logged to stderr and into `run_manifest.json.warnings[]`) — this is
  a **diagnostic only**; do not crash and do not edit `src/utils/dedup.py`.

### 2.3 `eval/runs/<run_id>/silver_labels.jsonl` (one record per line)

```json
{
  "qid": "q01",
  "tmdb_id": 27205,
  "grade": 3,
  "confidence": "high",
  "reason": "Overview explicitly mentions dreams, subconscious heists, layered reality.",
  "model": "llama3.2",
  "ts": "2026-05-19T15:30:42Z"
}
```

Rules ([05 §6.6](../specs/accuracy-audit/05-metrics-qc-and-labels.md#66-llm-pre-grading-llm_pregradepy)):

- `grade ∈ {0,1,2,3}` or `null` (synthetic failure record).
- `confidence ∈ {"high","medium","low"}`. Failure records use `"low"`.
- One record per `(qid, tmdb_id)`. Re-runs are idempotent: existing
  `(qid, tmdb_id, model)` rows are not regraded.
- `reason`: free text, ≤240 chars.
- `model`: literal `"llama3.2"` for Phase 1 (matches `src.config.LLM_MODEL`).
- `ts`: ISO-8601 UTC, second precision, suffixed `"Z"`.

### 2.4 `eval/runs/<run_id>/run_manifest.json`

```json
{
  "run_id": "2026-05-19-1530-nogit",
  "git_sha": null,
  "git_dirty": null,
  "git_mode": "no_git",
  "dataset_row_count": 27762,
  "chroma_collection_count": 27762,
  "embedding_model": "BAAI/bge-m3",
  "reranker_model": "BAAI/bge-reranker-v2-m3",
  "llm_model": "llama3.2",
  "rng_seed": 42,
  "warnings": [],
  "timestamps": {
    "start": "2026-05-19T15:30:00Z",
    "candidates_done": null,
    "silver_done": null,
    "provisional_metrics_done": null
  }
}
```

Rules:

- `run_id` format: `"YYYY-MM-DD-HHMM-nogit"` while in no-git mode. (When git is
  restored later, it becomes `"YYYY-MM-DD-HHMM-<short_sha>"` — no script change
  needed; the suffix comes from a single helper.)
- `rng_seed` defaults to `42`; overridable by CLI flag. Recorded verbatim.
- `dataset_row_count`/`chroma_collection_count` are auto-detected at run start
  (read from `src.config.DATASET_ROW_COUNT` and a one-time Chroma collection
  `.count()` call). If they mismatch, append a warning and continue.
- `warnings[]` accumulates strings emitted by `run_pipelines.py` and
  `llm_pregrade.py` (e.g., `"dedup_bug: tmdb_id=… ..."`).
- `timestamps.*` are filled in by each stage as it completes (`null` until
  the stage finishes).

### 2.5 `eval/runs/<run_id>/config_snapshot.json`

Auto-derived. The script imports `src.config` and dumps every `UPPER_CASE`,
non-callable, non-module attribute as `{name: value}`, JSON-serializable only
(coerce `Path` → `str`). Never hand-maintained.

### 2.6 `eval/runs/<run_id>/metrics_provisional.json`

```json
{
  "provisional": true,
  "run_id": "2026-05-19-1530-nogit",
  "label_source": "silver_only",
  "queries_total": 20,
  "by_mode": {
    "basic":    {"hit_at_5": 0.60, "strict_hit_at_5": 0.35, "mrr_at_5": 0.42,
                 "strict_mrr_at_5": 0.21, "ndcg_at_5": 0.55, "ci_half_widths":
                 {"hit_at_5": 0.11, "mrr_at_5": 0.10, "ndcg_at_5": 0.09},
                 "queries_excluded_null": 0, "queries_with_ideal_dcg_zero": 0},
    "advanced": { /* … same shape … */ },
    "hybrid":   { /* … same shape … */ }
  },
  "by_axis": {
    "vocab_distance": {
      "high":   {"by_mode": {"basic": {"hit_at_5": 0.50, "n": 8}, "advanced": …, "hybrid": …}},
      "medium": {"by_mode": { … , "n": 8}},
      "low":    {"by_mode": { … , "n": 4, "low_sample": false}}
    },
    "era":            { … },
    "genre":          { … },
    "length":         { … },
    "ambiguity":      { … }
  },
  "bootstrap": {"B": 1000, "method": "stratified_over_queries", "seed": 42}
}
```

Rules ([05 §7.3–7.6](../specs/accuracy-audit/05-metrics-qc-and-labels.md#73-metric-formulas)):

- `provisional: true` is **mandatory** and downstream consumers must refuse to
  drive prioritization off a provisional file.
- Per-axis slices with `n < 5` set `"low_sample": true` and are not used for
  decisions; they still appear in the file for transparency.
- Grade → relevance mapping (graded NDCG): `3 → 1.0`, `2 → 0.7`, `1 → 0.3`,
  `0 → 0.0`, `null → blocked / excluded` (provisional path reports the exclusion
  count rather than blocking).
- Bootstrap: B = 1000, stratified over queries, seed = `42` (mirrors
  `rng_seed`). CI half-widths reported alongside each metric.
- Storage ranks are 0-based; the metric loop uses 1-based `i = rank + 1` and
  this conversion is unit-tested.

### 2.7 `eval/runs/current_run.txt`

Plain text. Exactly one line: the latest `run_id`. No symlinks (Windows-safe).
Updated atomically (write `current_run.txt.tmp` then rename). Phase 1 does not
update this for *provisional* runs by default; updating happens only when a
`metrics.json` (non-provisional) lands in Phase 2. **Phase 1 leaves
`current_run.txt` absent**; that is intentional.

### 2.8 Path convention

All artifact paths are computed by `eval/scripts/_run_io.py` (CX-01).
**No script may build a run-dir path by hand**; everyone goes through the
helper. This is how multi-run coexistence stays sane.

---

## 3. Files / directories to create

Tree after Phase 1 lands (only `eval/` is new; nothing under `src/` changes):

```
eval/
├── README.md                                ← CX-01
├── queries/
│   ├── v1.candidate.jsonl                   ← CX-02 (script output, human reviews)
│   └── v1.jsonl                             ← human-committed after gate H1
├── runs/                                    ← created by _run_io on first run
│   └── (per-run dirs; empty in source tree until a run executes)
├── scripts/
│   ├── __init__.py                          ← CX-01
│   ├── _run_io.py                           ← CX-01 (shared run-dir + manifest)
│   ├── _schemas.py                          ← CX-01 (dataclass/TypedDict validators)
│   ├── _diversity.py                        ← CX-02 (axis counting helpers)
│   ├── generate_queries.py                  ← CX-02
│   ├── run_pipelines.py                     ← CX-03
│   ├── llm_pregrade.py                      ← CX-04
│   └── compute_metrics.py                   ← CX-05
└── tests/
    ├── __init__.py                          ← CX-01
    ├── conftest.py                          ← CX-01 (path setup so `import src` works)
    ├── test_run_io.py                       ← CX-01
    ├── test_schemas.py                      ← CX-01
    ├── test_generate_queries.py             ← CX-02
    ├── test_run_pipelines_union.py          ← CX-03 (pure union math, no pipeline call)
    ├── test_llm_pregrade_cache.py           ← CX-04 (cache + JSON-parse handling)
    └── test_compute_metrics.py              ← CX-05 (hand-computed expected values)
```

Notes:

- `eval/tests/` uses `unittest` from the stdlib so it runs without adding
  `pytest`. If `pytest` is later installed, the tests still work because
  `unittest.TestCase` subclasses are pytest-collectible.
- `eval/scripts/_*.py` are private helpers (underscore prefix). They are not
  invoked from the command line.
- `eval/queries/v1.candidate.jsonl` is the script's draft output and is meant
  to be replaced or edited into `v1.jsonl`. Only `v1.jsonl` is the
  evaluation-authoritative file. `v1.candidate.jsonl` may be deleted by the
  human after gate H1; CX-02 does not require it to persist.

---

## 4. Files to read but not modify

No Phase 1 handoff may write to these — reads only:

- `src/config.py`
- `src/models.py`
- `src/pipelines/basic.py`
- `src/pipelines/advanced.py`
- `src/pipelines/hybrid.py`
- `src/retrieval/semantic.py`
- `src/retrieval/bm25.py`
- `src/retrieval/fusion.py`
- `src/retrieval/reranker.py`
- `src/retrieval/query_processor.py`
- `src/retrieval/filters.py`
- `src/utils/dedup.py`
- `src/utils/debug.py`
- `src/llm/langchain_ollama.py`
- `src/llm/prompts.py`
- `scripts/quality_smoke_test.py`
- `data/movies_clean.csv`
- `data/chroma_bgem3/` (Chroma collection; query-only)
- `docs/superpowers/specs/accuracy-audit/*` (this is the spec we are
  implementing — never edit it)
- `AGENTS.md`, `CLAUDE.md`

If a handoff's diff touches any of these, **Claude review must reject** and
the handoff must be redone with the correct files-to-change list.

---

## 5. Implementation order

```
CX-01  eval skeleton + _run_io + _schemas + tests + README
   │   (independent — must merge first)
   ▼
CX-02  generate_queries.py → v1.candidate.jsonl
   │
   ▼
H1     Human reviews + edits candidate set → commits eval/queries/v1.jsonl
   │   (manual gate; no AI tool may write v1.jsonl)
   ▼
CX-03  run_pipelines.py  (needs v1.jsonl + CX-01 helpers)
   │
   ▼
CX-04  llm_pregrade.py   (needs candidates.jsonl from a CX-03 dry-run)
   │
   ▼
CX-05  compute_metrics.py + unit tests (needs silver_labels.jsonl from a CX-04 dry-run)
   │
   ▼
H2     Human runs the v1 baseline end-to-end:
       run_pipelines → llm_pregrade → compute_metrics
   │
   ▼
H3     Human + Claude review metrics_provisional.json shape and coverage
   │   (no interpretation of numbers — that is Phase 2)
   ▼
PHASE 1 COMPLETE — STOP. Do not start Phase 2.
```

Each `CX-NN` is a single Codex handoff, dispatched one at a time after explicit
human approval of the prompt (per CLAUDE.md "Autonomy boundaries"). Claude
reviews each diff and validation log before the next handoff is dispatched.

---

## 6. Codex handoffs

> **All handoffs share these hard rules** (do not repeat in each prompt — they
> are inherited from AGENTS.md and CLAUDE.md):
>
> - Only edit files in the handoff's "Files to change" list.
> - Never edit files in "Files to read but not change".
> - No edits to `src/*` in any Phase 1 handoff.
> - No retrieval/ranking/embedding/reranker behavior changes.
> - No new third-party dependency without escalating first.
> - On scope expansion: **stop and report** to Claude Code Pro; do not silently
>   grow the handoff.
> - On any validation command failing: **stop and report** with full error
>   text; do not attempt a fix outside scope.
> - In no-git mode: do not run any `git` command and do not require git state
>   from the environment.

---

### CX-01 — eval skeleton + shared run-IO + schemas + tests

**Goal:** Create `eval/` directory layout, the shared `_run_io.py` helper that
owns run-ID generation / manifest writing / config snapshotting / path
resolution, schema validators in `_schemas.py`, the `eval/README.md`
operator guide, and unit tests covering both helpers. Behaviorally pure —
this handoff produces NO eval runs.

**Files to change (create):**

- `eval/README.md`
- `eval/scripts/__init__.py` (empty marker file)
- `eval/scripts/_run_io.py`
- `eval/scripts/_schemas.py`
- `eval/tests/__init__.py` (empty marker file)
- `eval/tests/conftest.py` (adds project root to `sys.path` so `import src.config` works during tests)
- `eval/tests/test_run_io.py`
- `eval/tests/test_schemas.py`

**Files to read but not change:**

- `src/config.py`
- `AGENTS.md`, `CLAUDE.md`
- `docs/superpowers/specs/accuracy-audit/04-phase1-eval-harness.md` §6.1–6.3, §6.8
- `docs/superpowers/specs/accuracy-audit/10-validation-done-risks.md` §14
- This plan, §0–§4

**Acceptance criteria:**

- `_run_io.new_run_id(now=None)` returns a string matching
  `^\d{4}-\d{2}-\d{2}-\d{4}-nogit$` (UTC, minute-precision). Accepts an
  injected `now` for tests.
- `_run_io.run_dir(run_id)` returns `Path("eval/runs/<run_id>")` resolved from
  the project root regardless of the current working directory.
- `_run_io.ensure_run_dir(run_id)` creates the directory tree and returns the
  path. Idempotent.
- `_run_io.write_manifest(run_id, *, rng_seed=42, extras=None)` writes
  `run_manifest.json` with fields exactly as in §2.4 (incl. `git_sha: null`,
  `git_dirty: null`, `git_mode: "no_git"`). `extras` is merged into the
  top-level dict (used by later handoffs to record warnings / timestamps).
- `_run_io.snapshot_config()` returns a JSON-serializable dict of every
  `UPPER_CASE`, non-callable, non-module attribute on `src.config`. `Path`
  values are coerced to `str`. Any non-serializable attr is skipped with a
  string warning in the returned dict's `"_skipped"` list.
- `_run_io.write_config_snapshot(run_id)` writes `config_snapshot.json`.
- `_run_io.append_warning(run_id, message)` reads the manifest, appends to
  `warnings[]`, writes back atomically (tempfile + rename).
- `_run_io.update_timestamp(run_id, stage)` for `stage in {"start",
  "candidates_done", "silver_done", "provisional_metrics_done"}` stamps an
  ISO-8601 UTC second-precision string.
- `_schemas.validate_query_record(d)` raises `ValueError` with a precise
  message if a query record violates §2.1 enums or required keys; returns
  the record otherwise.
- `_schemas.validate_candidate_record(d)` enforces §2.2 invariants:
  `tmdb_id: int`, `qid: str`, `per_mode` keys ⊆ `{"basic","advanced","hybrid"}`,
  `per_mode[*].rank: int >= 0`, `in_top_k_of: list[str]`. Missing modes
  must be **absent**, not `None`.
- `_schemas.validate_silver_record(d)` enforces §2.3:
  `grade ∈ {0,1,2,3,None}`, `confidence ∈ {"high","medium","low"}`,
  `model: str`, `ts` is parseable ISO-8601.
- `eval/README.md` documents the directory layout (§2.8 path discipline),
  the run lifecycle from this plan §1, no-git mode, and a 10-line
  "how to run a v1 baseline" recipe (the commands from H2 below, with
  Windows PowerShell syntax in addition to POSIX).
- `python -m compileall eval/scripts` exits 0.
- `python -m unittest discover -s eval/tests -t .` exits 0 with at least 8
  passing tests across `test_run_io.py` and `test_schemas.py`.

**Validation commands** (copy-pasteable, PowerShell on Windows):

```powershell
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -t .
```

**Dependencies:** none.

**Risk level:** **low.** No behavior changes; only new files; pure helpers
with unit tests. The only subtle risk is that `_run_io.snapshot_config`
imports `src.config`, which loads `pathlib.Path` objects — handled by
the explicit `Path → str` coercion rule.

**Reviewer:** Claude Code Pro → human.

**Stop condition (Codex MUST stop and report when any of these is true):**

- Diff touches any file outside the "Files to change" list above.
- Any validation command exits non-zero.
- A schema decision differs from §2 (e.g., representing a missing mode as
  `null` instead of an absent key).
- The handoff needs to import a third-party package not already in the venv.

**Exact Codex prompt (paste to Codex CLI verbatim after human approval):**

```text
You are implementing handoff CX-01 of the CineMatch Phase 1 plan.

Authoritative inputs (READ FIRST, do not edit):
  - AGENTS.md
  - CLAUDE.md
  - docs/superpowers/plans/2026-05-19-phase1-eval-harness-plan.md (§0, §2, §3, §4, §6 CX-01)
  - docs/superpowers/specs/accuracy-audit/04-phase1-eval-harness.md §6.1-6.3, §6.8

Your task: create the eval/ skeleton, the _run_io.py helper, _schemas.py
validators, eval/README.md, and unit tests, exactly as specified under
"CX-01" in the plan. Do not implement any other handoff. Do not edit any
file under src/. Do not run any git command — the repo is in no-git mode.

Files to change (create only):
  - eval/README.md
  - eval/scripts/__init__.py
  - eval/scripts/_run_io.py
  - eval/scripts/_schemas.py
  - eval/tests/__init__.py
  - eval/tests/conftest.py
  - eval/tests/test_run_io.py
  - eval/tests/test_schemas.py

Hard constraints:
  - Manifest fields git_sha=null, git_dirty=null, git_mode="no_git".
  - new_run_id() format: YYYY-MM-DD-HHMM-nogit, UTC minute precision.
  - All run-dir paths go through _run_io; no other module may build them.
  - No new third-party imports.
  - Do not edit eval/queries/v1.jsonl or any spec file.

Validation (must pass before reporting done):
  - python -m compileall eval/scripts        → exit 0
  - python -m unittest discover -s eval/tests -t .   → exit 0, ≥ 8 tests

Report back:
  - Exact list of files changed.
  - Exact command lines run and their full output.
  - Any assumption you made that is not stated above.

Stop and escalate if scope grows, if a validation command fails, or if you
need to touch a file outside the list above.
```

---

### CX-02 — `generate_queries.py` (draft v1 query set)

**Goal:** Produce a draft 20-query set at `eval/queries/v1.candidate.jsonl`
that meets the diversity targets in §2.1, deliberately biased toward
vocabulary-mismatch failure modes. The human then reviews, edits, and commits
the final `eval/queries/v1.jsonl`. CX-02 **never writes `v1.jsonl` itself.**

**Files to change (create):**

- `eval/scripts/_diversity.py`
- `eval/scripts/generate_queries.py`
- `eval/queries/v1.candidate.jsonl`  ← script output; checked in as a draft for the human gate
- `eval/tests/test_generate_queries.py`

**Files to read but not change:**

- `eval/scripts/_run_io.py` (CX-01)
- `eval/scripts/_schemas.py` (CX-01)
- `docs/superpowers/specs/accuracy-audit/04-phase1-eval-harness.md` §6.4
- `data/movies_clean.csv` (for sanity — `generate_queries.py` may peek at
  the column names but must NOT use the dataset to "answer" queries; the
  queries themselves are author-written templates)
- This plan, §2.1, §6 CX-02

**Acceptance criteria:**

- `generate_queries.py` writes exactly **20** JSONL records to
  `eval/queries/v1.candidate.jsonl`, each passing `_schemas.validate_query_record`.
- Diversity counts (verified by `_diversity.summarize` and asserted in the test):
  - era: 4 pre-1980, 5 1980-2000, 6 2000-2015, 5 2015+
  - genre: ≥2 each of `drama`, `thriller`, `sf`, `animation`, `horror`, `comedy`
  - vocab_distance: 8 high, 8 medium, 4 low
  - length: 8 short (≤8 words), 8 medium, 4 long (length is recomputed from
    the actual query word count, not trusted from the tag)
  - ambiguity: 4 low, 12 medium, 4 high
- All `qid` values are `q01..q20`, zero-padded, unique, in order.
- The 8 high-vocab-distance queries deliberately use phrasing whose key
  content words are unlikely to appear verbatim in TMDB overviews
  (`generate_queries.py` documents this rule in a module docstring; the
  test only checks that 8 records carry `vocab_distance: "high"`).
- `notes` field is present on every record (may be `""` but the key must
  exist).
- The script is **deterministic** given a fixed `--seed` (default `42`):
  the same seed produces byte-identical output.
- A `--out PATH` flag overrides the default output path so tests can write
  to a temp file.
- `python -m compileall eval/scripts` exits 0.
- `python -m unittest eval.tests.test_generate_queries` exits 0 with at
  least 5 passing tests (record count, schema validity, diversity counts,
  determinism, deterministic-with-seed-override).

**Validation commands:**

```powershell
python -m compileall eval/scripts
python -m unittest eval.tests.test_generate_queries
python eval/scripts/generate_queries.py --out eval/queries/v1.candidate.jsonl
# Spot-check:
python -c "import json,sys; [print(json.loads(l)['qid'], '|', json.loads(l)['query']) for l in open('eval/queries/v1.candidate.jsonl', encoding='utf-8')]"
```

**Dependencies:** CX-01 merged.

**Risk level:** **low.** Pure data-generation; no runtime contact with
pipelines or LLM; no behavior change anywhere.

**Reviewer:** Claude Code Pro → human (the human is the final judge of query
content during gate H1).

**Stop condition:**

- Diff touches anything outside the listed files.
- Diversity counts do not match §2.1 exactly. (If §2.1 is infeasible for
  some axis combination, stop and escalate — do not silently relax.)
- The script writes `eval/queries/v1.jsonl` directly. That file is the
  human's responsibility after H1.

**Exact Codex prompt:**

```text
You are implementing handoff CX-02 of the CineMatch Phase 1 plan.

Authoritative inputs (READ FIRST, do not edit):
  - docs/superpowers/plans/2026-05-19-phase1-eval-harness-plan.md (§2.1, §6 CX-02)
  - docs/superpowers/specs/accuracy-audit/04-phase1-eval-harness.md §6.4
  - eval/scripts/_run_io.py, eval/scripts/_schemas.py (from CX-01)

Your task: implement generate_queries.py that emits a draft 20-query JSONL
file meeting the §2.1 diversity targets, plus a _diversity.py helper and a
unit test. Do NOT write eval/queries/v1.jsonl. Do NOT touch src/. The repo
is in no-git mode; do not run any git command.

Files to change (create only):
  - eval/scripts/_diversity.py
  - eval/scripts/generate_queries.py
  - eval/queries/v1.candidate.jsonl       (script output, kept as draft)
  - eval/tests/test_generate_queries.py

Hard constraints:
  - Output records pass _schemas.validate_query_record.
  - Diversity counts exactly match §2.1 (any infeasibility = stop and escalate).
  - 8 of the 20 queries carry vocab_distance="high" and use phrasing whose
    content words are unlikely to appear verbatim in TMDB overviews
    (document the rationale in the module docstring).
  - Output is deterministic given --seed (default 42).
  - No new third-party imports.

Validation:
  - python -m compileall eval/scripts                        → exit 0
  - python -m unittest eval.tests.test_generate_queries      → exit 0, ≥ 5 tests
  - python eval/scripts/generate_queries.py --out eval/queries/v1.candidate.jsonl
    produces exactly 20 valid records.

Report files changed, commands run, and any assumptions.
Stop and escalate on scope creep or validation failure.
```

---

### H1 — Human gate: review and commit `eval/queries/v1.jsonl`

This is **not a Codex handoff**. No AI tool may write `eval/queries/v1.jsonl`.

The human:

1. Reads `eval/queries/v1.candidate.jsonl`.
2. Edits queries for taste, realism, and vocabulary-mismatch quality.
3. Saves the final 20-record file as `eval/queries/v1.jsonl`.
4. Verifies schema and diversity by running:

   ```powershell
   python -c "from eval.scripts._schemas import validate_query_record; import json; [validate_query_record(json.loads(l)) for l in open('eval/queries/v1.jsonl', encoding='utf-8')]"
   python -c "from eval.scripts._diversity import summarize_file; import json; print(json.dumps(summarize_file('eval/queries/v1.jsonl'), indent=2))"
   ```

5. Once committed, **no AI tool may modify `eval/queries/v1.jsonl`** for the
   remainder of v1 (per [10 §16](../specs/accuracy-audit/10-validation-done-risks.md#16-tool-autonomy-rules)). v2.jsonl is the path forward if the queries
   need rework after grading begins.

Phase 1 cannot proceed past H1 without this file existing.

---

### CX-03 — `run_pipelines.py` (union of 3 pipelines → `candidates.jsonl`)

**Goal:** For each query in `eval/queries/v1.jsonl`, run Basic / Advanced /
Hybrid with `top_k=15`, build the dedup'd union per §2.2 (soft cap 8, hard
max 15, top-5-of-any-mode guaranteed), and write `candidates.jsonl` plus
`run_manifest.json` and `config_snapshot.json` into a new run directory.
This handoff **does not change any pipeline behavior** — it only invokes
existing `src.pipelines.*.run`.

**Files to change (create):**

- `eval/scripts/run_pipelines.py`
- `eval/tests/test_run_pipelines_union.py`

**Files to read but not change:**

- `eval/scripts/_run_io.py`, `_schemas.py` (CX-01)
- `eval/queries/v1.jsonl` (created at H1)
- `src/pipelines/basic.py`, `src/pipelines/advanced.py`, `src/pipelines/hybrid.py`
- `src/config.py`
- `src/utils/dedup.py` (for `get_movie_key`)
- `docs/superpowers/specs/accuracy-audit/04-phase1-eval-harness.md` §6.5, §6.8
- This plan, §2.2, §2.4, §6 CX-03

**Acceptance criteria:**

- Script CLI:

  ```
  python eval/scripts/run_pipelines.py \
      --queries eval/queries/v1.jsonl \
      --top-k 15 \
      [--seed 42] \
      [--run-id <override>] \
      [--limit N]            # for smoke runs
  ```

- On start: creates run dir, writes manifest (timestamps.start),
  writes config_snapshot.
- For each query (sequential — do not parallelize; Ollama serialises and we
  need reproducibility): calls `basic.run(q, top_k=15, with_explanation=False)`,
  `advanced.run(q, top_k=15, with_explanation=False)`,
  `hybrid.run(q, top_k=15, with_explanation=False)`. **The
  `with_explanation=False` flag is mandatory** so we don't burn LLM calls
  on explanations during candidate generation.
- Build the union by `tmdb_id` (primary) with `movie_key` (secondary
  cross-check). If two candidates have the same `tmdb_id` but different
  `movie_key`, **append** a `"dedup_bug: qid=<q> tmdb_id=<id> movie_keys=<a>,<b>"`
  warning to the manifest (do NOT raise).
- Sort union by best (lowest) rank across all modes — top-1 anywhere wins
  ties by mode order `basic < advanced < hybrid`.
- Apply soft cap = 8, hard max = 15. **Top-5 of every mode is guaranteed
  retained**, even if that pushes the union past 8.
- Each `per_mode` entry contains the keys actually emitted by that mode
  (`rank`, `semantic_score`, `bm25_score`, `rrf_score`, `rerank_score`,
  `final_score` — whichever are present in the pipeline's output dict).
  Use `0.0` as default only when the pipeline emitted the key; absent keys
  are omitted, not coerced.
- After all queries: stamp `timestamps.candidates_done`, write
  `candidates.jsonl` (one record per line, valid against
  `_schemas.validate_candidate_record`).
- `--limit N` runs only the first N queries (used by CX-04/CX-05 dry-runs
  and by the smoke test below).
- Pure-function unit tests in `test_run_pipelines_union.py` cover the
  union algorithm against synthetic per-mode rank lists (no pipeline
  invocation, no ChromaDB):
  - top-5 of each mode is preserved even at soft cap = 8;
  - soft cap is exceeded only as needed to preserve top-5s, never beyond
    hard max = 15;
  - ties broken by mode order `basic < advanced < hybrid`;
  - dedup_bug detection on shared tmdb_id / different movie_key.
- `python -m compileall eval/scripts` exits 0.
- `python -m unittest eval.tests.test_run_pipelines_union` exits 0 with
  at least 5 passing tests.

**Validation commands:**

```powershell
python -m compileall eval/scripts
python -m unittest eval.tests.test_run_pipelines_union
# Smoke run on first 2 queries (Codex confirms shape; not the v1 baseline):
python eval/scripts/run_pipelines.py --queries eval/queries/v1.jsonl --top-k 15 --limit 2
# Then verify the resulting candidates.jsonl validates:
python -c "from eval.scripts._schemas import validate_candidate_record; import json,glob,os; runs=sorted(glob.glob('eval/runs/*-nogit')); last=runs[-1]; [validate_candidate_record(json.loads(l)) for l in open(os.path.join(last,'candidates.jsonl'),encoding='utf-8')]; print('ok', last)"
```

**Dependencies:** CX-01, CX-02, gate H1 (so `v1.jsonl` exists).

**Risk level:** **medium.** Reads from the live pipelines, so a bug here
could write garbage candidate files and waste downstream LLM-grading time —
but the pipelines themselves are unchanged. The union algorithm has subtle
edge cases (top-5 guarantee × soft cap), which is why the algorithm is
covered by isolated unit tests **independent of any pipeline call**.

**Reviewer:** Claude Code Pro → human (human approves the smoke-run output
before any full v1 baseline at H2).

**Stop condition:**

- Diff touches any pipeline file, any retrieval/ranking/embedding/reranker
  module, `src/config.py`, or any file outside the listed list.
- Any pipeline is invoked with `with_explanation=True` (forbidden — wastes
  the LLM budget for candidate generation and risks drift).
- The script raises on a `dedup_bug` instead of recording a warning.
- Any unit test fails or the smoke run produces a non-schema-valid record.
- The script writes to `current_run.txt` (forbidden in Phase 1 — see §2.7).

**Exact Codex prompt:**

```text
You are implementing handoff CX-03 of the CineMatch Phase 1 plan.

Authoritative inputs (READ FIRST, do not edit):
  - docs/superpowers/plans/2026-05-19-phase1-eval-harness-plan.md (§2.2, §2.4, §6 CX-03)
  - docs/superpowers/specs/accuracy-audit/04-phase1-eval-harness.md §6.5, §6.8
  - eval/scripts/_run_io.py and _schemas.py from CX-01
  - eval/queries/v1.jsonl (committed at human gate H1)
  - src/pipelines/{basic,advanced,hybrid}.py (read only)

Your task: implement run_pipelines.py and a union-algorithm unit test.
You may NOT edit any pipeline or retrieval module. No git commands; the
repo is in no-git mode.

Files to change (create only):
  - eval/scripts/run_pipelines.py
  - eval/tests/test_run_pipelines_union.py

Hard constraints:
  - Always call pipelines with with_explanation=False.
  - Run queries strictly sequentially.
  - Per_mode keys are OMITTED for modes a candidate didn't appear in
    (never set to None).
  - dedup_bug events go into manifest.warnings[] — never raise.
  - Update timestamps.start at run start, timestamps.candidates_done when
    candidates.jsonl is finalized.
  - Do NOT write or update eval/runs/current_run.txt.
  - Build all run-dir paths via _run_io; do not hand-construct them.

Validation:
  - python -m compileall eval/scripts                          → exit 0
  - python -m unittest eval.tests.test_run_pipelines_union     → exit 0, ≥ 5 tests
  - python eval/scripts/run_pipelines.py --queries eval/queries/v1.jsonl --top-k 15 --limit 2
    produces a run dir whose candidates.jsonl passes schema validation.

Report files changed, commands run with full output (including the smoke
run), any warnings logged into the manifest, and any assumption made.
Stop and escalate on scope creep or validation failure.
```

---

### CX-04 — `llm_pregrade.py` (silver labels with cache + JSON-rate gate)

**Goal:** Read `candidates.jsonl` from a run dir and emit
`silver_labels.jsonl` with one record per `(qid, tmdb_id)` using the
existing `llama3.2` Ollama client and the §2.3 schema. Cache results so
re-runs are idempotent. Validate JSON-parse rate ≥ 95% on the first 20
calls before bulk grading the rest.

**Files to change (create):**

- `eval/scripts/llm_pregrade.py`
- `eval/tests/test_llm_pregrade_cache.py`

**Files to read but not change:**

- `eval/scripts/_run_io.py`, `_schemas.py` (CX-01)
- `src/llm/langchain_ollama.py` (use `_invoke_with_timeout` or the public
  interface; do NOT modify it)
- `src/config.py` (for `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`)
- `docs/superpowers/specs/accuracy-audit/05-metrics-qc-and-labels.md` §6.6
- This plan, §2.3, §6 CX-04

**Acceptance criteria:**

- Script CLI:

  ```
  python eval/scripts/llm_pregrade.py --run <run_id>  [--limit N]  [--seed 42]
  ```

  If `--run` is omitted, default to the most recently created
  `eval/runs/*-nogit` directory (resolved via `_run_io.latest_run()`).
- Reads `candidates.jsonl`; for each `(qid, tmdb_id)` pair, calls the LLM
  with the §6.6 grading prompt template. Treats the call as failed if any
  of: timeout, exception, JSON-parse failure, `grade` not in `{0,1,2,3}`,
  `confidence` not in `{"high","medium","low"}`. Failed → synthetic record
  `{grade: null, confidence: "low", reason: "<short failure reason>"}`.
- **Idempotent cache:** before issuing an LLM call, read existing rows in
  `silver_labels.jsonl` and skip any `(qid, tmdb_id, model)` already
  graded. Failed (null-grade) rows ARE re-attempted on next run (failure
  ≠ cached success).
- **JSON-parse-rate gate:** after the first **20** LLM calls of a fresh
  run (i.e., not pre-existing in the cache), compute the JSON-parse rate.
  If `< 0.95`, abort the rest of the run, append a manifest warning
  `"llm_pregrade aborted: parse_rate=<x> below 0.95"`, and exit with code 2.
  The 20 already-graded rows remain written so the human can inspect them.
  Re-runs after a prompt tweak continue from there (cache still applies to
  successful rows; failed rows retry).
- Writes records in `_schemas.validate_silver_record` shape, model
  = `src.config.LLM_MODEL` ("llama3.2"), `ts` ISO-8601 UTC second precision.
- Updates `manifest.timestamps.silver_done` when complete (and only when
  the JSON-parse gate did NOT abort).
- Unit tests in `test_llm_pregrade_cache.py`:
  - cache logic: existing `(qid, tmdb_id, model)` rows are skipped
    (mock the LLM caller; assert it is not invoked for those pairs);
  - failure rows are NOT cached (next run re-attempts);
  - JSON-parse-rate gate: synthetic 20 calls, ≥1 invalid → aborts.
  - The LLM is mocked via a dependency-injected callable; do not require
    Ollama running for the test.

**Validation commands:**

```powershell
python -m compileall eval/scripts
python -m unittest eval.tests.test_llm_pregrade_cache
# Dry-run on a 2-query smoke from CX-03:
python eval/scripts/llm_pregrade.py --run <run_id_from_cx03_smoke> --limit 6
python -c "from eval.scripts._schemas import validate_silver_record; import json; [validate_silver_record(json.loads(l)) for l in open('eval/runs/<run_id>/silver_labels.jsonl', encoding='utf-8')]; print('ok')"
```

**Dependencies:** CX-01, CX-02, CX-03, gate H1 (need a real `candidates.jsonl`).

**Risk level:** **medium.** LLM calls are the budget-heavy part of Phase 1
and the most variable. Cache correctness and JSON-rate gate are mandatory
guard-rails. Behavior of `src/llm/langchain_ollama.py` is unchanged.

**Reviewer:** Claude Code Pro → human (human dry-runs on a 2-query slice
before the v1 baseline at H2).

**Stop condition:**

- Diff edits any file outside the list (especially `src/llm/*`).
- Cache treats a `grade: null` row as cached (must re-attempt).
- The JSON-parse-rate gate aborts but the run silently writes
  `silver_done`.
- The script invents fields not in §2.3 (e.g., adding `prompt_hash`,
  `latency_ms`) — those belong in a future handoff if needed.

**Exact Codex prompt:**

```text
You are implementing handoff CX-04 of the CineMatch Phase 1 plan.

Authoritative inputs (READ FIRST, do not edit):
  - docs/superpowers/plans/2026-05-19-phase1-eval-harness-plan.md (§2.3, §6 CX-04)
  - docs/superpowers/specs/accuracy-audit/05-metrics-qc-and-labels.md §6.6
  - eval/scripts/_run_io.py and _schemas.py (CX-01)
  - src/llm/langchain_ollama.py (read only)
  - src/config.py (read only; use LLM_MODEL and LLM_TIMEOUT_SECONDS)

Your task: implement llm_pregrade.py with idempotent cache, JSON-parse-rate
gate, and a unit test that mocks the LLM. No edits to src/. No git commands.

Files to change (create only):
  - eval/scripts/llm_pregrade.py
  - eval/tests/test_llm_pregrade_cache.py

Hard constraints:
  - Cache key: (qid, tmdb_id, model). Successful (non-null grade) rows skip
    the LLM call; failed (grade=null) rows retry on next run.
  - After 20 fresh LLM calls in a run, abort with exit 2 if parse_rate < 0.95;
    write a manifest warning, do NOT stamp silver_done.
  - Records validate against _schemas.validate_silver_record.
  - LLM call signature is dependency-injectable for the unit test.
  - timestamps.silver_done is set ONLY on full completion (not on abort).

Validation:
  - python -m compileall eval/scripts                  → exit 0
  - python -m unittest eval.tests.test_llm_pregrade_cache  → exit 0
  - Dry-run on 2-query smoke (--limit 6) produces a valid silver_labels.jsonl.

Report files changed, commands run with full output, parse rate observed,
and any assumption made. Stop and escalate on scope creep or validation
failure.
```

---

### CX-05 — `compute_metrics.py` (provisional + bootstrap + axes + unit tests)

**Goal:** Compute Hit@5 / strict Hit@5 / MRR@5 / strict MRR@5 / NDCG@5 per
mode, plus per-axis slices and bootstrap CIs, from `candidates.jsonl` and
`silver_labels.jsonl` of a given run, writing `metrics_provisional.json`
exactly in the §2.6 shape with `provisional: true`. Unit tests cover the
0-base → 1-base rank conversion and the metric formulas against a tiny
synthetic example with hand-computed expected values.

**Files to change (create):**

- `eval/scripts/compute_metrics.py`
- `eval/tests/test_compute_metrics.py`

**Files to read but not change:**

- `eval/scripts/_run_io.py`, `_schemas.py` (CX-01)
- `docs/superpowers/specs/accuracy-audit/05-metrics-qc-and-labels.md` §7.1–7.6
- This plan, §2.6, §6 CX-05

**Acceptance criteria:**

- Script CLI:

  ```
  python eval/scripts/compute_metrics.py --run <run_id>  [--bootstrap-b 1000]  [--seed 42]
  ```

  Defaults: `--bootstrap-b 1000`, `--seed 42`. If `--run` is omitted,
  default to `_run_io.latest_run()`.
- Loads `run_manifest.json`, `candidates.jsonl`, `silver_labels.jsonl`.
  Builds, per mode, the per-query top-5 (using each candidate's
  `per_mode[<mode>].rank`, with `rank+1` as the 1-based position; ranks
  not present mean the candidate didn't appear in that mode's top-15 and
  is excluded from that mode's metric).
- Effective label for `(qid, tmdb_id)` in Phase 1 = silver (no gold yet).
  Missing silver → label is `null`.
- Metric formulas exactly per §7.3:
  - `Hit@5 = 1 if any top-5 has grade ≥ 2 else 0`
  - `strict_Hit@5 = 1 if any top-5 has grade == 3 else 0`
  - `MRR@5 = 1 / first_rank_with_grade≥2_in_top_5  (else 0)`
  - `strict_MRR@5 = 1 / first_rank_with_grade==3_in_top_5  (else 0)`
  - `DCG@5 = Σ_{i=1..5} rel(rank_i) / log2(i+1)`, with grade→relevance map
    `3→1.0, 2→0.7, 1→0.3, 0→0.0, null→excluded`
  - `iDCG@5 = pool-based`: build ideal top-5 from the union of graded
    candidates **for that query across all modes** (per §7.3), not from
    the dataset.
  - `NDCG@5 = DCG@5 / iDCG@5` if iDCG > 0, else label as
    `queries_with_ideal_dcg_zero` and exclude from the mode mean.
- **Null-label policy (provisional path):** if a top-5 candidate has
  `grade: null`, the query is **excluded** from that mode's mean for
  metrics that consume the missing slot (Hit@5 still computes if a
  non-null top-5 row has grade ≥ 2; NDCG excludes the query if any of
  the top-5's relevance is undefined for that mode). Counters
  `queries_excluded_null` reported per mode.
- Bootstrap: `B=1000`, stratified-over-queries, seeded by `--seed`. Report
  symmetric 95% CI **half-widths** for `hit_at_5`, `mrr_at_5`, `ndcg_at_5`
  per mode. Strict variants do not require CIs in Phase 1.
- Per-axis breakdown: for each tag axis
  (`era`, `genre`, `vocab_distance`, `length`, `ambiguity`), compute
  per-mode metrics on the sub-slice. Slice with `n < 5` → set
  `"low_sample": true`. Genre slices: a query with multiple genre tags
  contributes to each of its genres.
- Writes `metrics_provisional.json` exactly in §2.6 shape; `provisional: true`.
- Stamps `manifest.timestamps.provisional_metrics_done` on success.
- **Phase 1 does NOT update `current_run.txt`.**
- Unit tests in `test_compute_metrics.py` against a tiny synthetic dataset
  (3 queries, 2 modes, hand-computed expected values written in test
  docstrings):
  - 0-based stored rank → 1-based formula index conversion is correct;
  - Hit@5 / strict Hit@5;
  - MRR@5 first-rank inversion;
  - DCG@5 with the exact `1/log2(i+1)` denominators;
  - NDCG@5 pool-based iDCG (ideal built from the per-query union of
    graded candidates, not from all data);
  - null-label exclusion behavior per the rules above;
  - bootstrap CI shrinks toward 0 as the synthetic per-query metric
    variance shrinks (sanity check; not a strict equality).

**Validation commands:**

```powershell
python -m compileall eval/scripts
python -m unittest eval.tests.test_compute_metrics
# End-to-end dry-run on the CX-04 smoke output:
python eval/scripts/compute_metrics.py --run <run_id_from_cx04_smoke>
python -c "import json; d=json.load(open('eval/runs/<run_id>/metrics_provisional.json', encoding='utf-8')); assert d['provisional'] is True and 'by_mode' in d and 'by_axis' in d; print('ok')"
```

**Dependencies:** CX-01, CX-02, CX-03, CX-04.

**Risk level:** **medium.** Metric correctness is the foundation of every
Phase 4 ablation and Phase 5 prioritization decision later — a silent
off-by-one in rank or a wrong iDCG would invalidate the entire program.
Mitigations: explicit unit tests with hand-computed expected values; the
plan re-states the rank convention; iDCG is explicitly pool-based.

**Reviewer:** Claude Code Pro → human. Claude additionally cross-checks
the metric output on **one** query by hand before approving.

**Stop condition:**

- Diff touches any file outside the listed list.
- iDCG is computed from the dataset (or from a single mode) instead of
  per-query across-mode union.
- 0-base / 1-base conversion is collapsed (e.g., using stored rank
  directly in `log2(rank+1)`).
- `metrics.json` (non-provisional) is written — Phase 1 writes ONLY
  `metrics_provisional.json`.
- `current_run.txt` is written — Phase 1 does not update it.

**Exact Codex prompt:**

```text
You are implementing handoff CX-05 of the CineMatch Phase 1 plan.

Authoritative inputs (READ FIRST, do not edit):
  - docs/superpowers/plans/2026-05-19-phase1-eval-harness-plan.md (§2.6, §6 CX-05)
  - docs/superpowers/specs/accuracy-audit/05-metrics-qc-and-labels.md §7.1-7.6
  - eval/scripts/_run_io.py and _schemas.py (CX-01)

Your task: implement compute_metrics.py for the provisional path, plus a
unit test suite with hand-computed expected values on a 3-query 2-mode
synthetic dataset. No edits to src/. No git commands.

Files to change (create only):
  - eval/scripts/compute_metrics.py
  - eval/tests/test_compute_metrics.py

Hard constraints:
  - 0-based storage ranks, 1-based formula index (i = rank+1), verified
    by a dedicated unit test.
  - iDCG is pool-based: ideal top-5 is built from the union of GRADED
    candidates for the query across ALL evaluated modes — never from the
    dataset.
  - Grade→relevance: 3→1.0, 2→0.7, 1→0.3, 0→0.0, null→excluded.
  - Provisional null-label policy: report queries_excluded_null counts.
  - Bootstrap B=1000, stratified-over-queries, seeded.
  - Output exactly matches §2.6 shape; provisional: true is mandatory.
  - DO NOT write metrics.json (Phase 2 only).
  - DO NOT update eval/runs/current_run.txt.

Validation:
  - python -m compileall eval/scripts                  → exit 0
  - python -m unittest eval.tests.test_compute_metrics → exit 0, ≥ 7 tests
  - End-to-end dry-run on the CX-04 smoke run produces a valid
    metrics_provisional.json.

Report files changed, commands run with full output, and any assumption
made. Stop and escalate on scope creep, validation failure, or if any
metric you compute disagrees with a hand-computed expected value in the
unit test.
```

---

## 7. Validation commands (cumulative)

The full Phase 1 validation, run by the human at H2 after all five Codex
handoffs land:

```powershell
# 1. Compile-clean and tests-green for the harness
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -t .

# 2. Pipeline-import sanity (uses existing project smoke test; reads only)
python scripts/quality_smoke_test.py --no-llm

# 3. v1 baseline (long-running; human-triggered; do NOT autonomy-run)
python eval/scripts/run_pipelines.py --queries eval/queries/v1.jsonl --top-k 15
python eval/scripts/llm_pregrade.py
python eval/scripts/compute_metrics.py

# 4. Final shape check on metrics_provisional.json
python -c "import json,glob,os; runs=sorted(glob.glob('eval/runs/*-nogit')); last=runs[-1]; d=json.load(open(os.path.join(last,'metrics_provisional.json'), encoding='utf-8')); assert d['provisional'] is True and len(d['by_mode'])==3 and 'vocab_distance' in d['by_axis']; print('ok', last)"
```

Step (3) is the only one that is genuinely long-running (it issues hundreds
of Ollama calls). It runs **once** in Phase 1, by the human, per
[10 §16](../specs/accuracy-audit/10-validation-done-risks.md#16-tool-autonomy-rules)
(no long-running jobs by AI autonomy).

---

## 8. Human review checkpoints

| Gate | After handoff | Human action | Stop condition if not satisfied                               |
|------|---------------|--------------|---------------------------------------------------------------|
| R1   | CX-01         | Read diff (8 files); confirm tests pass on the human's machine | Any file outside the declared list; any test failure          |
| R2   | CX-02         | Read diff (4 files); confirm `v1.candidate.jsonl` looks usable | Diversity counts off; queries feel unrealistic                |
| H1   | (post-R2)     | **Edit and commit `eval/queries/v1.jsonl`** (no AI tool may do this) | Schema validation fails on the committed file                 |
| R3   | CX-03         | Read diff (2 files); run smoke `--limit 2` and inspect candidates | `src/*` touched; smoke run produces invalid candidates        |
| R4   | CX-04         | Read diff (2 files); run a 2-query smoke; eyeball silver labels   | Parse rate < 0.95; cache treats failures as cached            |
| R5   | CX-05         | Read diff (2 files); claude reviews 1-query metric by hand        | Hand-computed value disagrees with script output              |
| H2   | (post-R5)     | **Run the full v1 baseline** end-to-end per §7 step 3            | Any stage fails; `metrics_provisional.json` shape wrong       |
| H3   | (post-H2)     | Read `metrics_provisional.json`; confirm 3 modes × 5 axes present | Missing modes/axes; bootstrap fields absent                   |

**Phase 1 ends at H3.** No Phase 2 work (review sheet, Gradio app, gold
labels, QC, merge, final metrics) begins until a separate Phase 2 plan is
written and approved.

---

## 9. Risks and rollback

| Risk | Likelihood | Impact | Mitigation                                                                                          | Rollback                                                       |
|------|-----------|--------|------------------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| Codex silently expands a handoff scope (touches `src/`)                          | low    | high   | "Files to change" enumerated per handoff; Claude review against the list; stop-condition explicit | Discard diff; redo handoff with corrected files-to-change      |
| Union algorithm mis-applies soft cap and drops a top-5                            | medium | high   | Isolated unit tests on synthetic per-mode rank lists, independent of pipeline calls               | Fix in `run_pipelines.py`; rerun smoke `--limit 2`             |
| Off-by-one rank (0-base vs 1-base) in metric formulas                             | medium | high   | Dedicated unit test and explicit hand-computed expected values in `test_compute_metrics.py`       | Fix in `compute_metrics.py`; rerun unit tests + smoke          |
| iDCG built incorrectly (dataset-wide instead of per-query pool)                   | medium | high   | iDCG explicitly pool-based in §2.6 and CX-05 acceptance; covered by unit test                     | Fix and rerun unit test + smoke                                |
| LLM grader (llama3.2) noisy / low JSON-parse rate                                 | medium | medium | 20-call gate at ≥95% parse rate aborts the run with a manifest warning                            | Tweak prompt in `llm_pregrade.py` (cache preserves successes)  |
| Ollama unreachable mid-grading                                                    | low    | medium | Each call wrapped in the existing `_invoke_with_timeout` (25s); failures become null-grade rows that retry next run | Restart Ollama; re-run `llm_pregrade.py` (cache resumes)       |
| Config snapshotter chokes on a non-serializable attr                              | low    | low    | `_skipped` list + warning; never raises                                                            | Patch the coercion list; rerun                                  |
| `current_run.txt` accidentally written in Phase 1                                 | low    | medium | Stop condition on CX-03 and CX-05; explicit §2.7 rule                                              | Delete the file; the live invariant is "no Phase 1 update"     |
| Human commits a `v1.jsonl` that violates schema or diversity                      | medium | medium | Schema + diversity verification at H1 with copy-pasteable commands                                | Edit `v1.jsonl` until it passes; this is the only file an AI tool cannot fix |
| Codex installs a new dependency without escalating                                | low    | high   | Hard rule "no new third-party imports" in each handoff prompt                                      | Discard diff; redo handoff                                      |
| `metrics_provisional.json` mistakenly consumed for decisions                      | low    | high   | `provisional: true` field + plan §1 spelling out "Phase 1 stop point"                              | Phase 5 readers gate on this field (re-enforced in Phase 5 plan) |

**No code-rollback hazard exists in Phase 1**: every change is additive
under `eval/`, and no file under `src/` is touched. Rolling back any
handoff is just deleting the files it created (or reverting them when git
returns). The dataset and ChromaDB collection are read-only.

---

## 10. Stopping point

After H3 lands, **Phase 1 is complete. STOP.**

Do not:

- Read or interpret the metric numbers as a baseline claim (the file is
  `provisional: true`; that is the contract).
- Start `build_review_sheet.py`, `review_app.py`, `merge_labels.py`,
  `qc_analyze.py` (Phase 2).
- Start `audit/findings.md` or library lookups (Phase 3).
- Start `ablate.py` or ablation runs (Phase 4).
- Touch `src/*` or change retrieval/ranking/reranker (Phase 5 at earliest).
- Trigger ChromaDB re-ingestion (gated on Phase 4 evidence; human-only).

The next plan to write is **Phase 2 — gold review & QC**, scoped to:
`build_review_sheet.py`, `review_app.py` (Gradio), `qc_analyze.py`,
`merge_labels.py`, then a non-provisional `compute_metrics.py` run and the
first update to `eval/runs/current_run.txt`.

---

## 11. Self-review (Claude Code Pro, against Phase 1 specs)

Conducted against
[04-phase1-eval-harness.md](../specs/accuracy-audit/04-phase1-eval-harness.md),
[05-metrics-qc-and-labels.md](../specs/accuracy-audit/05-metrics-qc-and-labels.md),
[03-six-phase-plan.md](../specs/accuracy-audit/03-six-phase-plan.md) §1.1–1.6,
[09](../specs/accuracy-audit/09-ai-handoff-and-conflict-protocol.md),
[10](../specs/accuracy-audit/10-validation-done-risks.md).

| Spec requirement | Covered by | Notes |
|---|---|---|
| `eval/` directory layout (04 §6.1)                          | CX-01 (§3 tree)                  | Matches incl. `scripts/`, `runs/`, `queries/`. No symlink. `current_run.txt` deferred to Phase 2 per §2.7. |
| Data schemas (04 §6.2)                                      | §2.1–2.6 + `_schemas.py` (CX-01) | Verbatim shape; enums made explicit. |
| Run lifecycle (04 §6.3)                                     | §5 + CX-03/04/05                 | Phase 1 stops at provisional metrics; Phase 2 stages (review sheet through final metrics) deferred. |
| Query generation strategy (04 §6.4)                         | CX-02 + §2.1                     | Diversity targets enforced and unit-tested. |
| Candidate union construction (04 §6.5)                      | CX-03                            | Soft cap 8 / hard max 15 / top-5 preserved / dedup_bug warning. |
| Reproducibility (04 §6.8)                                   | CX-01 (`_run_io`)                | rng_seed=42, manifest, config_snapshot. Git fields nulled per §0. |
| LLM pre-grading (05 §6.6)                                   | CX-04                            | llama3.2, 25s timeout, cache, ≥95% JSON-parse gate, null records on failure. |
| Grade→relevance + null policy (05 §7.1, §7.2)               | CX-05 + §2.6                     | Provisional path reports `queries_excluded_null` (not blocks). |
| Metric formulas (05 §7.3)                                   | CX-05 + unit tests               | 0-base → 1-base conversion called out and tested. iDCG pool-based. |
| CIs (05 §7.4)                                               | CX-05                            | B=1000, stratified, seeded; half-widths reported. |
| Per-axis breakdown (05 §7.5)                                | CX-05                            | `low_sample` flag at n<5. |
| Provisional vs final outputs (05 §7.6)                      | CX-05 + §2.6                     | `provisional: true` mandatory; `metrics.json` is Phase 2. |
| AI handoff routing (09 §12)                                 | §6 + plan ownership              | Plan owner: Claude. Implementer: Codex. Reviewer: Claude → human. Routing-matrix override is explicit in this plan. |
| Conflict protocol (09 §13)                                  | §0 + §6 header                   | Branch locks deferred in no-git mode; "one handoff at a time + declared files-to-change + diff review" substitutes. |
| Validation gate (10 §14)                                    | §7 + per-handoff sections        | Honored in spirit (compile + tests + harness run). |
| Tool autonomy (10 §16)                                      | §7 (step 3) + §8 H2              | Long-running v1 baseline is human-triggered only. |
| Risks (10 §18)                                              | §9                               | Plan-level risks restated and extended with handoff-specific ones. |

**No spec requirement is uncovered.** The only deferred items are Phase 2+
content (review sheet, gold labels, QC, merge, final metrics,
current_run.txt update, axis-driven adaptive expansion) — those are out of
scope for Phase 1 by design.

---

## 12. Execution handoff

The writing-plans skill normally offers a choice between subagent-driven
execution and inline execution. Per CLAUDE.md, **neither applies here**:
Claude does not implement; Codex CLI does, one handoff at a time, after
explicit human approval per prompt. Claude reviews each diff before the
next handoff is dispatched.

**Next action requested from the human:** approve the plan (or request
edits), then explicitly approve **CX-01** as the first Codex handoff. No
Codex call will be made before that approval.
