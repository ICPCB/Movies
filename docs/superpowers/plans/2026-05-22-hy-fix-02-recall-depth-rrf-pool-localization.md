---
title: HY-FIX-02 — Recall-depth / RRF-fusion / rerank-pool localization (q08), analysis-first
date: 2026-05-22
owner: Claude Code Pro (plan owner, reviewer)
implementer: Codex CLI (one analysis ticket, human-approved before dispatch)
human: approves dispatch (Gate A); runs the q08 RRF-pool trace; accepts it and picks the recall/pool lever (Gate E)
spec_root: docs/superpowers/specs/accuracy-audit/
spec_files_used:
  - 05-metrics-qc-and-labels.md
parent_run: eval/runs/2026-05-19-1846-nogit
parent_plan: docs/superpowers/plans/2026-05-22-hy-fix-01-fixed-defect-localization.md
parent_diagnosis: eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json
git_mode: no_git
status: DRAFT — awaiting Gate A. Planning only. Nothing implemented, no Codex call made.
---

# HY-FIX-02 — Recall-Depth / RRF-Fusion / Rerank-Pool Localization (q08), analysis-first

> **For agentic workers:** This plan is executed by **Codex CLI** for one
> analysis ticket (HY-FIX-02), with explicit human approval before the
> Codex prompt is sent. Claude Code Pro reviews the diff and the validation
> log. **This plan is analysis-only. Its single in-scope ticket makes no
> `src/*` edits and changes no behavior.** It adds one diagnostic `eval/`
> tool that re-runs the hybrid retrieval stages for q08 — reusing the
> recorded HY-STAB-01 resolved queries — and captures the **RRF
> neighborhood around the rerank-pool cutoff**. **No fix is designed or
> dispatched by this plan** — the actual recall/pool fix is a separate,
> separately-gated ticket drafted only after HY-FIX-02's Gate E. The ticket
> uses the 9-field Codex handoff format from `CLAUDE.md`.

**This plan is the gated follow-on to HY-FIX-01.** HY-FIX-01's Gate D
(2026-05-22) accepted `localization.json`: of the 4 `fixed_defect` targets,
`recommended_first_fix = recall_depth_fusion_pool`. **q08** (Everything
Everywhere All at Once) is the cleanest case — `retrieved_dropped_before_
rerank_pool` in **both** deterministic arms — and is the priority. HY-FIX-02
localizes q08's recall/pool loss precisely enough to choose the fix lever.

**Goal (one sentence):** Build one Codex tool, `hy_fix_rrf_pool_trace.py`,
that — for q08 — re-runs the hybrid `semantic → bm25 → rrf` stages on the
**exact resolved queries HY-STAB-01 already recorded** (so it reproduces
HY-STAB-01's deterministic q08 state) and captures the **RRF-ranked
neighborhood around the `RERANK_TOP_K` cutoff** — the candidates q08 must
beat, their source mix, and q08's gap to the cutoff — so the human can
choose **which recall/pool lever** the fix must target (rerank-pool cutoff,
BM25 recall, RRF weighting, or semantic depth) **without editing `src/*`,
tuning config, or proposing a fix**.

**Architecture:** A single read-only diagnostic tool under
`eval/scripts/`. It reads HY-STAB-01's `stability_trace.jsonl` and
HY-FIX-01's `localization.json`, takes the recorded `pinned` / `no_llm`
`resolved.retrieval_query` + `rerank_query` for q08, feeds them into the
**already-Gate-D-reviewed** `hybrid_expansion_stability.run_stages`, and
tabulates `StageRun.rrf` (the full fused list). It writes one
`rrf_pool_trace.json`. It re-implements **no** ranking logic and edits no
`src/*`. Because it reuses the recorded queries, it needs **no Ollama**.

**Tech stack:** Python 3.11+, stdlib only (`json`, `pathlib`, `argparse`,
`sys`, `datetime`). Imports `eval.scripts._run_io`,
`eval.scripts.hybrid_live_trace`, and `eval.scripts.hybrid_expansion_stability`
as libraries; the live trace path loads the existing `src` retrieval models
via those imports. No new dependency.

---

## 0. Scope, gates, and hard constraints

### 0.1 What HY-FIX-02 is

One **analysis-only** Codex ticket on the `recall_depth_fusion_pool` fix
path. It produces evidence that localizes q08's loss inside the
RRF-fusion / rerank-pool stage. It does **not** fix anything and does
**not** design a fix. Per `CLAUDE.md`, Claude plans and reviews; Codex
implements; the human approves each gate and **runs the trace**.

It answers exactly one question HY-FIX-01 left open:

> q08 reaches RRF but ranks below the `RERANK_TOP_K = 50` rerank-pool
> cutoff. **Which recall/pool lever** — the cutoff itself, BM25 recall,
> RRF weighting, or semantic depth — would move it into the pool?

### 0.2 Hard constraints

1. **Analysis-only. No fix.** No edit to retrieval, BM25, RRF, fusion,
   reranker, embedding, query-expansion, blend, or any `src/*` / `app.py` /
   config code. The recall/pool fix is a **separate, separately-gated
   ticket** drafted only after this plan's Gate E.
2. **No `src/*` edits and no config mutation.** `src.config` is read and
   snapshotted, never edited or assigned to.
3. **No re-implementation of ranking logic.** The tool reuses
   `hybrid_expansion_stability.run_stages` (Gate-D-reviewed under
   HY-STAB-01) and reads the fused-list movie dicts; it re-implements no
   semantic / BM25 / RRF / rerank logic.
4. **Reuse the recorded resolved queries.** The tool feeds
   `run_stages` the exact `resolved.retrieval_query` / `rerank_query`
   HY-STAB-01 recorded for q08's `pinned` and `no_llm` arms — it does
   **not** call `expand_query`, so it needs **no Ollama** and faithfully
   reproduces HY-STAB-01's deterministic q08 state.
5. **q08 first.** The traced qid set defaults to `q08` (the clean
   both-arms recall/pool case). The tool accepts `--qids`; q05 and q10
   (same `recall_depth_fusion_pool` path in their `pinned` arm) may be
   traced later with the same tool — out of scope for this plan's
   deliverable, which is q08.
6. **Preserve prior evidence.** HY-STAB-01's and HY-FIX-01's outputs are
   read-only inputs; none is modified.
7. **No broad refactor.** One new script, one new test file, one one-line
   README edit.

### 0.3 Honest caveats

- **The trace loads models.** `run_stages` runs the live BGE-M3 embedder,
  the BM25 index, RRF, and the cross-encoder. Per `CLAUDE.md` ("Do not run
  long jobs"), the **model-loading trace is human-run** (§7.2); Codex runs
  only the hermetic validation (§7.1). It is light — q08 only, 2 arms, 1
  pass each (the deterministic arms need no repeats) — but it still loads
  the embedder + cross-encoder + the 27,762-row BM25 index.
- **Faithfulness self-check.** Because the tool reuses the recorded
  queries, the q08 RRF rank it reproduces should equal the value
  HY-STAB-01 recorded (pinned 183, no_llm 79). The tool records both and
  flags `reproduced_matches_recorded`; a mismatch is disclosed, not hidden
  (a small mismatch can arise from CPU/GPU float differences in semantic
  scoring — see §0.3 of HY-STAB-01).
- **No Ollama needed** — the LLM-expanded query is read from the recorded
  trace, not regenerated.
- **Localization, not fix-design.** HY-FIX-02 identifies the lever; sizing
  the exact config change and proving no regression is the *fix* ticket.

### 0.4 Non-goals

- Any `src/*`, `app.py`, or config change; any fix design or dispatch.
- q05 / q10 / q07 — q07 is the separate `reranker_scoring` path; q05/q10
  are deferred (same tool, later `--qids`).
- A BM25 root-cause study (why BM25 misses q08) — if §8 points at the BM25
  lever, that is a follow-on, not this ticket.
- Re-running the full evaluation or re-tracing all 8 hybrid-attributable
  qids.

### 0.5 Gate map

| Gate | When | Who | What |
|---|---|---|---|
| **A — Dispatch approval** | Before the HY-FIX-02 Codex prompt is sent | Human | Approves the §11 handoff. **This plan stops at Gate A.** |
| **D — Claude review** | After Codex finishes the tool + hermetic validation | Claude | Reviews the 3-file diff vs §4 and the §7.1 hermetic log against the §9 checklist. |
| **(human-run trace)** | After Gate D | Human | Runs `hy_fix_rrf_pool_trace.py` (§7.2); produces `rrf_pool_trace.json`. |
| **E — Human accept + lever decision** | After the human-run trace | Human + Claude | Claude summarizes `rrf_pool_trace.json` (§8). Human picks the recall/pool lever (§10) → a separate fix ticket. This plan pre-commits to no fix. |

---

## 1. Current evidence — q08 from HY-FIX-01

Read from
`eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json`
(HY-FIX-01, Gate D 2026-05-22).

- q08 = **Everything Everywhere All at Once**, `tmdb_id 545611`,
  `consolidated_fix_category = recall_depth_fusion_pool`, both deterministic
  arms `retrieved_dropped_before_rerank_pool`.

| arm | semantic rank / 1500 | bm25 | rrf rank / 800 | rrf score | in rerank pool? |
|---|---|---|---|---|---|
| `pinned` | 90 (score 0.540) | **absent** | **183** | 0.00943 | no |
| `no_llm` | 37 (score 0.585) | **absent** | **79** | 0.01887 | no |

**Reading.** q08 is retrieved by **semantic** at a usable depth (rank
37–90 of 1500) but is **never retrieved by BM25** in either arm. RRF
therefore gives q08 only a **single-source** score
(`rrf_score ≈ 1/(RRF_K + semantic_rank + 1)`: pinned `1/106 = 0.00943`,
no_llm `1/53 = 0.01887` — both consistent with `RRF_K = 15`). With only the
semantic contribution, 79–183 other fused candidates outscore q08, so it
lands well past the `RERANK_TOP_K = 50` rerank-pool cutoff and the
cross-encoder never scores it. The `no_llm` (deterministic) query retrieves
q08 markedly better (rrf 79) than the `pinned` LLM query (rrf 183).

**What HY-FIX-01 cannot yet tell us.** It records q08's own ranks but not
the *RRF neighborhood* — what the top-50 fused candidates look like (are
they dual-source?), how large q08's `rrf_score` gap to the cutoff is, and
therefore which lever is decisive. HY-FIX-02 captures exactly that.

---

## 2. Recall/pool fix levers and hypotheses

The trace confirms or refutes which lever a future fix should target.

**L1 — Rerank-pool cutoff (`RERANK_TOP_K`, currently 50).** Raising it
admits deeper RRF ranks to the cross-encoder. *Decisive if* q08's RRF rank
in the better arm is only modestly past 50 (a small `ranks_below_cutoff`).
*Predicted:* plausible for `no_llm` (rrf 79) but not `pinned` (rrf 183).

**L2 — BM25 recall.** q08 is absent from BM25 in both arms → it gets a
single-source RRF score. *Decisive if* the in-pool (rrf rank < 50)
candidates are predominantly **dual-source** — then q08's single-source
disadvantage, not its semantic rank, is what excludes it. The fix would be
a BM25-recall investigation (a follow-on), not a knob.

**L3 — RRF weighting (`RRF_K`, `SEMANTIC_WEIGHT`, `BM25_WEIGHT`).**
*Decisive if* the in-pool candidates are themselves mostly single-source
and q08's semantic rank is competitive with theirs — then re-weighting RRF
to reward strong single-source semantic hits would lift q08.

**L4 — Semantic retrieval depth (`CANDIDATE_POOL`).** *Decisive if* q08's
semantic rank were near `CANDIDATE_POOL = 1500`. *Predicted: refuted* — q08
sits at semantic rank 37–90, well inside the pool.

The trace's `neighborhood_source_mix` and `cutoff` block (§5) discriminate
L1 vs L2 vs L3; L4 is settled by q08's already-known semantic rank.

---

## 3. The analysis ticket — q08 RRF-pool neighborhood trace

For each traced qid (default `q08`), for each deterministic arm
(`pinned`, `no_llm`):

1. Read the arm's recorded `resolved.retrieval_query` and
   `resolved.rerank_query` (and the target `movie_key` / `tmdb_id` /
   `title`) from HY-STAB-01's `stability_trace.jsonl`. Assert the recorded
   queries are byte-identical across that arm's repeats (deterministic);
   raise otherwise.
2. Read the raw query text from `eval/queries/v1.jsonl`.
3. Call `hybrid_expansion_stability.run_stages(raw_query=<raw>,
   retrieval_query=<recorded>, rerank_query=<recorded>)` → `StageRun`.
4. From `StageRun.rrf` (the full fused list): locate the target by
   `movie_key`; capture its `semantic` / `bm25` / `rrf` rank+score, its
   `source_count`, and `in_rerank_pool`.
5. Capture the **RRF neighborhood** — fused ranks `0 .. RERANK_TOP_K - 1 +
   margin` (margin default 25 → ranks 0–74) — and the **cutoff boundary**
   (the last-in-pool rank `RERANK_TOP_K - 1` and first-out rank
   `RERANK_TOP_K`).
6. Cross-check the reproduced RRF rank against HY-STAB-01's recorded value
   (`reproduced_matches_recorded`).

The qid set is validated against HY-FIX-01's `localization.json`: every
requested qid must have `pinned`-arm `fix_category == recall_depth_fusion_pool`
(q08 qualifies — both arms; q05/q10 qualify via their `pinned` arm). A
requested qid that does not is a hard error.

---

## 4. Allowed and forbidden files

### 4.1 Allowed (HY-FIX-02 may create/modify only these three)

- **Create:** `eval/scripts/hy_fix_rrf_pool_trace.py`
- **Create:** `eval/tests/test_hy_fix_rrf_pool_trace.py`
- **Modify (one line — add `hy_fix_rrf_pool_trace.py` to the `scripts/`
  block of the Layout fence):** `eval/README.md`

### 4.2 Inputs (read-only)

- `eval/runs/<run_id>/analysis/hybrid_expansion_stability/stability_trace.jsonl`
- `eval/runs/<run_id>/analysis/hy_fix_localize/localization.json`
- `eval/queries/v1.jsonl`
- Modules imported as libraries, never edited: `eval.scripts._run_io`,
  `eval.scripts.hybrid_live_trace`, `eval.scripts.hybrid_expansion_stability`,
  and (transitively, via those) the `src` retrieval modules.

### 4.3 Output (the tool's only write)

- `eval/runs/<run_id>/analysis/hy_fix_rrf_pool/rrf_pool_trace.json`

Directory via `mkdir(parents=True, exist_ok=True)`; file via
`_run_io._atomic_write_json`.

### 4.4 Forbidden

- Anything under `src/`, `app.py`, any recommender-runtime module,
  `src/config.py`.
- `candidates.jsonl`, `gold_labels.jsonl`, `silver_labels.jsonl`,
  `metrics.json`, `run_manifest.json`, `config_snapshot.json`.
- Anything under any existing `analysis/` subdirectory (incl.
  `analysis/hybrid_expansion_stability/`, `analysis/hy_fix_localize/`).
- Any existing `eval/scripts/*` module — imported, never edited. Any
  `eval/queries` file.

The tool's **only** write is the one file in §4.3.

---

## 5. Output schema — `rrf_pool_trace.json`

```json
{
  "schema_version": "hy-fix-02.v1",
  "run_id": "2026-05-19-1846-nogit",
  "generated_at": "2026-05-22T12:00:00Z",
  "source_artifacts": {
    "stability_trace": "analysis/hybrid_expansion_stability/stability_trace.jsonl",
    "localization": "analysis/hy_fix_localize/localization.json"
  },
  "config": {
    "CANDIDATE_POOL": 1500, "RERANK_POOL": 800, "RRF_K": 15,
    "RERANK_TOP_K": 50, "FINAL_TOP_K": 5,
    "SEMANTIC_WEIGHT": 1.0, "BM25_WEIGHT": 1.0
  },
  "neighborhood_margin": 25,
  "per_qid": [
    {
      "qid": "q08",
      "tmdb_id": 545611,
      "title": "Everything Everywhere All at Once",
      "movie_key": "title:everything everywhere all at once|year:2022",
      "pinned_arm_fix_category": "recall_depth_fusion_pool",
      "arms": {
        "pinned": {
          "retrieval_query": "<recorded from stability_trace.jsonl>",
          "rerank_query": "<recorded from stability_trace.jsonl>",
          "rrf_list_len": 800,
          "target": {
            "semantic": {"present": true, "rank": 90, "score": 0.540},
            "bm25": {"present": false, "rank": null, "score": null},
            "rrf": {"present": true, "rank": 183, "score": 0.00943},
            "source_count": 1,
            "in_rerank_pool": false
          },
          "recorded_rrf_rank": 183,
          "reproduced_matches_recorded": true,
          "cutoff": {
            "rerank_top_k": 50,
            "last_in_pool": {"rrf_rank": 49, "movie_key": "...", "title": "...",
                             "rrf_score": 0.031, "semantic_rank": 12, "bm25_rank": 40,
                             "source_count": 2},
            "first_out_of_pool": {"rrf_rank": 50, "...": "same shape"},
            "target_rrf_rank": 183,
            "ranks_below_cutoff": 134,
            "rrf_score_gap_to_last_in_pool": 0.0216
          },
          "neighborhood": [
            {"rrf_rank": 0, "movie_key": "...", "title": "...", "rrf_score": 0.12,
             "semantic_rank": 0, "bm25_rank": 1, "source_count": 2},
            "... ranks 0 .. (RERANK_TOP_K - 1 + neighborhood_margin) ..."
          ],
          "neighborhood_source_mix": {"dual_source": 0, "semantic_only": 0, "bm25_only": 0},
          "in_pool_source_mix": {"dual_source": 0, "semantic_only": 0, "bm25_only": 0}
        },
        "no_llm": { "...": "same shape" }
      }
    }
  ]
}
```

**Field rules:**

- `config` — read verbatim from HY-STAB-01's `stability_diagnosis.json` →
  `trace_meta.config` (and `RRF_K` is present there). Not recomputed.
- `per_qid` — one entry per traced qid (default just `q08`), sorted by
  `qid`.
- `target` — q08's row found in `StageRun.rrf` by `movie_key`.
  `semantic` / `bm25` rank+score and `rrf` rank+score are read from the
  fused movie dict's `semantic_rank` / `semantic_score` / `bm25_rank` /
  `bm25_score` / `rrf_score` fields and its index in `StageRun.rrf`.
  `source_count` = `(semantic_rank is not None) + (bm25_rank is not None)`.
  `in_rerank_pool` = `rrf_rank < RERANK_TOP_K`.
- `recorded_rrf_rank` — q08's `rrf.rank` from `stability_trace.jsonl` for
  this arm; `reproduced_matches_recorded` = whether the reproduced
  `target.rrf.rank` equals it.
- `cutoff` — `last_in_pool` / `first_out_of_pool` are the fused entries at
  index `RERANK_TOP_K - 1` and `RERANK_TOP_K`. `ranks_below_cutoff` =
  `target.rrf.rank - (RERANK_TOP_K - 1)`. `rrf_score_gap_to_last_in_pool`
  = `last_in_pool.rrf_score - target.rrf.score`.
- `neighborhood` — fused entries at ranks `0 .. RERANK_TOP_K - 1 +
  neighborhood_margin`; each carries `rrf_rank`, `movie_key`, `title`,
  `rrf_score`, `semantic_rank`, `bm25_rank`, `source_count`.
- `neighborhood_source_mix` — counts of `source_count` over the
  `neighborhood`; `in_pool_source_mix` — the same over only ranks
  `< RERANK_TOP_K`. These two are the key L2/L3 discriminators.

---

## 6. Why this ticket is analysis-only and faithful

1. **It reuses a Gate-D-reviewed composition.**
   `hybrid_expansion_stability.run_stages` reproduces the hybrid
   `semantic → bm25 → rrf → rerank` stages and was reviewed and accepted
   at HY-STAB-01's Gate D. HY-FIX-02 calls it unchanged and only **reads**
   `StageRun.rrf`.
2. **It reuses the recorded queries — no new non-determinism, no Ollama.**
   Feeding `run_stages` the exact `resolved.retrieval_query` /
   `rerank_query` HY-STAB-01 recorded reproduces HY-STAB-01's deterministic
   q08 state; `reproduced_matches_recorded` proves it. No `expand_query`
   call, so no Ollama.
3. **It reads fused-list fields, never recomputes them.** `rrf_score`,
   `semantic_rank`, `bm25_rank` are already on every fused movie dict
   (set by `semantic_search` / `bm25_search` and carried through
   `rrf_fusion`). `source_count` and the source-mix counts are arithmetic
   on those read values — not a re-implementation of RRF.
4. **No `src/*` edit, no config mutation.** `src.config` is read for the
   `config` snapshot only. The tool writes one file under
   `analysis/hy_fix_rrf_pool/`.
5. **The fix is out of scope.** HY-FIX-02 names the lever; the config/`src`
   change and its paired-bootstrap regression gate are the *fix* ticket,
   separately gated after Gate E.

---

## 7. Validation commands

### 7.1 Agent-runnable (Codex runs; Claude re-runs at Gate D) — hermetic, no models

```
python -m compileall eval/scripts
python -m unittest discover -s eval/tests -v
python -m eval.scripts.hy_fix_rrf_pool_trace --run 2026-05-19-1846-nogit --dry-run
```

Expected:

1. `compileall` reports `Listing ... OK`.
2. All tests pass; the count is `previous + N`. Baseline is **139** from
   HY-FIX-01; HY-FIX-02 adds at least 9 → expect **≥ 148**. Codex reports
   exact before/after counts.
3. `--dry-run` exits 0, **imports no model** (`src.models`,
   `src.retrieval.semantic/bm25/reranker`, `src.llm.*` absent from
   `sys.modules` — asserted by `test_dry_run_no_model_import`), **writes
   nothing**, and prints the traced qid(s) with each arm's recorded
   `retrieval_query` / `rerank_query` resolved from `stability_trace.jsonl`.

### 7.2 Human-run (after Gate D — loads models)

The trace loads BGE-M3, the cross-encoder, and the BM25 index — **no
Ollama** (it reuses the recorded queries). On the 8 GB RTX 4070 the trace
runs on the GPU; nothing else need share VRAM, so no Ollama-CPU step is
required. Use the project venv.

```
.\venv\Scripts\python.exe -u -X faulthandler -m eval.scripts.hy_fix_rrf_pool_trace --run 2026-05-19-1846-nogit
python -c "import json,pathlib; d=json.loads(pathlib.Path('eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_trace.json').read_text(encoding='utf-8')); q=d['per_qid'][0]; print('qid', q['qid']); [print(arm, '| rrf_rank', a['target']['rrf']['rank'], '| reproduced_ok', a['reproduced_matches_recorded'], '| ranks_below_cutoff', a['cutoff']['ranks_below_cutoff'], '| in_pool_source_mix', a['in_pool_source_mix'], '| target_source_count', a['target']['source_count']) for arm,a in q['arms'].items()]"
```

Expected:

1. The trace exits 0 and writes
   `analysis/hy_fix_rrf_pool/rrf_pool_trace.json` covering q08, both arms.
2. The one-liner prints, per arm, q08's reproduced RRF rank, whether it
   matches HY-STAB-01's recorded rank, `ranks_below_cutoff`, the
   `in_pool_source_mix`, and q08's `source_count`. Those values are the
   diagnostic result — Claude summarizes them at Gate E.

---

## 8. Decision rules — choosing the recall/pool lever

After the human-run trace, Claude summarizes `rrf_pool_trace.json`; the
human picks **one** lever. Use the **`no_llm` arm** as the primary basis —
it is the deterministic, LLM-free control and gave q08 its better RRF rank.

- **L1 — raise `RERANK_TOP_K`.** Favoured when `no_llm`
  `cutoff.ranks_below_cutoff` is small (q08 within ~30 ranks of the
  cutoff). A modest raise admits q08 to the cross-encoder. Cost: more
  cross-encoder calls per query — the fix ticket must bound the increase
  and check latency.
- **L2 — BM25 recall.** Favoured when q08's `target.source_count == 1`
  (BM25-absent) **and** `in_pool_source_mix.dual_source` is the large
  majority of the top-50 — q08's single-source RRF score is the
  disqualifier. The fix is a BM25-recall investigation (why BM25's
  field-weighted index misses q08), itself analysis-first — **not** a knob.
- **L3 — RRF weighting (`RRF_K` / `SEMANTIC_WEIGHT` / `BM25_WEIGHT`).**
  Favoured when the top-50 are themselves mostly single-source
  (`in_pool_source_mix.semantic_only` large) yet outrank q08 — i.e. q08's
  semantic rank is simply not competitive under the current RRF curve.
- **L4 — semantic depth (`CANDIDATE_POOL`).** Refuted in advance — q08's
  semantic rank (37–90) is far inside `CANDIDATE_POOL = 1500`. Only revisit
  if the trace contradicts HY-FIX-01.

**Sequencing.** Whatever lever is chosen, the fix is a **separate,
separately-gated ticket** (§10). If the trace shows q08 needs L2 (a BM25
gap), the fix ticket itself starts analysis-first (a BM25-recall trace)
before any `src/*` change. q05 and q10 (same `pinned`-arm path) are
re-traced with this same tool (`--qids q05,q10`) before their fix is
sized.

---

## 9. Gate D review checklist (Claude, after Codex finishes)

Report findings as **matches spec / deviations / blockers**.

- [ ] **Scope:** the diff touches exactly the 3 files in §4.1.
- [ ] **No `src/` edit, no config mutation:** no file under `src/` is
      created/modified; `src.config` is read, never assigned.
- [ ] **Reuse, not re-implement:** the tool calls
      `hybrid_expansion_stability.run_stages` and reads `StageRun.rrf`; it
      re-implements no semantic / BM25 / RRF / rerank logic.
- [ ] **Recorded queries:** the `pinned` / `no_llm` `retrieval_query` and
      `rerank_query` are read from `stability_trace.jsonl` and asserted
      byte-identical across that arm's repeats; `expand_query` is **never**
      called.
- [ ] **qid validation:** requested qids are checked against
      `localization.json` — each must have `pinned`-arm
      `fix_category == recall_depth_fusion_pool`; `q08` is the default.
- [ ] **Capture:** `target`, `cutoff` (`last_in_pool` /
      `first_out_of_pool` / `ranks_below_cutoff` /
      `rrf_score_gap_to_last_in_pool`), `neighborhood`,
      `neighborhood_source_mix`, `in_pool_source_mix`, and
      `reproduced_matches_recorded` are all present and match §5.
- [ ] **Output scope:** the only write is
      `analysis/hy_fix_rrf_pool/rrf_pool_trace.json`; atomic; directory
      `mkdir(parents=True, exist_ok=True)`.
- [ ] **`--dry-run`:** exits 0, imports no model, writes nothing.
- [ ] **Hermetic validation:** §7.1 ran — `compileall` OK, unit count
      ≥ 148, `--dry-run` clean.
- [ ] **Schema:** `rrf_pool_trace.json` matches §5 exactly.

If all pass: Gate D green → human runs §7.2 → Gate E.

---

## 10. Gate E decision tree (human, after the human-run trace)

Claude summarizes `rrf_pool_trace.json`; the human picks **exactly one**.

1. **Cutoff lever (L1)** — `no_llm` `ranks_below_cutoff` is small:
   → **Draft a separate, separately-gated `RERANK_TOP_K` fix ticket**,
   gated on a paired-bootstrap eval (no regression) and a latency check.
2. **BM25-recall lever (L2)** — q08 is BM25-absent and the top-50 are
   majority dual-source:
   → **Draft a separate, separately-gated BM25-recall plan**, itself
   analysis-first (a BM25-recall trace before any `src/*` change).
3. **RRF-weighting lever (L3)** — the top-50 are majority single-source
   and outrank q08:
   → **Draft a separate, separately-gated RRF-weighting fix ticket**,
   gated on a paired-bootstrap eval.
4. **Inconclusive** — `reproduced_matches_recorded` is false for an arm,
   or no lever is clearly indicated:
   → **Stop. Re-trace or widen `neighborhood_margin`.** Do not draft a
   fix on inconsistent evidence.

This plan **pre-commits to no branch and no fix.** Its product is the
evidence in `rrf_pool_trace.json`.

---

## 11. Ticket HY-FIX-02 — Codex-ready handoff

### 1. Goal

Build `eval/scripts/hy_fix_rrf_pool_trace.py`: a diagnostic tool that, for
q08, re-runs the hybrid `semantic → bm25 → rrf` stages on HY-STAB-01's
recorded `pinned` / `no_llm` resolved queries (via
`hybrid_expansion_stability.run_stages`), captures the RRF neighborhood
around the `RERANK_TOP_K` cutoff, and writes
`analysis/hy_fix_rrf_pool/rrf_pool_trace.json`. Analysis-only: no `src/*`
edits, no config mutation, no fix.

### 2. Files to change

- Create: `eval/scripts/hy_fix_rrf_pool_trace.py`
- Create: `eval/tests/test_hy_fix_rrf_pool_trace.py`
- Modify (one line): `eval/README.md`

### 3. Files to read but NOT change

- `eval/scripts/_run_io.py`, `eval/scripts/hybrid_live_trace.py`,
  `eval/scripts/hybrid_expansion_stability.py`.
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_trace.jsonl`
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_diagnosis.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json`
- `eval/queries/v1.jsonl`

### 4. Acceptance criteria

1. **CLI:** `python -m eval.scripts.hy_fix_rrf_pool_trace [--run RUN_ID]
   [--qids q08] [--margin 25] [--dry-run]`. `--run` defaults to
   `_run_io.latest_run()`; `--qids` is a comma list defaulting to `q08`;
   `--margin` (neighborhood margin) defaults to `25` (≥ 0).
2. **Error type:** define `HyFixRrfPoolError(ValueError)`; `main()`
   catches it, prints to `stderr`, returns non-zero, writes nothing.
3. **Preconditions:** raise `HyFixRrfPoolError` and write nothing if
   `stability_trace.jsonl`, `stability_diagnosis.json`,
   `localization.json`, or `eval/queries/v1.jsonl` is missing.
4. **qid validation:** each `--qids` entry must appear in
   `localization.json` `per_target` with `arms.pinned.fix_category ==
   "recall_depth_fusion_pool"`; otherwise raise `HyFixRrfPoolError`.
5. **Recorded queries:** for each traced qid and each arm in
   `("pinned","no_llm")`, collect that arm's rows for the target from
   `stability_trace.jsonl`; assert every repeat's
   `resolved.retrieval_query` and `resolved.rerank_query` are identical
   (raise otherwise); use those strings. The tool **must not** call
   `expand_query`. Read the raw query text from `eval/queries/v1.jsonl`.
6. **`--dry-run`:** resolve qids, targets, and the recorded queries; print
   `run_id=`, `qids=`, and per (qid, arm) the `retrieval_query` /
   `rerank_query`; exit 0; **write nothing**; **import no model**
   (`src.models`, `src.retrieval.semantic/bm25/reranker`, `src.llm.*` must
   not be imported on the dry-run path — defer those imports into the
   live-trace path).
7. **Stage run:** for each (qid, arm), call
   `hybrid_expansion_stability.run_stages(raw_query=<raw>,
   retrieval_query=<recorded>, rerank_query=<recorded>)` and use
   `StageRun.rrf` (the fused list). Do not re-implement any stage.
8. **Capture:** build the §5 `per_qid[].arms[arm]` object — `target`
   (located in `StageRun.rrf` by `movie_key`; `semantic`/`bm25`/`rrf`
   rank+score read from the fused movie dict and its index;
   `source_count`; `in_rerank_pool`), `recorded_rrf_rank` +
   `reproduced_matches_recorded`, `cutoff` (entries at index
   `RERANK_TOP_K-1` and `RERANK_TOP_K`; `ranks_below_cutoff`;
   `rrf_score_gap_to_last_in_pool`), `neighborhood` (ranks `0 ..
   RERANK_TOP_K-1+margin`), `neighborhood_source_mix`, `in_pool_source_mix`.
   If the target is absent from `StageRun.rrf`, set `target.rrf.present =
   false` with null rank/score and `in_rerank_pool = false`, and `cutoff`
   with `target_rrf_rank = null` / `ranks_below_cutoff = null`.
9. **`config`:** read `CANDIDATE_POOL`, `RERANK_POOL`, `RRF_K`,
   `RERANK_TOP_K`, `FINAL_TOP_K`, `SEMANTIC_WEIGHT`, `BM25_WEIGHT` verbatim
   from `stability_diagnosis.json` → `trace_meta.config`.
10. **`rrf_pool_trace.json`:** exact §5 schema; `schema_version`
    `"hy-fix-02.v1"`; `generated_at` UTC second precision; `per_qid`
    sorted by `qid`. Written atomically via `_run_io._atomic_write_json`
    to `analysis/hy_fix_rrf_pool/rrf_pool_trace.json`; directory via
    `mkdir(parents=True, exist_ok=True)`. No other file is written.
11. **CLI output (non-dry-run):** print `run_id=`, the output path,
    `qids=`, and per (qid, arm) the reproduced `rrf` rank and
    `reproduced_matches_recorded`.
12. **`test_hy_fix_rrf_pool_trace.py`** is hermetic (no models, no
    network; `tempfile.TemporaryDirectory`; monkeypatch
    `hybrid_expansion_stability.run_stages` with a fake returning a
    synthetic `StageRun`; synthetic `stability_trace.jsonl` /
    `stability_diagnosis.json` / `localization.json` / `v1.jsonl`; follow
    `eval/tests/test_hy_fix_localize.py`) and includes at least:
    - `test_recorded_queries_used` — the fake `run_stages` asserts it
      receives the recorded `retrieval_query` / `rerank_query`.
    - `test_expand_query_never_called` — a patched `expand_query` that
      raises; a full run completes.
    - `test_target_located_in_rrf` — target found by `movie_key`; rank,
      score, `source_count`, `in_rerank_pool` correct.
    - `test_target_absent_from_rrf` — target not in the fused list →
      `target.rrf.present = false`, graceful `cutoff`.
    - `test_cutoff_boundary` — `last_in_pool` / `first_out_of_pool` /
      `ranks_below_cutoff` / `rrf_score_gap_to_last_in_pool` correct.
    - `test_source_mix_counts` — `neighborhood_source_mix` /
      `in_pool_source_mix` count `source_count` correctly.
    - `test_reproduced_matches_recorded` — true when reproduced RRF rank
      equals the recorded one, false otherwise.
    - `test_qid_not_recall_pool_rejected` — a `--qids` entry whose
      `localization.json` pinned category is not `recall_depth_fusion_pool`
      → `HyFixRrfPoolError`.
    - `test_dry_run_no_model_import` — after `--dry-run`, `src.models`
      absent from `sys.modules`; nothing written.
    - `test_missing_input_exits_nonzero` — a missing input → non-zero
      exit, nothing written.
13. **No `src/` edit; no config mutation; no `expand_query` call; no stage
    logic re-implemented.**

### 5. Validation commands

Run §7.1 (hermetic). Report per `AGENTS.md`: files changed, commands run,
before/after test counts, failures verbatim, the `--dry-run` stdout, and
any assumptions. **Do not run §7.2** — the model-loading trace is
human-run after Gate D.

### 6. Dependencies

- HY-STAB-01 — `stability_trace.jsonl` + `stability_diagnosis.json`, and
  the importable `hybrid_expansion_stability.run_stages` (satisfied).
- HY-FIX-01 — `localization.json` (satisfied; Gate D 2026-05-22).
- The working-tree `src/` retrieval pipeline + ChromaDB + the BM25 source
  CSV are required **only for the human-run §7.2 step**.

### 7. Risk level

**Low.** Three-file change; one read-only `eval/` tool that reuses the
Gate-D-reviewed `run_stages` and reads its output. Real risks: (a) writing
outside `analysis/hy_fix_rrf_pool/`, (b) calling `expand_query` instead of
reusing recorded queries, (c) re-implementing stage logic. Criteria
5/7/8/13, the §4.4 forbidden list, and atomic writes close all three.

### 8. Reviewer

Claude Code Pro, per the §9 Gate D checklist.

### 9. Codex prompt (planning artifact — NOT dispatched by this plan)

```
You are working on the CineMatch eval harness (Python 3.11+, no-git mode).

Implement ticket HY-FIX-02 exactly as specified in
docs/superpowers/plans/2026-05-22-hy-fix-02-recall-depth-rrf-pool-localization.md
section 11, with the output schema in section 5.

You may edit ONLY:
  - eval/scripts/hy_fix_rrf_pool_trace.py      (create)
  - eval/tests/test_hy_fix_rrf_pool_trace.py   (create)
  - eval/README.md                             (add ONE line:
                                                hy_fix_rrf_pool_trace.py in the
                                                scripts/ block of the Layout fence)

Do not edit any other file. No src/* edits. No src/config.py edits. No edits
to any existing eval script. Do not run pip installs. Do not run any git
command.

HARD CONSTRAINTS:
  - ANALYSIS-ONLY. The tool MUST NOT change, re-implement, or tune any
    ranking / retrieval / BM25 / RRF / fusion / reranker / embedding /
    query-expansion / config logic, and MUST NOT propose a fix.
  - It MUST NOT mutate src.config (read-only snapshot of config values from
    stability_diagnosis.json trace_meta.config).
  - It reuses hybrid_expansion_stability.run_stages AS A LIBRARY to run the
    hybrid stages and reads StageRun.rrf. It MUST NOT re-implement semantic /
    bm25 / rrf / rerank logic.
  - It MUST NOT call expand_query / use Ollama. For each traced qid and arm
    (pinned, no_llm) it reads the recorded resolved.retrieval_query and
    resolved.rerank_query from stability_trace.jsonl, asserts they are
    identical across that arm's repeats, and feeds those exact strings to
    run_stages.
  - Traced qids (default q08) are validated against localization.json: each
    must have arms.pinned.fix_category == "recall_depth_fusion_pool".
  - The tool's ONLY write is eval/runs/<run_id>/analysis/hy_fix_rrf_pool/
    rrf_pool_trace.json (atomic via _run_io._atomic_write_json; directory via
    mkdir(parents=True, exist_ok=True)). It MUST NOT modify any existing
    artifact under analysis/ or anything under src/.
  - The --dry-run path MUST NOT import any model module (src.models,
    src.retrieval.semantic/bm25/reranker, src.llm.*): defer those imports
    into the live-trace path.
  - If a required input file is missing, raise HyFixRrfPoolError (a
    ValueError subclass), exit non-zero, write nothing.

Acceptance criteria 1-13 in section 11 are all required. Run ONLY the
hermetic validation in section 7.1 (compileall, unittest discover,
--dry-run). DO NOT run the model-loading trace in section 7.2 -- that is
human-run. Report per AGENTS.md (files changed, commands run, before/after
test counts, failures verbatim, the --dry-run stdout, assumptions).
```

---

## 12. Stop for Gate A approval

Per `CLAUDE.md`, Claude does **not** dispatch Codex automatically. **This
plan stops here.** Nothing is implemented until the human gives **Gate A**
for the §11 handoff.

Order once Gate A is given: Gate A → Codex implements + §7.1 hermetic
validation → Gate D (Claude, §9) → human-run §7.2 trace → Gate E (human
picks a §10 lever → a separate, separately-gated fix ticket).

**No ranking, retrieval, fusion, reranker, or config change is implemented
or dispatched by this plan.**

---

## 13. Self-review against this plan's own constraints

1. **Analysis-only; no fix; no `src/*` edit; no config mutation** — §0.2,
   §10/§12, §11 criteria 13, the Codex prompt. ✓
2. **Reuses `run_stages`; no stage re-implementation** — §3, §6.1, §11
   criterion 7/13. ✓
3. **No Ollama; reuses recorded queries** — §0.2.4, §6.2, §11 criterion 5;
   `expand_query` never called. ✓
4. **q08 first** — §0.2.5, §1, `--qids` default `q08`; q05/q10 deferred to
   the same tool. ✓
5. **Localizes the recall/pool loss to a lever** — §5 `cutoff` +
   `*_source_mix`, §8 decision rules (L1–L4). ✓
6. **Faithfulness checked** — `reproduced_matches_recorded` (§5, §0.3). ✓
7. **Output schema + validation commands** — §5, §7.1/§7.2. ✓
8. **Gates A / D / E defined** — §0.5, §9, §10, §12. ✓
9. **Codex-ready ticket** — §11 has all 9 `CLAUDE.md` handoff fields. ✓
10. **Produces evidence, not a fix** — §10 drafts only *separate* fix
    tickets; §12 pre-commits to none. ✓
11. **No git commands** — none in any validation block. ✓

---

## 14. Gate A — awaiting approval

**Status:** DRAFT. Planning only. Nothing implemented; no Codex call made.
The plan stops here until the human approves the §11 handoff (**Gate A**).
