---
title: HY-STAB-01 — Hybrid expansion instability trace
date: 2026-05-21
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one tooling ticket, human-approved before dispatch)
human: approves dispatch (Gate A); runs the live trace; accepts the trace and makes the fix-direction decision (Gate E)
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 05-metrics-qc-and-labels.md
parent_run: eval/runs/2026-05-19-1846-nogit
parent_plan: docs/superpowers/plans/2026-05-21-hy-trace-01-live-hybrid-pipeline-trace.md
parent_diagnosis: eval/runs/2026-05-19-1846-nogit/analysis/hybrid_live_trace/diagnosis.json
git_mode: no_git
status: COMPLETE — Gate A approved; implemented by Codex; Gate D PASSED (2026-05-22); live trace run 2026-05-22; Gate E (2026-05-22) dominant_finding=mixed. Follow-on plan HY-FIX-01. See §16.
---

# HY-STAB-01 — Hybrid Expansion Instability Trace

> **For agentic workers:** This plan is executed by **Codex CLI** for one
> tooling ticket (HY-STAB-01), with explicit human approval before the
> Codex prompt is sent. Claude Code Pro reviews the diff and the hermetic
> validation log. **This plan is trace-only / diagnostics-only. No
> `src/*` edits. No `app.py` / recommender-runtime edits. No ranking,
> retrieval, BM25, RRF, fusion, reranker, embedding, or query-expansion
> behavior change. No config tuning. No `src.config` mutation.** It adds
> one read-only diagnostic tool under `eval/` that imports the live `src`
> retrieval functions — and the proven HY-TRACE-01 helpers — as libraries.
> The ticket uses the 9-field Codex handoff format from `CLAUDE.md`.

**This plan is the gated follow-on to HY-TRACE-01.** HY-TRACE-01's Gate E
(2026-05-21) result was `dominant_mechanism = inconclusive`: 6 of 8
hybrid-attributable targets were **unstable** — their loss classification
flipped across the 3 repeats — so HY-TRACE-01 §11 branch 4 was taken
(**stop, request additional trace, do not draft a fix**). HY-STAB-01 is
that additional trace.

**Goal (one sentence):** Build one Codex tool,
`hybrid_expansion_stability.py`, that traces each of the 8
hybrid-attributable gold grade-3 targets through the hybrid pipeline under
**three controlled query arms** — `live` (fresh non-deterministic
`expand_query` every repeat), `pinned` (one `expand_query` output reused
across repeats), and `no_llm` (deterministic query, no LLM call) — and a
**q03-specific final-score blend decomposition**, so the human can
**separate instability caused by LLM query expansion from fixed ranking
defects** — without editing `src/*`, mutating config, or changing any
behavior.

**Architecture:** A single read-only diagnostic tool under
`eval/scripts/`. It **reuses HY-TRACE-01** (`eval/scripts/hybrid_live_trace.py`)
as a library — its input loading (`_prepare_inputs`), per-stage capture
(`_stage_presence`, `_rerank_capture`, `_identity_warning`), classifier
(`classify_loss`), and aggregation (`_per_target`, `_loss_counts`,
`_mechanism_summary`, `_dominant_mechanism`) — and adds only what is new:
a **retrieval-query-parametrized stage runner**, the **3-arm loop**, the
**pinned-expansion cache**, the **cross-arm instability attribution**, and
the **q03 blend decomposition**. It writes outputs only into
`eval/runs/<run_id>/analysis/hybrid_expansion_stability/`.

**Tech stack:** Python 3.11+, stdlib only (`json`, `pathlib`, `argparse`,
`sys`, `csv`, `datetime`, `statistics`). Imports existing eval modules
(`eval.scripts._run_io`, `eval.scripts.error_report`,
`eval.scripts.hybrid_live_trace`) and live `src` modules (`src.config`,
`src.retrieval.*`, `src.pipelines.hybrid`, `src.utils.dedup`,
`src.llm.langchain_ollama`) **as libraries** — none are modified. No new
dependency.

---

## 0. Scope, gates, and hard constraints

### 0.1 What HY-STAB-01 is

One **trace-only** Codex tooling ticket. It produces evidence; it fixes
nothing. Per `CLAUDE.md`, Claude plans and reviews; Codex implements; the
human approves each gate and **runs the live trace**.

It answers exactly one question HY-TRACE-01 left open:

> Of the hybrid strict-gap, how much is **variance** from the
> non-deterministic `expand_query` call, and how much is a **fixed
> defect** that survives when the retrieval query is held constant?

### 0.2 Hard constraints (binding on the ticket and every step)

1. **Trace-only. No behavior-changing fix.** No edit to retrieval, BM25,
   RRF, fusion, reranker, embedding, query-expansion, or any `src/*` /
   `app.py` / recommender-runtime code. If the trace warrants a fix, that
   is a **separate, separately-gated plan** — never this one.
2. **No config tuning and no `src.config` mutation.** `src/config.py` is
   read and snapshotted, never edited, and never assigned to at runtime.
   In particular, the `no_llm` arm is produced by **feeding the
   deterministic query into the stage functions** — *not* by setting
   `HYBRID_USE_LLM_EXPANSION = False` (see §7).
3. **No `src/*` edits.** All tooling lives under `eval/`. `src` modules
   and `eval/scripts/hybrid_live_trace.py` are **imported as libraries**,
   never modified.
4. **No prompt / recommendation / UX changes.**
5. **No eval-label or prior-artifact changes.** `gold_labels.jsonl`,
   `silver_labels.jsonl`, `metrics.json`, and every existing `analysis/`
   artifact — including `analysis/hybrid_live_trace/` and
   `analysis/hybrid_gap/` — are read-only inputs.
6. **Same query set as HY-TRACE-01.** Exactly the 8 `hybrid_attributable`
   qids. No re-litigating q12 / q13; the 7 `no_perfect_candidate` qids are
   not traced.
7. **No broad refactor.** One new script, one new test file, one
   one-line README edit. Nothing else.
8. **The ticket is trace-only.** §7 proves no `src/` instrumentation is
   required; therefore none is in scope.

### 0.3 Honest caveats

- **The trace re-runs the live pipeline; the `live` arm is
  non-deterministic by design.** That non-determinism is the *subject* of
  this study, not a nuisance — the `pinned` and `no_llm` arms are the
  controls.
- **`pinned` and `no_llm` are expected to be deterministic but this is
  asserted, not assumed.** Each is run `--repeat` times; if either is *not*
  byte-stable, that is itself a finding (it would mean a second
  non-deterministic element exists beyond `expand_query`).
- **The q03 blend decomposition's `quality_prior` and `upstream_prior` are
  pool-normalized** — `rerank()` divides them by the per-pool maxima
  (`src/retrieval/reranker.py` lines 111-119). They are comparable *within*
  one arm/repeat's 50-member pool, **not** across pools. The decomposition
  reports them as the reranker computed them and says so.
- **Ollama must be reachable** for the `live` and `pinned` arms (they call
  `expand_query`). The `no_llm` arm needs no Ollama. If `expand_query`
  fails, it returns the input query unchanged (`src/llm/langchain_ollama.py`
  lines 255-260) — the tool records the resolved query verbatim either way.
- **On this machine (8 GB RTX 4070 Laptop GPU)** the trace's BGE-M3 +
  cross-encoder do not fit in VRAM alongside an Ollama that is also on the
  GPU. The §8.2 human-run block pins Ollama to CPU; see §8.2.
- **Identity is keyed on `movie_key`** (normalized title + year) — the same
  identity HY-TRACE-01, `rrf_fusion`, and the reranker use. A per-stage
  `tmdb_id` cross-check is recorded as `identity_warning` on disagreement.

### 0.4 Non-goals (explicit deferrals)

- **Any ranking / RRF / BM25 / reranker / fusion / embedding /
  query-expansion change**, any `src/*` / `app.py` / config edit. A fix,
  if chosen at Gate E, is its own separately-gated plan.
- **A pure raw-query arm.** "LLM expansion disabled" is realized as the
  `no_llm` arm = the deterministic query `expand_retrieval_query(
  normalize_query(q))`, which is exactly what `hybrid.run()` uses when
  `HYBRID_USE_LLM_EXPANSION = False`. A fourth arm using the bare
  un-expanded query is out of scope.
- **Editing `hybrid_live_trace.py`, `hybrid_gap_trace.py`,
  `hybrid_stage_trace.py`, `error_report.py`.** All imported, never edited.
- **Re-running the full 20-query / 3-mode evaluation.** HY-STAB-01 traces
  exactly 8 queries through exactly one mode (hybrid), under 3 arms.
- A markdown narrative report — the decision is made from
  `stability_diagnosis.json` and `q03_blend_decomposition.json` at Gate E.
- **Tuning `expand_query`** (temperature, seeding, caching). Those are
  *candidate fixes*; HY-STAB-01 only measures whether they would help.

### 0.5 Gate map

| Gate | When | Who | What |
|---|---|---|---|
| **A — Dispatch approval** | Before the HY-STAB-01 Codex prompt is sent | Human | Approves the specific §12 handoff. Per `CLAUDE.md`, Claude does **not** auto-dispatch Codex. **This plan stops at Gate A.** |
| **D — Claude review** | After Codex finishes the tool + hermetic validation | Claude | Reviews the 3-file diff vs the §4 allowed list and the §8.1 hermetic log against the §10 checklist. Reports matches / deviations / blockers. |
| **(human-run trace)** | After Gate D | Human | Runs `hybrid_expansion_stability.py --repeat 5` (§8.2); produces the three output files. |
| **E — Human accept + fix-direction decision** | After the human-run trace | Human + Claude | Claude summarizes the diagnosis (§9). Human picks a §11 branch. This plan pre-commits to no fix. |

---

## 1. Current evidence (from HY-TRACE-01)

All figures are read from
`eval/runs/2026-05-19-1846-nogit/analysis/hybrid_live_trace/diagnosis.json`
and `trace.jsonl` (HY-TRACE-01, completed 2026-05-21, `--repeat 3`).

- **`dominant_mechanism = inconclusive`.** `loss_classification_counts`:
  `rerank_recovered_final_demoted` 1, `hybrid_top5_hit` 1, **`unstable` 6**,
  all others 0. `mechanism_summary`: `recall_depth` 0,
  `final_score_blend` 1, `reranker` 0, `resolved_or_unstable` 7.
- **6 of 8 targets are unstable** — `q04 q05 q06 q07 q08 q10` flip
  `loss_classification` across the 3 repeats.
- **Only 2 targets are stable:**
  - **q03 WALL·E** — `rerank_recovered_final_demoted` all 3 repeats: the
    cross-encoder ranks it `rerank_rank` 0-1, but `final_score` demotes it
    to `final_rank` 6-7. `rerank_score` is byte-identical across repeats
    (`0.03167380020022392`).
  - **q18 You've Got Mail** — `hybrid_top5_hit` all 3 repeats
    (`final_rank` 1/3/3). Not a hybrid miss; HX-01's "miss" was a
    labeled-subset artifact.
- **The variance is upstream.** `resolved.retrieval_query` differs every
  repeat (e.g. q08 EEAAO semantic rank 741 → 1008 → absent; q04 Teen Witch
  43 → 65 → 1). `resolved.rerank_query` is **identical** across repeats,
  and `rerank_score` is byte-identical per candidate — so the cross-encoder
  is deterministic and **the only non-deterministic element is the
  `expand_query` LLM call** (`llama3.2`, `temperature=0.2`).
- HX-01 had found the reranker innocent; HY-TRACE-01 partly revised that —
  `rerank_demoted` appeared for q07 (2/3 repeats) and q10 (1/3).

**Why HY-TRACE-01's evidence is insufficient for a decision.** A single
non-deterministic arm cannot separate *variance* from *defect*. A target
that misses in HY-TRACE-01 may miss because (a) `expand_query` happened to
produce a bad query that repeat, or (b) the pipeline mishandles it
regardless of the query. These demand opposite responses — improve
expansion determinism/quality vs. fix a ranking stage — and HY-TRACE-01
cannot tell them apart. HY-STAB-01 closes exactly this gap by holding the
retrieval query constant in two control arms.

---

## 2. Hypotheses

The trace is designed to confirm or refute these — it assumes none.

**S1 — Pure expansion variance.** Most unstable targets are **stable in
both the `pinned` and `no_llm` arms**. Their hybrid gap is an artifact of
`expand_query` non-determinism, not a pipeline defect. *Predicted
signature:* `attribution = expansion_variance_only`. Fix space (deferred)
= expansion determinism (temperature 0, seeding, caching).

**S2 — Fixed final-blend defect (q03).** q03 WALL·E is
`rerank_recovered_final_demoted` in **all three arms** — the cross-encoder
recovers it but the `final_score` blend re-demotes it regardless of the
query. *Predicted signature:* `attribution = fixed_defect`; the q03 blend
decomposition shows which blend component (`quality_prior`,
`upstream_prior`, `source_agreement`) lifts competitors over it. Fix space
(deferred) = the `RERANK_*_WEIGHT` blend.

**S3 — LLM expansion is net-harmful for some targets.** For some targets
the `no_llm` arm yields `hybrid_top5_hit` while the `live` arm frequently
misses → LLM expansion *degrades* retrieval for them. *Predicted
signature:* `no_llm_classification = hybrid_top5_hit` with `live` unstable
or missing → `attribution = expansion_dependent` (harm).

**S4 — LLM expansion is net-helpful / necessary for some targets.** For
some targets the `no_llm` arm yields `unretrieved` / `retrieved_dropped_*`
while `live` / `pinned` can hit → LLM expansion improves recall.
*Predicted signature:* `no_llm_classification` is a recall-loss class and
`pinned`/`live` are better → `attribution = expansion_dependent` (rescue).

**S5 — Downstream is fully deterministic.** The `pinned` and `no_llm` arms
produce byte-stable results across all repeats → confirms the only
non-determinism is `expand_query`. *Predicted signature:* every target is
`stable` in `pinned` and `no_llm`. (HY-TRACE-01 strongly indicated this;
S5 is the explicit control check. A failure of S5 is a notable finding.)

---

## 3. Exact queries and arms

### 3.1 Queries

HY-STAB-01 traces **exactly the 8 `hybrid_attributable` qids**, identical
to HY-TRACE-01, each with its gold grade-3 target:

| qid | gold grade-3 target | HY-TRACE-01 result |
|---|---|---|
| q03 | 10681 — WALL·E | stable `rerank_recovered_final_demoted` |
| q04 | 25199 — Teen Witch | unstable |
| q05 | 144204 — Thanatomorphose | unstable |
| q06 | 367551 — American Hero | unstable |
| q07 | 63700 — My Babysitter's a Vampire | unstable |
| q08 | 545611 — Everything Everywhere All at Once | unstable |
| q10 | 8329 — [REC] | unstable |
| q18 | 9489 — You've Got Mail | stable `hybrid_top5_hit` |

The qid list and targets are loaded by **reusing
`hybrid_live_trace._prepare_inputs`** (which reads
`analysis/hybrid_gap/diagnosis.json` → `partition.hybrid_attributable`,
asserts it equals `HYBRID_ATTRIBUTABLE_QIDS`, and resolves gold grade-3
targets from `gold_labels.jsonl`). q12 / q13 are not traced.

### 3.2 The three arms

For a query `q`, let `processed = normalize_query(q)` and
`deterministic_query = expand_retrieval_query(processed)`. All three arms
use the **same** `rerank_query = deterministic_query` and the **same**
downstream composition (`semantic_search` → dedup → `bm25_search` → dedup
→ `rrf_fusion` → dedup+sort → `rerank`). They differ **only** in
`retrieval_query`:

| Arm | `retrieval_query` | `expand_query` calls | Determinism |
|---|---|---|---|
| **`live`** | `expand_retrieval_query(expand_query(processed) or processed)` — recomputed **every repeat** | one per (qid, repeat) | non-deterministic (the subject) |
| **`pinned`** | `expand_retrieval_query(pinned_expansion or processed)`, where `pinned_expansion = expand_query(processed)` is computed **once per qid** and reused for every repeat | one per qid | deterministic given the pin |
| **`no_llm`** | `deterministic_query` — `expand_query` is **never called** | zero | deterministic |

- The `live` arm reproduces HY-TRACE-01's behavior (it must match
  `hybrid.run()` with `HYBRID_USE_LLM_EXPANSION = True`).
- The `no_llm` arm reproduces `hybrid.run()`'s behavior when
  `HYBRID_USE_LLM_EXPANSION = False` — **without** mutating config (§7).
- The `pinned` arm is the bridge: same LLM-expanded query as a typical
  `live` repeat, but held constant — it isolates whether everything
  downstream of `expand_query` is deterministic (S5).

`--repeat` applies to every arm. `pinned`/`no_llm` repeats are expected
identical; running them anyway is the S5 control.

---

## 4. Allowed files (HY-STAB-01 may create/modify only these three)

- **Create:** `eval/scripts/hybrid_expansion_stability.py`
- **Create:** `eval/tests/test_hybrid_expansion_stability.py`
- **Modify (one line — add `hybrid_expansion_stability.py` to the
  `scripts/` block of the Layout fence):** `eval/README.md`

### Inputs (read-only — the tool must never write these)

- `eval/runs/<run_id>/gold_labels.jsonl` — gold grade-3 truth.
- `eval/runs/<run_id>/analysis/hybrid_gap/diagnosis.json` — the
  `hybrid_attributable` qid list.
- `eval/queries/v1.jsonl` — query text.
- `data/movies_clean.csv` — the `tmdb_id → movie_key` identity bridge.
- Modules **imported as libraries, never edited:**
  `eval.scripts._run_io`, `eval.scripts.error_report`,
  `eval.scripts.hybrid_live_trace`, `src.config`,
  `src.retrieval.query_processor`, `src.retrieval.filters`,
  `src.retrieval.semantic`, `src.retrieval.bm25`, `src.retrieval.fusion`,
  `src.retrieval.reranker`, `src.utils.dedup`, `src.pipelines.hybrid`
  (the private `_score` helper), `src.llm.langchain_ollama` (`expand_query`).

### Outputs (the tool's only writes)

- `eval/runs/<run_id>/analysis/hybrid_expansion_stability/stability_trace.jsonl`
- `eval/runs/<run_id>/analysis/hybrid_expansion_stability/stability_diagnosis.json`
- `eval/runs/<run_id>/analysis/hybrid_expansion_stability/q03_blend_decomposition.json`

`analysis/hybrid_expansion_stability/` is created with
`mkdir(parents=True, exist_ok=True)`; all three files are written
atomically via `_run_io._atomic_write_text` / `_atomic_write_json`.

---

## 5. Forbidden files (the tool must never create or modify any of these)

- **Anything under `src/`** — including `src/config.py`, every
  `src/retrieval/*`, `src/pipelines/*`, `src/models.py`, `src/llm/*`,
  `src/utils/*`.
- `app.py` and any recommender-runtime module.
- `candidates.jsonl`, `gold_labels.jsonl`, `silver_labels.jsonl`,
  `metrics.json`, `metrics_provisional.json`, `run_manifest.json`,
  `config_snapshot.json`.
- Anything under `analysis/hybrid_live_trace/`, `analysis/hybrid_gap/`,
  `analysis/error_report/`, `analysis/hybrid_stage_trace/`,
  `analysis/regrade/`, `analysis/case_studies/`,
  `analysis/audit_silver_labels/`.
- `compute_metrics.py`, `merge_labels.py`, `error_report.py`,
  `hybrid_gap_trace.py`, `hybrid_stage_trace.py`, `hybrid_live_trace.py`,
  `run_pipelines.py`, `_run_io.py`, `_schemas.py` — all imported, never
  edited.
- Any `eval/queries` file; `eval/queries/v1.jsonl` is read-only.

The tool's **only** writes are the three files named in §4 Outputs.

---

## 6. Output schema

### 6.1 `stability_trace.jsonl`

One JSON object per **(arm, qid, gold-grade-3 tmdb_id, repeat)**, sorted by
`(arm, qid, tmdb_id, repeat)` with `arm` ordered `live, pinned, no_llm`.
It is HY-TRACE-01's `trace.jsonl` record **plus** an `arm` field and an
`expansion_source` field inside `resolved`. Exact keys:

```json
{
  "schema_version": "hy-stab-01.v1",
  "run_id": "2026-05-19-1846-nogit",
  "arm": "pinned",
  "qid": "q03",
  "tmdb_id": 10681,
  "movie_key": "title:wall e|year:2008",
  "title": "WALL·E",
  "gold_grade": 3,
  "repeat": 0,
  "resolved": {
    "expansion_source": "pinned",
    "retrieval_query": "<exact query passed to semantic_search/bm25_search>",
    "rerank_query": "<exact query passed to rerank>",
    "filters": null
  },
  "semantic": {"present": true, "rank": 35, "score": 0.528, "list_len": 1500},
  "bm25":     {"present": true, "rank": 86, "score": 49.2, "list_len": 1500},
  "rrf":      {"present": true, "rank": 40, "score": 0.029, "list_len": 800},
  "rerank":   {"in_pool": true, "rerank_score": 0.0317, "rerank_rank": 1},
  "final":    {"final_score": 0.280, "final_rank": 7, "in_top5": false, "in_top15": true},
  "identity_warning": null,
  "loss_classification": "rerank_recovered_final_demoted"
}
```

- `arm` ∈ `{"live", "pinned", "no_llm"}`; `resolved.expansion_source` ∈
  `{"live", "pinned", "deterministic"}` (mirrors `arm`, made explicit so
  the row is self-describing).
- `semantic` / `bm25` / `rrf` / `rerank` / `final` / `identity_warning` /
  `loss_classification` are produced by the **reused** HY-TRACE-01
  capture helpers (`_stage_presence`, `_rerank_capture`,
  `_identity_warning`, `classify_loss`) — identical semantics to
  HY-TRACE-01 §6.1, including the `loss_classification` enum
  (`unretrieved`, `retrieved_dropped_at_fusion`,
  `retrieved_dropped_before_rerank_pool`, `rerank_recovered_final_demoted`,
  `rerank_demoted`, `hybrid_top5_hit`, `other`).
- For `arm = "pinned"` and `arm = "no_llm"`, `resolved.retrieval_query` is
  identical across that arm's repeats by construction.

### 6.2 `stability_diagnosis.json`

```json
{
  "schema_version": "hy-stab-01.v1",
  "run_id": "2026-05-19-1846-nogit",
  "trace_meta": {
    "traced_at": "2026-05-21T21:30:00Z",
    "pipeline_traced": "src/pipelines/hybrid.py run() lines 66-91 (parse_filters -> rerank); retrieval_query supplied per arm",
    "arms": ["live", "pinned", "no_llm"],
    "repeats": 5,
    "embedding_model": "BAAI/bge-m3",
    "reranker_model": "BAAI/bge-reranker-v2-m3",
    "llm_model": "llama3.2",
    "config": { "...": "the same numeric knobs HY-TRACE-01 records" },
    "qids_traced": ["q03","q04","q05","q06","q07","q08","q10","q18"],
    "targets_total": 8
  },
  "per_arm": {
    "live":   {"per_target": [ ... ], "loss_classification_counts": { ... },
               "mechanism_summary": { ... }, "dominant_mechanism": "inconclusive"},
    "pinned": {"per_target": [ ... ], "loss_classification_counts": { ... },
               "mechanism_summary": { ... }, "dominant_mechanism": "..."},
    "no_llm": {"per_target": [ ... ], "loss_classification_counts": { ... },
               "mechanism_summary": { ... }, "dominant_mechanism": "..."}
  },
  "instability_attribution": [
    {
      "qid": "q03", "tmdb_id": 10681, "title": "WALL·E",
      "live_stable": true,   "live_classification": "rerank_recovered_final_demoted",
      "pinned_stable": true, "pinned_classification": "rerank_recovered_final_demoted",
      "no_llm_stable": true, "no_llm_classification": "rerank_recovered_final_demoted",
      "live_final_rank": {"min": 6, "median": 7, "max": 7, "n_present": 5},
      "attribution": "fixed_defect"
    }
  ],
  "attribution_summary": {
    "fixed_defect": 0, "expansion_dependent": 0,
    "expansion_variance_only": 0, "stable_hit": 0, "inconclusive": 0
  },
  "dominant_finding": "..."
}
```

- `per_arm.<arm>` — each arm aggregated **exactly** as HY-TRACE-01
  aggregates its single arm: `per_target` (per-repeat `classifications`,
  `stable`, agreed `classification` or `"unstable"`),
  `loss_classification_counts`, `mechanism_summary`,
  `dominant_mechanism`. Produced by reusing
  `hybrid_live_trace._per_target` / `_loss_counts` /
  `_mechanism_summary` / `_dominant_mechanism` on each arm's rows. Each
  arm's `loss_classification_counts` and `mechanism_summary` sum to
  `targets_total`.
- `instability_attribution` — one entry per (qid, tmdb_id), sorted by
  `(qid, tmdb_id)`. `live_final_rank` summarizes `final.final_rank` over
  the `live` arm's repeats (`min`/`median`/`max` over repeats where the
  target reached the pool; `n_present` = how many of those repeats; all
  `null` and `n_present` 0 if it never reached the pool). `attribution` is
  computed deterministically, **first matching rule wins**. Write `N` for
  the `no_llm` arm's per-target result and `P` for the `pinned` arm's;
  "hit" = stable `hybrid_top5_hit`; "miss" = stable and a non-hit loss
  class (∉ `{"hybrid_top5_hit", "other"}`):

  | `attribution` | rule (precedence order) | meaning |
  |---|---|---|
  | `stable_hit` | `live_stable` **and** `live_classification == "hybrid_top5_hit"` | not a miss (q18) |
  | `inconclusive` (S5 guard) | `pinned` **or** `no_llm` is unstable, **or** either's classification is `"other"` | a control arm is itself unstable (S5 refuted) or undecidable — cannot attribute |
  | `fixed_defect` | `N` is a **miss** **and** `P` is a **miss** | the LLM-free deterministic control fails **and** a fixed LLM expansion does not rescue it — a genuine ranking defect. Keys on `no_llm`; `pinned` only confirms no rescue. |
  | `expansion_dependent` | (`N` **miss** **and** `P` **hit** — expansion *rescues*) **or** (`N` **hit** **and** `P` **miss** — a fixed expansion *harms*) | LLM expansion materially changes recovery; the rescue case must **not** count as a fixed defect — the pipeline-with-LLM works |
  | `expansion_variance_only` | `N` **hit** **and** `P` **hit** (`live` not a stable hit) | both fixed-query controls recover it; only the non-deterministic `expand_query` intermittently loses it — pure run-to-run variance |
  | `inconclusive` | defensive — no rule above matched | undecidable |

  Precedence is strictly top-to-bottom. The S5-guard `inconclusive` row is
  evaluated **before** `fixed_defect` / `expansion_dependent` /
  `expansion_variance_only`, so those three may assume `N` and `P` are each
  exactly a "hit" or a "miss". `fixed_defect` keys on the `no_llm` arm (the
  genuine LLM-free control); a `pinned`-only miss never yields
  `fixed_defect`.
- `attribution_summary` — counts over `instability_attribution`; sums to
  `targets_total`.
- `dominant_finding` ∈ `{"expansion_related", "fixed_defect", "mixed",
  "inconclusive"}`, computed by the §11 rule — `expansion_related` covers
  both `expansion_variance_only` and `expansion_dependent`. Best-effort
  label; the human decides at Gate E regardless.

### 6.3 `q03_blend_decomposition.json`

q03 WALL·E is HY-TRACE-01's one stable `rerank_recovered_final_demoted`
case. This file decomposes its `final_score` against the competitors that
outrank it, **per arm, at repeat 0** (deterministic arms → repeat 0 is
representative; `live` arm → repeat 0 with `note` that it varies).

```json
{
  "schema_version": "hy-stab-01.v1",
  "run_id": "2026-05-19-1846-nogit",
  "qid": "q03", "tmdb_id": 10681, "title": "WALL·E",
  "blend_formula": "final_score = rerank_score + 0.08*quality_prior + 0.20*upstream_prior + 0.10*source_agreement",
  "config_weights": {
    "RERANK_VOTE_COUNT_WEIGHT": 0.08,
    "RERANK_UPSTREAM_WEIGHT": 0.20,
    "RERANK_SOURCE_AGREEMENT_BONUS": 0.10
  },
  "priors_are_pool_normalized": true,
  "per_arm": {
    "pinned": {
      "repeat": 0,
      "retrieval_query": "...",
      "target_in_pool": true,
      "target": {
        "movie_key": "title:wall e|year:2008",
        "rerank_score": 0.0317, "rerank_rank": 1,
        "quality_prior": 0.41, "upstream_prior": 0.55, "source_agreement": 1.0,
        "final_score": 0.280, "final_rank": 7,
        "contributions": {"rerank_score": 0.0317, "vote": 0.0328,
                          "upstream": 0.110, "agreement": 0.10}
      },
      "leapfrog_competitors": [
        {
          "final_rank": 0, "title": "...", "movie_key": "...",
          "rerank_score": 0.029, "rerank_rank": 4,
          "quality_prior": 0.98, "upstream_prior": 0.91, "source_agreement": 1.0,
          "final_score": 0.41,
          "contributions": {"rerank_score": 0.029, "vote": 0.078,
                            "upstream": 0.182, "agreement": 0.10}
        }
      ],
      "leapfrog_count": 7,
      "note": null
    },
    "no_llm": { "...": "same shape" },
    "live":   { "...": "same shape", "note": "live arm; repeat 0 only — varies across repeats" }
  }
}
```

- For each arm, the tool runs (or reuses) that arm's repeat-0 q03 stage
  run, takes the **50-member scored rerank pool**, and reads — never
  recomputes — each candidate's `rerank_score`, `quality_prior`,
  `upstream_prior`, `source_agreement`, `final_score` (the fields
  `src/retrieval/reranker.py` lines 127-139 attach to every pool member).
- `contributions` is arithmetic on those read values:
  `vote = RERANK_VOTE_COUNT_WEIGHT * quality_prior`,
  `upstream = RERANK_UPSTREAM_WEIGHT * upstream_prior`,
  `agreement = RERANK_SOURCE_AGREEMENT_BONUS * source_agreement`,
  `rerank_score` carried through. (`rerank_score + vote + upstream +
  agreement` must equal `final_score` within 1e-6 — asserted by a test.)
- `target` = WALL·E's pool row (or `target_in_pool: false`,
  `target: null` if WALL·E did not reach that arm/repeat's pool).
- `leapfrog_competitors` = every pool member with
  `final_rank < target.final_rank` **and** `rerank_rank > target.rerank_rank`
  (ranked above WALL·E *despite* a worse cross-encoder score — the
  blend-demotion victims-of vs. WALL·E), sorted by `final_rank`.
  `leapfrog_count` = its length. Empty list / count 0 when WALL·E is not
  in the pool.
- `note` — a per-arm caveat string, or `null`. For the `live` arm it is
  the literal `"live arm; repeat 0 only — varies across repeats"` (the
  live decomposition is one non-deterministic sample). For the `pinned`
  and `no_llm` arms it is `null` — those arms are deterministic, so their
  repeat-0 decomposition is representative. An arm not selected by
  `--arms` is omitted from `per_arm` entirely; `note` never signals a
  missing arm.
- `priors_are_pool_normalized: true` restates the §0.3 caveat in-band.

---

## 7. Why an eval-only script suffices — no `src/` change, no config mutation

The hard constraints (§0.2) forbid any `src/*` edit and any `src.config`
mutation. Neither is required. Proof:

1. **The three arms differ only in one string.** §3.2: `live`, `pinned`,
   `no_llm` share the entire downstream composition and `rerank_query`;
   only `retrieval_query` differs. HY-TRACE-01 already proved (its Gate D,
   `test_composition_matches_hybrid_run`) that an eval script can
   reproduce the hybrid stage composition faithfully by importing the
   stage functions. HY-STAB-01 adds **one parameter** — the caller-supplied
   `retrieval_query` — to that same composition.

2. **`no_llm` needs no config mutation.** `hybrid.run()` lines 58-63
   choose `retrieval_query = deterministic_query` when
   `HYBRID_USE_LLM_EXPANSION` is false. The tool gets the *identical*
   `retrieval_query` by simply passing `deterministic_query` into the
   stage runner — it never reads or writes `HYBRID_USE_LLM_EXPANSION`. The
   config flag stays untouched; the tool just declines to call
   `expand_query`. Setting the flag at runtime would be a `src.config`
   mutation and is **forbidden** (§0.2.2).

3. **`pinned` is a cached return value.** The tool calls the real
   `expand_query(processed)` once per qid and stores the returned string.
   Reusing a stored string is the tool's own logic — no `src` change.

4. **The q03 blend decomposition reads, never recomputes.**
   `src/retrieval/reranker.py` `rerank()` writes `rerank_score`,
   `quality_prior`, `upstream_prior`, `source_agreement`, `final_score`
   onto every pool member (lines 127-139). The tool calls the real
   `rerank(..., top_k=RERANK_TOP_K, rerank_pool=RERANK_TOP_K)` — the same
   "full scored pool" trick HY-TRACE-01 uses — and reads those attached
   fields. The `contributions` arithmetic (`weight * prior`) uses weights
   read from `src.config`; it does not re-derive the cross-encoder score
   or the priors. A test asserts the read components sum back to
   `final_score`, so any drift is caught.

5. **Faithfulness is enforced by a test, not by hope.** The new tool's
   stage runner is anchored to HY-TRACE-01's Gate-D-proven
   `_run_hybrid_stages` by `test_live_arm_matches_hybrid_live_trace`
   (§12 criterion 12) — with stage functions and `expand_query`
   monkeypatched to deterministic fakes on `hybrid_live_trace`'s shared
   stage globals, the `live`-arm stage run must equal
   `hybrid_live_trace._run_hybrid_stages`.

**Conclusion:** HY-STAB-01 is a pure `eval/` tool that imports `src`
retrieval functions and HY-TRACE-01 helpers as libraries. No `src/` file
is created or modified; `src.config` is read, never mutated.

---

## 8. Validation commands

### 8.1 Agent-runnable (Codex runs; Claude re-runs at Gate D) — hermetic, no models

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hybrid_expansion_stability --run 2026-05-19-1846-nogit --dry-run
```

Expected:

1. `compileall` reports `Listing ... OK`.
2. All tests pass; the count is `previous + N`. Baseline is **115** from
   HY-TRACE-01; HY-STAB-01 adds at least 13 → expect **≥ 128**. Codex
   reports the exact before/after counts.
3. `--dry-run` exits 0, **imports no model** (`src.models`,
   `src.retrieval.semantic`, `src.retrieval.bm25`,
   `src.retrieval.reranker`, `src.llm.*` must not be imported on the
   `--dry-run` path — asserted by `test_dry_run_no_model_import`),
   **writes nothing**, and prints the 8 traced qids with each resolved
   gold grade-3 target and the arm list.

### 8.2 Human-run (after Gate D — loads models, calls Ollama)

**Environment note (binding on this machine — 8 GB RTX 4070 Laptop GPU).**
Ollama must run `llama3.2` on the **CPU** so the trace's BGE-M3 +
cross-encoder fit in VRAM. An empty `CUDA_VISIBLE_DEVICES` does **not**
work — Ollama still discovers the GPU. Start Ollama as:

```
CUDA_VISIBLE_DEVICES=-1 OLLAMA_LLM_LIBRARY=cpu ollama serve
```

Confirm `nvidia-smi` shows ≥ ~5.5 GB free VRAM before launching. Then:

```
python -m eval.scripts.hybrid_expansion_stability --run 2026-05-19-1846-nogit --repeat 5
python -c "import json,pathlib; d=json.loads(pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_diagnosis.json').read_text(encoding='utf-8')); tt=d['trace_meta']['targets_total']; assert len(d['instability_attribution'])==tt; assert sum(d['attribution_summary'].values())==tt; [print(a, sum(pa['loss_classification_counts'].values())==tt==sum(pa['mechanism_summary'].values())) for a,pa in d['per_arm'].items()]; print('attribution', d['attribution_summary'], '-> finding:', d['dominant_finding'])"
```

Expected:

1. The trace exits 0 and writes `stability_trace.jsonl`
   (3 arms × 8 qids × `repeat` records = 120 at `--repeat 5`),
   `stability_diagnosis.json`, and `q03_blend_decomposition.json`.
2. The one-liner confirms `instability_attribution` covers all 8 targets,
   `attribution_summary` sums to `targets_total`, and each arm's counts
   sum to `targets_total`; then prints the attribution counts and
   `dominant_finding`. The **specific** counts are the diagnostic result —
   they are not pre-asserted; Claude summarizes them at Gate E.

`--repeat 5` is the dominant runtime knob: 120 pipeline runs (each loads
no extra model — singletons are loaded once). `--repeat` may be lowered to
shorten the run; `pinned`/`no_llm` are deterministic so a low count still
exercises S5, but ≥ 5 gives the `live` arm a usable variance sample.

---

## 9. How to interpret results

Read `stability_diagnosis.json` and `q03_blend_decomposition.json` after
the human-run trace.

- **`per_arm.no_llm` and `per_arm.pinned` should each be all-`stable`.**
  If so, S5 holds — the only non-determinism is `expand_query`. If a
  control arm contains an `unstable` target, S5 is **refuted** and there
  is a second non-deterministic element to find before any fix.
- **`attribution = fixed_defect`** → the target fails even with the
  LLM-free deterministic query **and** a fixed LLM expansion does not
  rescue it — a genuine pipeline defect. Read that target's `no_llm`
  `classification` for the mechanism (`rerank_recovered_final_demoted` →
  final-score blend, confirms **S2**; `retrieved_dropped_*` /
  `unretrieved` → recall/depth; `rerank_demoted` → reranker).
- **`attribution = expansion_dependent`** → LLM expansion materially
  changes recovery. `no_llm` miss + `pinned` hit = expansion *rescues* the
  target (confirms **S4** — **not** a ranking defect; do not fix ranking
  for it). `no_llm` hit + `pinned` miss = a fixed expansion *harms* it
  (confirms **S3**). The lever is `expand_query` quality/correctness.
- **`attribution = expansion_variance_only`** → both fixed-query controls
  recover the target; only the non-deterministic `expand_query`
  intermittently loses it. Run-to-run variance, not a defect. The lever is
  `expand_query` determinism. Confirms **S1**.
- **`attribution = stable_hit`** → not a problem (q18 expected).
- **`q03_blend_decomposition.json`** → for each arm, compare WALL·E's
  `contributions` against its `leapfrog_competitors`. The component with
  the largest competitor-minus-WALL·E gap is the blend lever that demotes
  it. This scopes (does not perform) any future blend fix.

**The decision axis is expansion-related vs. fixed defect.** If
`expansion_variance_only` + `expansion_dependent` dominate, the next plan
targets `expand_query`; if `fixed_defect` dominates, it targets the
implicated ranking stage; if both are present, both — sequenced (§11).

---

## 10. Gate D review checklist (Claude, after Codex finishes)

Report findings as **matches spec / deviations / blockers**, in that order.

- [ ] **Scope:** the diff touches **exactly** the 3 files in §4 —
      `hybrid_expansion_stability.py`, `test_hybrid_expansion_stability.py`,
      one line of `eval/README.md` — nothing else.
- [ ] **No `src/` edit:** no file under `src/`, no `app.py`, no
      `src/config.py` created or modified.
- [ ] **No config mutation:** `src.config` is read via import/`getattr`,
      never assigned to. The `no_llm` arm is realized by passing
      `deterministic_query`, **not** by setting `HYBRID_USE_LLM_EXPANSION`.
- [ ] **`src` and `hybrid_live_trace` used as libraries only:** the tool
      imports them and **re-implements no** retrieval / BM25 / RRF /
      fusion / reranker / embedding / blend logic. The only private
      symbols imported are `src.pipelines.hybrid._score` and the
      `hybrid_live_trace` helpers.
- [ ] **Three arms correct:** `live` recomputes `expand_query` every
      repeat; `pinned` calls it once per qid and reuses; `no_llm` never
      calls it and uses `deterministic_query`. `rerank_query` is
      `deterministic_query` in all three.
- [ ] **Faithfulness:** `test_live_arm_matches_hybrid_live_trace` exists,
      passes, and genuinely patches stage functions + `expand_query` on
      `hybrid_live_trace`'s shared stage globals (the single set both
      modules use).
- [ ] **q03 decomposition reads, not recomputes:** components come from
      the movie dicts `rerank()` populated; `test_q03_contributions_sum`
      asserts `rerank_score + weighted priors == final_score` (±1e-6).
- [ ] **Rerank-pool capture:** the tool calls `rerank(...,
      top_k=RERANK_TOP_K, rerank_pool=RERANK_TOP_K)` to obtain the full
      scored pool — it does not re-score or re-blend.
- [ ] **Output scope:** the tool's only writes are the three
      `analysis/hybrid_expansion_stability/` files; writes are atomic;
      the directory is `mkdir(parents=True, exist_ok=True)`.
- [ ] **Forbidden files:** nothing in §5 is created or modified;
      `--dry-run` writes nothing.
- [ ] **Queries:** traced qids resolved via
      `hybrid_live_trace._prepare_inputs`; equal `HYBRID_ATTRIBUTABLE_QIDS`;
      q12 / q13 not traced.
- [ ] **Hermetic validation:** §8.1 ran — `compileall` OK, unit count
      ≥ 128, `--dry-run` exits 0, imports no model, writes nothing.
- [ ] **Schema:** the three files match §6 exactly (keys, sort order,
      `arm` / `attribution` enums, every arm's counts and each
      `attribution_summary` sum to `targets_total`).

If all pass: Gate D is green; the human runs §8.2. Any blocker stops the
plan for a fix before the human-run trace.

---

## 11. Gate E decision tree (human, after the human-run trace)

Claude summarizes the diagnosis; the human picks **exactly one** branch.
Let `A = attribution_summary` over the 8 targets, and
`expansion_total = A.expansion_variance_only + A.expansion_dependent` —
both are LLM-expansion-attributable; neither is a query-independent
ranking defect.

1. **Expansion dominates** — `expansion_total ≥ 5` and `A.fixed_defect ≤ 1`:
   → **Draft a separate, separately-gated `expand_query` plan.** If
   `A.expansion_variance_only` is the larger share, scope it to
   *determinism* (`temperature=0`, seeding, a per-query expansion cache);
   if `A.expansion_dependent` is the larger share, scope it to expansion
   *quality / correctness* (prompt hardening). Gated on a paired-bootstrap
   eval showing no regression. Not dispatched here.

2. **Fixed defects dominate** — `A.fixed_defect ≥ 3` and
   `expansion_total ≤ 2`:
   → **Draft a separate, separately-gated fix plan**, scoped by the
   `no_llm` mechanism of the `fixed_defect` targets (final-score blend vs.
   recall/depth vs. reranker). The q03 blend decomposition already scopes
   the blend case. Not dispatched here.

3. **Mixed** — `A.fixed_defect ≥ 2` **and** `expansion_total ≥ 2`:
   → **Draft two separate scoped plans** (one for the `expand_query`
   issue, one for the fixed-defect mechanism), each separately gated.
   Sequence by target count, larger first.

4. **Inconclusive** — `A.inconclusive ≥ 3`, **or** a control arm
   (`pinned` / `no_llm`) is itself unstable (S5 refuted), **or** no branch
   above is satisfied:
   → **Stop. Request additional trace, not a fix.** If S5 is refuted,
   the follow-up first finds the second non-deterministic element. No fix
   plan is drafted on inconclusive evidence.

`dominant_finding` is the tool's best-effort pre-label of this tree:
`expansion_related` for branch 1, `fixed_defect` for branch 2, `mixed`
for branch 3, `inconclusive` for branch 4 (or when no branch is
satisfied). The human decides regardless. **This plan pre-commits to no
branch.** Its sole product is the evidence in the three §6 output files.

---

## 12. Ticket HY-STAB-01 — Codex-ready handoff

### 1. Goal

Build `eval/scripts/hybrid_expansion_stability.py`: a read-only diagnostic
tool that traces each of the 8 `hybrid_attributable` gold grade-3 targets
through the hybrid pipeline under three retrieval-query arms (`live`,
`pinned`, `no_llm`), classifies each target's loss per arm, attributes its
instability (expansion variance vs. fixed defect), decomposes q03's
`final_score` blend, and writes `stability_trace.jsonl`,
`stability_diagnosis.json`, `q03_blend_decomposition.json` under
`analysis/hybrid_expansion_stability/`. Trace-only: it imports `src`
retrieval functions and the HY-TRACE-01 helpers as libraries and changes
no behavior.

### 2. Files to change

- Create: `eval/scripts/hybrid_expansion_stability.py`
- Create: `eval/tests/test_hybrid_expansion_stability.py`
- Modify (one line): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/hybrid_live_trace.py` (reuse its helpers — see criteria),
  `eval/scripts/_run_io.py`, `eval/scripts/error_report.py`.
- `src/config.py`, `src/retrieval/query_processor.py`,
  `src/retrieval/filters.py`, `src/retrieval/semantic.py`,
  `src/retrieval/bm25.py`, `src/retrieval/fusion.py`,
  `src/retrieval/reranker.py`, `src/utils/dedup.py`,
  `src/pipelines/hybrid.py`, `src/llm/langchain_ollama.py`.
- `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl`,
  `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_gap/diagnosis.json`,
  `eval/queries/v1.jsonl`, `data/movies_clean.csv`.

### 4. Acceptance criteria

1. **CLI:** `python -m eval.scripts.hybrid_expansion_stability
   [--run RUN_ID] [--repeat N] [--queries PATH]
   [--arms live,pinned,no_llm] [--dry-run]`. `--run` defaults to
   `_run_io.latest_run()`; `--repeat` defaults to `5` (must be ≥ 1);
   `--queries` defaults to `eval/queries/v1.jsonl`; `--arms` is a
   comma-list defaulting to `live,pinned,no_llm` (any subset allowed;
   order is normalized to `live, pinned, no_llm`).

2. **Reuse, don't re-implement.** Import from
   `eval.scripts.hybrid_live_trace`: `HYBRID_ATTRIBUTABLE_QIDS`, `Target`,
   `TraceInputs`, `HybridLiveTraceError`, `_prepare_inputs`,
   `_ensure_live_imports`, `_stage_presence`, `_rerank_capture`,
   `_identity_warning`, `_snapshot_movies`, `classify_loss`,
   `_per_target`, `_loss_counts`, `_mechanism_summary`,
   `_dominant_mechanism`. Input loading and target resolution **must** go
   through `hybrid_live_trace._prepare_inputs` (do not duplicate it). The
   tool defines its own error class
   `HybridStabilityError(HybridLiveTraceError)`.

3. **Preconditions:** rely on `_prepare_inputs` for the missing-input
   checks (`gold_labels.jsonl`, `hybrid_gap/diagnosis.json`, the queries
   file, `data/movies_clean.csv`); on failure it raises
   `HybridLiveTraceError` — `main()` catches `HybridLiveTraceError` (and
   thus the subclass), prints to `stderr`, returns non-zero, writes
   nothing.

4. **`--dry-run`:** resolve inputs and targets; print `run_id=`,
   `arms=<comma list>`, `qids_traced=...`, and each qid with its gold
   grade-3 targets (`tmdb_id`, `title`, `movie_key`); exit 0; **write
   nothing**; **import no model** — `src.models`,
   `src.retrieval.semantic/bm25/reranker`, `src.llm.*` must not be in
   `sys.modules` after `--dry-run` (defer all live imports into the
   trace path).

5. **Parametrized stage runner.** Implement
   `run_stages(*, raw_query, retrieval_query, rerank_query) -> StageRun`
   (reuse `hybrid_live_trace.StageRun`) that reproduces
   `src/pipelines/hybrid.py` run() lines 66-91 with the **caller-supplied**
   `retrieval_query` and `rerank_query`: `filters = parse_filters(
   raw_query) or None`; `sem = deduplicate_movies(semantic_search(
   retrieval_query, top_k=CANDIDATE_POOL, filters=filters),
   prefer_score="semantic_score")`; `bm = deduplicate_movies(bm25_search(
   retrieval_query, top_k=CANDIDATE_POOL, filters=filters),
   prefer_score="bm25_score")`; `fused = deduplicate_movies(rrf_fusion(
   sem, bm, top_k=RERANK_POOL), prefer_score="rrf_score")` then
   `fused.sort(key=lambda x: _score(x,"final_score","rrf_score"),
   reverse=True)`; `scored_pool = rerank(rerank_query, fused,
   top_k=RERANK_TOP_K, rerank_pool=RERANK_TOP_K)`. Snapshot each list with
   `_snapshot_movies` before the next stage. Access every stage callable
   and pool constant (`normalize_query`, `expand_retrieval_query`,
   `expand_query`, `parse_filters`, `semantic_search`, `bm25_search`,
   `rrf_fusion`, `rerank`, `_score`, `CANDIDATE_POOL`, `RERANK_POOL`,
   `RERANK_TOP_K`) through the `hybrid_live_trace` module globals after
   calling `hybrid_live_trace._ensure_live_imports()` — reference that one
   shared set; do **not** create a second set of stage references in the
   new module, so tests have a single monkeypatch target.

6. **Arm query derivation.** For each qid, `processed = normalize_query(
   query)`; `deterministic_query = expand_retrieval_query(processed)`;
   `rerank_query = deterministic_query` (all arms).
   - `live`: per repeat, `retrieval_query = expand_retrieval_query(
     expand_query(processed) or processed)` — `expand_query` called every
     repeat.
   - `pinned`: `pinned_expansion = expand_query(processed)` computed
     **once per qid**; per repeat `retrieval_query = expand_retrieval_query(
     pinned_expansion or processed)`.
   - `no_llm`: `retrieval_query = deterministic_query`; `expand_query` is
     never called.
   The tool **must not** read or write `HYBRID_USE_LLM_EXPANSION` /
   `LLM_RETRIEVAL_ENABLED`.

7. **Trace records.** For each selected arm, each traced qid, each repeat
   `0..N-1`, each gold grade-3 target: build a `stability_trace.jsonl`
   record with the exact §6.1 schema. Reuse `_stage_presence`,
   `_rerank_capture`, `_identity_warning`, `classify_loss` for the
   `semantic`/`bm25`/`rrf`/`rerank`/`final`/`identity_warning`/
   `loss_classification` fields. Add `arm` and `resolved.expansion_source`.
   `schema_version = "hy-stab-01.v1"` (module constant `SCHEMA_VERSION`).
   Rows sorted by `(arm, qid, tmdb_id, repeat)` with arm order
   `live, pinned, no_llm`.

8. **`stability_diagnosis.json`:** exact §6.2 schema. `per_arm.<arm>` is
   built by running `_per_target` / `_loss_counts` / `_mechanism_summary`
   / `_dominant_mechanism` on that arm's trace rows. `trace_meta` records
   `traced_at` (UTC, second precision), `arms`, `repeats`, the three model
   names and numeric config knobs (reuse the values
   `_ensure_live_imports` loads), `qids_traced`, `targets_total`.
   `instability_attribution` per the §6.2 table; `live_final_rank` =
   `min`/`median`/`max`/`n_present` over the `live` arm's `final.final_rank`
   for repeats where the target was in the pool (`statistics.median`;
   all `null`, `n_present` 0 if never in pool). `attribution_summary`
   counts; `dominant_finding` per §11. Every arm's
   `loss_classification_counts` and `mechanism_summary`, and
   `attribution_summary`, sum to `targets_total`; raise
   `HybridStabilityError` if not.
   - If `--arms` selects a subset, `per_arm` contains only the run arms;
     for any target whose `pinned` or `no_llm` arm was not run, the
     corresponding `*_stable` / `*_classification` fields are `null` and
     `attribution` is `inconclusive`.

9. **`q03_blend_decomposition.json`:** exact §6.3 schema. For each run arm,
   take that arm's **repeat-0** q03 `StageRun.scored_pool`; for every pool
   member read `rerank_score`, `quality_prior`, `upstream_prior`,
   `source_agreement`, `final_score`; compute `contributions`
   (`vote = RERANK_VOTE_COUNT_WEIGHT*quality_prior`,
   `upstream = RERANK_UPSTREAM_WEIGHT*upstream_prior`,
   `agreement = RERANK_SOURCE_AGREEMENT_BONUS*source_agreement`,
   `rerank_score` carried). `rerank_rank` = 0-indexed rank by
   `rerank_score`; `final_rank` = 0-indexed rank by `final_score`.
   `target` = WALL·E's row (matched by `movie_key`; `target_in_pool:false`
   + `target:null` if absent). `leapfrog_competitors` = pool members with
   `final_rank < target.final_rank` and `rerank_rank > target.rerank_rank`,
   sorted by `final_rank`; `leapfrog_count` = its length. q03 is always
   traced; the q03 decomposition includes only the arms that ran (an arm
   absent from `--arms` is simply omitted from `per_arm`). The per-arm
   `note` field carries that arm's caveat per §6.3 — it does not signal
   the arm list.

10. **Writes nothing else.** Only the three
    `analysis/hybrid_expansion_stability/` files; directory via
    `mkdir(parents=True, exist_ok=True)`; files via
    `_run_io._atomic_write_text` / `_atomic_write_json`. No file in §5 is
    touched.

11. **CLI output (non-dry-run):** print `run_id=`, the three output
    paths, `arms=`, `repeats=`, `targets_total=`, `attribution_summary=`,
    and `dominant_finding=`.

12. **`test_hybrid_expansion_stability.py`** is hermetic (no models, no
    Ollama, no network; `tempfile.TemporaryDirectory`; monkeypatched stage
    functions, `expand_query`, and `_run_io` paths — follow
    `eval/tests/test_hybrid_live_trace.py`) and includes at least:
    - `test_live_arm_matches_hybrid_live_trace` — stage functions and
      `expand_query` monkeypatched to deterministic fakes on
      `hybrid_live_trace`'s shared stage globals (the single set both
      modules use); assert the `live`-arm `StageRun` equals
      `hybrid_live_trace._run_hybrid_stages`'s.
    - `test_pinned_arm_calls_expand_query_once_per_qid` — a counting fake
      `expand_query`; after a `pinned`-arm trace of one qid at
      `--repeat 3`, assert exactly one call and three identical
      `resolved.retrieval_query` values.
    - `test_no_llm_arm_never_calls_expand_query` — a fake `expand_query`
      that raises; a `no_llm`-arm trace completes and its
      `resolved.retrieval_query` equals `expand_retrieval_query(
      normalize_query(q))`.
    - `test_attribution_fixed_defect` — fakes make a target a stable
      non-hit in **both** `no_llm` and `pinned`; assert
      `attribution == "fixed_defect"`.
    - `test_attribution_expansion_dependent` — fakes make a target a
      stable miss in `no_llm` but a stable `hybrid_top5_hit` in `pinned`
      (LLM expansion rescues it); assert
      `attribution == "expansion_dependent"`, and the target is **not**
      counted under `fixed_defect`.
    - `test_attribution_expansion_variance_only` — fakes make a target
      unstable in `live` but stable in `pinned` and `no_llm`; assert
      `attribution == "expansion_variance_only"`.
    - `test_attribution_stable_hit` — stable `hybrid_top5_hit` in `live`
      → `attribution == "stable_hit"`.
    - `test_attribution_inconclusive_when_control_arm_unstable` — a
      `pinned` arm made unstable by fakes → `attribution == "inconclusive"`.
    - `test_q03_contributions_sum` — for a synthetic pool,
      `rerank_score + vote + upstream + agreement == final_score` within
      1e-6 for every decomposed row.
    - `test_q03_leapfrog_competitors` — a synthetic pool where one
      candidate has worse `rerank_rank` but better `final_rank` than the
      target → it appears in `leapfrog_competitors`.
    - `test_dry_run_no_model_import` — after `--dry-run`, `src.models`
      absent from `sys.modules`; nothing written.
    - `test_missing_diagnosis_exits_nonzero` — precondition failure →
      non-zero exit, nothing written.
    - `test_diagnosis_counts_sum_to_targets_total` — every arm's counts
      and `attribution_summary` sum to `targets_total`.

13. **No `src/` edit; `src` and `hybrid_live_trace` imported as libraries
    only;** no retrieval / BM25 / RRF / reranker / blend logic
    re-implemented; `src.config` never mutated; no new LLM call added to
    any ranking path.

### 5. Validation commands

Run §8.1 (agent-runnable, hermetic). Report per `AGENTS.md`: files
changed, commands run, before/after test counts, any failures verbatim,
the `--dry-run` stdout, and any assumptions. **Do not run §8.2** — the
live model-loading trace is human-run after Gate D.

### 6. Dependencies

- HY-TRACE-01 — `eval/scripts/hybrid_live_trace.py` must exist and be
  importable (satisfied; HY-TRACE-01 complete, Gate D passed, live trace
  run 2026-05-21).
- HX-01 — `analysis/hybrid_gap/diagnosis.json` (satisfied).
- ML-01 — `gold_labels.jsonl` (satisfied).
- The working-tree `src/` pipeline; ChromaDB (`data/chroma_bgem3`),
  `data/movies_clean.csv`, and a reachable Ollama with `llama3.2` are
  required **only for the human-run §8.2 step**, not for Codex.

### 7. Risk level

**Low.** Three-file change; one new read-only `eval/` tool that reuses the
already-reviewed HY-TRACE-01 helpers and imports `src` functions without
editing them. The real risks are (a) writing outside
`analysis/hybrid_expansion_stability/`, (b) re-implementing or mutating
ranking logic instead of importing it, (c) the `no_llm` arm being realized
via a config mutation, or (d) the parametrized stage runner drifting from
`hybrid.run()`. Acceptance criteria 5/6/9/10/13, the §5 forbidden list,
atomic writes, and `test_live_arm_matches_hybrid_live_trace` close all
four.

### 8. Reviewer

Claude Code Pro, per the §10 Gate D checklist. Specifically verifies: the
diff touches exactly the 3 files; no `src/*` edited; no `src.config`
mutation; the `no_llm` arm uses `deterministic_query` (not a config flag);
the tool re-implements no ranking logic and reuses HY-TRACE-01 helpers;
the q03 decomposition reads attached fields and the contributions sum to
`final_score`; the tool's only writes are the three
`analysis/hybrid_expansion_stability/` files; the hermetic validation
passed. Claude then signs off Gate D, the human runs §8.2, and Claude
summarizes the diagnosis for the Gate E decision.

### 9. Codex prompt (planning artifact — NOT dispatched by this plan)

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket HY-STAB-01 exactly as specified in
docs/superpowers/plans/2026-05-21-hy-stab-01-hybrid-expansion-instability-trace.md
section 12 ("Ticket HY-STAB-01 -- Codex-ready handoff"), with the output
schema in section 6.

You may edit ONLY:
  - eval/scripts/hybrid_expansion_stability.py       (create)
  - eval/tests/test_hybrid_expansion_stability.py    (create)
  - eval/README.md                                   (add ONE line:
                                                      hybrid_expansion_stability.py
                                                      in the scripts/ block
                                                      of the Layout fence)

Do not edit any other file. No src/* edits. No src/config.py edits. No
edit to eval/scripts/hybrid_live_trace.py or any other existing eval
script. No app.py / recommender-runtime edits. Do not run pip installs.
Do not run any git command.

HARD CONSTRAINTS:
  - This tool is TRACE-ONLY / DIAGNOSTICS-ONLY. It MUST NOT change,
    re-implement, or tune any ranking / retrieval / BM25 / RRF / fusion /
    reranker / embedding / query-expansion logic.
  - It MUST NOT mutate src.config. In particular the no_llm arm is
    produced by passing the deterministic query into the stage functions
    -- NOT by setting HYBRID_USE_LLM_EXPANSION = False.
  - It IMPORTS the real functions from src.retrieval.*, src.utils.dedup,
    src.config, src.pipelines.hybrid (the private _score helper),
    src.llm.langchain_ollama (expand_query), AND reuses the helpers from
    eval.scripts.hybrid_live_trace AS LIBRARIES. It MUST NOT re-implement
    input loading, per-stage capture, the loss classifier, or the
    aggregation -- reuse hybrid_live_trace._prepare_inputs,
    _stage_presence, _rerank_capture, _identity_warning, classify_loss,
    _per_target, _loss_counts, _mechanism_summary, _dominant_mechanism.
  - Three arms (live / pinned / no_llm) differ ONLY in retrieval_query;
    rerank_query is the deterministic query in all three. live recomputes
    expand_query every repeat; pinned calls it once per qid and reuses;
    no_llm never calls it.
  - The q03 blend decomposition READS rerank_score / quality_prior /
    upstream_prior / source_agreement / final_score off the movie dicts
    that src.retrieval.reranker.rerank() already attaches -- it MUST NOT
    re-compute the cross-encoder score or the priors. Obtain the full
    scored pool via rerank(..., top_k=RERANK_TOP_K, rerank_pool=RERANK_TOP_K).
  - The tool's ONLY writes are eval/runs/<run_id>/analysis/
    hybrid_expansion_stability/{stability_trace.jsonl,
    stability_diagnosis.json,q03_blend_decomposition.json}. It MUST NOT
    modify candidates.jsonl, gold_labels.jsonl, silver_labels.jsonl,
    metrics.json, run_manifest.json, anything under analysis/hybrid_gap/,
    analysis/hybrid_live_trace/, analysis/error_report/, or src/.
  - The --dry-run path MUST NOT import any model module (src.models,
    src.retrieval.semantic/bm25/reranker, src.llm.*): defer those imports
    into the live-trace code path.
  - If any required input file is missing, the precondition check (via
    hybrid_live_trace._prepare_inputs) raises; main() catches
    HybridLiveTraceError, prints to stderr, exits non-zero, writes nothing.

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
HY-STAB-01 handoff in §12.

Suggested order once Gate A is given:

1. **Gate A** — human approves the §12 handoff → Codex implements
   `hybrid_expansion_stability.py` + tests and runs the §8.1 hermetic
   validation.
2. **Gate D** — Claude reviews the 3-file diff and hermetic log against
   the §10 checklist.
3. **Human-run trace** — the human runs §8.2
   (`hybrid_expansion_stability.py --repeat 5`), producing the three
   output files.
4. **Gate E** — Claude summarizes the diagnosis (§9); the human picks a
   §11 branch. Any fix is a **new, separately-gated plan** — not
   implemented or dispatched by HY-STAB-01.

**No ranking, retrieval, fusion, reranker, expansion, or config change is
implemented or dispatched by this plan.**

---

## 14. Self-review against this plan's own constraints

1. **Trace-only; no ranking/retrieval/config change** — §0.2 constraints
   1-4, §0.4 non-goals, §12 criteria 5/6/10/13, and the Codex prompt all
   forbid any behavior change, any `src/*` edit, and any config tuning or
   mutation. ✓
2. **No `src.config` mutation for `no_llm`** — §3.2, §7 point 2, §12
   criterion 6, §10, and the Codex prompt all state the `no_llm` arm
   passes `deterministic_query` and never touches the flag. ✓
3. **Trace-only feasibility proven** — §7 shows the 3 arms are one
   parametrized string, `no_llm` needs no config mutation, `pinned` is a
   cached return value, the q03 decomposition reads attached fields, and
   faithfulness is test-enforced. ✓
4. **Reuses HY-TRACE-01, does not duplicate it** — §12 criterion 2 lists
   the imported helpers; criterion 13 and §10 forbid re-implementation. ✓
5. **Covers all four requested comparisons** — comparison 1 = `live` arm
   (§3.2); comparison 2 = `pinned` arm (§3.2); comparison 3 = `no_llm`
   arm (§3.2, §7.2); comparison 4 = `q03_blend_decomposition.json`
   (§6.3, §12.9). ✓
6. **Exact queries** — §3.1 traces exactly the 8 `hybrid_attributable`
   qids via `_prepare_inputs`; q12/q13 excluded. ✓
7. **Separates variance from fixed defect** — the `instability_attribution`
   logic (§6.2) and the §9 interpretation map each target to
   `fixed_defect` / `expansion_dependent` / `expansion_variance_only` /
   `stable_hit` / `inconclusive`; `fixed_defect` keys on the LLM-free
   `no_llm` control, so an expansion-rescued target is not mislabelled. ✓
8. **Gates A / D / E defined** — §0.5 gate map, §10 Gate D checklist,
   §11 Gate E decision tree, §13 stop-for-Gate-A. ✓
9. **Expected outputs and validation commands** — §6 schemas, §8.1
   hermetic + §8.2 human-run commands with expected results. ✓
10. **Codex-ready ticket** — §12 has all 9 `CLAUDE.md` handoff fields. ✓
11. **Produces evidence, not a fix** — §11 drafts only *separate* plans;
    §13 pre-commits to none; the §12.9 prompt is plan text, not an
    invocation. No ranking fix proposed. ✓
12. **Honest about limits** — §0.3 discloses the live arm's
    non-determinism, the pool-normalized priors, the Ollama / GPU
    requirement, and the `movie_key` identity. ✓
13. **No git commands** — none in any validation block (no-git mode). ✓
```

---

## 15. Gate A — awaiting approval

**Status:** DRAFT. Planning only. Nothing implemented; no Codex call made.
The plan stops here until the human approves the §12 handoff (**Gate A**).

*(Superseded — Gate A was approved 2026-05-22. See §16.)*

---

## 16. Gate E record (2026-05-22)

HY-STAB-01 ran the full gate sequence: **Gate A** approved (2026-05-22) →
Codex implemented the 3 files (115 → 129 tests, +14) → **Gate D PASSED**
(Claude review, 2026-05-22 — matches spec, no blockers; `src/` verified
untouched) → **human-run §8.2 live trace** (2026-05-22, `--repeat 5`, 3
arms, Ollama CPU-only) → **Gate E**. Outputs:
`analysis/hybrid_expansion_stability/{stability_trace.jsonl,
stability_diagnosis.json, q03_blend_decomposition.json}`.

### 16.1 Result

- **S5 confirmed.** `live` is non-deterministic; `pinned` and `no_llm` are
  each fully stable — no second non-deterministic element exists beyond
  `expand_query`.
- `attribution_summary`: **`fixed_defect` 4**, `expansion_dependent` 1,
  `expansion_variance_only` 2, `stable_hit` 1, `inconclusive` 0.
- `dominant_finding`: **`mixed`**.

### 16.2 Per-target

| qid | target | attribution | `pinned` | `no_llm` |
|---|---|---|---|---|
| q03 | WALL·E | expansion_variance_only | hybrid_top5_hit | hybrid_top5_hit |
| q04 | Teen Witch | expansion_variance_only | hybrid_top5_hit | hybrid_top5_hit |
| q05 | Thanatomorphose | **fixed_defect** | retrieved_dropped_before_rerank_pool | rerank_recovered_final_demoted |
| q06 | American Hero | expansion_dependent | rerank_recovered_final_demoted | hybrid_top5_hit |
| q07 | My Babysitter's a Vampire | **fixed_defect** | rerank_demoted | rerank_demoted |
| q08 | Everything Everywhere All at Once | **fixed_defect** | retrieved_dropped_before_rerank_pool | retrieved_dropped_before_rerank_pool |
| q10 | [REC] | **fixed_defect** | retrieved_dropped_before_rerank_pool | rerank_demoted |
| q18 | You've Got Mail | stable_hit | — | — |

### 16.3 Gate E decision

Per §11, the result satisfies **branch 3 — Mixed** (`fixed_defect = 4 ≥ 2`
**and** `expansion_total = expansion_variance_only 2 + expansion_dependent
1 = 3 ≥ 2`); `dominant_finding = mixed` confirms it. §11 branch 3 directs
two separate scoped plans, larger cluster first. The larger cluster is the
**4 fixed defects** (`q05 q07 q08 q10`); the expansion cluster (q03/q04
variance, q06 dependent) is the smaller, deferred one. q18 is not a defect.

**Decision (human, 2026-05-22):** localize and explain the fixed-defect
cluster **before** any `src/*` fix. → new analysis-first plan
**HY-FIX-01** (`docs/superpowers/plans/2026-05-22-hy-fix-01-fixed-defect-
localization.md`), priority `q08` then `q07`. The expansion cluster is a
separate later plan. **No fix dispatched by HY-STAB-01.**

HY-STAB-01 is preserved as the evidence base for HY-FIX-01.
