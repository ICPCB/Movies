---
title: HY-FIX-01 — Fixed-defect localization (analysis-first)
date: 2026-05-22
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one analysis ticket, human-approved before dispatch)
human: approves dispatch (Gate A); accepts the localization and picks the fix direction (Gate E)
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 05-metrics-qc-and-labels.md
parent_run: eval/runs/2026-05-19-1846-nogit
parent_plan: docs/superpowers/plans/2026-05-21-hy-stab-01-hybrid-expansion-instability-trace.md
parent_diagnosis: eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_diagnosis.json
git_mode: no_git
status: DRAFT — awaiting Gate A. Planning only. Nothing implemented, no Codex call made.
---

# HY-FIX-01 — Fixed-Defect Localization (analysis-first)

> **For agentic workers:** This plan is executed by **Codex CLI** for one
> analysis ticket (HY-FIX-01), with explicit human approval before the
> Codex prompt is sent. Claude Code Pro reviews the diff and the validation
> log. **This plan is analysis-only. Its single in-scope ticket makes no
> `src/*` edits, runs no model, and changes no behavior.** It adds one
> read-only `eval/` script that aggregates the *already-produced*
> HY-STAB-01 trace outputs into per-stage rank/score tables. **No fix is
> designed or dispatched by this plan** — a fix is a separate,
> separately-gated plan drafted only after HY-FIX-01's Gate E. The ticket
> uses the 9-field Codex handoff format from `CLAUDE.md`.

**This plan is the gated follow-on to HY-STAB-01.** HY-STAB-01's Gate E
(2026-05-22) found `dominant_finding = mixed`: of the 8 hybrid-attributable
targets, **4 are `fixed_defect`** — `q05 q07 q08 q10` — i.e. they fail even
with a fixed retrieval query, independent of LLM-expansion variance. Per
HY-STAB-01 §11 branch 3, the larger cluster (the 4 fixed defects) is
addressed first, and the human directed that they be **localized and
explained before any `src/*` fix is proposed**. HY-FIX-01 is that
localization.

**Goal (one sentence):** Build one read-only Codex tool,
`hy_fix_localize.py`, that consumes HY-STAB-01's `stability_trace.jsonl` +
`stability_diagnosis.json` and produces, for each of the 4 `fixed_defect`
targets (`q05 q07 q08 q10`, priority `q08` then `q07`), a per-stage
rank/score table per arm plus a deterministic loss-stage and fix-category —
so the human can decide **which stage the next fix must target** (recall
depth / fusion / rerank pool, reranker scoring, final blend, or — out of
scope here — LLM-expansion stability) **without editing `src/*`, running a
model, or proposing a fix**.

**Architecture:** A single read-only diagnostic tool under
`eval/scripts/`. It reads two JSON artifacts HY-STAB-01 already wrote,
re-tabulates the gold target's per-stage ranks/scores, maps each
deterministic-arm `loss_classification` to a fix category, and writes one
`localization.json`. It imports **no** `src` module and runs **no** model —
the entire ticket, including its real run, is hermetic.

**Tech stack:** Python 3.11+, stdlib only (`json`, `pathlib`, `argparse`,
`sys`, `statistics`, `datetime`). Imports `eval.scripts._run_io` for path
resolution and atomic writes. No new dependency. No `src` import.

---

## 0. Scope, gates, and hard constraints

### 0.1 What HY-FIX-01 is

One **analysis-only** Codex ticket. It produces evidence that *localizes*
the 4 fixed defects to a pipeline stage and a fix category. It does **not**
fix anything and does **not** design a fix. Per `CLAUDE.md`, Claude plans
and reviews; Codex implements; the human approves each gate.

It answers exactly one question HY-STAB-01 left open:

> For each of the 4 `fixed_defect` targets, **which pipeline stage** loses
> it, and therefore **which category of fix** the next plan must target?

### 0.2 Hard constraints (binding on the ticket and every step)

1. **Analysis-only. No fix.** No edit to retrieval, BM25, RRF, fusion,
   reranker, embedding, query-expansion, blend, or any `src/*` / `app.py` /
   recommender-runtime / config code. A fix is a **separate,
   separately-gated plan** drafted only after this plan's Gate E.
2. **No `src/*` edits and no `src` import.** The tool is pure JSON
   aggregation; it neither imports nor mutates any `src` module or
   `src.config`.
3. **No models, no Ollama, no network.** The tool reads finished JSON
   artifacts. The *entire* ticket — including the real run — is hermetic.
4. **Reuse existing trace outputs.** The only inputs are HY-STAB-01's
   `stability_trace.jsonl` and `stability_diagnosis.json`. The tool does
   **not** re-run the pipeline.
5. **No re-implementation of ranking logic.** The tool re-uses the
   `loss_classification` HY-STAB-01 already computed; it does not
   re-classify, re-rank, or re-score anything.
6. **Preserve HY-STAB-01.** Its three output files are read-only inputs;
   none is modified.
7. **Same 4 targets.** Exactly the `fixed_defect` qids `q05 q07 q08 q10`,
   read at runtime from `stability_diagnosis.json`. q03/q04/q06/q18 are
   **not** localized here — q03/q04 (`expansion_variance_only`) and q06
   (`expansion_dependent`) belong to a separate deferred expansion plan;
   q18 is `stable_hit` (not a defect).
8. **No broad refactor.** One new script, one new test file, one one-line
   README edit. Nothing else.

### 0.3 Honest caveats

- **Localization, not full fix-design.** The tool pinpoints the *stage* and
  *category* of each loss from the gold target's own per-stage ranks. For
  targets lost **inside** the cross-encoder pool (`reranker_scoring`,
  `final_blend`), explaining *why the competitors outrank it* needs the
  full 50-candidate rerank pool, which `stability_trace.jsonl` does **not**
  carry (only `q03_blend_decomposition.json` has a pool, and q03 is not a
  fixed defect). HY-FIX-01 deliberately stops at category assignment; the
  competitor-level decomposition is the first ticket of the *fix* plan
  (§7), reusing HY-STAB-01's `_decompose_pool`.
- **Deterministic arms are the localization basis.** `fixed_defect` is
  defined on the `pinned` and `no_llm` arms. HY-STAB-01 confirmed both are
  byte-stable (S5). The tool asserts that determinism (all repeats of a
  `pinned`/`no_llm` (qid,target) identical) and localizes on repeat 0. The
  `live` arm is non-deterministic and is reported only as a compact
  per-repeat summary, never as the localization basis.
- **`mixed` is a real outcome.** When a target's `pinned` and `no_llm` arms
  localize to different stages (q05, q10), the tool labels it `mixed` and
  records both. §7 says how to sequence a mixed target.

### 0.4 Non-goals (explicit deferrals)

- **Any `src/*`, `app.py`, or config change**, and any fix design. A fix is
  its own separately-gated plan (§7, §9).
- **Re-running the hybrid pipeline / loading models.** HY-FIX-01 consumes
  finished artifacts only.
- **The competitor-level rerank-pool decomposition** for q05/q07/q10 — that
  is the fix plan's first ticket, not this one.
- **The expansion cluster** (q03, q04, q06). Separate deferred plan.
- **Editing HY-STAB-01 / HY-TRACE-01 tooling or their outputs.**
- A markdown narrative report — the decision is made from
  `localization.json` at Gate E.

### 0.5 Gate map

| Gate | When | Who | What |
|---|---|---|---|
| **A — Dispatch approval** | Before the HY-FIX-01 Codex prompt is sent | Human | Approves the §10 handoff. Per `CLAUDE.md`, Claude does **not** auto-dispatch Codex. **This plan stops at Gate A.** |
| **D — Claude review** | After Codex finishes the tool + validation | Claude | Reviews the 3-file diff vs §3 and the §6 validation log (incl. the produced `localization.json`) against the §8 checklist. Reports matches / deviations / blockers. |
| **E — Human accept + fix-direction decision** | After Gate D | Human + Claude | Claude summarizes `localization.json` (§7). Human picks a §9 branch → a **new, separately-gated fix plan**. HY-FIX-01 pre-commits to no fix. |

There is **no human-run step** — the tool is hermetic, so Codex produces
`localization.json` during validation and Claude reviews it at Gate D.

---

## 1. Current evidence — HY-STAB-01 Gate E (2026-05-22)

Read from
`eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_diagnosis.json`
(HY-STAB-01, `--repeat 5`, 3 arms, S5 confirmed: `live` non-deterministic,
`pinned` and `no_llm` both stable).

- `attribution_summary`: **`fixed_defect` 4**, `expansion_dependent` 1,
  `expansion_variance_only` 2, `stable_hit` 1, `inconclusive` 0.
- `dominant_finding`: **`mixed`**.

| qid | gold target | attribution | `pinned` loss | `no_llm` loss |
|---|---|---|---|---|
| q03 | WALL·E | expansion_variance_only | hybrid_top5_hit | hybrid_top5_hit |
| q04 | Teen Witch | expansion_variance_only | hybrid_top5_hit | hybrid_top5_hit |
| **q05** | **Thanatomorphose** | **fixed_defect** | retrieved_dropped_before_rerank_pool | rerank_recovered_final_demoted |
| q06 | American Hero | expansion_dependent | rerank_recovered_final_demoted | hybrid_top5_hit |
| **q07** | **My Babysitter's a Vampire** | **fixed_defect** | rerank_demoted | rerank_demoted |
| **q08** | **Everything Everywhere All at Once** | **fixed_defect** | retrieved_dropped_before_rerank_pool | retrieved_dropped_before_rerank_pool |
| **q10** | **[REC]** | **fixed_defect** | retrieved_dropped_before_rerank_pool | rerank_demoted |
| q18 | You've Got Mail | stable_hit | — | — |

**The 4 fixed defects, coarse read (to be confirmed by HY-FIX-01):**

- **q08** — `retrieved_dropped_before_rerank_pool` in **both** arms. The
  cleanest **recall-depth / rerank-pool** failure: the target reaches RRF
  but ranks below the `RERANK_TOP_K = 50` cut, so the cross-encoder never
  scores it.
- **q07** — `rerank_demoted` in **both** arms. The cleanest **reranker
  scoring** failure: the target enters the pool but the cross-encoder ranks
  it ≥ 5.
- **q05** — **mixed**: `pinned` = pool-cutoff (recall depth), `no_llm` =
  `rerank_recovered_final_demoted` (final blend).
- **q10** — **mixed**: `pinned` = pool-cutoff (recall depth), `no_llm` =
  `rerank_demoted` (reranker).

HY-STAB-01 already grouped these; HY-FIX-01 confirms each with the actual
per-stage rank/score numbers and assigns the fix category deterministically.

---

## 2. The 4 targets, hypotheses, and priority

HY-FIX-01 localizes **exactly** the 4 `fixed_defect` qids, read at runtime
from `stability_diagnosis.json` (`instability_attribution` entries with
`attribution == "fixed_defect"`) and asserted to equal the documented
constant `FIXED_DEFECT_QIDS = ("q05","q07","q08","q10")` — a mismatch is a
hard error.

**Per-target hypotheses the localization confirms or refutes:**

- **H-q08 — recall depth / rerank-pool cutoff.** Both deterministic arms
  show the target present in `semantic`/`bm25`/`rrf` but `rerank.in_pool =
  false`. *Confirmed if* the `rrf.rank` ≥ `RERANK_TOP_K` in both arms.
- **H-q07 — reranker scoring.** Both arms show `rerank.in_pool = true` with
  `rerank.rerank_rank ≥ 5`. *Confirmed if* so in both arms.
- **H-q05 — mixed (recall-depth + final-blend).** `pinned` =
  pool-cutoff; `no_llm` = `final_rank ≥ 5` with `rerank_rank < 5`.
- **H-q10 — mixed (recall-depth + reranker).** `pinned` = pool-cutoff;
  `no_llm` = `rerank_rank ≥ 5`.

**Priority — `q08` then `q07`, then `q05`, `q10`.** Rationale: q08 and q07
are *clean single-mechanism* defects (both deterministic arms agree), so
they are unambiguous to scope; q05 and q10 are `mixed`. The documented
constant is `PRIORITY_ORDER = ("q08","q07","q05","q10")`.

---

## 3. Allowed and forbidden files

### 3.1 Allowed (HY-FIX-01 may create/modify only these three)

- **Create:** `eval/scripts/hy_fix_localize.py`
- **Create:** `eval/tests/test_hy_fix_localize.py`
- **Modify (one line — add `hy_fix_localize.py` to the `scripts/` block of
  the Layout fence):** `eval/README.md`

### 3.2 Inputs (read-only — the tool must never write these)

- `eval/runs/<run_id>/analysis/hybrid_expansion_stability/stability_trace.jsonl`
- `eval/runs/<run_id>/analysis/hybrid_expansion_stability/stability_diagnosis.json`
- `eval.scripts._run_io` — imported as a library for path resolution and
  atomic writes, never edited.

### 3.3 Output (the tool's only write)

- `eval/runs/<run_id>/analysis/hy_fix_localize/localization.json`

The directory is created with `mkdir(parents=True, exist_ok=True)`; the
file is written atomically via `_run_io._atomic_write_json`.

### 3.4 Forbidden (the tool must never create or modify any of these)

- **Anything under `src/`**, `app.py`, any recommender-runtime module.
- `candidates.jsonl`, `gold_labels.jsonl`, `silver_labels.jsonl`,
  `metrics.json`, `run_manifest.json`, `config_snapshot.json`.
- Anything under `analysis/hybrid_expansion_stability/`,
  `analysis/hybrid_live_trace/`, `analysis/hybrid_gap/`, or any other
  existing `analysis/` subdirectory.
- Any existing `eval/scripts/*` module (incl. `hybrid_expansion_stability.py`,
  `hybrid_live_trace.py`, `_run_io.py`) — imported where needed, never
  edited. Any `eval/queries` file.

The tool's **only** write is the one file in §3.3.

---

## 4. Output schema — `localization.json`

```json
{
  "schema_version": "hy-fix-01.v1",
  "run_id": "2026-05-19-1846-nogit",
  "generated_at": "2026-05-22T10:00:00Z",
  "source_artifacts": {
    "stability_trace": "analysis/hybrid_expansion_stability/stability_trace.jsonl",
    "stability_diagnosis": "analysis/hybrid_expansion_stability/stability_diagnosis.json"
  },
  "fixed_defect_qids": ["q05", "q07", "q08", "q10"],
  "priority_order": ["q08", "q07", "q05", "q10"],
  "stage_pipeline": ["semantic", "bm25", "rrf", "rerank", "final"],
  "config": {
    "CANDIDATE_POOL": 1500, "RERANK_POOL": 800,
    "RERANK_TOP_K": 50, "FINAL_TOP_K": 5
  },
  "per_target": [
    {
      "qid": "q08",
      "tmdb_id": 545611,
      "title": "Everything Everywhere All at Once",
      "attribution": "fixed_defect",
      "arms": {
        "pinned": {
          "deterministic": true,
          "stage_table": {
            "semantic": {"present": true,  "rank": 612, "score": 0.50, "list_len": 1500},
            "bm25":     {"present": false, "rank": null, "score": null, "list_len": 1500},
            "rrf":      {"present": true,  "rank": 233, "score": 0.013, "list_len": 800},
            "rerank":   {"in_pool": false, "rerank_score": null, "rerank_rank": null},
            "final":    {"final_score": null, "final_rank": null, "in_top5": false, "in_top15": false}
          },
          "loss_stage": "retrieved_dropped_before_rerank_pool",
          "fix_category": "recall_depth_fusion_pool"
        },
        "no_llm": { "...": "same shape" },
        "live": {
          "deterministic": false,
          "repeats": 5,
          "loss_stage_per_repeat": ["retrieved_dropped_at_fusion", "...", "..."],
          "final_rank_summary": {"min": null, "median": null, "max": null, "n_present": 0}
        }
      },
      "consolidated_fix_category": "recall_depth_fusion_pool",
      "arms_agree": true,
      "notes": "<templated one-line explanation derived from the numbers>"
    }
  ],
  "fix_category_summary": {
    "recall_depth_fusion_pool": 0, "reranker_scoring": 0,
    "final_blend": 0, "mixed": 0, "none": 0, "inconclusive": 0
  },
  "recommended_sequence": ["q08", "q07", "q05", "q10"],
  "recommended_first_fix": "recall_depth_fusion_pool"
}
```

**Field rules:**

- `fixed_defect_qids` — read from `stability_diagnosis.json`
  (`instability_attribution` where `attribution == "fixed_defect"`),
  sorted, asserted equal to `FIXED_DEFECT_QIDS`.
- `config` — read verbatim from `stability_diagnosis.json` →
  `trace_meta.config` (the relevant pool/top-k knobs). Not recomputed.
- `per_target` — one entry per `fixed_defect` target, sorted by `qid`.
- `arms.pinned` / `arms.no_llm` — the deterministic controls. The tool
  collects every `stability_trace.jsonl` row for that `(arm, qid, tmdb_id)`,
  **asserts all repeats are byte-identical** on the `semantic` / `bm25` /
  `rrf` / `rerank` / `final` / `loss_classification` fields (else raise —
  an S5 violation), and emits repeat 0's values as `stage_table` +
  `loss_stage` (= that row's `loss_classification`).
- `arms.live` — non-deterministic; emit `repeats`,
  `loss_stage_per_repeat` (the `loss_classification` of each live repeat,
  ordered by `repeat`), and `final_rank_summary`
  (`min`/`median`/`max`/`n_present` over live repeats where
  `final.final_rank` is not null). No `stage_table` for `live`.
- `loss_stage` ∈ the HY-STAB-01 `loss_classification` enum
  (`unretrieved`, `retrieved_dropped_at_fusion`,
  `retrieved_dropped_before_rerank_pool`, `rerank_recovered_final_demoted`,
  `rerank_demoted`, `hybrid_top5_hit`, `other`) — **copied, never
  recomputed**.
- `fix_category` — deterministic map from `loss_stage`:

  | `loss_stage` | `fix_category` |
  |---|---|
  | `unretrieved` | `recall_depth_fusion_pool` |
  | `retrieved_dropped_at_fusion` | `recall_depth_fusion_pool` |
  | `retrieved_dropped_before_rerank_pool` | `recall_depth_fusion_pool` |
  | `rerank_demoted` | `reranker_scoring` |
  | `rerank_recovered_final_demoted` | `final_blend` |
  | `hybrid_top5_hit` | `none` |
  | `other` | `inconclusive` |

- `consolidated_fix_category` — if `pinned.fix_category ==
  no_llm.fix_category`, that value; else the literal `"mixed"`.
  `arms_agree` = the boolean of that equality.
- `notes` — a one-line string built from a per-`loss_stage` template,
  filled with the target's numbers (e.g. for q08: `"q08 reaches RRF at
  rank <rrf.rank>/<RERANK_POOL> in both deterministic arms but the
  cross-encoder pool is the top <RERANK_TOP_K>; lost before reranking."`).
  Templated text only — no new analysis.
- `fix_category_summary` — counts of `consolidated_fix_category` over the 4
  targets; the six keys shown; sums to 4.
- `recommended_sequence` — the `fixed_defect` qids ordered: clean
  (`arms_agree == true`) targets first, ordered upstream→downstream by
  `consolidated_fix_category` (`recall_depth_fusion_pool` → `reranker_scoring`
  → `final_blend`), then `mixed` targets ordered by `qid`. With the current
  evidence this yields `["q08","q07","q05","q10"]` = `PRIORITY_ORDER`; the
  tool asserts the two agree.
- `recommended_first_fix` — the `consolidated_fix_category` of
  `recommended_sequence[0]`. Best-effort; the human decides at Gate E.

---

## 5. Why a read-only script suffices

1. **Everything needed is already on disk.** `stability_trace.jsonl`
   carries, for every `(arm, qid, target, repeat)`, the gold target's
   `semantic` / `bm25` / `rrf` / `rerank` / `final` rank+score blocks and
   the `loss_classification`. The per-stage table is a *projection* of that
   file; no pipeline run is needed.
2. **The classification is reused, not recomputed.** `loss_stage` is copied
   verbatim from HY-STAB-01's `loss_classification` (itself produced by the
   Gate-D-reviewed `classify_loss`). HY-FIX-01 adds only a static
   `loss_stage → fix_category` lookup (§4) — a table, not ranking logic.
3. **No `src` import.** The tool needs no model, no retrieval function, no
   `src.config`. It imports only `eval.scripts._run_io` (paths + atomic
   write). The entire ticket — including the real run — is hermetic, so
   Codex produces `localization.json` during validation and there is no
   human-run step.
4. **The competitor-level "why" is deliberately out of scope.** Explaining
   *which* candidates outrank a pool-resident target needs the 50-member
   rerank pool, which lives only in `q03_blend_decomposition.json` (q03 is
   not a fixed defect). Generalizing that decomposition to q05/q07/q10 is
   the **fix plan's** first ticket (§7) — it reuses HY-STAB-01's
   `_decompose_pool` and is separately gated.

---

## 6. Validation commands

The whole ticket is hermetic — Codex runs all of §6; Claude re-runs it at
Gate D.

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hy_fix_localize --run 2026-05-19-1846-nogit
python -c "import json,pathlib; d=json.loads(pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json').read_text(encoding='utf-8')); pt=d['per_target']; assert [t['qid'] for t in pt]==['q05','q07','q08','q10']; assert sum(d['fix_category_summary'].values())==4; print('localization ok'); [print(t['qid'], t['consolidated_fix_category'], '| pinned:', t['arms']['pinned']['loss_stage'], '| no_llm:', t['arms']['no_llm']['loss_stage']) for t in pt]; print('recommended_first_fix:', d['recommended_first_fix'])"
```

Expected:

1. `compileall` reports `Listing ... OK`.
2. All tests pass; the count is `previous + N`. Baseline is **129** from
   HY-STAB-01; HY-FIX-01 adds at least 10 → expect **≥ 139**. Codex reports
   the exact before/after counts.
3. The real run exits 0 and writes
   `analysis/hy_fix_localize/localization.json` — covering exactly
   `q05 q07 q08 q10`, `fix_category_summary` summing to 4.
4. The one-liner prints each target's `consolidated_fix_category` and
   per-arm `loss_stage`, and `recommended_first_fix`. The **specific**
   categories are the diagnostic result — they are not pre-asserted; Claude
   summarizes them at Gate E.

---

## 7. Decision rules — interpreting `localization.json`

After Gate D, Claude summarizes `localization.json`; the human uses the
rules below to choose the next fix plan. **HY-FIX-01 drafts no fix.**

### 7.1 Per-target rule — which category a target's fix belongs to

For each `fixed_defect` target, read `consolidated_fix_category`:

| `consolidated_fix_category` | the next fix for that target targets… |
|---|---|
| `recall_depth_fusion_pool` | retrieval depth (`CANDIDATE_POOL`), RRF fusion ranking, and/or the `RERANK_TOP_K = 50` rerank-pool cutoff — the target never reaches the cross-encoder |
| `reranker_scoring` | the cross-encoder stage — the target is scored by the reranker but ranked ≥ 5. The lever is the document/query form fed to the cross-encoder, **not** a config weight |
| `final_blend` | the `RERANK_VOTE_COUNT_WEIGHT` / `RERANK_UPSTREAM_WEIGHT` / `RERANK_SOURCE_AGREEMENT_BONUS` blend — the cross-encoder ranks it top-5 but the blend re-demotes it |
| `mixed` | the target fails at **different** stages under the two deterministic queries. **Fix the upstream stage first** — a downstream fix (reranker/blend) cannot help a target that never reaches the pool. Re-trace after the upstream fix to see whether the downstream mechanism still bites |
| `none` / `inconclusive` | contradicts HY-STAB-01 — **stop**, do not fix, re-trace (see §9 branch 4) |

### 7.2 Cross-target rule — which fix plan to draft first

1. **Sequence clean targets before mixed ones, upstream before
   downstream.** `recommended_sequence` already encodes this.
2. **The first fix plan targets `recommended_first_fix`.** With the current
   evidence that is `recall_depth_fusion_pool` (q08, and the `pinned`-arm
   mechanism shared by q05 and q10) — so the first fix plan is a
   **retrieval-depth / fusion / rerank-pool plan**, and it also unblocks
   the upstream half of q05 and q10.
3. **The second fix plan targets the next clean category** —
   `reranker_scoring` (q07, and q10's `no_llm` mechanism).
4. **Re-trace between fix plans.** After the recall/pool fix, re-run
   HY-STAB-01 on q05/q08/q10; a target that now reaches the pool may reveal
   a residual `reranker_scoring` or `final_blend` defect, or may resolve.
5. **Every fix plan is itself analysis-first.** Its **first ticket** is a
   read-only **rerank-pool decomposition** for its targets — reuse
   HY-STAB-01's `_decompose_pool` to dump the 50-candidate
   `rerank_score` / blend-component table (this needs one human-run model
   pass, separately gated) — *before* any `src/*` change ticket. No weight
   or config is changed without the competitor evidence in hand.
6. **LLM-expansion stability is out of scope for the fixed defects.** By
   construction a `fixed_defect` fails with a *fixed* query, so an
   expansion fix cannot help it. The expansion cluster (q03/q04
   `expansion_variance_only`, q06 `expansion_dependent`) is a **separate
   deferred plan** — choose that path only for those qids, never for
   `q05 q07 q08 q10`.

### 7.3 Decision axis summary

`recall_depth_fusion_pool` vs `reranker_scoring` vs `final_blend` is the
axis. Upstream losses (recall/fusion/pool) are **prerequisite** — fix them
first; downstream losses (reranker, blend) are only meaningfully fixable
for targets that reach the cross-encoder. `mixed` targets are sequenced by
their upstream half.

---

## 8. Gate D review checklist (Claude, after Codex finishes)

Report findings as **matches spec / deviations / blockers**, in that order.

- [ ] **Scope:** the diff touches **exactly** the 3 files in §3.1 —
      `hy_fix_localize.py`, `test_hy_fix_localize.py`, one line of
      `eval/README.md` — nothing else.
- [ ] **No `src/` edit and no `src` import:** no file under `src/` is
      created or modified; the tool imports no `src` module.
- [ ] **No models / no network:** the tool imports no model module, calls
      no Ollama, opens no socket — verified hermetic.
- [ ] **Reuse, not recompute:** `loss_stage` is copied verbatim from
      `stability_trace.jsonl`'s `loss_classification`; the tool
      re-classifies / re-ranks / re-scores nothing. `fix_category` is the
      static §4 lookup.
- [ ] **Inputs read-only:** only `stability_trace.jsonl` and
      `stability_diagnosis.json` are read; neither (nor any other existing
      artifact) is modified.
- [ ] **Targets:** `fixed_defect_qids` are read from
      `stability_diagnosis.json` and asserted equal to
      `("q05","q07","q08","q10")`; a mismatch raises.
- [ ] **Determinism assertion:** for each `pinned` / `no_llm`
      `(qid,target)` the tool asserts all repeats are byte-identical and
      raises otherwise.
- [ ] **Output scope:** the tool's only write is
      `analysis/hy_fix_localize/localization.json`; the write is atomic;
      the directory is `mkdir(parents=True, exist_ok=True)`.
- [ ] **Preconditions:** a missing input raises a `HyFixLocalizeError`
      (`ValueError` subclass), exits non-zero, writes nothing.
- [ ] **Validation:** §6 ran — `compileall` OK, unit count ≥ 139, the real
      run exits 0 and wrote a `localization.json` whose `per_target` covers
      `q05 q07 q08 q10` and whose `fix_category_summary` sums to 4.
- [ ] **Schema:** `localization.json` matches §4 exactly (keys, the
      `loss_stage → fix_category` map, `consolidated_fix_category` rule,
      `recommended_sequence` rule).

If all pass: Gate D is green → Gate E (§9). Any blocker stops the plan for
a fix before Gate E.

---

## 9. Gate E decision tree (human, after Gate D)

Claude summarizes `localization.json`; the human picks **exactly one**
branch. Let `S = fix_category_summary` over the 4 targets.

1. **Recall/pool is the lead mechanism** — `recommended_first_fix ==
   "recall_depth_fusion_pool"` (the expected outcome — q08 clean, plus the
   `pinned` half of q05 and q10):
   → **Draft a separate, separately-gated retrieval-depth / fusion /
   rerank-pool fix plan**, analysis-first (its first ticket = the
   rerank-pool decomposition per §7.2 rule 5). Then draft the
   `reranker_scoring` plan for q07. Not dispatched here.

2. **Reranker scoring is the lead mechanism** — `recommended_first_fix ==
   "reranker_scoring"`:
   → **Draft a separate, separately-gated reranker-scoring fix plan**,
   analysis-first. Sequence the remaining categories after. Not dispatched
   here.

3. **Final-blend is the lead mechanism** — `recommended_first_fix ==
   "final_blend"`:
   → **Draft a separate, separately-gated final-score-blend fix plan**,
   analysis-first, scoped to the `RERANK_*_WEIGHT` blend and gated on a
   paired-bootstrap eval showing no regression. Not dispatched here.

4. **Inconclusive** — any target's `consolidated_fix_category` is `none` or
   `inconclusive` (the localization contradicts HY-STAB-01's
   `fixed_defect`), **or** a determinism assertion failed:
   → **Stop. Re-trace, do not fix.** A `fixed_defect` target that
   localizes to `none`/`inconclusive`, or a control arm that is not
   byte-stable, means the evidence is inconsistent — resolve that before
   any fix.

This plan **pre-commits to no branch and no fix.** Its sole product is the
evidence in `localization.json`.

---

## 10. Ticket HY-FIX-01 — Codex-ready handoff

### 1. Goal

Build `eval/scripts/hy_fix_localize.py`: a read-only analysis tool that
consumes HY-STAB-01's `stability_trace.jsonl` + `stability_diagnosis.json`
and writes `analysis/hy_fix_localize/localization.json` — a per-stage
rank/score table per arm, a per-arm `loss_stage` + `fix_category`, and a
`consolidated_fix_category` for each of the 4 `fixed_defect` targets
(`q05 q07 q08 q10`). Analysis-only: imports no `src` module, runs no model,
proposes no fix.

### 2. Files to change

- Create: `eval/scripts/hy_fix_localize.py`
- Create: `eval/tests/test_hy_fix_localize.py`
- Modify (one line): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py` (imported as a library).
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_trace.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_diagnosis.json`

### 4. Acceptance criteria

1. **CLI:** `python -m eval.scripts.hy_fix_localize [--run RUN_ID]`.
   `--run` defaults to `_run_io.latest_run()`.
2. **Error type:** define `HyFixLocalizeError(ValueError)`. `main()`
   catches it, prints to `stderr`, returns non-zero, writes nothing.
3. **Preconditions:** if `<run>/analysis/hybrid_expansion_stability/
   stability_trace.jsonl` or `.../stability_diagnosis.json` is missing,
   raise `HyFixLocalizeError` and write nothing.
4. **Targets:** read `instability_attribution` from
   `stability_diagnosis.json`; `fixed_defect_qids` = sorted qids whose
   `attribution == "fixed_defect"`; assert it equals the module constant
   `FIXED_DEFECT_QIDS = ("q05","q07","q08","q10")` — mismatch raises
   `HyFixLocalizeError`. `PRIORITY_ORDER = ("q08","q07","q05","q10")` is a
   module constant.
5. **Per-arm stage tables:** for each `fixed_defect` target and each arm
   present in `stability_trace.jsonl`, collect all rows for
   `(arm, qid, tmdb_id)`. For `pinned` / `no_llm`: assert every repeat is
   byte-identical on `semantic` / `bm25` / `rrf` / `rerank` / `final` /
   `loss_classification` (raise `HyFixLocalizeError` if not — an S5
   violation); emit `deterministic: true`, `stage_table` (the five stage
   blocks of repeat 0), `loss_stage` (repeat 0's `loss_classification`),
   `fix_category` (the §4 map). For `live`: emit `deterministic: false`,
   `repeats`, `loss_stage_per_repeat` (ordered by `repeat`), and
   `final_rank_summary` (`min`/`median`/`max` via `statistics.median` over
   live repeats with non-null `final.final_rank`, `n_present`; all `null`
   / 0 if none).
6. **`fix_category` map:** exactly the §4 table. `consolidated_fix_category`
   = `pinned.fix_category` if it equals `no_llm.fix_category`, else
   `"mixed"`; `arms_agree` is that equality.
7. **`notes`:** one templated line per target, selected by the
   `consolidated_fix_category` (or by `loss_stage` for a clean target),
   filled with the target's numbers. Templated text only — no new
   analysis, no ranking logic.
8. **`localization.json`:** exact §4 schema — `schema_version`
   (`"hy-fix-01.v1"`), `run_id`, `generated_at` (UTC, second precision),
   `source_artifacts`, `fixed_defect_qids`, `priority_order`,
   `stage_pipeline` (`["semantic","bm25","rrf","rerank","final"]`),
   `config` (read verbatim from `stability_diagnosis.json` →
   `trace_meta.config`, the keys `CANDIDATE_POOL` / `RERANK_POOL` /
   `RERANK_TOP_K` / `FINAL_TOP_K`), `per_target` (sorted by `qid`),
   `fix_category_summary` (six keys, sums to 4), `recommended_sequence`
   (the §4 rule; assert it equals `PRIORITY_ORDER`), `recommended_first_fix`.
9. **Writes nothing else.** Only `analysis/hy_fix_localize/
   localization.json`; directory via `mkdir(parents=True, exist_ok=True)`;
   file via `_run_io._atomic_write_json`. No file in §3.4 is touched.
10. **CLI output:** print `run_id=`, the output path,
    `fixed_defect_qids=`, `fix_category_summary=`, and
    `recommended_first_fix=`.
11. **No `src` import; no model; no network.** The tool imports only
    stdlib and `eval.scripts._run_io`. It re-implements no ranking,
    retrieval, or classification logic — `loss_stage` is copied from the
    input.
12. **`test_hy_fix_localize.py`** is hermetic (`tempfile.TemporaryDirectory`;
    synthetic `stability_trace.jsonl` + `stability_diagnosis.json`; follow
    `eval/tests/test_hybrid_expansion_stability.py` for the
    `_run_io`-path-swap pattern) and includes at least:
    - `test_fix_category_recall_depth` — `unretrieved`,
      `retrieved_dropped_at_fusion`, and
      `retrieved_dropped_before_rerank_pool` each map to
      `recall_depth_fusion_pool`.
    - `test_fix_category_reranker` — `rerank_demoted` →
      `reranker_scoring`.
    - `test_fix_category_final_blend` — `rerank_recovered_final_demoted` →
      `final_blend`.
    - `test_consolidated_agree` — both arms same category →
      that category, `arms_agree=true`.
    - `test_consolidated_mixed` — `pinned` recall-depth, `no_llm`
      final-blend → `consolidated_fix_category="mixed"`, `arms_agree=false`.
    - `test_deterministic_arm_assertion` — a `pinned` arm whose repeats
      differ → `HyFixLocalizeError`.
    - `test_fixed_defect_qids_mismatch` — a diagnosis whose
      `fixed_defect` set ≠ `FIXED_DEFECT_QIDS` → `HyFixLocalizeError`.
    - `test_live_arm_summary` — live arm emits `loss_stage_per_repeat` and
      `final_rank_summary`.
    - `test_missing_input_exits_nonzero` — a missing `stability_trace.jsonl`
      → non-zero exit, nothing written.
    - `test_localization_schema_and_recommended_sequence` — a full
      synthetic run produces a `localization.json` matching §4, with
      `fix_category_summary` summing to 4 and `recommended_sequence`
      equal to `PRIORITY_ORDER`.

### 5. Validation commands

Run §6 (all hermetic). Report per `AGENTS.md`: files changed, commands
run, before/after test counts, any failures verbatim, the real-run stdout,
and any assumptions.

### 6. Dependencies

- HY-STAB-01 — `analysis/hybrid_expansion_stability/stability_trace.jsonl`
  and `stability_diagnosis.json` must exist (satisfied; HY-STAB-01
  complete, Gate E 2026-05-22).
- `eval.scripts._run_io` (satisfied).

### 7. Risk level

**Low.** Three-file change; one new read-only `eval/` tool that imports no
`src` module and runs no model. The real risks are (a) writing outside
`analysis/hy_fix_localize/`, (b) recomputing a classification instead of
copying `loss_classification`, or (c) localizing on the non-deterministic
`live` arm. Acceptance criteria 5/6/9/11, the §3.4 forbidden list, atomic
writes, and the determinism assertion close all three.

### 8. Reviewer

Claude Code Pro, per the §8 Gate D checklist. Specifically verifies: the
diff touches exactly the 3 files; no `src/*` edited and no `src` imported;
`loss_stage` is copied not recomputed; the tool's only write is
`localization.json`; the determinism assertion exists; the validation
produced a schema-correct `localization.json`. Claude then signs off Gate
D and summarizes `localization.json` for the Gate E decision.

### 9. Codex prompt (planning artifact — NOT dispatched by this plan)

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket HY-FIX-01 exactly as specified in
docs/superpowers/plans/2026-05-22-hy-fix-01-fixed-defect-localization.md
section 10 ("Ticket HY-FIX-01 -- Codex-ready handoff"), with the output
schema in section 4.

You may edit ONLY:
  - eval/scripts/hy_fix_localize.py        (create)
  - eval/tests/test_hy_fix_localize.py     (create)
  - eval/README.md                         (add ONE line: hy_fix_localize.py
                                            in the scripts/ block of the
                                            Layout fence)

Do not edit any other file. No src/* edits. No edits to any existing eval
script. Do not run pip installs. Do not run any git command.

HARD CONSTRAINTS:
  - ANALYSIS-ONLY. The tool reads finished JSON artifacts and writes one
    JSON. It MUST NOT change, re-implement, or tune any ranking / retrieval
    / reranker / blend / config logic, and MUST NOT propose a fix.
  - It MUST NOT import any src module and MUST NOT load any model or call
    Ollama or the network. It imports only stdlib and eval.scripts._run_io.
  - loss_stage MUST be copied verbatim from each stability_trace.jsonl
    row's loss_classification. Do NOT re-classify, re-rank, or re-score.
    fix_category is the static loss_stage -> fix_category table in
    section 4.
  - Inputs (read-only): stability_trace.jsonl and stability_diagnosis.json
    under eval/runs/<run_id>/analysis/hybrid_expansion_stability/. The tool
    MUST NOT modify them or any other existing artifact.
  - The tool's ONLY write is eval/runs/<run_id>/analysis/hy_fix_localize/
    localization.json (atomic via _run_io._atomic_write_json; directory via
    mkdir(parents=True, exist_ok=True)).
  - The 4 fixed_defect qids are read from stability_diagnosis.json
    (instability_attribution, attribution == "fixed_defect") and asserted
    to equal ("q05","q07","q08","q10"). Localize on the deterministic
    pinned/no_llm arms; assert their repeats are byte-identical; the live
    arm is reported only as a per-repeat summary.
  - If a required input file is missing, raise HyFixLocalizeError (a
    ValueError subclass), exit non-zero, write nothing.

Acceptance criteria 1-12 in section 10 are all required. Run the full
validation in section 6 (compileall, unittest discover, the real run, and
the one-liner) -- it is all hermetic (no models). Report back per AGENTS.md
(files changed, commands run, before/after test counts, failures verbatim,
the real-run stdout, and any assumptions).
```

---

## 11. Stop for Gate A approval

Per `CLAUDE.md` autonomy boundaries, Claude does **not** dispatch Codex
automatically. **This plan stops here.** Nothing is implemented and no
Codex call is made until the human gives **Gate A** approval for the
HY-FIX-01 handoff in §10.

Suggested order once Gate A is given:

1. **Gate A** — human approves the §10 handoff → Codex implements
   `hy_fix_localize.py` + tests and runs the §6 validation (all hermetic).
2. **Gate D** — Claude reviews the 3-file diff and the produced
   `localization.json` against the §8 checklist.
3. **Gate E** — Claude summarizes `localization.json` (§7); the human
   picks a §9 branch. The chosen fix is a **new, separately-gated plan**
   (itself analysis-first per §7.2 rule 5) — not implemented or dispatched
   by HY-FIX-01.

**No ranking, retrieval, fusion, reranker, blend, or config change is
implemented or dispatched by this plan.**

---

## 12. Self-review against this plan's own constraints

1. **Analysis-only; no fix; no `src/*` edit** — §0.2 constraints 1-2, §0.4
   non-goals, §10 criteria 9/11, and the Codex prompt all forbid any fix,
   any `src/*` edit, and any `src` import. ✓
2. **Reuses existing outputs; no model run** — §0.2.3-4, §5; the tool
   consumes `stability_trace.jsonl` + `stability_diagnosis.json` only. ✓
3. **No re-implementation of ranking logic** — §0.2.5, §10 criterion 11;
   `loss_stage` is copied, `fix_category` is a static table. ✓
4. **Preserves HY-STAB-01** — §3.2/§3.4: its outputs are read-only inputs;
   the tool writes only `analysis/hy_fix_localize/localization.json`. ✓
5. **Localizes the 4 fixed defects** — §2, §4 `per_target`; q05/q07/q08/q10
   read from `stability_diagnosis.json`, q03/q04/q06/q18 excluded. ✓
6. **Priority q08 then q07** — §2 `PRIORITY_ORDER`, §4
   `recommended_sequence` rule (clean-first, upstream→downstream). ✓
7. **Per-stage rank/score tables delivered** — §4 `stage_table` per arm
   (semantic/bm25/rrf/rerank/final rank+score). ✓
8. **Output schema + validation commands** — §4 schema, §6 commands with
   expected results. ✓
9. **Decision rules delivered** — §7 (per-target + cross-target +
   stop rules) and §9 Gate E tree map the localization to one of recall
   depth/fusion/rerank pool, reranker scoring, final blend, or (deferred)
   LLM-expansion stability. ✓
10. **Gates A / D / E defined** — §0.5 gate map, §8 checklist, §9 tree,
    §11 stop-for-Gate-A. ✓
11. **Codex-ready ticket** — §10 has all 9 `CLAUDE.md` handoff fields. ✓
12. **No git commands** — none in any validation block (no-git mode). ✓

---

## 13. Gate A — awaiting approval

**Status:** DRAFT. Planning only. Nothing implemented; no Codex call made.
The plan stops here until the human approves the §10 handoff (**Gate A**).
