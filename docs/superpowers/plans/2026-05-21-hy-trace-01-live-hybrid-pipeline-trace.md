---
title: HY-TRACE-01 — Live/full hybrid pipeline root-cause trace
date: 2026-05-21
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one tooling ticket, human-approved before dispatch)
human: approves dispatch (Gate A); runs the live trace; accepts the trace and makes the fix-direction decision (Gate E)
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 05-metrics-qc-and-labels.md
parent_run: eval/runs/2026-05-19-1846-nogit
parent_plan: docs/superpowers/plans/2026-05-21-hybrid-strict-gap-diagnostic-plan.md
git_mode: no_git
status: Gate D PASSED (2026-05-21). HY-TRACE-01 implemented by Codex CLI (3 files; 103 -> 115 tests, +12) and reviewed by Claude Code Pro — matches spec, no blockers. Next: human-run live trace, then Gate E. No fix dispatched.
---

# HY-TRACE-01 — Live/Full Hybrid Pipeline Root-Cause Trace

> **For agentic workers:** This plan is executed by **Codex CLI** for one
> tooling ticket (HY-TRACE-01), with explicit human approval before the
> Codex prompt is sent. Claude Code Pro reviews the diff and the hermetic
> validation log. **This plan is trace-only. No `src/*` edits. No
> `app.py` / recommender-runtime edits. No ranking, retrieval, BM25, RRF,
> fusion, reranker, or embedding behavior change. No config tuning.** It
> adds one read-only diagnostic tool under `eval/` that *imports the live
> `src/` retrieval stage functions as libraries* and reproduces the hybrid
> pipeline composition to capture true ranked lists. The ticket uses the
> 9-field Codex handoff format from `CLAUDE.md`.

**This plan is the gated follow-on to HX-01** (`2026-05-21-hybrid-strict-
gap-diagnostic-plan.md`). HX-01's Gate E (2026-05-21) accepted the hybrid
strict-gap diagnosis and chose **option (1): deeper analysis** — explicitly
deferring a fix until a **live/full hybrid pipeline trace with true ranked
lists** exists. HX-01 could only re-sort the sparse 220-row labeled subset
in `candidates.jsonl`; it could not tell, for the 5 "absent from hybrid
top-15" cases, whether the perfect movie was *unretrieved* or merely
*ranked low*. HY-TRACE-01 produces that missing evidence.

**Goal (one sentence):** Build one Codex tool, `hybrid_live_trace.py`,
that re-runs the live hybrid pipeline on the 8 hybrid-attributable queries
from HX-01 and records, for every gold grade-3 target, its true rank and
score at each pipeline stage (semantic → BM25 → RRF fusion → rerank pool →
reranker → final blend) — classifying the loss mechanism per target —
**without editing `src/*`, without changing any ranking behavior, and
without tuning any config**, producing the evidence base for the Gate E
fix-direction decision.

**Architecture:** A single read-only diagnostic tool under
`eval/scripts/`. It imports the *real* stage functions from
`src.retrieval.*` and `src.utils.dedup` and reproduces `hybrid.run()`'s
stage composition (`src/pipelines/hybrid.py` lines 52–100) so it can
capture each intermediate ranked list — which `hybrid.run()` itself does
not return. Faithfulness to `hybrid.run()` is enforced by a unit test
(`test_composition_matches_hybrid_run`). It writes outputs only into
`eval/runs/<run_id>/analysis/hybrid_live_trace/`.

**Tech stack:** Python 3.11+, stdlib (`json`, `pathlib`, `argparse`,
`sys`, `datetime`). Imports existing eval modules
(`eval.scripts._run_io`, `error_report`) and live `src` modules
(`src.config`, `src.retrieval.*`, `src.pipelines.hybrid`,
`src.utils.dedup`) **as libraries** — none are modified. No new
dependency.

---

## 0. Scope, gates, and hard constraints

### 0.1 What HY-TRACE-01 is

One **trace-only** Codex tooling ticket. It produces evidence; it does not
fix anything. Per `CLAUDE.md`, Claude plans and reviews; Codex implements;
the human approves each gate and **runs the live trace**.

### 0.2 Hard constraints (binding on the ticket and every step)

1. **Trace-only. No behavior-changing ranking fix.** No edit to retrieval,
   BM25, RRF, fusion, reranker, embedding, or any `src/*` / `app.py` /
   recommender-runtime code. If the trace warrants a fix, that is a
   **separate, separately-gated plan** — never this one.
2. **No config tuning.** `src/config.py` is read and snapshotted, never
   edited. The trace runs the pipeline under whatever config is live.
3. **No `src/*` edits.** All tooling lives under `eval/`. `src` modules
   are **imported as libraries**, never modified (see §7).
4. **No prompt / recommendation / UX changes.**
5. **No eval-label changes.** `gold_labels.jsonl`, `silver_labels.jsonl`,
   `metrics.json`, and every `analysis/` artifact from prior tickets are
   read-only inputs.
6. **No re-litigating q12 / q13.** q12 is a resolved silver-label
   artifact; q13 is `no_perfect_candidate` (no gold grade-3) — a
   structural strict miss, **not a bug**. Neither is traced, and q13 is
   never treated as a ranking bug.
7. **No broad refactor.** One new script, one new test file, one
   one-line README edit. Nothing else.
8. **The first ticket is trace-only.** §7 proves no `src/`
   instrumentation is required; therefore none is in scope. If Gate D
   review finds the composition cannot be faithfully reproduced, the
   fallback is a *separate* follow-up ticket — not an in-scope expansion.

### 0.3 Honest caveats

- **The trace re-runs the live pipeline; it is not idempotent by design.**
  Unlike HX-01 (deterministic re-sort of stored data), HY-TRACE-01
  executes retrieval, fusion, and the cross-encoder live. `hybrid.run()`
  resolves its retrieval query through a **non-deterministic Ollama
  `expand_query` call** (`HYBRID_USE_LLM_EXPANSION = True`). The trace
  therefore runs each query **`--repeat` times** (default 3), records the
  exact resolved query for every repeat, and reports per-target rank
  **stability** across repeats. Non-determinism is *measured and
  disclosed*, never assumed away.
- **The live trace loads heavy models** (BGE-M3 embedder, the
  `bge-reranker-v2-m3` cross-encoder, ChromaDB, the 27,762-row BM25
  index) and calls Ollama. Per `CLAUDE.md` ("Do not run long jobs"), the
  **live trace run is human-run**. Codex implements the tool and runs only
  the **hermetic** validation (compile, unit tests, `--dry-run`); the
  human runs the model-loading trace after Gate D.
- **Identity is keyed on `movie_key` (normalized title + year)** — the
  same identity `src.utils.dedup`, `rrf_fusion`, and the reranker use. A
  per-stage `tmdb_id` cross-check is recorded as `identity_warning` when
  it disagrees; classification trusts `movie_key` because that is what the
  pipeline itself collapses on.

### 0.4 Non-goals (explicit deferrals)

- **Any ranking / RRF / BM25 / reranker / fusion / embedding / query-
  expansion change**, and any `src/*`, `app.py`, or config edit. A fix, if
  chosen at Gate E, is its own separately-gated plan.
- **`src/` instrumentation** (a `trace=` parameter, a debug hook). §7
  proves it is unnecessary; it is rejected for this ticket.
- **Editing `hybrid_gap_trace.py` (HX-01), `hybrid_stage_trace.py`
  (CX-08), or `error_report.py` (CX-10).**
- **Re-running the full 20-query / 3-mode evaluation.** HY-TRACE-01 traces
  exactly 8 queries through exactly one mode (hybrid).
- A markdown narrative report — the decision is made from
  `diagnosis.json` at Gate E.

### 0.5 Gate map

| Gate | When | Who | What |
|---|---|---|---|
| **A — Dispatch approval** | Before the HY-TRACE-01 Codex prompt is sent | Human | Approves the specific HY-TRACE-01 handoff. Per `CLAUDE.md`, Claude does **not** auto-dispatch Codex. **This plan stops here until Gate A is given.** |
| **D — Claude review** | After Codex finishes the tool + hermetic validation | Claude | Reviews the 3-file diff vs the allowed list (§4) and the hermetic validation log (§8). Confirms no `src/*` touched, no ranking logic re-implemented, scope correct. Reports matches / deviations / blockers. |
| **(human-run trace)** | After Gate D | Human | Runs `hybrid_live_trace.py --repeat 3` (§8 human-run block); produces `trace.jsonl` + `diagnosis.json`. |
| **E — Human accept + fix-direction decision** | After the human-run trace | Human + Claude | Claude summarizes `diagnosis.json` (§10). Human accepts the trace and picks a Gate E branch (§12). This plan pre-commits to no fix. |

---

## 1. Current evidence

All figures are read from the accepted authoritative artifacts in
`eval/runs/2026-05-19-1846-nogit/` and verified for this plan.

- **`metrics.json`** (`merged_gold_over_silver`, `provisional: false`) —
  `strict_hit@5`: basic **0.50**, advanced **0.50**, hybrid **0.25**.
- **HX-01 `analysis/hybrid_gap/diagnosis.json`** partitions the 15 hybrid
  strict-miss queries: `hybrid_attributable` **8**, `shared_miss` **0**,
  `no_perfect_candidate` **7**. Strict-hit has a hard ceiling of 13/20
  because 7 of the 15 misses have no gold grade-3 candidate at all.
- **`hybrid_attributable` = `q03 q04 q05 q06 q07 q08 q10 q18`** — for each,
  a gold grade-3 candidate provably exists *and* at least one other mode
  ranks it top-5, yet hybrid does not.
- **HX-01 `analysis/hybrid_gap/trace.jsonl`** (the per-target stage trace
  over the 220-row labeled subset) found the gap splits into **≥ 2
  mechanisms**:
  1. The perfect candidate is **absent from hybrid's labeled top-15** in
     **5/8** cases — `q04, q05, q07, q08, q18` — while basic and/or
     advanced rank it top-5.
  2. The reranker **recovers** the perfect candidate (`rerank_score` rank
     ≈ 1–2) but the **final-score blend re-demotes** it in the remaining
     **3/8** cases — `q03, q06, q10`.
- **RRF and the cross-encoder are not the primary suspects** — HX-01's
  `rrf_score` and `rerank_score` demoting counts are 0; the reranker
  appears to *recover* the target in several cases.
- **Gold grade-3 targets** (from `gold_labels.jsonl`, `grade == 3`, per
  HX-01 `trace.jsonl`): q03→`10681` (WALL·E), q04→`25199` (Teen Witch),
  q05→`144204` (Thanatomorphose), q06→`367551` (American Hero),
  q07→`63700` (My Babysitter's a Vampire), q08→`545611` (Everything
  Everywhere All at Once), q10→`8329` ([REC]), q18→`9489` (You've Got
  Mail).

**Why HX-01's evidence is insufficient.** HX-01's stage ranks are
positions inside the **220-row labeled subset**, not full ranked lists:

- `not_retrieved_by_hybrid` in HX-01 means "absent from hybrid's labeled
  top-15 / no `per_mode.hybrid` block" — which conflates *truly
  unretrieved* (not in the 1,500-deep semantic or BM25 lists) with
  *retrieved but ranked low* (e.g. semantic rank 900, or RRF rank 600).
  These demand **opposite fixes** and HX-01 cannot tell them apart.
- HX-01's `demoting_stage` is a first-crossing heuristic over sparse
  ranks; for q03 it labels `semantic_score` even though the live story is
  a rerank-recovery / final-demotion. Only true ranked lists resolve this.

HY-TRACE-01 closes exactly this gap by re-running the live pipeline and
recording true ranks out of `CANDIDATE_POOL = 1500`, `RERANK_POOL = 800`,
and `RERANK_TOP_K = 50`.

---

## 2. Root-cause hypotheses

The trace is designed to confirm or refute these — it does not assume any.

**Pipeline-structure context (verified in `src/pipelines/`):**

| Mode | Retrieval query | Semantic passes | Fusion | Rerank | Final ordering |
|---|---|---|---|---|---|
| `basic` | `expand_retrieval_query(normalize_query(q))` — **deterministic, no LLM** | 1 | none | none | `final_score = semantic_score` |
| `advanced` | LLM-expanded **+ HyDE** synthetic-overview pass | 2 (expanded + HyDE), RRF-fused | RRF(semantic, BM25) | cross-encoder | blended `final_score` |
| `hybrid` | LLM-expanded (`expand_query`) — **no HyDE** | 1 | RRF(semantic, BM25) | cross-encoder | blended `final_score` |

**H1 — Retrieval recall loss (hybrid lacks HyDE).** For the 5
advanced-referenced targets (`q03 q04 q08 q10 q18`), advanced's second
semantic pass over a HyDE synthetic overview retrieves the target; hybrid
runs only one semantic pass over the LLM-expanded query and never sees it.
*Predicted signature:* target absent from hybrid's semantic top-1500 →
`unretrieved`.

**H2 — LLM query-expansion drift.** For the 3 basic-referenced targets
(`q05 q06 q07`), basic finds the target with a **plain deterministic
query** and no reranker. Hybrid retrieves with a **non-deterministic
LLM-expanded query**. If hybrid's semantic misses what basic's semantic
finds, the only difference is the query string. *Predicted signature:*
target present in basic-style retrieval but absent/low in hybrid's
semantic, with a visibly drifted `resolved.retrieval_query`; possibly
**unstable** across `--repeat`.

**H3 — Fusion / pool-depth cutoff.** The target is retrieved by semantic
and/or BM25 but lost before the cross-encoder ever scores it — either
dropped at the `rrf_fusion` `top_k = RERANK_POOL = 800` cap, or surviving
RRF but ranked ≥ `RERANK_TOP_K = 50` so it never enters the rerank pool.
*Predicted signature:* `retrieved_dropped_at_fusion` or
`retrieved_dropped_before_rerank_pool`.

**H4 — Final-score blend re-demotion.** For `q03 q06 q10`, the
cross-encoder ranks the target highly but
`final_score = rerank_score + 0.08·vote_prior + 0.20·upstream_prior +
0.10·source_agreement` (`src/retrieval/reranker.py`) re-demotes it: the
target has a strong `rerank_score` but a weak `rrf_score`-derived
`upstream_prior` and/or low `vote_count`, so the blend pulls it back below
competitors. *Predicted signature:* `rerank_recovered_final_demoted`
(`rerank_rank < 5` but `final_rank ≥ 5`).

**H5 — Instability.** The hybrid gap is partly variance from the
non-deterministic `expand_query` call rather than a fixed defect.
*Predicted signature:* a target's `loss_classification` differs across
`--repeat` runs → `stable: false`.

HX-01 already weakened the "RRF" and "reranker itself" hypotheses; the
trace will either confirm that or revise it with true ranks.

---

## 3. Exact queries to trace

HY-TRACE-01 traces **exactly these 8 queries** — the
`hybrid_attributable` partition from HX-01's `diagnosis.json`:

| qid | query | gold grade-3 target | HX-01 reference mode |
|---|---|---|---|
| q03 | a trash robot falls in love in space | 10681 — WALL·E | advanced |
| q04 | teenage witches weaponize popularity and resentment | 25199 — Teen Witch | advanced |
| q05 | a body horror story where ambition mutates into something intimate and disgusting | 144204 — Thanatomorphose | basic |
| q06 | a superhero comedy where a smug celebrity keeps failing upward… | 367551 — American Hero | basic |
| q07 | a mockumentary about vampires sharing chores, rent, and eternal grudges | 63700 — My Babysitter's a Vampire | basic |
| q08 | a multiverse family comedy about taxes, laundry, martial arts… | 545611 — Everything Everywhere All at Once | advanced |
| q10 | found footage friends chased through a haunted apartment maze | 8329 — [REC] | advanced |
| q18 | a romantic comedy about fake identities, email, and urban bookstores | 9489 — You've Got Mail | advanced |

**Rules:**

- The qid list is **read at runtime from `analysis/hybrid_gap/
  diagnosis.json` → `partition.hybrid_attributable`** (single source of
  truth) and asserted to equal the documented constant
  `HYBRID_ATTRIBUTABLE_QIDS` above. A mismatch is a hard error.
- The gold grade-3 target tmdb_ids are **read from `gold_labels.jsonl`**
  (`grade == 3`), never hardcoded. A qid with **multiple** grade-3 labels
  has **every** grade-3 target traced (one trace record per target).
- `q12` and `q13` are **not** in this set and are **not** traced. The 7
  `no_perfect_candidate` qids (`q02 q09 q13 q14 q16 q17 q19`) are not
  traced — they have no gold grade-3 target.

---

## 4. Allowed files (HY-TRACE-01 may create/modify only these three)

- **Create:** `eval/scripts/hybrid_live_trace.py`
- **Create:** `eval/tests/test_hybrid_live_trace.py`
- **Modify (one line — add `hybrid_live_trace.py` to the `scripts/` block
  of the Layout fence):** `eval/README.md`

### Inputs (read-only — the tool must never write these)

- `eval/runs/<run_id>/gold_labels.jsonl` — gold grade-3 truth.
- `eval/runs/<run_id>/analysis/hybrid_gap/diagnosis.json` — the
  `hybrid_attributable` qid list.
- `eval/queries/v1.jsonl` — query text.
- `data/movies_clean.csv` — the `tmdb_id → movie_key` identity bridge
  (the `id` column is the TMDB id; verified: `id 550` = *Fight Club*).
- Modules **imported as libraries, never edited:**
  `eval.scripts._run_io`, `eval.scripts.error_report`, `src.config`,
  `src.retrieval.query_processor`, `src.retrieval.filters`,
  `src.retrieval.semantic`, `src.retrieval.bm25`, `src.retrieval.fusion`,
  `src.retrieval.reranker`, `src.utils.dedup`, `src.pipelines.hybrid`
  (for the private `_score` sort helper — see §7).

### Outputs (the tool's only writes)

- `eval/runs/<run_id>/analysis/hybrid_live_trace/trace.jsonl`
- `eval/runs/<run_id>/analysis/hybrid_live_trace/diagnosis.json`

`analysis/hybrid_live_trace/` is created with
`mkdir(parents=True, exist_ok=True)`; both files are written atomically
via `_run_io._atomic_write_text` / `_atomic_write_json`.

---

## 5. Forbidden files (the tool must never create or modify any of these)

- **Anything under `src/`** — including `src/config.py`, every
  `src/retrieval/*`, `src/pipelines/*`, `src/models.py`, `src/llm/*`,
  `src/utils/*`.
- `app.py` and any recommender-runtime module.
- `candidates.jsonl`, `gold_labels.jsonl`, `silver_labels.jsonl`,
  `metrics.json`, `metrics_provisional.json`, `run_manifest.json`,
  `config_snapshot.json`.
- Anything under `analysis/error_report/`, `analysis/hybrid_gap/`,
  `analysis/hybrid_stage_trace/`, `analysis/regrade/`,
  `analysis/case_studies/`, `analysis/audit_silver_labels/`.
- `compute_metrics.py`, `merge_labels.py`, `error_report.py`,
  `hybrid_gap_trace.py`, `hybrid_stage_trace.py`, `run_pipelines.py`,
  `_run_io.py`, `_schemas.py` — all imported, never edited.
- Any eval/queries file; `eval/queries/v1.jsonl` is read-only.

The tool's **only** writes are the two files named in §4 Outputs.

---

## 6. Trace output schema

### 6.1 `analysis/hybrid_live_trace/trace.jsonl`

One JSON object per **(qid, gold-grade-3 tmdb_id, repeat)**, sorted by
`(qid, tmdb_id, repeat)`. Exact keys:

```json
{
  "schema_version": "hy-trace-01.v1",
  "run_id": "2026-05-19-1846-nogit",
  "qid": "q03",
  "tmdb_id": 10681,
  "movie_key": "title:wall e|year:2008",
  "title": "WALL·E",
  "gold_grade": 3,
  "repeat": 0,
  "resolved": {
    "retrieval_query": "<the exact query passed to semantic_search/bm25_search>",
    "rerank_query": "<the exact query passed to rerank>",
    "filters": null
  },
  "semantic": {"present": true,  "rank": 41,  "score": 0.55, "list_len": 1487},
  "bm25":     {"present": true,  "rank": 118, "score": 31.2, "list_len": 640},
  "rrf":      {"present": true,  "rank": 63,  "score": 0.041, "list_len": 800},
  "rerank":   {"in_pool": false, "rerank_score": null, "rerank_rank": null},
  "final":    {"final_score": null, "final_rank": null, "in_top5": false, "in_top15": false},
  "identity_warning": null,
  "loss_classification": "retrieved_dropped_before_rerank_pool"
}
```

**Stage capture rules** — the tool reproduces `hybrid.run()` lines 52–100
(see §7) and, for each target (matched by `movie_key`), records:

- `semantic` — position/score in `sem` (post-`deduplicate_movies`,
  `prefer_score="semantic_score"`); `rank` is 0-indexed; `present=false`
  with `rank=null, score=null` if absent; `list_len` = len(`sem`).
- `bm25` — same, for `bm` (post-dedup, `prefer_score="bm25_score"`).
- `rrf` — same, for `fused` (post-`rrf_fusion(top_k=RERANK_POOL)`,
  post-dedup, sorted by the hybrid `_score(x,"final_score","rrf_score")`
  key); `score` is `rrf_score`.
- `rerank` — `in_pool` = target is among the `RERANK_TOP_K = 50` the
  cross-encoder scored; `rerank_score` = raw cross-encoder score;
  `rerank_rank` = 0-indexed rank by `rerank_score` among the scored pool.
  All three are `null` when `in_pool=false`.
- `final` — `final_score` = the blended score; `final_rank` = 0-indexed
  rank by `final_score` among the scored pool; `in_top5` =
  `final_rank < 5`; `in_top15` = `final_rank < 15`. Score/rank `null`
  when `in_pool=false`.
- `identity_warning` — `null`, or a short string when the `movie_key`
  match and the semantic-stage `tmdb_id` match disagree (§0.3).
- `schema_version` / `run_id` — constant on every record (the module
  constant `SCHEMA_VERSION = "hy-trace-01.v1"`); they make `trace.jsonl`
  self-describing without `diagnosis.json`.

**`loss_classification`** — exactly one of, computed deterministically:

| value | rule | mechanism |
|---|---|---|
| `unretrieved` | not in `semantic` **and** not in `bm25` | recall/depth |
| `retrieved_dropped_at_fusion` | in semantic/BM25 but not in `rrf` (lost at the `RERANK_POOL=800` cap) | recall/depth (fusion) |
| `retrieved_dropped_before_rerank_pool` | in `rrf` but `rerank.in_pool=false` (RRF rank ≥ 50) | recall/depth (pool cutoff) |
| `rerank_recovered_final_demoted` | `in_pool`, `rerank_rank < 5`, `final_rank ≥ 5` | final-score blend |
| `rerank_demoted` | `in_pool`, `rerank_rank ≥ 5` | reranker |
| `hybrid_top5_hit` | `in_pool`, `final_rank < 5` | resolved / instability |
| `other` | defensive — none of the above | inconclusive |

### 6.2 `analysis/hybrid_live_trace/diagnosis.json`

```json
{
  "schema_version": "hy-trace-01.v1",
  "run_id": "2026-05-19-1846-nogit",
  "trace_meta": {
    "traced_at": "2026-05-21T20:00:00Z",
    "pipeline_traced": "src/pipelines/hybrid.py run() lines 52-100",
    "repeats": 3,
    "embedding_model": "BAAI/bge-m3",
    "reranker_model": "BAAI/bge-reranker-v2-m3",
    "llm_model": "llama3.2",
    "config": {
      "CANDIDATE_POOL": 1500, "RERANK_POOL": 800, "RERANK_TOP_K": 50,
      "FINAL_TOP_K": 5, "RRF_K": 15,
      "SEMANTIC_WEIGHT": 1.0, "BM25_WEIGHT": 1.0,
      "RERANK_VOTE_COUNT_WEIGHT": 0.08, "RERANK_UPSTREAM_WEIGHT": 0.20,
      "RERANK_SOURCE_AGREEMENT_BONUS": 0.10,
      "HYBRID_USE_LLM_EXPANSION": true, "LLM_RETRIEVAL_ENABLED": true
    },
    "qids_traced": ["q03","q04","q05","q06","q07","q08","q10","q18"],
    "targets_total": 8
  },
  "per_target": [
    {
      "qid": "q03", "tmdb_id": 10681, "title": "WALL·E",
      "classifications": ["rerank_recovered_final_demoted",
                          "rerank_recovered_final_demoted",
                          "rerank_recovered_final_demoted"],
      "stable": true,
      "classification": "rerank_recovered_final_demoted"
    }
  ],
  "loss_classification_counts": {
    "unretrieved": 0, "retrieved_dropped_at_fusion": 0,
    "retrieved_dropped_before_rerank_pool": 0,
    "rerank_recovered_final_demoted": 0, "rerank_demoted": 0,
    "hybrid_top5_hit": 0, "other": 0, "unstable": 0
  },
  "mechanism_summary": {
    "recall_depth": 0, "final_score_blend": 0,
    "reranker": 0, "resolved_or_unstable": 0
  },
  "dominant_mechanism": "..."
}
```

- `schema_version` — the literal `"hy-trace-01.v1"` (module constant
  `SCHEMA_VERSION`). `trace_meta` additionally records `traced_at` (UTC,
  second precision), `repeats`, the three model names read from
  `src.config` (`EMBEDDING_MODEL`, `RERANKER_MODEL`, `LLM_MODEL`), and the
  numeric `config` knobs (top_k / pool / cutoff / weight values).
- `per_target` — one entry per (qid, tmdb_id), sorted by `(qid,
  tmdb_id)`; `classifications` lists the per-repeat result;
  `stable = (all repeats identical)`; `classification` = the agreed value
  when `stable`, else the literal string `"unstable"`.
- `loss_classification_counts` — counts over the **per-target** results
  (one vote per target, using the stable value or `"unstable"`); sums to
  `targets_total`.
- `mechanism_summary` — `recall_depth` = `unretrieved` +
  `retrieved_dropped_at_fusion` + `retrieved_dropped_before_rerank_pool`;
  `final_score_blend` = `rerank_recovered_final_demoted`; `reranker` =
  `rerank_demoted`; `resolved_or_unstable` = `hybrid_top5_hit` + `other` +
  `unstable`. Sums to `targets_total`.
- `dominant_mechanism` ∈ `{"recall_depth", "final_score_blend",
  "reranker", "mixed", "inconclusive"}`, computed by the §11 rule. It is a
  best-effort label; the human decides at Gate E regardless.

---

## 7. Why an eval-only script suffices — no `src/` instrumentation

The hard constraint (§0.2.8) requires the first ticket to be trace-only
"unless the plan proves a tiny instrumentation change is required." It is
**not** required. Proof:

1. **Every hybrid stage is an importable, free-standing function.**
   `hybrid.run()` (`src/pipelines/hybrid.py`) is pure glue: it calls
   `normalize_query`, `expand_retrieval_query`, `expand_query`,
   `parse_filters`, `semantic_search`, `bm25_search`, `deduplicate_movies`,
   `rrf_fusion`, and `rerank` — all module-level functions importable
   without side effects. An eval script can call the **identical
   callables** the pipeline uses.

2. **The intermediate lists are recoverable without instrumentation.**
   `hybrid.run()` returns only the final top-k, but the trace obtains each
   intermediate list by holding the return value of each stage call it
   makes itself. The one subtlety — the **rerank pool** and the
   **per-pool `rerank_score` / `final_score`** — is solved without any
   `src/` change: calling the real `rerank(query, fused,
   top_k=RERANK_TOP_K, rerank_pool=RERANK_TOP_K)` returns the **entire
   50-member scored pool** sorted by `final_score`. `rerank()`'s scoring,
   blending, and sorting are independent of `top_k`; only the final
   `pool[:top_k]` slice differs. So `rerank(..., top_k=50)[:5]` is
   provably identical to `rerank(..., top_k=5)` — the trace gets every
   pool member's `rerank_score` and `final_score` for free.

3. **Faithfulness is enforced by a test, not by hope.** The only residual
   risk is mis-ordering the ~15-line composition. `test_composition_
   matches_hybrid_run` (§12) monkeypatches the stage functions on **both**
   `src.pipelines.hybrid` and `hybrid_live_trace` with the same
   deterministic fakes, then asserts the trace's reconstructed final order
   equals `hybrid.run()`'s. Composition drift becomes a **test failure**,
   not a silent bug. The trace also imports `hybrid._score` (the one
   private symbol) so the fused-list sort key is byte-identical to the
   pipeline's.

4. **Instrumentation was considered and rejected.** A `trace=` parameter
   on `hybrid.run()` would be behavior-neutral but is still a `src/*`
   edit, the most cautious-handled area in this project (`CLAUDE.md`,
   `AGENTS.md`). Point 3 already gives provable fidelity without it. If —
   and only if — Gate D review finds the composition cannot be faithfully
   reproduced, the fallback is a **separate** follow-up ticket adding a
   guarded `trace=` parameter; that is out of scope here.

**Conclusion:** HY-TRACE-01 is a pure `eval/` tool that imports `src`
retrieval functions as libraries. No `src/` file is created or modified.

---

## 8. Validation commands

### 8.1 Agent-runnable (Codex runs; Claude re-runs at Gate D) — hermetic, no models

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hybrid_live_trace --run 2026-05-19-1846-nogit --dry-run
```

Expected:

1. `compileall` reports `Listing ... OK`.
2. All tests pass; the count is `previous + N` (baseline is **103** from
   HX-01 §7.1; HY-TRACE-01 adds at least 11 → expect **≥ 114**). Codex
   reports the exact before/after counts.
3. `--dry-run` exits 0, **imports no model** (`src.models` is never
   imported — asserted by `test_dry_run_no_model_import`), **writes
   nothing**, and prints the 8 traced qids with each resolved gold
   grade-3 target (`tmdb_id`, `title`, `movie_key`).

### 8.2 Human-run (after Gate D — loads models, calls Ollama)

```
python -m eval.scripts.hybrid_live_trace --run 2026-05-19-1846-nogit --repeat 3
python -c "import json,pathlib; d=json.loads(pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/hybrid_live_trace/diagnosis.json').read_text(encoding='utf-8')); pt=d['per_target']; assert len(pt)>=8, 'expect >=8 targets'; lc=d['loss_classification_counts']; ms=d['mechanism_summary']; assert sum(lc.values())==d['trace_meta']['targets_total']==sum(ms.values()), 'counts must sum to targets_total'; print('trace ok'); print('classifications', lc); print('mechanism', ms, '-> dominant:', d['dominant_mechanism'])"
```

Expected:

1. The trace exits 0 and writes `analysis/hybrid_live_trace/trace.jsonl`
   (≥ 8 qids × `repeat` records) and `diagnosis.json`.
2. The one-liner confirms `per_target` covers all 8 targets and that
   `loss_classification_counts` and `mechanism_summary` each sum to
   `targets_total`, then prints the counts and `dominant_mechanism`. The
   **specific** counts are the diagnostic result — they are not
   pre-asserted; Claude summarizes them at Gate E and the human decides.

---

## 9. How to interpret results

Read `diagnosis.json` after the human-run trace. For each target,
`loss_classification` maps to a mechanism (§6.2 `mechanism_summary`):

- **`unretrieved`** → the target is in neither the 1,500-deep semantic nor
  the BM25 list. This is a **true recall failure** — confirms **H1**
  (likely the missing HyDE pass) or **H2** (LLM query drift). Compare the
  `resolved.retrieval_query` across qids: drift visible vs. the plain
  query points at expansion; consistent-but-still-missing points at HyDE.
- **`retrieved_dropped_at_fusion`** → retrieved, but RRF's
  `top_k = 800` cap dropped it. A **fusion/depth** loss — H3. Inspect the
  target's `semantic.rank` / `bm25.rank`: deep ranks (e.g. > 800) mean a
  retrieval-depth problem; good ranks mean RRF scoring demoted it.
- **`retrieved_dropped_before_rerank_pool`** → survived RRF but ranked
  ≥ 50, so the cross-encoder never scored it. A **pool-cutoff/depth**
  loss — H3.
- **`rerank_recovered_final_demoted`** → the cross-encoder ranked it
  top-5 but the blended `final_score` re-demoted it. A **final-score
  blend** loss — confirms **H4**. The fix space is the
  `RERANK_VOTE_COUNT_WEIGHT` / `RERANK_UPSTREAM_WEIGHT` /
  `RERANK_SOURCE_AGREEMENT_BONUS` blend, not retrieval.
- **`rerank_demoted`** → the cross-encoder itself ranked it ≥ 5. This
  would **revise HX-01** (which found the reranker innocent); treat as a
  reranker-quality finding needing its own analysis.
- **`hybrid_top5_hit`** → the live pipeline *does* place the target
  top-5. The HX-01 miss was a labeled-subset artifact or LLM-expansion
  variance — check `stable`. Not a bug to fix.
- **`unstable`** (`stable: false`) → the classification flips across
  repeats — confirms **H5**. The "gap" for that target is variance, not
  a fixed defect; a fix would be unverifiable until the instability is
  understood.

**Recall/depth vs. final-score blend is the decision axis.** The first
three classifications are upstream-of-rerank (retrieval/fusion); the
fourth is downstream (blend). Which dominates picks the Gate E branch.

---

## 10. Gate D review checklist (Claude, after Codex finishes)

Claude reviews the 3-file diff and the §8.1 hermetic log. Report findings
as **matches spec / deviations / blockers**, in that order.

- [ ] **Scope:** the diff touches **exactly** the 3 files in §4
      (`hybrid_live_trace.py`, `test_hybrid_live_trace.py`, one line of
      `eval/README.md`) — nothing else.
- [ ] **No `src/` edit:** no file under `src/`, no `app.py`, no
      `src/config.py` is created or modified.
- [ ] **`src` used as a library only:** the tool *imports*
      `src.retrieval.*`, `src.utils.dedup`, `src.config`,
      `src.pipelines.hybrid` — and **re-implements no** retrieval, BM25,
      RRF, fusion, reranker, or embedding logic. The only private symbol
      imported is `hybrid._score`.
- [ ] **No new LLM call inside ranking code** and **no config mutation**
      — `src.config` is read/snapshotted, never assigned to.
- [ ] **Faithfulness:** `test_composition_matches_hybrid_run` exists,
      passes, and genuinely patches the stage functions on both
      `src.pipelines.hybrid` and the trace module. Claude **diffs the
      tool's hybrid-composition block line-by-line against
      `src/pipelines/hybrid.py` lines 52–100**.
- [ ] **Rerank-pool capture:** the tool calls `rerank(...,
      top_k=RERANK_TOP_K, rerank_pool=RERANK_TOP_K)` to obtain the full
      scored pool (§7 point 2) — it does not re-score or re-blend itself.
- [ ] **Output scope:** the tool's only writes are
      `analysis/hybrid_live_trace/trace.jsonl` and `diagnosis.json`;
      writes are atomic; `analysis/hybrid_live_trace/` is `mkdir(parents,
      exist_ok)`.
- [ ] **Forbidden files:** nothing in §5 is created or modified;
      `--dry-run` writes nothing.
- [ ] **Queries:** the traced qids are read from
      `hybrid_gap/diagnosis.json` and asserted to equal
      `HYBRID_ATTRIBUTABLE_QIDS`; gold grade-3 targets are read from
      `gold_labels.jsonl`; `q12` / `q13` are not traced.
- [ ] **Hermetic validation:** §8.1 ran — `compileall` OK, unit count
      ≥ 114, `--dry-run` exits 0, imports no model, writes nothing.
- [ ] **Schema:** `trace.jsonl` / `diagnosis.json` match §6 exactly
      (keys, sort order, `loss_classification` enum, `mechanism_summary`
      arithmetic).

If all pass: Gate D is green; the human runs §8.2. Any blocker stops the
plan for a fix before the human-run trace.

---

## 11. Gate E decision tree (human, after the human-run trace)

Claude summarizes `diagnosis.json`; the human picks **exactly one**
branch. Let `M = mechanism_summary` over the 8 targets.

1. **Recall/depth dominates** — `M.recall_depth ≥ 5` and
   `M.final_score_blend ≤ 1` and `resolved_or_unstable ≤ 2`:
   → **Draft a separate, separately-gated retrieval-depth / fusion plan.**
   Scope it by the sub-classifications (`unretrieved` vs.
   `dropped_at_fusion` vs. `dropped_before_rerank_pool`) and by the
   resolved-query evidence (H1 HyDE gap vs. H2 expansion drift). Not
   dispatched here.

2. **Final-score re-demotion dominates** — `M.final_score_blend ≥ 5` and
   `M.recall_depth ≤ 1` and `resolved_or_unstable ≤ 2`:
   → **Draft a separate, separately-gated final-score blend-fix plan**,
   scoped to the `RERANK_VOTE_COUNT_WEIGHT` / `RERANK_UPSTREAM_WEIGHT` /
   `RERANK_SOURCE_AGREEMENT_BONUS` blend and gated on a paired-bootstrap
   eval showing no regression. Not dispatched here.

3. **Mixed** — `M.recall_depth ≥ 2` **and** `M.final_score_blend ≥ 2`:
   → **Draft two separate scoped plans** (one per mechanism), each
   separately gated. Sequence them by target count, larger first.

4. **Inconclusive** — `unstable ≥ 3`, **or** no branch above is satisfied,
   **or** `rerank_demoted ≥ 2` (which would contradict HX-01):
   → **Stop. Request additional trace, not a fix.** Likely follow-ups: a
   deeper instability study (H5), or — only if §7 point 4's residual risk
   materialized — a guarded `src/` `trace=` instrumentation ticket. **No
   fix plan is drafted on inconclusive evidence.**

This plan **pre-commits to no branch.** Its sole product is the evidence
in `diagnosis.json`.

---

## 12. Ticket HY-TRACE-01 — Codex-ready handoff

### 1. Goal

Build `eval/scripts/hybrid_live_trace.py`: a read-only diagnostic tool
that re-runs the live hybrid pipeline on the 8 `hybrid_attributable`
queries, records each gold grade-3 target's true rank/score at every
stage, classifies the loss mechanism per target, and writes `trace.jsonl`
+ `diagnosis.json` under `analysis/hybrid_live_trace/`. Trace-only: it
imports `src` retrieval functions as libraries and changes no behavior.

### 2. Files to change

- Create: `eval/scripts/hybrid_live_trace.py`
- Create: `eval/tests/test_hybrid_live_trace.py`
- Modify (one line): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `eval/scripts/error_report.py`.
- `src/config.py`, `src/retrieval/query_processor.py`,
  `src/retrieval/filters.py`, `src/retrieval/semantic.py`,
  `src/retrieval/bm25.py`, `src/retrieval/fusion.py`,
  `src/retrieval/reranker.py`, `src/utils/dedup.py`,
  `src/pipelines/hybrid.py`.
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`,
  `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_gap/diagnosis.json`,
  `eval/queries/v1.jsonl`, `data/movies_clean.csv`.

### 4. Acceptance criteria

1. **CLI:** `python -m eval.scripts.hybrid_live_trace [--run RUN_ID]
   [--repeat N] [--queries PATH] [--dry-run]`. `--run` defaults to
   `_run_io.latest_run()`; `--repeat` defaults to `3` (must be ≥ 1);
   `--queries` defaults to `eval/queries/v1.jsonl`.

2. **Preconditions — raise `HybridLiveTraceError` (a `ValueError`
   subclass), exit non-zero, write nothing** if any of these is missing:
   `<run>/gold_labels.jsonl`, `<run>/analysis/hybrid_gap/diagnosis.json`,
   the queries file, `data/movies_clean.csv`. `main()` catches it, prints
   to `stderr`, returns non-zero.

3. **Traced qids:** read `partition.hybrid_attributable` from
   `hybrid_gap/diagnosis.json`; assert it equals the module constant
   `HYBRID_ATTRIBUTABLE_QIDS = ("q03","q04","q05","q06","q07","q08",
   "q10","q18")` — mismatch raises `HybridLiveTraceError`.

4. **Targets:** load `gold_labels.jsonl` via
   `error_report._load_gold_labels`. For each traced qid,
   `targets(qid)` = every `tmdb_id` with merged `grade == 3`. Each target
   is bridged to a `movie_key` from `data/movies_clean.csv` (the `id`
   column is the TMDB id): build a dict `{"title", "year",
   "release_date"}` from that CSV row and call
   `src.utils.dedup.get_movie_key` (do **not** pass `movie_id`, so the key
   uses the title+year branch the pipeline uses). A grade-3 tmdb_id with
   no CSV row → `HybridLiveTraceError`.

5. **`--dry-run`:** resolve preconditions, traced qids, and targets;
   print each qid with its targets (`tmdb_id`, `title`, `movie_key`);
   exit 0; **write nothing**; and **import no model** — `src.models`,
   `src.retrieval.semantic`, `src.retrieval.bm25`,
   `src.retrieval.reranker`, `src.llm.*` must not be imported on the
   `--dry-run` path (defer those imports into the live-trace path only).

6. **Live trace (per traced qid, per repeat `0..N-1`):** reproduce
   `src/pipelines/hybrid.py` `run()` lines 52–100 exactly, importing the
   real functions and `hybrid._score`:
   - `processed = normalize_query(query)`;
     `deterministic_query = expand_retrieval_query(processed)`;
     `retrieval_query = expand_retrieval_query(expand_query(processed) or
     processed)` when `HYBRID_USE_LLM_EXPANSION and LLM_RETRIEVAL_ENABLED`
     else `deterministic_query`; `rerank_query = deterministic_query`;
     `filters = parse_filters(query) or None`.
   - `sem = deduplicate_movies(semantic_search(retrieval_query,
     top_k=CANDIDATE_POOL, filters=filters), prefer_score="semantic_score")`.
   - `bm = deduplicate_movies(bm25_search(retrieval_query,
     top_k=CANDIDATE_POOL, filters=filters), prefer_score="bm25_score")`.
   - `fused = deduplicate_movies(rrf_fusion(sem, bm, top_k=RERANK_POOL),
     prefer_score="rrf_score")`; then
     `fused.sort(key=lambda x: _score(x,"final_score","rrf_score"),
     reverse=True)`.
   - `scored_pool = rerank(rerank_query, fused, top_k=RERANK_TOP_K,
     rerank_pool=RERANK_TOP_K)` — the full scored pool sorted by
     `final_score` (§7 point 2).
   - Snapshot every needed rank/score **before** the next stage so
     `rerank`'s in-place mutation cannot corrupt earlier captures.

7. **Per-target capture & classification:** match each target by
   `movie_key` in `sem`, `bm`, `fused`, and `scored_pool`; cross-check the
   semantic stage by `tmdb_id` against the result `id` and set
   `identity_warning` on disagreement. Emit one `trace.jsonl` record per
   `(qid, tmdb_id, repeat)` with the exact §6.1 schema, including
   `resolved.retrieval_query` / `rerank_query` / `filters` (the resolved
   query recorded verbatim for every repeat), the per-record
   `schema_version` / `run_id`, and the deterministic `loss_classification`
   from the §6.1 table.

8. **`diagnosis.json`:** exact §6.2 schema — top-level `schema_version`
   (the module constant `SCHEMA_VERSION = "hy-trace-01.v1"`); `trace_meta`
   with `traced_at`, `repeats`, the model names `embedding_model` /
   `reranker_model` / `llm_model` read from `src.config`
   (`EMBEDDING_MODEL` / `RERANKER_MODEL` / `LLM_MODEL`), and the numeric
   `config` knobs; `per_target` (per-repeat `classifications`, `stable`,
   agreed `classification` or `"unstable"`); `loss_classification_counts`;
   `mechanism_summary`; and `dominant_mechanism` per the §11 rule. Counts
   sum to `targets_total`.

9. **Determinism of structure, not of values.** `trace.jsonl` rows are
   sorted by `(qid, tmdb_id, repeat)`; `per_target` by `(qid, tmdb_id)`.
   Stage scores/ranks are live values and are **not** expected to be
   byte-stable across invocations — that is what `--repeat` measures.

10. **Writes nothing else.** Only `analysis/hybrid_live_trace/
    trace.jsonl` and `diagnosis.json`; directory via `mkdir(parents=True,
    exist_ok=True)`; files via `_run_io._atomic_write_text` /
    `_atomic_write_json`. No file in §5 is touched.

11. **CLI output (non-dry-run):** print `run_id=`, both output paths,
    `repeats=`, `targets_total=`, the `loss_classification_counts`, and
    `dominant_mechanism`.

12. **`test_hybrid_live_trace.py`** is hermetic (no models, no Ollama, no
    network; `tempfile.TemporaryDirectory`; monkeypatched stage functions
    and `_run_io` paths, following `eval/tests/test_error_report.py` and
    `test_hybrid_gap_trace.py`) and includes at least:
    - `test_composition_matches_hybrid_run` — monkeypatch the stage
      functions on **both** `src.pipelines.hybrid` and
      `eval.scripts.hybrid_live_trace` with identical deterministic fakes;
      assert the trace's reconstructed final top-15 equals
      `hybrid.run(query, top_k=15, with_explanation=False)`.
    - `test_target_resolution_from_gold_labels` — grade-3 tmdb_ids
      resolved and bridged to `movie_key` from a synthetic CSV.
    - `test_loss_unretrieved`, `test_loss_dropped_at_fusion`,
      `test_loss_dropped_before_rerank_pool`,
      `test_loss_rerank_recovered_final_demoted`,
      `test_loss_rerank_demoted`, `test_loss_hybrid_top5_hit` — one per
      `loss_classification` value, driven by fake stage outputs.
    - `test_repeat_stability_aggregation` — two repeats with differing
      classifications → `stable=false`, `classification="unstable"`,
      `unstable` counted in `mechanism_summary.resolved_or_unstable`.
    - `test_dry_run_no_model_import` — after `--dry-run`, assert
      `src.models` is absent from `sys.modules`; nothing written.
    - `test_missing_diagnosis_exits_nonzero` — precondition failure →
      non-zero exit, nothing written.
    - `test_mechanism_summary_sums_to_targets_total`.

13. **No `src/` edit; `src` imported as a library only;** no retrieval /
    BM25 / RRF / reranker / embedding logic re-implemented; `src.config`
    never mutated; no new LLM call added to any ranking path.

### 5. Validation commands

Run §8.1 (agent-runnable, hermetic). Report per `AGENTS.md`: files
changed, commands run, before/after test counts, any failures verbatim,
the `--dry-run` stdout, and any assumptions. **Do not run §8.2** — the
live model-loading trace is human-run after Gate D.

### 6. Dependencies

- HX-01 — `analysis/hybrid_gap/diagnosis.json` must exist (satisfied;
  HX-01 complete, accepted at Gate E 2026-05-21).
- ML-01 — `gold_labels.jsonl` (satisfied).
- The working-tree `src/` pipeline is the trace subject; ChromaDB
  (`data/chroma_bgem3`), `data/movies_clean.csv`, and a reachable Ollama
  are required **only for the human-run §8.2 step**, not for Codex.

### 7. Risk level

**Low.** Three-file change; one new read-only `eval/` tool that imports
`src` functions without editing them. The real risks are (a) the tool
writing outside `analysis/hybrid_live_trace/`, (b) re-implementing or
mutating ranking logic instead of importing it, or (c) the reproduced
composition drifting from `hybrid.run()`. Acceptance criteria 6/7/10/13,
the §5 forbidden list, atomic writes, and
`test_composition_matches_hybrid_run` close all three.

### 8. Reviewer

Claude Code Pro, per the §10 Gate D checklist. Specifically verifies: the
diff touches exactly the 3 files; no `src/*` is edited; the tool
re-implements no ranking logic and imports `src` as a library only; the
hybrid composition matches `hybrid.py:52-100` line-by-line; the tool's
only writes are the two `analysis/hybrid_live_trace/` files; the hermetic
validation passed. Claude then signs off Gate D, the human runs §8.2, and
Claude summarizes `diagnosis.json` for the Gate E decision.

### 9. Codex prompt (planning artifact — NOT dispatched by this plan)

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket HY-TRACE-01 exactly as specified in
docs/superpowers/plans/2026-05-21-hy-trace-01-live-hybrid-pipeline-trace.md
section 12 ("Ticket HY-TRACE-01 -- Codex-ready handoff"), with the output
schema in section 6.

You may edit ONLY:
  - eval/scripts/hybrid_live_trace.py      (create)
  - eval/tests/test_hybrid_live_trace.py   (create)
  - eval/README.md                         (add ONE line: hybrid_live_trace.py
                                            in the scripts/ block of the
                                            Layout fence)

Do not edit any other file. No src/* edits. No src/config.py edits. No
app.py / recommender-runtime edits. Do not run pip installs. Do not run
any git command.

HARD CONSTRAINTS:
  - This tool is TRACE-ONLY. It MUST NOT change, re-implement, or tune any
    ranking / retrieval / BM25 / RRF / fusion / reranker / embedding /
    query-expansion logic, and MUST NOT mutate src.config.
  - It IMPORTS the real functions from src.retrieval.*, src.utils.dedup,
    src.config, and src.pipelines.hybrid (the private _score helper) AS
    LIBRARIES. It MUST NOT re-implement retrieval/fusion/rerank logic.
  - It reproduces src/pipelines/hybrid.py run() lines 52-100 to capture
    each stage's ranked list (acceptance criterion 6). Faithfulness is
    enforced by test_composition_matches_hybrid_run.
  - The rerank pool and per-pool scores are obtained by calling the real
    rerank(..., top_k=RERANK_TOP_K, rerank_pool=RERANK_TOP_K) -- never by
    re-scoring or re-blending in the tool.
  - The tool's ONLY writes are eval/runs/<run_id>/analysis/
    hybrid_live_trace/trace.jsonl and diagnosis.json. It MUST NOT modify
    candidates.jsonl, gold_labels.jsonl, silver_labels.jsonl,
    metrics.json, run_manifest.json, anything under analysis/hybrid_gap/,
    analysis/error_report/, analysis/regrade/, or anything under src/.
  - error_report.py, _run_io.py, hybrid_gap_trace.py and all src modules
    are IMPORTED and MUST NOT be edited. Load gold labels via
    error_report._load_gold_labels.
  - The --dry-run path MUST NOT import any model module (src.models,
    src.retrieval.semantic/bm25/reranker, src.llm.*): defer those imports
    into the live-trace code path.
  - If any required input file is missing, raise HybridLiveTraceError,
    exit non-zero, and write nothing.

Acceptance criteria 1-13 in section 12 are all required. Run ONLY the
hermetic validation in section 8.1 (compileall, unittest discover,
--dry-run). DO NOT run the model-loading trace in section 8.2 -- that step
is human-run. Report back per AGENTS.md validation rules (files changed,
commands run, before/after test counts, failures verbatim, the --dry-run
stdout, and any assumptions).
```

---

## 13. Stop for Gate A approval

Per `CLAUDE.md` autonomy boundaries, Claude does **not** dispatch Codex
automatically. **This plan stops here.** Nothing is implemented and no
Codex call is made until the human gives **Gate A** approval for the
HY-TRACE-01 handoff in §12.

Suggested order once Gate A is given:

1. **Gate A** — human approves the §12 handoff → Codex implements
   `hybrid_live_trace.py` + tests and runs the §8.1 hermetic validation.
2. **Gate D** — Claude reviews the 3-file diff and hermetic log against
   the §10 checklist.
3. **Human-run trace** — the human runs §8.2
   (`hybrid_live_trace.py --repeat 3`), producing `trace.jsonl` +
   `diagnosis.json`.
4. **Gate E** — Claude summarizes `diagnosis.json` (§9); the human picks a
   §11 branch. If a fix branch is chosen, the fix is a **new,
   separately-gated plan** — not implemented or dispatched by HY-TRACE-01.

**No ranking, retrieval, fusion, reranker, or config change is
implemented or dispatched by this plan.**

---

## 14. Self-review against this plan's own constraints

1. **Trace-only; no ranking/retrieval/config change** — §0.2 constraints
   1–4, §0.4 non-goals, §12 criteria 6/10/13, and the Codex prompt all
   forbid any behavior change, any `src/*` edit, and any config tuning. ✓
2. **First ticket is trace-only; instrumentation proven unnecessary** —
   §7 proves an eval-only script accesses every stage (importable stage
   functions + the `rerank(top_k=50)` trick + a faithfulness test);
   instrumentation is considered and rejected. ✓
3. **Prefers a trace script under `eval/scripts`** — the sole deliverable
   is `eval/scripts/hybrid_live_trace.py`. ✓
4. **Exact queries** — §3 traces exactly the 8 `hybrid_attributable`
   qids, read from `hybrid_gap/diagnosis.json`; q12/q13 excluded. ✓
5. **Distinguishes the five fates** — §6.1's `loss_classification` enum
   maps `unretrieved` / `retrieved_dropped_at_fusion` /
   `retrieved_dropped_before_rerank_pool` /
   `rerank_recovered_final_demoted`, plus `rerank_demoted` and
   `hybrid_top5_hit`; structural `no_perfect_candidate` is excluded by
   construction (only grade-3-bearing qids are traced). ✓
6. **No re-litigating q12/q13; q13 not a bug** — §0.2.6, §3; q13 is
   `no_perfect_candidate` and is not traced. ✓
7. **All 12 required sections present** — current evidence §1; hypotheses
   §2; queries §3; allowed files §4; forbidden files §5; output schema
   §6; validation §8; interpretation §9; Gate D checklist §10; Gate E
   decision tree §11; Codex-ready handoff §12; stop for Gate A §13. ✓
8. **Produces evidence, not a fix** — §11 drafts *separate* plans; §13
   pre-commits to none; the §12.9 prompt is plan text, not an
   invocation. ✓
9. **Honest about limits** — §0.3 discloses non-determinism (handled by
   `--repeat`), the human-run model-loading step, and `movie_key`
   identity. ✓
10. **No git commands** — none in any validation block (no-git mode). ✓

---

## 15. Gate D record (2026-05-21)

HY-TRACE-01 implemented by Codex CLI (`codex exec`, workspace-write
sandbox, exit 0); reviewed by Claude Code Pro against the §10 checklist.

### 15.1 Result: **matches spec — no blockers.**

| Check | Outcome |
|---|---|
| Scope — exactly the 3 approved files | ✓ `hybrid_live_trace.py`, `test_hybrid_live_trace.py`, one line of `eval/README.md` |
| No `src/*` edit | ✓ verified — no `src/` file modified |
| `src` imported as a library only; no ranking logic re-implemented | ✓ stage functions deferred via `_ensure_live_imports`; only private symbol is `hybrid._score` |
| No config mutation | ✓ `src.config` read via `getattr`, never assigned |
| Faithfulness vs `hybrid.py:52-100` | ✓ `_run_hybrid_stages` diffed line-by-line; `test_composition_matches_hybrid_run` imports a fresh stubbed `hybrid` and asserts equality |
| Rerank-pool capture via real `rerank(top_k=RERANK_TOP_K)` | ✓ no re-scoring/re-blending in the tool |
| Output scope + atomic writes | ✓ only `analysis/hybrid_live_trace/{trace.jsonl,diagnosis.json}` |
| Forbidden files untouched; `--dry-run` writes nothing | ✓ verified — output dir absent after dry-run |
| Hermetic validation | ✓ `compileall` OK; **115 tests pass** (baseline 103, +12); `--dry-run` exits 0, imports no model, prints all 8 targets |
| Schema sufficient for Gate E | ✓ per-stage rank/score/fate + per-target stability + `mechanism_summary` + `dominant_mechanism` |

### 15.2 Minor deviations (disclosed, accepted — not blockers)

1. **Classification precedence.** The tool checks `hybrid_top5_hit`
   (`final_rank < 5`) before `rerank_demoted`. For the edge case
   `final_rank < 5 AND rerank_rank >= 5`, the §6.1 table read top-to-bottom
   would say `rerank_demoted`; the tool says `hybrid_top5_hit`. The tool
   is **correct** — a target in hybrid's top-5 is a hit, not a miss — and
   resolves an ambiguity the §6.1 table left implicit.
2. **Stage order.** `_run_hybrid_stages` runs `semantic → dedup → bm25 →
   dedup`; `hybrid.run()` runs `semantic → bm25 → dedup → dedup`. The
   calls are independent and pure; `test_composition_matches_hybrid_run`
   proves identical output.

### 15.3 Observations (no action required)

- `test_composition_matches_hybrid_run` leaves a stub-imported
  `src.pipelines.hybrid` in `sys.modules`; the full 115-test suite passes
  regardless of order. Cosmetic.
- The tool omits `hybrid.run()`'s empty-query guards — irrelevant for the
  8 non-empty traced queries.

### 15.4 Next step

Gate D is green. The **human-run live trace** (§8.2) is now unblocked:
`python -m eval.scripts.hybrid_live_trace --run 2026-05-19-1846-nogit
--repeat 3` (loads BGE-M3, the cross-encoder, ChromaDB; calls Ollama).
After it writes `trace.jsonl` + `diagnosis.json`, Claude summarizes the
result (§9) and the human takes the Gate E decision (§11). **No fix is
dispatched by this plan.**
