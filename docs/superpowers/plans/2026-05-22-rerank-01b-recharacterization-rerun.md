# RERANK-01B — RERANK-01 Re-Run on the Repaired Text Snapshot (q05, q10)

Status: READY FOR CODEX — not yet implemented
Date: 2026-05-22
Owner: Codex automation (RERANK-01B ticket) + Claude (gate/review)
Branch: `automation/cinematch-accuracy-audit-full`
Mode: analysis-only · hermetic (no model, no GPU, no network, no embedder)
Predecessors: DECOMP-01 (`7a52bfc`); RERANK-01 INCOMPLETE (`1037096`);
RERANK-01A (`f538b41`, gate-review PASS).

---

## GATE BANNER — read first

**Phase 5 (any `src/*` accuracy change) remains BLOCKED.**

RERANK-01B completes the RERANK-01 characterization that was left
`inconclusive` only because of the now-repaired text-source gap. It is
hermetic analysis. It **does not** edit `src/*`, run any model, or start
Phase 5. RERANK-02 stays blocked until RERANK-01B is reviewed.

---

## 1. Why RERANK-01B exists

RERANK-01 (`1037096`) returned `failure_mode=inconclusive` /
`analysis_complete=False` because 4 q05 false-positive document texts could not
be reconstructed — its `tmdb_id`-keyed lookup against `candidates.jsonl` +
`movies_clean.csv` failed for BM25-only pool members (whose DECOMP-01 `tmdb_id`
is actually a `movies_clean.csv` row index).

RERANK-01A (`f538b41`) fixed the data side: it produced a hermetic,
**movie_key-keyed** snapshot
`eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_text_snapshot.json`
(`schema_version: rerank-01a-text-snapshot.v1`) that resolves **all 268**
q05/q10 extended-pool members (both arms), each with a verified `movie_key`,
the exact reconstructed `document_text`, and a `document_fields` composition.

RERANK-01B is the small, focused rewire: make `rerank_failure_q05_q10.py`
consume that snapshot instead of `candidates.jsonl` + `movies_clean.csv`, and
re-run to a **complete** (`analysis_complete=True`), non-`inconclusive`
characterization.

---

## 2. Ticket RERANK-01B — full Codex handoff

### 2.1 Ticket id

`RERANK-01B`

### 2.2 Goal / Objective

Rewire `eval/scripts/rerank_failure_q05_q10.py` so it resolves each q05/q10
pool member's document text by **`movie_key`** from the RERANK-01A snapshot
(never by `tmdb_id` from `candidates.jsonl`/`movies_clean.csv`), then re-run it
to produce a **complete** q05/q10 cross-encoder characterization with an
explicit, evidenced `failure_mode` classification.

"Done" means: the regenerated
`analysis/rerank_failure/q05_q10_reranker_characterization.json` has
`analysis_complete=True`, `unresolved_text_members=[]`, and a `failure_mode`
that is **not** `inconclusive` *unless* the now-complete evidence genuinely
supports no single classification; unit tests pass; `compileall` passes;
`git diff --name-only -- src/` is empty.

### 2.3 Method

Modify `rerank_failure_q05_q10.py`:

1. **Replace the text-source inputs.** Remove the `candidates.jsonl` and
   `data/movies_clean.csv` loads and the `tmdb_id`-keyed
   `resolve_movie_text_fields` logic. Add a load of the RERANK-01A snapshot
   `analysis/rerank_failure/q05_q10_text_snapshot.json`; assert its
   `schema_version == "rerank-01a-text-snapshot.v1"` and
   `analysis_complete == true` (if the snapshot is itself incomplete, STOP —
   do not proceed on partial data).
2. **Index the snapshot** by `(qid, arm, movie_key)` → member record. Each
   member record already carries `document_text`, `document_fields`,
   `source_stage`, `id_semantics`, `stage_ranks`, `stage_scores`.
3. **Resolve every characterized candidate by `movie_key`.** For the gold
   target and each false positive above it (the existing selection logic in
   `characterize_arm` is unchanged — it still reads pool membership and
   reranker scores from the DECOMP-01 artifact), look up the document text via
   the snapshot's `movie_key`. The DECOMP-01 `extended_pool_rows[]` carry
   `movie_key`, so the join key is available on both sides. **Do not re-derive
   `document_text`** — consume the snapshot's value verbatim (it already
   encodes the stage-dependent assembly: BM25-only members use
   `overview[:500]` + `genres_clean`; semantic members use full Chroma
   metadata).
4. **Keep** the reranker scores, stage ranks, score-gap, and
   stage-disagreement logic reading from the DECOMP-01 artifact as today —
   RERANK-01B changes only the *document-text source*, not the score source.
5. **Record `source_stage`** per characterized candidate in the artifact (from
   the snapshot) so the failure-mode reasoning can distinguish BM25-only from
   semantic-sourced documents.
6. **Re-run** and let the existing `classify_failure_mode` produce a
   classification on the now-complete data. Do not hard-code or force the
   outcome.
7. **Update** the unit tests in `test_rerank_failure_q05_q10.py` for the new
   snapshot-based resolution (replace any `candidates.jsonl`/`movies_clean`
   fixtures with snapshot fixtures); keep the no-model assertion test.

### 2.4 Files to MODIFY (allowed)

- `eval/scripts/rerank_failure_q05_q10.py` — snapshot-based text resolution.
- `eval/tests/test_rerank_failure_q05_q10.py` — tests for the new resolution.
- `docs/superpowers/reports/rerank-01-q05-q10.md` — regenerated by the re-run.
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — append the RERANK-01B
  checkpoint.

### 2.5 Files REGENERATED (data artifact, gitignored)

- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_reranker_characterization.json`
  — overwritten by the re-run. Gitignored under `eval/runs/`; left on disk,
  not force-added.

### 2.6 Files to READ but not change

- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_text_snapshot.json`
  — the RERANK-01A snapshot (the new text source).
- `eval/scripts/rerank_text_snapshot.py` — read for the snapshot schema.
- `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
  — reranker scores and stage ranks (unchanged source).
- `eval/scripts/_run_io.py` — run-path helpers.

### 2.7 Files FORBIDDEN

- `src/**` — **no edits.** RERANK-01B remains hermetic; importing the pure
  `build_movie_document` is no longer needed (text comes from the snapshot)
  but a read-only import is tolerated if a test still uses it.
- Any model / embedder / GPU / Ollama / network call.
- `eval/scripts/rerank_text_snapshot.py` and the snapshot artifact — read-only.
- `eval/scripts/decomp_pool_q05_q10.py` and the DECOMP-01 artifact — read-only.
- `eval/queries/**`, any `*_labels.jsonl`, anything q07.

### 2.8 Acceptance criteria

1. `rerank_failure_q05_q10.py` resolves document text **only** by `movie_key`
   from the RERANK-01A snapshot. It no longer reads `candidates.jsonl` or
   `data/movies_clean.csv`. It remains hermetic — no model/embedder/GPU/
   network.
2. The regenerated `q05_q10_reranker_characterization.json` has
   `analysis_complete == true` and `unresolved_text_members == []`.
3. Every characterized candidate (target + false positives above it, both arms,
   q05 and q10) carries a non-null `document_text` and `document_fields`, plus
   `source_stage`.
4. `failure_mode.classification` is set with cited `evidence[]`. It must not be
   `inconclusive` unless the now-complete evidence genuinely supports no single
   classification — and if `inconclusive` is still emitted, the report must
   state precisely why the *complete* data is still ambiguous.
5. `compileall` passes; `unittest discover -s eval/tests` passes (≥ 207
   baseline, adjusted for changed RERANK-01 tests); `git diff --name-only --
   src/` is empty.
6. The report `rerank-01-q05-q10.md` is regenerated and internally consistent
   with the new artifact.

### 2.9 Validation commands

```powershell
git status --short --branch
./venv/Scripts/python.exe -m compileall eval/scripts
./venv/Scripts/python.exe -m unittest discover -s eval/tests
./venv/Scripts/python.exe -m eval.scripts.rerank_failure_q05_q10 --run 2026-05-19-1846-nogit
git diff --name-only -- src/
```

Expected: `compileall` clean; tests OK; the runner prints
`analysis_complete=True`, `unresolved_text_members=0`, a non-`inconclusive`
`failure_mode` (or a justified `inconclusive`), `phase5_gate=blocked`;
`git diff -- src/` empty.

### 2.10 Dependencies

- RERANK-01A snapshot present with `analysis_complete=true`.
- DECOMP-01 artifact present.
- Project venv. **No GPU, no models, no Ollama, no network.**

### 2.11 Risk

**Low.** A localized rewire of one eval script's text-source layer; the score
logic is untouched; hermetic; no `src` edit. The main risk — a wrong
`movie_key` join — is bounded: the snapshot's keys were each verified against
DECOMP-01 in RERANK-01A, and a missing key must STOP, not guess.

### 2.12 Stop conditions

- STOP before any `src/*` edit.
- STOP if the RERANK-01A snapshot is missing, has the wrong `schema_version`,
  or reports `analysis_complete=false`.
- STOP if any characterized candidate's `movie_key` is absent from the
  snapshot — record it; do not fall back to `tmdb_id` or guess.
- STOP if a model/embedder/GPU/network call would be needed.
- STOP if Codex would edit a file outside Section 2.4.

### 2.13 Commit policy

- Commit **only after** `compileall` and `unittest discover` pass **and** the
  re-run reports `analysis_complete=true`.
- One checkpoint commit. `git add` exactly: `eval/scripts/rerank_failure_q05_q10.py`,
  `eval/tests/test_rerank_failure_q05_q10.py`,
  `docs/superpowers/reports/rerank-01-q05-q10.md`,
  `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
- Commit message: `eval: complete q05 q10 reranker characterization (RERANK-01B)`.
- The regenerated `q05_q10_reranker_characterization.json` is gitignored —
  leave on disk, **do not `git add -f`**. It must exist on disk for review.
- **Never stage `src/*` or `graphify-out/`.**

### 2.14 Reviewer

Codex self-review for mechanics; Claude gate-reviews RERANK-01B (the completed
characterization + `failure_mode`) before any RERANK-02 scoping.

---

## 3. Codex-ready prompt — RERANK-01B

> Implement ticket RERANK-01B per
> `docs/superpowers/plans/2026-05-22-rerank-01b-recharacterization-rerun.md`
> (Section 2). Modify only: `eval/scripts/rerank_failure_q05_q10.py`,
> `eval/tests/test_rerank_failure_q05_q10.py`,
> `docs/superpowers/reports/rerank-01-q05-q10.md` (regenerated by the re-run),
> and append a RERANK-01B checkpoint to
> `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`. Do not edit any other
> file. Do not edit `src/*`.
>
> Rewire `rerank_failure_q05_q10.py` so it resolves each q05/q10 pool member's
> document text by `movie_key` from the RERANK-01A snapshot
> `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_text_snapshot.json`
> (`schema_version: rerank-01a-text-snapshot.v1`) — never by `tmdb_id` from
> `candidates.jsonl` or `data/movies_clean.csv`. Remove those two inputs and
> the `tmdb_id`-keyed resolution. Assert the snapshot's `schema_version` and
> `analysis_complete=true`; STOP if the snapshot is incomplete. Index the
> snapshot by `(qid, arm, movie_key)`; each member already carries
> `document_text`, `document_fields`, `source_stage`, `stage_ranks`,
> `stage_scores`. Keep the existing pool-membership selection and all reranker
> score / stage-rank / score-gap / stage-disagreement logic reading from the
> DECOMP-01 artifact unchanged — RERANK-01B changes ONLY the document-text
> source. Consume the snapshot's `document_text` verbatim; do not re-derive it
> (it already encodes stage-dependent assembly). Record `source_stage` per
> characterized candidate in the artifact.
>
> Re-run the script and let the existing `classify_failure_mode` produce a
> classification on the now-complete data — do not hard-code or force the
> outcome. The regenerated
> `analysis/rerank_failure/q05_q10_reranker_characterization.json` must have
> `analysis_complete=true` and `unresolved_text_members=[]`. The
> `failure_mode` must carry cited evidence and must not be `inconclusive`
> unless the complete data genuinely supports no single classification (if so,
> the report must explain precisely why). Update
> `test_rerank_failure_q05_q10.py` for the snapshot-based resolution (replace
> `candidates.jsonl`/`movies_clean` fixtures with snapshot fixtures; keep the
> no-model assertion test).
>
> Hermetic — no model, embedder, GPU, Ollama, or network. Run all validation
> commands and paste output: `./venv/Scripts/python.exe -m compileall
> eval/scripts`; `./venv/Scripts/python.exe -m unittest discover -s
> eval/tests`; `./venv/Scripts/python.exe -m eval.scripts.rerank_failure_q05_q10
> --run 2026-05-19-1846-nogit`; `git diff --name-only -- src/` (must be empty).
> Commit only after validation passes AND the re-run reports
> `analysis_complete=true`, with message
> `eval: complete q05 q10 reranker characterization (RERANK-01B)`, staging only
> the script, test, report, and ledger. Leave the regenerated gitignored
> `q05_q10_reranker_characterization.json` on disk — do NOT `git add -f` it.
> Never stage `src/*` or `graphify-out/`.
>
> Hard stops: stop before any `src/*` edit; stop if the snapshot is missing /
> wrong-schema / incomplete; stop if any characterized candidate's `movie_key`
> is absent from the snapshot (record it, do not guess or fall back to
> `tmdb_id`); stop if a model/embedder/GPU/network call would be needed; stop
> if you would edit a file outside the ticket's allowed list. Phase 5 remains
> BLOCKED. Append the RERANK-01B ledger checkpoint with files changed,
> commands, validation results, the `failure_mode` classification, and the
> next action.

---

## 4. After RERANK-01B (not part of this ticket)

- **Claude gate-review** of RERANK-01B — the completed characterization and its
  `failure_mode`.
- **RERANK-02** plan — authored **only if** RERANK-01B's evidence supports a
  model-backed what-if (its scope is shaped by the `failure_mode`, per the
  RERANK-01 plan Section 5 mapping). If RERANK-01B is `inconclusive` or points
  away from the cross-encoder, RERANK-02 is not the next ticket.

**Phase 5 remains BLOCKED throughout.** No `src/*` edit until a separate
Phase 5 plan is authored and reviewed READY.

---

## 5. Self-review — coverage

- Re-run RERANK-01 on the repaired snapshot — Section 2.2/2.3. ✓
- Snapshot consumed by `movie_key`, no `tmdb_id` fallback — 2.3, 2.8.1, 2.12. ✓
- Complete, non-`inconclusive` characterization as the goal — 2.2, 2.8.2/4. ✓
- Ticket fully defined: id, goal, allowed/forbidden files, Codex prompt,
  commands, validation, stop conditions, commit policy — Sections 2-3. ✓
- Hermetic; no `src/*` edit; Phase 5 BLOCKED. ✓
