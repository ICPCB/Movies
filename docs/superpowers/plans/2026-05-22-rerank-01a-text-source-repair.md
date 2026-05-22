# RERANK-01A — Hermetic Document-Text Source Repair (q05, q10)

Status: READY FOR CODEX — not yet implemented
Date: 2026-05-22
Owner: Codex automation (RERANK-01A ticket) + Claude (gate/review)
Branch: `automation/cinematch-accuracy-audit-full`
Mode: analysis-only · hermetic (no model, no GPU, no network, no embedder)
Predecessors: DECOMP-01 (`7a52bfc`); RERANK-01 INCOMPLETE checkpoint (`1037096`)
Unblocks: a complete re-run of RERANK-01; then (conditionally) RERANK-02.

---

## GATE BANNER — read first

**Phase 5 (any `src/*` accuracy change) remains BLOCKED.**

RERANK-01A is a hermetic **data-repair** ticket. It produces a trustworthy
movie-text snapshot and a root-cause diagnosis. It **does not** edit `src/*`,
run any model, or start Phase 5. RERANK-02 stays blocked until RERANK-01 is
re-run to completion on this snapshot.

---

## 1. Why RERANK-01A exists — the root cause (already diagnosed)

RERANK-01 returned `failure_mode=inconclusive` / `analysis_complete=False`
because 4 q05 false-positive document texts could not be reconstructed from
`candidates.jsonl` + `data/movies_clean.csv` keyed by `tmdb_id`. The gate
review investigated and found the **root cause** — verified against `src`:

**The pipeline uses two different `id` semantics depending on the retrieval
stage that surfaced a candidate.**

- **Semantic stage** (`src/retrieval/semantic.py:74-108`): the movie dict's
  `id` is the **real TMDB id**, parsed from the Chroma document id
  `tmdb_{tmdb_id}` (`semantic.py:79-80`). Text fields come from the **Chroma
  collection `movies` metadata** (`overview`, `genres`, `keywords`, `tagline`).
- **BM25 stage** (`src/retrieval/bm25.py:163-187`): the movie dict's `id` is
  `int(idx)` — the **0-based pandas DataFrame row index** into
  `data/movies_clean.csv` (`bm25.py:168-169`). It is **not** a TMDB id. Text
  fields come from the CSV row, with `overview` pre-truncated to 500 chars and
  `genres`/`keywords` taken from the `genres_clean`/`keywords_clean` columns.
- **RRF fusion** (`src/retrieval/fusion.py`) keys on `movie_key` (title+year).
  For a candidate found by **both** stages, the semantic dict is copied first
  (`fusion.py:50`) and the BM25 side only **fills empty fields**
  (`fusion.py:65-73`) — so `id` and the text fields stay **semantic**. For a
  **BM25-only** candidate the entry is the BM25 dict, so `id` is a row index.

DECOMP-01 recorded whatever `id` each pool member carried and labelled the
field `tmdb_id`. **That label is a misnomer for BM25-only members** — for them
`tmdb_id` is a `movies_clean.csv` row index.

**Confirmed evidence** (the 4 unresolved q05 false positives — all
`semantic_rank=null`, BM25-only):

| DECOMP `tmdb_id` | DECOMP title | `movies_clean.csv` **row index** | real TMDB id (CSV `id` col) at that row |
|---:|---|---|---:|
| 8353  | Supernova                              | row 8353 = "Supernova" ✓ | 10384 |
| 24218 | The Bold, the Corrupt and the Beautiful | row 24218 = exact match ✓ | 478804 |
| 21993 | On the Job                             | row 21993 = exact match ✓ | 190754 |
| 25394 | Posse                                  | row 25394 = exact match ✓ | 45874 |

The "tmdb 8353 → Limite" mismatch RERANK-01 reported is explained: TMDB id 8353
*is* "Limite" (a real movie in both the CSV `id` column and Chroma as
`tmdb_8353`), but DECOMP-01's `8353` was a **row index** pointing at
"Supernova". RERANK-01's title cross-check correctly caught and refused it — it
produced no wrong data.

**Authoritative source per stage** (the corpus the pipeline actually reads):

- Semantic-sourced member → **Chroma collection `movies`** in
  `data/chroma_bgem3` (count 27,762), fetched by `tmdb_{id}`.
- BM25-only member → **`data/movies_clean.csv`** (27,762 rows), fetched by
  **positional row index** `iloc[id]`.

Chroma `.get()` is a pure metadata read — **no embedder, no GPU, no network.**
Both sources are repo-local. RERANK-01A is therefore fully hermetic.

---

## 2. Ticket RERANK-01A — full Codex handoff

### 2.1 Ticket id

`RERANK-01A`

### 2.2 Goal / Objective

Produce a hermetic, **trustworthy, complete** movie-text snapshot for every
extended-rerank-pool member of q05 and q10 (both deterministic arms) by
resolving each member through the **stage-correct** id semantics, so that
RERANK-01 can be re-run to a complete (`analysis_complete=True`),
non-`inconclusive` characterization. The ticket also records a root-cause
diagnosis (the dual id-semantics defect and the tmdb-8353 reconciliation).

"Done" means: the snapshot artifact resolves **100%** of q05+q10 extended-pool
members across both arms (`unresolved` empty, `analysis_complete=True`), every
resolved member passes a `movie_key` cross-check against its DECOMP-01 row,
unit tests pass, `compileall` passes, and `git diff --name-only -- src/` is
empty.

### 2.3 Method

A new hermetic script `eval/scripts/rerank_text_snapshot.py`:

1. **Load** the DECOMP-01 artifact
   `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`.
   For q05 and q10, for both arms (`pinned`, `no_llm`), iterate **every**
   `extended_pool_rows[]` member (not only the target / false positives — the
   whole pool, so the snapshot is reusable by RERANK-02).
2. **Open the Chroma collection read-only**:
   `chromadb.PersistentClient(path=CHROMA_DIR).get_collection(COLLECTION_NAME)`
   using `CHROMA_DIR` / `COLLECTION_NAME` from `src.config`. Use only
   `collection.get(ids=[...], include=["metadatas"])` — **never** `.query()`,
   never `get_embedder`, never the embedder model.
3. **Load** `data/movies_clean.csv` with `pandas.read_csv(MOVIES_CSV)` — the
   same call `bm25._load()` makes — so `df.iloc[id]` matches the pipeline's
   row indexing exactly.
4. **Resolve each pool member, stage-aware:**
   - **Semantic-sourced** (`semantic_rank` is not `null`): `id` = the DECOMP
     `tmdb_id` value, interpreted as a **real TMDB id**. Fetch Chroma
     `tmdb_{id}` metadata. Build the movie dict with the **semantic field
     recipe** (Section 2.4). `id_semantics = "tmdb_id"`,
     `resolved_from = "chroma:movies"`. Source stage is `"semantic+bm25"` if
     `bm25_rank` is also set, else `"semantic"`.
   - **BM25-only** (`semantic_rank` is `null` and `bm25_rank` is not `null`):
     `id` = the DECOMP `tmdb_id` value, interpreted as a **`movies_clean.csv`
     0-based row index**. Fetch `df.iloc[id]`. Build the movie dict with the
     **BM25 field recipe** (Section 2.4). `id_semantics = "movies_clean_row_index"`,
     `resolved_from = "movies_clean.csv:iloc"`, source stage `"bm25_only"`.
   - **Neither rank set**: a pool member must come from at least one stage —
     record it `unresolved` with reason `no_source_stage` (a stop condition).
5. **Reconstruct the document.** Import the **pure** functions
   `build_movie_document` and `get_movie_key` from `src.retrieval.reranker` /
   `src.utils.dedup` (read-only imports — no model). Compute
   `document_text = build_movie_document(movie_dict)` and a `document_fields`
   composition (fields present/empty, `overview_chars`, `overview_truncated`,
   `keywords_truncated`, `document_text_len`, `document_degenerate`).
6. **Cross-check.** Compute `get_movie_key(movie_dict)` and require it to equal
   the DECOMP-01 row's `movie_key`. On mismatch, mark the member `unresolved`
   with reason `movie_key_mismatch` and record both keys — do **not** emit a
   guessed snapshot row.
7. **Write** the snapshot JSON and the diagnosis report.

### 2.4 Field recipes — reconstruct EXACTLY as the pipeline does

These must match `src` byte-for-byte; cite the source lines in code comments.

**Semantic recipe** (mirror `src/retrieval/semantic.py:89-106`), from Chroma
metadata `meta`:

```
title        = meta.get("title", "")
release_date = str(meta.get("release_date", ""))
year         = _derive_year(meta)          # semantic.py:20-30 logic
genres       = meta.get("genres", "")
overview     = meta.get("overview", "")
keywords     = meta.get("keywords", "")
tagline      = meta.get("tagline", "")
```

**BM25 recipe** (mirror `src/retrieval/bm25.py:169-185`), from the pandas row
`row = df.iloc[id]`:

```
title        = str(row["title"])
release_date = str(row.get("release_date", ""))
year         = _derive_year(row)           # bm25.py:92-102 logic
genres       = str(row.get("genres_clean", row.get("genres", "")))
overview     = str(row.get("overview", ""))[:500]      # NOTE the [:500]
keywords     = str(row.get("keywords_clean", "") or "")
tagline      = str(row.get("tagline", "") or "")
```

`build_movie_document` (`src/retrieval/reranker.py:38-66`) then truncates
`overview` to 600 and `tagline`/`keywords` to 200 — apply it unchanged via the
imported function; do not re-implement it.

`_derive_year` differs in input type between the two stages; replicate both
small helpers locally (they are pure, ~10 lines each) rather than importing
private `src` functions.

### 2.5 Files to CREATE (allowed)

- `eval/scripts/rerank_text_snapshot.py` — the hermetic snapshot builder.
- `eval/tests/test_rerank_text_snapshot.py` — unit tests for the pure
  functions (stage classification, both field recipes, movie_key cross-check,
  coverage/`analysis_complete` logic) on offline fixtures.
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_text_snapshot.json`
  — the trustworthy text snapshot (the RERANK-01-rerun input).
- `docs/superpowers/reports/rerank-01a-text-source-repair.md` — the diagnosis
  + repair report.

### 2.6 Files to MODIFY (allowed)

- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — append the RERANK-01A
  checkpoint.

### 2.7 Files to READ but not change

- `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
  — pool membership, per-member `semantic_rank`/`bm25_rank`/`movie_key`/`title`.
- `data/chroma_bgem3/**` — Chroma store, opened read-only via `.get()`.
- `data/movies_clean.csv` — corpus, read-only.
- `src/retrieval/semantic.py`, `src/retrieval/bm25.py`, `src/retrieval/fusion.py`,
  `src/retrieval/reranker.py`, `src/utils/dedup.py`, `src/config.py` — read to
  mirror the field recipes; import **only** the pure `build_movie_document`,
  `get_movie_key`, and the `CHROMA_DIR`/`COLLECTION_NAME`/`MOVIES_CSV` config
  constants.
- `eval/scripts/_run_io.py` — run-path helpers.
- `eval/scripts/rerank_failure_q05_q10.py` — RERANK-01 runner (the consumer of
  this snapshot); read for the schema it will need.

### 2.8 Files FORBIDDEN

- `src/**` — **no edits.** Only read-only imports of the pure
  `build_movie_document` / `get_movie_key` / config constants are permitted.
- Any model / embedder / GPU / Ollama / network call, and `chromadb` `.query()`
  (which would embed). RERANK-01A uses only `chromadb` `.get()`.
- `eval/queries/**`, any `*_labels.jsonl`, anything q07.
- `eval/scripts/decomp_pool_q05_q10.py` and the DECOMP-01 artifact — read-only.
- `eval/scripts/rerank_failure_q05_q10.py` — **not modified by RERANK-01A.**
  The RERANK-01 re-run that consumes this snapshot is a *separate* step
  (sequence step 6), reviewed on its own.

### 2.9 Acceptance criteria

1. `rerank_text_snapshot.py` is hermetic: imports only stdlib, `pandas`,
   `chromadb`, `eval.scripts._run_io`, and the pure
   `src.retrieval.reranker.build_movie_document` /
   `src.utils.dedup.get_movie_key` / `src.config` constants. It loads no
   model/embedder, makes no GPU/Ollama/network call, and uses only
   `chromadb` `.get()`. A unit test asserts no embedder/`.query()` use.
2. The snapshot resolves **100%** of q05 and q10 extended-pool members across
   both arms; `unresolved` is empty and `analysis_complete` is `true`.
3. Every resolved member carries: `movie_key`, `decomp_id`, `source_stage`
   (`semantic` / `semantic+bm25` / `bm25_only`), `id_semantics`
   (`tmdb_id` / `movies_clean_row_index`), `resolved_from`, the seven text
   fields, `document_text`, and `document_fields`.
4. Every resolved member's `get_movie_key(reconstructed)` equals its DECOMP-01
   row `movie_key` (`movie_key_crosscheck_ok: true` for all).
5. The artifact `diagnosis` block explains the dual id-semantics defect and
   explicitly reconciles tmdb 8353 (DECOMP `8353` = `movies_clean.csv` row
   index → "Supernova"; TMDB id 8353 → "Limite").
6. `python -m compileall eval/scripts` passes; `unittest discover -s
   eval/tests` passes (≥ 201 baseline + new RERANK-01A tests);
   `git diff --name-only -- src/` is empty.
7. The report follows Section 2.11. No Phase 5 work; q07 untouched.

### 2.10 Validation commands

```powershell
git status --short --branch
./venv/Scripts/python.exe -m compileall eval/scripts
./venv/Scripts/python.exe -m unittest discover -s eval/tests
./venv/Scripts/python.exe -m eval.scripts.rerank_text_snapshot --run 2026-05-19-1846-nogit
git diff --name-only -- src/
```

Expected:
- `compileall` — compiles `rerank_text_snapshot.py` with no error.
- `unittest discover` — all OK, count ≥ 201 + new RERANK-01A tests.
- `rerank_text_snapshot` — writes
  `analysis/rerank_failure/q05_q10_text_snapshot.json`; prints
  `analysis_complete=True`, `unresolved=0`, and per-qid coverage counts.
- `git diff --name-only -- src/` — empty.

### 2.11 Report format — `docs/superpowers/reports/rerank-01a-text-source-repair.md`

Markdown, in order: (1) Header — ticket id, timestamp, run, hermetic scope
line. (2) Root cause — the dual id-semantics defect, with the `src` line
references. (3) tmdb 8353 reconciliation. (4) Coverage table — per `(qid,arm)`
member counts and resolved/unresolved. (5) Source-stage breakdown — how many
members resolved via Chroma vs `movies_clean.csv:iloc`. (6) Snapshot location
and the schema RERANK-01's re-run will consume. (7) Phase 5 gate — one line:
`Phase 5 remains BLOCKED.`

### 2.12 Dependencies

- DECOMP-01 artifact present and path-verified.
- `data/chroma_bgem3` Chroma store and `data/movies_clean.csv` present.
- Project venv (`./venv/Scripts/python.exe`) — has `pandas`, `chromadb`,
  `rank_bm25`. **No GPU, no models, no Ollama, no network.**

### 2.13 Risk

**Low.** Hermetic data read + deterministic reconstruction. No model, no GPU,
no `src` edit. The only correctness risk — picking the wrong id semantics — is
caught by the mandatory `movie_key` cross-check (acceptance criterion 4): a
wrong resolution fails the cross-check and is reported `unresolved`, never
emitted as a snapshot row.

### 2.14 Stop conditions

- **STOP before any `src/*` edit.**
- **STOP if a model / embedder / GPU / Ollama / network call would be needed**,
  or if Chroma cannot be read via `.get()` alone.
- **STOP if any q05/q10 extended-pool member cannot be resolved** by the
  stage-correct rule — record the member and reason; do not guess. (If a
  genuine member is in neither Chroma nor `movies_clean.csv`, that is a deeper
  data defect → escalate, do not fabricate.)
- **STOP if a resolved member fails the `movie_key` cross-check** — record both
  keys; do not emit a guessed row.
- **STOP if Codex edits any file outside Section 2.5/2.6.**

### 2.15 Commit policy

- Commit **only after** `compileall` and `unittest discover` pass **and**
  `rerank_text_snapshot.py` produced the snapshot with `analysis_complete=True`.
- **One** checkpoint commit. `git add` exactly: `eval/scripts/rerank_text_snapshot.py`,
  `eval/tests/test_rerank_text_snapshot.py`,
  `docs/superpowers/reports/rerank-01a-text-source-repair.md`,
  `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
- Commit message: `eval: repair q05 q10 reranker text sources (RERANK-01A)`.
- The snapshot JSON lives under the gitignored `eval/runs/` tree — **leave it
  on disk, do not `git add -f`** (it is intermediate tooling output; the
  eventual completed RERANK-01 characterization is the gate evidence). It must
  exist on disk for the RERANK-01A review and the RERANK-01 re-run.
- **Never stage `src/*` or `graphify-out/`.**

### 2.16 Reviewer

Codex self-review for mechanics; Claude gate-reviews RERANK-01A before the
RERANK-01 re-run (sequence step 5). Gate discipline: cite concrete artifact
values.

---

## 3. Codex-ready prompt — RERANK-01A

> Implement ticket RERANK-01A per
> `docs/superpowers/plans/2026-05-22-rerank-01a-text-source-repair.md`
> (Section 2). Create only these files: `eval/scripts/rerank_text_snapshot.py`,
> `eval/tests/test_rerank_text_snapshot.py`,
> `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_text_snapshot.json`,
> `docs/superpowers/reports/rerank-01a-text-source-repair.md`; and append a
> RERANK-01A checkpoint to `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
> Do not modify any other file. Do not edit `src/*`.
>
> Build a HERMETIC text-snapshot runner — no model, no embedder, no GPU, no
> Ollama, no network. It imports only stdlib, `pandas`, `chromadb`,
> `eval.scripts._run_io`, and the pure `build_movie_document`
> (`src.retrieval.reranker`), `get_movie_key` (`src.utils.dedup`), and the
> `CHROMA_DIR` / `COLLECTION_NAME` / `MOVIES_CSV` constants (`src.config`).
> Open Chroma read-only with `chromadb.PersistentClient` +
> `get_collection(COLLECTION_NAME)` and use ONLY `collection.get(ids=...,
> include=["metadatas"])` — never `.query()`, never `get_embedder`.
>
> Root cause (already diagnosed, verified against `src`): the pipeline uses two
> `id` semantics. Semantic-stage candidates (`src/retrieval/semantic.py`) carry
> the real TMDB id (Chroma doc id `tmdb_{id}`) and Chroma-metadata text.
> BM25-only candidates (`src/retrieval/bm25.py:168-169`) carry
> `int(idx)` — a 0-based `movies_clean.csv` pandas row index — and CSV-row
> text. RRF fusion (`src/retrieval/fusion.py:50,65-73`) gives the semantic dict
> precedence, so a candidate found by both stays semantic. DECOMP-01 labelled
> whatever id each pool member carried as `tmdb_id`; that label is a misnomer
> for BM25-only members.
>
> For q05 and q10, for both arms (`pinned`, `no_llm`), iterate EVERY
> `extended_pool_rows[]` member of
> `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`.
> Resolve each member stage-aware: if `semantic_rank` is not null → treat the
> DECOMP `tmdb_id` as a real TMDB id, fetch Chroma `tmdb_{id}` metadata, build
> the movie dict with the semantic field recipe (mirror `semantic.py:89-106`);
> if `semantic_rank` is null and `bm25_rank` is not null → treat the DECOMP
> `tmdb_id` as a `movies_clean.csv` 0-based row index, fetch `df.iloc[id]` from
> `pandas.read_csv(MOVIES_CSV)`, build the movie dict with the BM25 field
> recipe (mirror `bm25.py:169-185`, including `overview[:500]`,
> `genres_clean`, `keywords_clean`). Then compute `document_text =
> build_movie_document(movie_dict)` and a `document_fields` composition. Mark
> `source_stage` (`semantic` / `semantic+bm25` / `bm25_only`), `id_semantics`,
> and `resolved_from` on every member.
>
> Cross-check every resolved member: `get_movie_key(movie_dict)` MUST equal the
> DECOMP-01 row `movie_key`; on mismatch mark the member `unresolved` with
> reason `movie_key_mismatch` and both keys — never emit a guessed row. The
> snapshot must resolve 100% of q05+q10 members (`unresolved` empty,
> `analysis_complete=true`). Include a `diagnosis` block explaining the dual
> id-semantics and reconciling tmdb 8353 (DECOMP `8353` = `movies_clean.csv`
> row index → "Supernova"; TMDB id 8353 → "Limite").
>
> Ship unit tests for the pure functions (stage classification, both field
> recipes, movie_key cross-check, coverage/`analysis_complete`) on offline
> fixtures, including a test asserting no embedder / `.query()` use. Run all
> validation commands and paste output:
> `./venv/Scripts/python.exe -m compileall eval/scripts`;
> `./venv/Scripts/python.exe -m unittest discover -s eval/tests`;
> `./venv/Scripts/python.exe -m eval.scripts.rerank_text_snapshot --run 2026-05-19-1846-nogit`;
> `git diff --name-only -- src/` (must be empty). Commit only after validation
> passes AND the snapshot reports `analysis_complete=true`, with message
> `eval: repair q05 q10 reranker text sources (RERANK-01A)`, staging only the
> script, test, report, and ledger. Leave the gitignored
> `q05_q10_text_snapshot.json` on disk — do NOT `git add -f` it. Never stage
> `src/*` or `graphify-out/`.
>
> Hard stops: stop before any `src/*` edit; stop if a model/embedder/GPU/
> network call would be needed; stop if any q05/q10 pool member cannot be
> resolved or fails the movie_key cross-check (record it, do not guess); stop
> if you would edit a file outside the ticket's allowed list. Phase 5 remains
> BLOCKED. Append the RERANK-01A ledger checkpoint with files changed,
> commands, validation results, coverage counts, and the next action.

---

## 4. After RERANK-01A (not part of this ticket)

- **Step 5 — Claude review** of RERANK-01A before continuing.
- **Step 6 — RERANK-01 re-run** (a *separate*, separately-reviewed change):
  modify `eval/scripts/rerank_failure_q05_q10.py` to consume
  `q05_q10_text_snapshot.json` keyed by `movie_key` instead of
  `candidates.jsonl` + `movies_clean.csv` keyed by `tmdb_id`; re-run to a
  complete, non-`inconclusive` characterization; review again.
- **Step 7 — RERANK-02** plan only if the completed RERANK-01 evidence
  supports it.

**Phase 5 remains BLOCKED throughout.** No `src/*` edit occurs until a separate
Phase 5 plan is authored and reviewed READY.

Note for the RERANK-01 re-run: the exact reranker document is stage-dependent
(BM25-only members use `overview[:500]` + `genres_clean`/`keywords_clean`;
semantic members use full Chroma metadata). The snapshot already encodes this
per member, so the re-run consumes `document_text` directly and must not
re-derive it.

---

## 5. Self-review — coverage against the requested scope

- Root cause identified (authoritative repo-local source actually used) —
  Section 1. ✓
- Resolve the missing q05 false positives — Section 2.3/2.4 (stage-aware
  resolution; BM25-only → `movies_clean.csv` row index). ✓
- Reconcile tmdb 8353 "Supernova" vs "Limite" — Section 1 table + acceptance
  criterion 5 + diagnosis block. ✓
- Produce trustworthy text snapshots for the RERANK-01 re-run — Section 2.3
  step 7 + artifact, with a mandatory `movie_key` cross-check. ✓
- Ticket fully defined: id (2.1), goal (2.2), allowed/forbidden files
  (2.5-2.8), Codex prompt (Section 3), commands (2.10), validation/acceptance
  (2.9), report format (2.11), stop conditions (2.14), commit policy (2.15). ✓
- Hermetic — no model/GPU/network; Chroma read via `.get()` only. ✓
- Phase 5 BLOCKED; no `src/*` edit. ✓
