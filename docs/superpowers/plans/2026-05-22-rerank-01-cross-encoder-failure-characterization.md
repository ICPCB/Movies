# RERANK-01 — Cross-Encoder Scoring Failure Characterization (q05, q10)

Status: READY FOR CODEX — not yet implemented
Date: 2026-05-22
Owner: Codex automation (RERANK-01 ticket) + Claude (gate/review)
Branch: `automation/cinematch-accuracy-audit-full`
Mode: analysis-only · hermetic (no model, no GPU, no network)
Predecessors: QL-01; RG-03 (`c7998c5`); DECOMP-01 (`7a52bfc`) + DECOMP-01-REVIEW (PASS)
Extends: `docs/superpowers/plans/2026-05-22-pre-phase5-gate-plan.md`

---

## GATE BANNER — read first

**Phase 5 (any `src/*` accuracy change) remains BLOCKED.**

DECOMP-01 returned `safe_localized_fix_ruled_out`; DECOMP-01-REVIEW (G2) was
PASS and confirmed **Exit B** of the pre-Phase-5 gate: no bounded rerank-cutoff
or final-blend reweight rescues q05 and q10 across all deterministic arms.
RERANK-01 is an **investigation** ticket, not a fix. It produces evidence and a
classification only. **It does not start Phase 5, does not write a Phase 5
plan, and does not edit `src/*`.** Phase 5 stays blocked at the end of
RERANK-01 regardless of outcome.

---

## 1. Current state summary

- Branch `automation/cinematch-accuracy-audit-full` at `7a52bfc`
  (`eval: decompose q05 q10 rerank pool (DECOMP-01)`).
- **DECOMP-01 complete, committed, gate-reviewed PASS.** Decision:
  `safe_localized_fix_ruled_out`. Artifact on disk (gitignored under
  `eval/runs/`): `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
  (`schema_version: decomp-01-q05-q10.v1`).
- **RG-03 complete and closed** (`c7998c5`) — q07 is a closed label/data issue,
  out of scope here.
- **194 unit tests pass** as of DECOMP-01 (190 prior + 4 new). No `src/*`
  change anywhere in the audit to date.
- Working tree: only `graphify-out/` untracked (pre-existing, unrelated).

### What DECOMP-01 established (the escalation)

For the q05 (Thanatomorphose, tmdb 144204) and q10 ([REC]) gold targets, the
DECOMP-01 extended-pool decomposition recorded these target ranks (0-indexed,
across the 67-row extended rerank pool):

| qid | arm    | RRF rank | rerank rank | final rank |
|-----|--------|---------:|------------:|-----------:|
| q05 | pinned | 66       | 4           | 54         |
| q05 | no_llm | 1        | 5           | 10         |
| q10 | pinned | 53       | 7           | 12         |
| q10 | no_llm | 10       | 7           | 7          |

DECOMP-01-REVIEW's verdict: *"A bounded cutoff increase or final-blend reweight
cannot lift a target whose `rerank_score` is itself outside top-5."* The defect
escalates to the **reranker / cross-encoder scoring stage**. The escalation is
**stage-dependent**, and RERANK-01's design must respect that:

- **`no_llm` arms are the clean reranker signal.** The target is well-retrieved
  upstream (q05 no_llm RRF rank 1; q10 no_llm RRF rank 10) yet the cross-encoder
  pushes it out of the top 5 (rerank rank 5, 7). This is the cross-encoder
  demoting a target its upstream stages ranked well — the smoking gun.
- **`pinned` arms mix two losses.** q05 pinned RRF rank 66 / q10 pinned RRF
  rank 53 — the target is dropped *before* the standard 50-row rerank pool
  (`recorded_loss_stage: retrieved_dropped_before_rerank_pool`). That is an
  RRF recall-depth loss already characterized by HY-FIX-02 / DECOMP-01, **not**
  a reranker loss. In the *extended* 67-row pool q05 pinned reranks to 4 (good)
  but the final blend demotes it to 54 — a final-blend loss DECOMP-01 already
  ruled un-fixable in isolation.

So the **reranker is one of several loss stages, not the sole villain.**
RERANK-01 must isolate the reranker's specific contribution and not re-litigate
the RRF or final-blend losses DECOMP-01 already covered.

---

## 2. Answers to the four investigation questions

### Q1 — What is the next investigation ticket after DECOMP-01?

**`RERANK-01`** — a hermetic characterization of *why* the `bge-reranker-v2-m3`
cross-encoder under-scores the q05 and q10 gold targets. It is analysis-only,
no model, no GPU, no network — consistent with the HY-FIX hermetic-analysis
pattern. It is defined in full in Section 3.

It is followed by a **placeholder ticket `RERANK-02`** (Section 5) — a
model-backed what-if whose exact scope is *intentionally not specified here*
because it depends on RERANK-01's `failure_mode` classification. Same
discipline the pre-Phase-5 gate plan used to leave Phase 5 unspecified until
DECOMP-01's evidence existed.

### Q2 — What evidence do we need to understand the reranker failure?

Four pieces of evidence, **all derivable hermetically** from artifacts that
already exist plus one pure `src` function:

1. **Reranker scores: gold target vs the false positives that outrank it.**
   The DECOMP-01 artifact's `extended_pool_rows[]` already records, per pool
   member, `rerank_score` and `rerank_rank`. The score *gap* between the gold
   target and each top-5 occupant is the magnitude of the failure.
2. **The exact `(query, document)` text pair the cross-encoder receives.**
   The cross-encoder is fed `[rerank_query, build_movie_document(movie)]`
   (`src/retrieval/reranker.py:108`). The `rerank_query` per arm is recorded in
   the DECOMP-01 artifact. The document side is produced by the **pure**
   function `build_movie_document` (`src/retrieval/reranker.py:38`) — RERANK-01
   imports that one function read-only and applies it to each candidate's
   corpus fields to reconstruct the *exact* document string, with zero drift
   risk from re-implementing it.
3. **Document-field composition (genre / tag / metadata effect).**
   `build_movie_document` concatenates Title → Genres → Tagline →
   Overview (≤600 chars) → Keywords (≤200 chars). For the target vs the false
   positives, RERANK-01 records which fields are present / empty / truncated.
   A degenerate document (e.g. empty overview, truncated keywords) is itself a
   failure mode; a healthy document points the finger at the model.
4. **Stage disagreement map: BM25 vs semantic vs reranker vs final.**
   The DECOMP-01 artifact has all five stage ranks per member. Where the
   reranker *disagrees* with a well-ranked RRF result (the `no_llm` arms) is
   the decisive reranker evidence; where the loss is upstream RRF or downstream
   blend, RERANK-01 attributes it to those stages and does **not** call it a
   reranker failure.

None of this needs a model run — the reranker *scores* already exist in the
DECOMP-01 artifact, and the document *text* is a deterministic pure-function
output. That keeps RERANK-01 cheap, fast, and low-risk.

### Q3 — Should the next ticket compare [the six candidate analyses]?

| # | Candidate analysis | In RERANK-01? | Rationale |
|---|--------------------|---------------|-----------|
| 1 | Reranker scores: gold targets vs false positives | **YES — core** | Hermetic from the DECOMP-01 artifact. The score gap *is* the failure magnitude. |
| 2 | Query / overview text pairs | **YES — core** | Reconstructed via the pure `build_movie_document`. Reveals whether the failure is in the text fed to the model. |
| 3 | Genre / tag / metadata effects | **YES — as observation** | Recorded as document-field composition (present/empty/truncated) for target vs false positives. Not a separate sweep. |
| 4 | Reranker model limitations | **HYPOTHESIS ONLY** | RERANK-01 can *flag* a model-capability hypothesis (e.g. non-English / niche-domain titles) but cannot *prove* it without a comparison model → that proof belongs to RERANK-02. |
| 5 | Alternative scoring prompts / feature inputs | **NO — defer to RERANK-02** | A what-if requires re-scoring with a model. Bundling it now is scope creep and would prematurely shape a `src/*`-flavored change before the failure is even classified. |
| 6 | Lexical / BM25 vs semantic vs reranker disagreement | **YES — core** | Hermetic from the DECOMP-01 artifact's per-stage ranks. Separates a true reranker loss from an RRF or final-blend loss. |

**RERANK-01 = items 1, 2, 6 (core) + item 3 (observation) + item 4 (hypothesis
flag only). RERANK-02 = items 4 (proof) and 5 (what-if).** This split keeps each
ticket bounded and one-at-a-time per the automation rules: characterize the
failure first (hermetic, cheap), *then* test the leading hypothesis with a
model (RERANK-02). Running model-backed what-ifs before the failure is
classified would be an un-targeted sweep.

### Q4 — The next ticket, fully defined

See Section 3.

---

## 3. Ticket RERANK-01 — full Codex handoff

### 3.1 Ticket id

`RERANK-01`

### 3.2 Objective / Goal

Produce a hermetic characterization of *why* the `bge-reranker-v2-m3`
cross-encoder under-scores the q05 (Thanatomorphose) and q10 ([REC]) gold
targets — by comparing, per `(qid, deterministic arm)`, the gold target's
`rerank_score` and the exact `(rerank_query, document_text)` pair against the
false positives that outrank it in the rerank stage, and by mapping where the
BM25 / semantic / RRF / reranker / final stages disagree. The ticket ends with
an explicit `failure_mode` classification and a recommended RERANK-02 scope. It
**proves nothing about a fix** and **proposes no `src/*` change** — it produces
the evidence and the hypothesis that RERANK-02 will test.

"Done" means: the artifact exists with a complete per-arm characterization for
q05 and q10, an evidenced `failure_mode` classification, unit tests pass,
`compileall` passes, and `git diff --name-only -- src/` is empty.

### 3.3 Method

A new hermetic analysis script `eval/scripts/rerank_failure_q05_q10.py`:

1. **Load the reranker scores** from the DECOMP-01 artifact
   `analysis/decomp/q05_q10_pool_decomposition.json` — `per_qid[].arms[].`
   `extended_pool_rows[]` (each row has `rerank_score`, `rerank_rank`,
   `rrf_rank`, `semantic_rank`, `bm25_rank`, `final_rank`, `is_target`,
   `tmdb_id`, `title`, `year`) and `arms[].rerank_query`.
2. **Reconstruct the exact `(query, document)` text pairs.** Import the pure
   function `build_movie_document` from `src.retrieval.reranker` (read-only
   import — see acceptance criterion 2). For the gold target and every false
   positive that ranks **above the target in the rerank stage**, look up the
   movie's full text fields (`title`, `year`, `genres`, `tagline`, `overview`,
   `keywords`) and call `build_movie_document` to get the document string the
   cross-encoder actually received. Field source order: first
   `eval/runs/2026-05-19-1846-nogit/candidates.jsonl` (already carries
   `overview`, `genres`, `keywords`, `tagline`, `title`, `year` per candidate);
   fall back to the corpus `data/movies_clean.csv` keyed by `tmdb_id` for any
   pool member not in `candidates.jsonl`.
3. **Compute, per `(qid, arm)`:**
   - target `rerank_score`, `rerank_rank`;
   - for each false positive above the target: `rerank_score`, `rerank_rank`,
     and `rerank_score_gap_vs_target` (`fp.rerank_score - target.rerank_score`);
   - **document-field composition** for target and each false positive: which
     of title / genres / tagline / overview / keywords are present vs empty,
     `overview_chars`, `overview_truncated` (> 600), `keywords_truncated`
     (> 200), total `document_text_len`;
   - **stage-disagreement** flags: `reranker_demoted_well_retrieved_target`
     (true when the target's RRF rank ≤ standard cutoff but its rerank rank is
     worse and outside top-5 — the clean reranker loss, expected in the
     `no_llm` arms), and an attribution of the loss stage (`rrf_recall` /
     `reranker` / `final_blend`) so a non-reranker loss is not mislabelled.
4. **Classify** an overall `failure_mode` (Section 3.10 enum) with cited
   evidence, and **recommend a RERANK-02 scope**.
5. **Write** the JSON artifact and the markdown report.

The script is **hermetic**: it imports only stdlib, `eval.scripts._run_io`, and
the single pure function `src.retrieval.reranker.build_movie_document`. It
loads **no model**, calls **no LLM / Ollama / network**, and uses **no GPU**.
The reranker *scores* are read from the DECOMP-01 artifact — never recomputed.

### 3.4 Files to CREATE (allowed)

- `eval/scripts/rerank_failure_q05_q10.py` — the hermetic characterization
  runner.
- `eval/tests/test_rerank_failure_q05_q10.py` — unit tests for the pure
  functions (document-field analysis, score-gap computation, stage-disagreement
  attribution, failure-mode classification) on offline fixtures.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_reranker_characterization.json`
  — the characterization artifact (the investigation evidence).
- `docs/superpowers/reports/rerank-01-q05-q10.md` — the characterization report.

### 3.5 Files to MODIFY (allowed)

- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — append the RERANK-01
  checkpoint.

### 3.6 Files to READ but not change

- `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
  — DECOMP-01 decomposition: reranker scores, stage ranks, `rerank_query`.
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl` — per-candidate text
  fields (primary source for document reconstruction).
- `data/movies_clean.csv` — movie corpus (fallback source for pool members not
  in `candidates.jsonl`).
- `src/retrieval/reranker.py` — read to understand the stage; **import only the
  pure function `build_movie_document`**. Do not import or call `rerank`,
  `get_reranker`, or any model.
- `eval/scripts/decomp_pool_q05_q10.py` — pattern reference for artifact
  loading and arm handling.
- `eval/scripts/_run_io.py` — run-path helpers.
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json`
  — q05/q10 target ids and per-arm stage table (cross-check).
- `docs/superpowers/reports/decomp-01-q05-q10.md` — DECOMP-01 conclusions.

### 3.7 Files FORBIDDEN

- `src/**` — **no edits.** The only permitted `src` interaction is a read-only
  import of the pure function `build_movie_document`.
- Any model / LLM / Ollama / network / GPU call — RERANK-01 is hermetic.
- `eval/queries/**`.
- Any `*_labels.jsonl` (gold or silver).
- Anything q07 — q07 is closed (RG-03).
- `eval/scripts/decomp_pool_q05_q10.py` and the DECOMP-01 artifact — read-only;
  RERANK-01 must not modify or regenerate them.
- `eval/scripts/merge_labels.py`, `build_regrade_sheet.py`,
  `check_regrade_sheet.py`, `compute_metrics.py` — not part of RERANK-01.

### 3.8 Acceptance criteria

1. `rerank_failure_q05_q10.py` runs hermetically: it imports only stdlib,
   `eval.scripts._run_io`, and `src.retrieval.reranker.build_movie_document`.
   It loads no model and makes no LLM / Ollama / network / GPU call. A unit
   test asserts no reranker model is instantiated (e.g. the script does not
   reference `get_reranker` / `reranker.predict`).
2. The import of `build_movie_document` is read-only and triggers no model
   load. If importing `src.retrieval.reranker` has any side effect that loads a
   model or opens a network/Ollama connection, the ticket **STOPS** (see
   Section 3.12).
3. The artifact `q05_q10_reranker_characterization.json` contains, for q05 and
   q10, for both deterministic arms (`pinned`, `no_llm`): the gold target's
   `rerank_score` / `rerank_rank`; every false positive above the target in the
   rerank stage with `rerank_score`, `rerank_rank`, `rerank_score_gap_vs_target`;
   the reconstructed `document_text` and `document_fields` composition for the
   target and each such false positive; and the stage-disagreement attribution.
4. Reconstructed reranker *scores* are taken verbatim from the DECOMP-01
   artifact — RERANK-01 recomputes no score. The artifact records the
   DECOMP-01 artifact path and `schema_version` it consumed under
   `source_artifacts`.
5. The artifact carries an explicit `failure_mode.classification` from the
   Section 3.10 enum, with `failure_mode.evidence[]` citing concrete artifact
   values, and a `failure_mode.recommended_followup` describing a RERANK-02
   scope.
6. `python -m compileall eval/scripts` passes; `python -m unittest discover -s
   eval/tests` passes (≥ 194 tests — the DECOMP-01 baseline — plus the new
   RERANK-01 tests); `git diff --name-only -- src/` is empty.
7. The report `rerank-01-q05-q10.md` follows the Section 3.11 format.
8. No Phase 5 work; no `src/*` change; q07 untouched; no `eval/queries/**` or
   `*_labels.jsonl` touched.

### 3.9 Validation commands

```powershell
git status --short --branch
git log --oneline --decorate -6
./venv/Scripts/python.exe -m compileall eval/scripts
./venv/Scripts/python.exe -m unittest discover -s eval/tests
./venv/Scripts/python.exe -m eval.scripts.rerank_failure_q05_q10 --run 2026-05-19-1846-nogit
git diff --name-only -- src/
```

Expected:
- `compileall` — compiles `eval/scripts/rerank_failure_q05_q10.py` with no
  error.
- `unittest discover` — all tests OK, count ≥ 194 + new RERANK-01 tests.
- `rerank_failure_q05_q10` — writes
  `analysis/rerank_failure/q05_q10_reranker_characterization.json`; prints the
  `failure_mode.classification` and confirms `phase5_gate: blocked`.
- `git diff --name-only -- src/` — empty output.

### 3.10 `failure_mode` classification enum

The artifact must set `failure_mode.classification` to exactly one of:

- `document_text_degenerate` — the target's reconstructed reranker document is
  missing or truncates a key field (e.g. empty `overview`, overview truncated
  far below the 600-char budget by an upstream data gap) such that the
  cross-encoder is starved of signal. A text-construction / data defect.
- `metadata_genre_mismatch` — the false positives win on Genres / Keywords
  surface overlap with the `rerank_query` that the cross-encoder rewards, while
  the target's metadata under-signals. A feature-composition effect.
- `query_document_semantic_gap` — the `rerank_query` and the target's document
  are both well-formed and on-topic, yet the cross-encoder still scores them
  apart. Points to a paraphrase / semantic-matching weakness.
- `model_capability_limit_hypothesis` — the failure correlates with a
  domain/language signal (non-English titles, niche horror) where the
  cross-encoder appears weak. A **hypothesis** RERANK-01 may flag but cannot
  confirm without a comparison model — confirmation is RERANK-02's job.
- `stage_disagreement_only` — the reranker actually scores the target
  competitively and the decisive loss is upstream (RRF recall) or downstream
  (final blend). This would partially contradict the DECOMP-01-REVIEW
  escalation and must be reported loudly as a flag to re-examine.
- `mixed` — more than one of the above holds, materially, across the arms.
- `inconclusive` — the evidence does not support any single classification.
  A valid, expected outcome; it does not unblock anything.

A `model_capability_limit_hypothesis`, `mixed`, or `inconclusive` result is
acceptable and must not be inflated into a more specific claim than the
evidence supports.

### 3.11 Report format — `docs/superpowers/reports/rerank-01-q05-q10.md`

Markdown, these sections in order:

1. **Header** — ticket id, timestamp, run id, scope line (`eval/report only;
   no src/* edits; hermetic`).
2. **Method** — one paragraph: artifacts consumed, the pure-function import,
   hermetic confirmation.
3. **Per-arm characterization** — one table per `(qid, arm)` (4 tables):
   columns `role` (target / FP), `tmdb_id`, `title`, `rerank_rank`,
   `rerank_score`, `score_gap_vs_target`, `doc_len`, `overview_chars`,
   `fields_present`.
4. **Stage-disagreement summary** — per `(qid, arm)`: the attributed loss
   stage (`rrf_recall` / `reranker` / `final_blend`) and whether
   `reranker_demoted_well_retrieved_target` is true.
5. **Failure mode** — the `classification`, the cited `evidence[]`, and why
   competing classifications were rejected.
6. **Recommended RERANK-02 scope** — what model-backed what-if RERANK-02
   should run, given the classification.
7. **Phase 5 gate** — one line: `Phase 5 remains BLOCKED.`

### 3.12 Stop conditions

- **STOP before any `src/*` edit.** RERANK-01 never edits `src`.
- **STOP if importing `src.retrieval.reranker` loads a model or opens a
  network / Ollama connection.** If `build_movie_document` cannot be imported
  in isolation without a model side effect, stop and report — do not work
  around it by re-implementing the function (re-implementation risks document
  drift, which defeats the ticket's purpose).
- **STOP if a required pool member's text fields are in neither
  `candidates.jsonl` nor `data/movies_clean.csv`** — record which `tmdb_id`
  is missing and stop rather than guessing the document text.
- **STOP and report `inconclusive`** rather than overstating the evidence. A
  weak or contradictory result is a valid outcome; do not force a specific
  `failure_mode`.
- **STOP if the analysis would require recomputing a reranker score** — scores
  come from the DECOMP-01 artifact only. Needing a model means the question
  belongs to RERANK-02, not RERANK-01.
- **STOP if a deterministic arm's stage ranks in the DECOMP-01 artifact
  contradict `localization.json`** — report the divergence; do not proceed on
  inconsistent inputs.

### 3.13 Commit policy

- Commit **only after** `compileall` and `unittest discover` pass **and**
  `rerank_failure_q05_q10.py` has produced the artifact.
- **One** checkpoint commit. `git add` exactly the tracked deliverables:
  `eval/scripts/rerank_failure_q05_q10.py`,
  `eval/tests/test_rerank_failure_q05_q10.py`,
  `docs/superpowers/reports/rerank-01-q05-q10.md`,
  `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
- Commit message: `eval: characterize q05 q10 cross-encoder failure (RERANK-01)`.
- **Gitignored-artifact decision (confirm with the Human before committing):**
  `analysis/rerank_failure/q05_q10_reranker_characterization.json` lives under
  the gitignored `eval/runs/` tree. DECOMP-01 left its equivalent artifact
  uncommitted; QL-01 / HY-FIX-02B/03/04 force-added theirs with `git add -f`.
  Recommendation: **confirm with the Human** whether to `git add -f` this one
  file. Either way the artifact must exist on disk for review.
- **No `src/*` file is ever staged.** `graphify-out/` is never staged.

### 3.14 Dependencies

- DECOMP-01 artifact present and path-verified:
  `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`.
- `candidates.jsonl` and `data/movies_clean.csv` present.
- The project venv (`./venv/Scripts/python.exe`) — needed for `eval/scripts`
  imports. **No GPU, no models, no Ollama, no network.**

### 3.15 Risk

**Low.** Hermetic analysis — no model, no GPU, no `src` edit, no label change.
The only `src` interaction is a read-only import of a pure function. The risk
is limited to mis-attributing a loss stage; the per-arm stage table and the
explicit `inconclusive` exit mitigate it.

### 3.16 Reviewer

Codex self-review is sufficient for RERANK-01 mechanics on this branch (no
`src/*` edit, no label change, hermetic). Claude is the recommended
architecture reviewer for the `failure_mode` classification before RERANK-02 is
scoped. External review (Gemini / ChatGPT / Human) is optional and
non-blocking. Gate discipline: any review must cite concrete artifact values,
not the reported summary.

---

## 4. RERANK-01 first Codex-ready prompt

> Implement ticket RERANK-01 per
> `docs/superpowers/plans/2026-05-22-rerank-01-cross-encoder-failure-characterization.md`
> (Section 3). Create only these files:
> `eval/scripts/rerank_failure_q05_q10.py`,
> `eval/tests/test_rerank_failure_q05_q10.py`,
> `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_reranker_characterization.json`,
> `docs/superpowers/reports/rerank-01-q05-q10.md`; and append a RERANK-01
> checkpoint to `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
>
> Build a HERMETIC characterization runner — no model, no GPU, no LLM, no
> Ollama, no network. It imports only stdlib, `eval.scripts._run_io`, and the
> single pure function `build_movie_document` from `src.retrieval.reranker`
> (read-only import; do not import or call `rerank` or `get_reranker`). It must
> NOT edit `src/*` and must NOT recompute any reranker score.
>
> For q05 (Thanatomorphose, tmdb 144204) and q10 ([REC]), for both
> deterministic arms (`pinned`, `no_llm`): read the reranker scores and all
> stage ranks from the DECOMP-01 artifact
> `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
> (`per_qid[].arms[].extended_pool_rows[]`, `arms[].rerank_query`). For the
> gold target and every false positive that ranks above the target in the
> rerank stage, reconstruct the exact `(rerank_query, document_text)` pair by
> calling `build_movie_document` on the movie's text fields — sourced first
> from `eval/runs/2026-05-19-1846-nogit/candidates.jsonl`, falling back to
> `data/movies_clean.csv` keyed by `tmdb_id`. Compute, per arm: the target's
> `rerank_score`/`rerank_rank`; each false positive's `rerank_score`,
> `rerank_rank`, and `rerank_score_gap_vs_target`; the document-field
> composition (title/genres/tagline/overview/keywords present-or-empty,
> `overview_chars`, `overview_truncated`, `keywords_truncated`,
> `document_text_len`) for the target and each false positive; and a
> stage-disagreement attribution (`rrf_recall` / `reranker` / `final_blend`)
> with a `reranker_demoted_well_retrieved_target` flag. Note that the `no_llm`
> arms are the clean reranker signal (target well-retrieved upstream yet
> demoted by the cross-encoder); the `pinned` arms mix an RRF recall-depth loss
> and a final-blend loss already characterized by DECOMP-01 — attribute those
> correctly and do not relabel them as reranker losses.
>
> End the artifact with `failure_mode.classification` set to exactly one of
> `document_text_degenerate`, `metadata_genre_mismatch`,
> `query_document_semantic_gap`, `model_capability_limit_hypothesis`,
> `stage_disagreement_only`, `mixed`, `inconclusive` — with
> `failure_mode.evidence[]` citing concrete artifact values and
> `failure_mode.recommended_followup` describing a RERANK-02 model-backed
> what-if scope. Do not overstate: `model_capability_limit_hypothesis`,
> `mixed`, and `inconclusive` are valid outcomes.
>
> Ship unit tests for the pure functions (document-field analysis, score-gap
> computation, stage-disagreement attribution, failure-mode classification) on
> offline fixtures, including a test asserting the script instantiates no
> reranker model. Run all validation commands and paste their output:
> `./venv/Scripts/python.exe -m compileall eval/scripts`;
> `./venv/Scripts/python.exe -m unittest discover -s eval/tests`;
> `./venv/Scripts/python.exe -m eval.scripts.rerank_failure_q05_q10 --run 2026-05-19-1846-nogit`;
> `git diff --name-only -- src/` (must be empty). Commit only after validation
> passes, with message
> `eval: characterize q05 q10 cross-encoder failure (RERANK-01)`, staging only
> the script, test, report, and ledger — confirm with the Human whether to
> `git add -f` the gitignored
> `analysis/rerank_failure/q05_q10_reranker_characterization.json` artifact.
> Never stage `src/*` or `graphify-out/`.
>
> Hard stops: stop before any `src/*` edit; stop if importing
> `src.retrieval.reranker` loads a model or opens a network/Ollama connection
> (do not re-implement `build_movie_document` as a workaround); stop if a
> required pool member's text fields are in neither `candidates.jsonl` nor
> `movies_clean.csv`; stop and report `inconclusive` rather than overstating.
> Phase 5 remains BLOCKED — RERANK-01 does not start Phase 5 and does not write
> a Phase 5 plan. Append the RERANK-01 ledger checkpoint with files changed,
> commands, validation results, the `failure_mode` classification, and the next
> action.

---

## 5. RERANK-02 — placeholder (not specified here)

**RERANK-02 is intentionally left unspecified.** Its scope — a model-backed
cross-encoder what-if — depends on RERANK-01's `failure_mode.classification`:

- `document_text_degenerate` → RERANK-02 re-scores the target with a repaired
  document representation and measures the rank change.
- `metadata_genre_mismatch` → RERANK-02 ablates Genres / Keywords from the
  document and measures the effect on target vs false positives.
- `query_document_semantic_gap` → RERANK-02 tests alternative `rerank_query`
  formulations.
- `model_capability_limit_hypothesis` → RERANK-02 compares `bge-reranker-v2-m3`
  against an alternative cross-encoder on the same pairs.
- `stage_disagreement_only` / `inconclusive` → re-open the stage attribution;
  RERANK-02 may not be the right next ticket.

RERANK-02 will be a model-backed (GPU) ticket and must be written as its own
separately-gated plan with allowed/forbidden files, a recorded cost/time
budget, validation commands, and a stop condition — exactly as DECOMP-01 was.
**RERANK-02 is not authored or dispatched by this plan.**

---

## 6. Phase 5 status

**Phase 5 remains BLOCKED and must not start.** RERANK-01 is investigation, not
implementation. Even a `failure_mode` that points clearly at a cause does
**not** unblock Phase 5: a fix must still be *proven safe* (rescues the target
with bounded collateral) by a model-backed ticket, and Phase 5 itself requires
its own separately-gated plan. Nothing in RERANK-01 authorizes a `src/*` edit.

---

## 7. Self-review — coverage against the requested scope

- Next investigation ticket after DECOMP-01 — `RERANK-01`, Section 2 Q1 + 3. ✓
- Evidence needed to understand the reranker failure — Section 2 Q2 (4 items,
  all hermetic). ✓
- Should the next ticket compare the six candidate analyses — Section 2 Q3
  (table: 1/2/6 core, 3 observation, 4 hypothesis, 5 → RERANK-02). ✓
- Next ticket fully defined — Section 3: ticket id (3.1), objective (3.2),
  allowed files (3.4/3.5), forbidden files (3.7), exact Codex prompt (Section
  4), commands (3.9), validation checks (3.8), report format (3.11), stop
  condition (3.12), commit policy (3.13). ✓ All nine CLAUDE.md Codex-handoff
  fields present (goal, files-to-change, files-to-read, acceptance,
  validation, dependencies 3.14, risk 3.15, reviewer 3.16, Codex prompt). ✓
- Phase 5 remains BLOCKED, must not start — gate banner + Section 6. ✓
- No `src/*` edit — enforced in 3.7, 3.8, 3.12; this plan writes only a doc. ✓
- Codex not dispatched — this plan stops at the prompt; nothing is run. ✓
- Plan file written under `docs/superpowers/plans/`. ✓
