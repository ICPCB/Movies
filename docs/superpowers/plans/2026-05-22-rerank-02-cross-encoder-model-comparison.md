# RERANK-02 — Cross-Encoder Failure: Content-Gap Test + Model Comparison (q05, q10)

Status: READY FOR REVIEW — model-backed; **do not dispatch without Human go-ahead**
Date: 2026-05-22
Owner: Codex automation (RERANK-02 ticket) + Claude (gate/review) + Human (model-set + GPU-run authorization)
Branch: `automation/cinematch-accuracy-audit-full`
Mode: Phase A analysis-only/hermetic · Phase B model-backed (GPU + one-time model download)
Predecessors: DECOMP-01 (`7a52bfc`); RERANK-01A (`f538b41`); RERANK-01B (`732d3ef`, gate-review PASS).

---

## GATE BANNER — read first

**Phase 5 (any `src/*` accuracy change) remains BLOCKED.**

RERANK-02 is an **investigation** ticket. It does not edit `src/*` and does not
start Phase 5. **Even a `model_capability_confirmed` outcome does NOT unblock
Phase 5** — swapping the reranker model is an architecture change that would
first require a full gold/silver-set regression eval (a separate ticket). See
Section 6.

This plan is **model-backed (Phase B)**. Per the automation rules, the GPU run
must be authorized and budgeted before it executes. **Claude has authored the
plan but is not dispatching it** — the Human should confirm the alternative
model set (Section 4) and authorize the GPU run.

---

## 1. Why RERANK-02 exists — and a caveat on the RERANK-01B classification

RERANK-01B (`732d3ef`) completed the q05/q10 characterization on the repaired
text snapshot and classified `failure_mode = model_capability_limit_hypothesis`.

**Claude's RERANK-01B gate review flagged that classification as weakly
discriminated**, for two concrete reasons:

1. **`bge-reranker-v2-m3` is already a multilingual model.** The classifier
   chose `model_capability_limit_hypothesis` because a crude `_domain_signals`
   heuristic fired (target titles `Thanatomorphose`, `[REC]` are "atypical").
   A non-English title is not, by itself, a capability gap for an m3 model.
2. **The classifier cannot emit `metadata_genre_mismatch`.** That value is in
   the enum but has no code path — so the content/genre-overlap alternative was
   never tested before `model_capability_limit_hypothesis` was chosen.

A direct content signal supports the caveat: the q10 `no_llm` `rerank_query` is
*"found footage friends chased through a haunted apartment maze"*. The seven
false positives that outrank `[REC]` are found-footage **ghost/haunting** films
(Ghost Team One, Apartment 143, Grave Encounters, …). `[REC]` is found-footage
but it is an **infection/outbreak** film — not "haunted". The cross-encoder may
be scoring the query–document match **correctly**; the defect could be the
**rewritten `rerank_query`** (a query/content gap), not the model.

So RERANK-02 must **not** jump straight to "swap the model". It must first test,
hermetically, whether the failure is a content/semantic gap — and only then run
the model comparison to confirm or refute a true model-capability limit.

---

## 2. Ticket RERANK-02 — full Codex handoff

### 2.1 Ticket id

`RERANK-02`

### 2.2 Goal / Objective

Determine **why** the `bge-reranker-v2-m3` cross-encoder ranks the q05 and q10
gold targets outside the top-5 — distinguishing three causes:

- **content/semantic gap** — the rewritten `rerank_query` genuinely describes
  the false positives better than the target (defect is upstream of the
  reranker);
- **model-capability limit** — the query–document match is sound but the
  *current model* mis-scores it (an alternative cross-encoder would rank the
  target into top-5 on the identical pairs);
- **neither decisively** — `inconclusive`.

The ticket runs a hermetic content-gap analysis (Phase A) and a model
comparison (Phase B), and ends with one explicit `decision`.

"Done" means: the artifact carries Phase A and Phase B results and a single
`decision`; unit tests pass; `compileall` passes; `git diff --name-only --
src/` is empty; expected vs actual GPU cost/time is recorded.

### 2.3 Method — Phase A (hermetic, no model)

A new script `eval/scripts/rerank_model_comparison.py`. Phase A, for q05 and
q10 (both arms, headline = `no_llm`), using the RERANK-01A snapshot
`q05_q10_text_snapshot.json` and the RERANK-01B characterization artifact:

1. For each `(qid, arm)`, take the `rerank_query` and the `document_text` of
   the gold target and of every false positive ranked above it.
2. Compute **lexical-overlap** metrics between the `rerank_query` and each
   document: token-overlap count and Jaccard over a simple lowercase
   word-tokenization (reuse a tiny local tokenizer; do **not** import the BM25
   internals). Compute the overlap separately against the document's `genres`,
   `keywords`, and `overview` fields (from the snapshot's per-member text
   fields).
3. Flag, per `(qid, arm)`, whether **every** false positive above the target
   has strictly higher query-overlap than the target (a `content_gap` signal),
   and report the margin.
4. Phase A emits a `content_gap` finding per qid: `content_gap_present` /
   `content_gap_absent` / `mixed`, with the overlap table as evidence.

Phase A is hermetic — stdlib + the two JSON artifacts only. No model, no
network, no GPU.

### 2.4 Method — Phase B (model-backed, GPU + one-time download)

Phase B re-scores the **exact** `(rerank_query, document_text)` pairs from the
snapshot with one or more **alternative** cross-encoders and compares the gold
target's resulting **rank** against the `bge-reranker-v2-m3` baseline.

- **Baseline** = the recorded `bge-reranker-v2-m3` `rerank_score` already in
  the DECOMP-01 artifact / RERANK-01B characterization. **Do not re-run the
  current model** — its scores exist.
- **Alternative model(s)** — see Section 4. Load each via its library directly
  in the eval script (`sentence_transformers.CrossEncoder` or the model's
  documented loader). **Never import or modify `src/*`** to do this; **add no
  LLM call.**
- For each `(qid, arm)`, score **all extended-pool members** (the 67-row pool
  the snapshot covers) with each alternative model, rank the pool by that
  model's score, and record the gold target's rank.
- The comparison metric is **rank-based**, not raw-score — different models
  have different score scales. The question is: under model X, does the target
  reach rank < 5?

### 2.5 Decision values

The artifact ends with exactly one `decision`:

- `content_gap_dominant` — Phase A shows the `rerank_query` describes the false
  positives better than the target for the headline (`no_llm`) arms, **and**
  Phase B shows no alternative model rescues the target. The defect is upstream
  of the reranker (the rewritten `rerank_query` / query expansion). Recommends
  a query-expansion investigation, not a reranker change.
- `model_capability_confirmed` — at least one alternative cross-encoder ranks
  the target into the top-5 on the identical pairs while `bge-reranker-v2-m3`
  does not. Names the model and the rank achieved. **Does not unblock Phase 5**
  (see Section 6).
- `model_capability_ruled_out` — no alternative model rescues the target and
  Phase A shows no clear content gap; the loss is intrinsic to the
  query/document pair.
- `inconclusive` — the evidence does not support a single decision.

`content_gap_dominant`, `model_capability_ruled_out`, and `inconclusive` are
all valid, expected outcomes. Do not force `model_capability_confirmed`.

### 2.6 Files to CREATE (allowed)

- `eval/scripts/rerank_model_comparison.py` — Phase A + Phase B runner.
- `eval/tests/test_rerank_model_comparison.py` — unit tests for the pure
  functions (lexical-overlap metrics, content-gap flag, rank computation,
  decision logic) on offline fixtures; a test asserting Phase A imports no
  model and that the script makes no `src/*` edit / LLM call.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_model_comparison.json`
  — the comparison artifact (Phase A + Phase B + decision).
- `docs/superpowers/reports/rerank-02-model-comparison.md` — the report.

### 2.7 Files to MODIFY (allowed)

- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — append the RERANK-02
  checkpoint(s) (Phase A checkpoint, then Phase B checkpoint).

### 2.8 Files to READ but not change

- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_text_snapshot.json`
  — the `(rerank_query, document_text)` pairs and per-member text fields.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_reranker_characterization.json`
  — RERANK-01B characterization (target/FP selection, baseline ranks).
- `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
  — baseline `bge-reranker-v2-m3` scores/ranks.
- `eval/scripts/_run_io.py` — run-path helpers.
- `src/config.py` — read-only, only if a reranker config constant is needed.

### 2.9 Files FORBIDDEN

- `src/**` — **no edits.** RERANK-02 must not modify the pipeline; the
  alternative models are loaded only inside the eval script.
- Any **LLM** call (Ollama / `expand_query` / generation) inside the scoring
  path.
- `eval/scripts/rerank_text_snapshot.py`, `rerank_failure_q05_q10.py`,
  `decomp_pool_q05_q10.py` and their artifacts — read-only.
- `eval/queries/**`, any `*_labels.jsonl`, anything q07.

### 2.10 Acceptance criteria

1. Phase A is hermetic (stdlib + the two input JSON artifacts only — no model,
   no network, no GPU). A unit test asserts the Phase A functions import no
   model library.
2. The artifact records, per `(qid, arm)`: the Phase A lexical-overlap table
   (target vs each false positive, against genres/keywords/overview) and a
   `content_gap` finding.
3. Phase B records, for each alternative model and each `(qid, arm)`: the gold
   target's rank in the re-scored extended pool, alongside the
   `bge-reranker-v2-m3` baseline rank.
4. The artifact carries exactly one `decision` from Section 2.5, with
   `evidence[]` citing concrete Phase A / Phase B values.
5. `rerank_model_comparison.py` makes **no `src/*` edit** and **no LLM call**;
   `git diff --name-only -- src/` is empty.
6. Phase B records **expected** cost/time/VRAM **before** the run and **actual**
   after (automation rule for long jobs). Each alternative model used is named
   with its resolved version/revision.
7. `compileall` passes; `unittest discover -s eval/tests` passes (≥ 211
   baseline + new tests). The report follows Section 2.12.

### 2.11 Validation commands

```powershell
git status --short --branch
./venv/Scripts/python.exe -m compileall eval/scripts
./venv/Scripts/python.exe -m unittest discover -s eval/tests
# Phase A only (hermetic):
./venv/Scripts/python.exe -m eval.scripts.rerank_model_comparison --run 2026-05-19-1846-nogit --phase a
# Phase B (model-backed, GPU — authorized long job):
./venv/Scripts/python.exe -m eval.scripts.rerank_model_comparison --run 2026-05-19-1846-nogit --phase b
git diff --name-only -- src/
```

For the GPU run, per project notes: `ollama serve` with
`CUDA_VISIBLE_DEVICES=-1` to keep `llama3.2` on CPU; use the project venv.

### 2.12 Report format — `docs/superpowers/reports/rerank-02-model-comparison.md`

Markdown: (1) Header — ticket, timestamp, run, scope. (2) Phase A — the
lexical-overlap table per `(qid, arm)` and the content-gap finding. (3) Phase B
— per-model target-rank table vs the baseline, plus cost/time/VRAM. (4)
Decision — the `decision` value with cited evidence and rejected alternatives.
(5) What this means for Phase 5 — explicitly: no Phase 5 unblock; the
follow-up per Section 6. (6) Phase 5 gate — `Phase 5 remains BLOCKED.`

### 2.13 Dependencies — gated long-running job (Phase B)

- GPU: 8 GB RTX 4070. The baseline `bge-reranker-v2-m3` used ~5.3 GB in
  DECOMP-01; the alternative model must fit within the remaining budget — see
  Section 4 for VRAM-aware candidates.
- Network: a **one-time model download** for each alternative cross-encoder
  (HuggingFace). This is the only network use; record the download size.
- The RERANK-01A snapshot and RERANK-01B / DECOMP-01 artifacts must be present.

### 2.14 Risk

**Medium** — Phase B is a model-backed GPU run with a one-time model download;
it reads `src` config only and never edits `src`. Risks: VRAM overflow (bounded
by the Section 4 candidate selection), and model-loading/dependency friction
(`trust_remote_code`, extra packages). The analysis is read-only
instrumentation; no pipeline behavior changes.

### 2.15 Stop conditions

- STOP before any `src/*` edit.
- STOP if Phase B would add an LLM call into the scoring path.
- STOP if an alternative model exceeds the recorded VRAM budget — re-scope to a
  smaller candidate (Section 4), record the new budget, then continue.
- STOP if a model requires `trust_remote_code` or a dependency not in the venv
  and the Human has not approved adding it — record the blocker, fall back to
  the next candidate, or stop.
- STOP and report `inconclusive` rather than overstating — do not force
  `model_capability_confirmed`.
- STOP if Codex would edit a file outside Section 2.6/2.7.

### 2.16 Commit policy

- Phase A and Phase B may be **separate checkpoint commits** (Phase A is
  hermetic and can commit independently; Phase B commits after the GPU run).
- `git add` only: `eval/scripts/rerank_model_comparison.py`,
  `eval/tests/test_rerank_model_comparison.py`,
  `docs/superpowers/reports/rerank-02-model-comparison.md`,
  `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
- Commit messages: `eval: rerank-02 phase A content-gap analysis` and
  `eval: rerank-02 phase B cross-encoder model comparison`.
- The `q05_q10_model_comparison.json` artifact is gitignored under
  `eval/runs/` — leave on disk, do not `git add -f`.
- **Never stage `src/*` or `graphify-out/`.**

### 2.17 Reviewer

Codex self-review for mechanics. **Claude gate-reviews the `decision`.**
External review (Human) is **recommended** because RERANK-02 may point toward a
reranker-model change — an architecture-sensitive direction under `CLAUDE.md`.

---

## 3. Codex-ready prompt — RERANK-02

> **Do not run this until the Human has confirmed the alternative model set
> (Section 4) and authorized the Phase B GPU run.**
>
> Implement ticket RERANK-02 per
> `docs/superpowers/plans/2026-05-22-rerank-02-cross-encoder-model-comparison.md`
> (Section 2). Create only: `eval/scripts/rerank_model_comparison.py`,
> `eval/tests/test_rerank_model_comparison.py`,
> `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_model_comparison.json`,
> `docs/superpowers/reports/rerank-02-model-comparison.md`; and append
> RERANK-02 checkpoints to `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
> Do not edit `src/*`.
>
> Phase A (hermetic — no model, no network, no GPU): for q05 and q10 (both
> arms), from `q05_q10_text_snapshot.json` and the RERANK-01B characterization,
> compute lexical-overlap metrics (token overlap count + Jaccard, lowercase
> word tokenization) between each arm's `rerank_query` and the gold target's
> and false positives' `genres` / `keywords` / `overview` text. Flag per
> `(qid, arm)` whether every false positive above the target has strictly
> higher query overlap than the target (`content_gap` signal) and report the
> margin.
>
> Phase B (model-backed, GPU, one-time model download): re-score the exact
> `(rerank_query, document_text)` pairs for every extended-pool member of q05
> and q10 (both arms) with the Human-confirmed alternative cross-encoder(s)
> from Section 4, loaded directly via their library inside this eval script —
> never via `src`, and with no LLM call. The `bge-reranker-v2-m3` baseline
> comes from the recorded DECOMP-01 scores; do not re-run it. For each
> alternative model and each `(qid, arm)`, rank the pool by that model's score
> and record the gold target's rank vs the baseline rank. Record expected
> cost/time/VRAM before the run and actual after; name each model's resolved
> revision.
>
> End the artifact with one `decision`: `content_gap_dominant`,
> `model_capability_confirmed` (name the model + rank achieved),
> `model_capability_ruled_out`, or `inconclusive` — with `evidence[]` citing
> concrete Phase A / Phase B values. Do not force `model_capability_confirmed`.
> Note in the report that `model_capability_confirmed` does NOT unblock Phase 5
> (a model swap needs a separate full-set regression eval first).
>
> Ship unit tests for the pure functions (overlap metrics, content-gap flag,
> rank computation, decision logic) on offline fixtures, including a test that
> Phase A imports no model library. Run all validation commands and paste
> output: `compileall eval/scripts`; `unittest discover -s eval/tests`;
> `rerank_model_comparison --phase a`; `rerank_model_comparison --phase b`;
> `git diff --name-only -- src/` (must be empty). Commit Phase A and Phase B as
> separate checkpoints staging only the script, test, report, and ledger;
> leave the gitignored `q05_q10_model_comparison.json` on disk. Never stage
> `src/*` or `graphify-out/`.
>
> Hard stops: stop before any `src/*` edit; stop if Phase B would add an LLM
> call; stop if a model exceeds the VRAM budget or needs an unapproved
> dependency (record, fall back, or stop); stop and report `inconclusive`
> rather than overstating; stop if you would edit a file outside the allowed
> list. Phase 5 remains BLOCKED.

---

## 4. Alternative model set — **Human confirmation recommended**

The baseline is `bge-reranker-v2-m3` (BAAI, multilingual, ~568M params,
~5.3 GB VRAM observed in DECOMP-01). A meaningful comparison needs a
cross-encoder that is **architecturally/training-distinct** and **fits the
remaining VRAM** on the 8 GB RTX 4070. Candidates, in recommended order:

1. **`jinaai/jina-reranker-v2-base-multilingual`** (~278M) — multilingual,
   the most direct apples-to-apples capability test. Note: needs
   `trust_remote_code=True` and possibly `einops` — a dependency decision.
2. **`Alibaba-NLP/gte-multilingual-reranker-base`** (~306M) — multilingual,
   `sentence-transformers`-compatible; lighter dependency footprint.
3. **`cross-encoder/ms-marco-MiniLM-L-6-v2`** (~22M) — small English
   MS-MARCO cross-encoder; a contrast baseline (a *different* result here is
   informative even though it is English-centric).

**Recommendation:** run candidate 2 (or 1) as the primary multilingual
comparison and candidate 3 as a cheap contrast. Selecting the model set edges
toward an architecture decision (`CLAUDE.md`) — the Human should confirm the
set and approve any new dependency (`trust_remote_code`, `einops`) before
Phase B runs.

---

## 5. Note on the RERANK-01B classifier limitation (for the audit trail)

RERANK-01B's `classify_failure_mode` has no code path that emits
`metadata_genre_mismatch`, and its `model_capability_limit_hypothesis` branch
fires on a crude title heuristic. This is a **pre-existing** limitation of the
RERANK-01 classifier — RERANK-01B was correctly scoped to *not* change
classifier logic. RERANK-02's Phase A is the proper test of the
content/genre-overlap alternative. No separate ticket is needed to "fix" the
unreachable enum value; RERANK-02 supersedes it with real evidence.

---

## 6. After RERANK-02 — Phase 5 remains gated

- **`content_gap_dominant`** → the defect is the rewritten `rerank_query` /
  query expansion, upstream of the reranker. Next ticket: a query-expansion
  investigation — **not** a reranker change, **not** Phase 5.
- **`model_capability_confirmed`** → an alternative model rescues q05/q10 on
  these pairs. This still **does not unblock Phase 5.** A reranker-model swap
  is an architecture change that must first pass a **full gold/silver-set
  rerank regression eval** (a new ticket) proving it does not regress the other
  queries. Only then could a Phase 5 plan be authored.
- **`model_capability_ruled_out` / `inconclusive`** → Phase 5 stays blocked;
  escalate to a broader reranker/architecture decision.

**No `src/*` edit occurs until a separate Phase 5 plan is authored and reviewed
READY.** Phase 5 remains BLOCKED.

---

## 7. Self-review — coverage

- Tests model-capability vs content-gap (does not assume a model swap) —
  Sections 1, 2.3, 2.4, 2.5. ✓
- Hermetic Phase A + gated model-backed Phase B with cost/time budget —
  2.3, 2.4, 2.13, 2.16. ✓
- Ticket fully defined: id, goal, allowed/forbidden files, Codex prompt,
  commands, validation, stop conditions, commit policy — Sections 2-3. ✓
- Model set named with VRAM/dependency criteria; Human confirmation flagged —
  Section 4. ✓
- Phase 5 stays BLOCKED; model swap explicitly does not auto-unblock it —
  Sections 5-6. ✓
