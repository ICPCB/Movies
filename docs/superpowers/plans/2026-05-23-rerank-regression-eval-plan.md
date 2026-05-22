# RERANK-REGRESSION-EVAL — Full Gold/Silver-Set Reranker-Swap Regression Eval

Status: READY FOR REVIEW — model-backed; **do not dispatch without Human
authorization** (see GATE BANNER).
Date: 2026-05-23
Owner: Claude (plan/architecture) + Codex (implementation, when authorized) +
Human (GPU-run authorization + Phase 5 product decision)
Branch: `automation/cinematch-accuracy-audit-full`
Predecessors: RERANK-02 / RERANK-02B (`f516d15`, decision
`model_capability_confirmed`); RERANK-02-REVIEW (gate-review PASS).
Revision: 2026-05-23 — revised after an advisory external review (Codex CLI;
`docs/superpowers/reviews/rerank-regression-eval-external-ai-review.md`):
applied four internal-consistency fixes (top-15 artifact depth, null-metric
handling, exact q10-fix mode, monkeypatch target + `basic`-mode invariant).

---

## GATE BANNER — read first

**Phase 5 (any `src/*` accuracy change) remains BLOCKED.**

This is the regression-eval gate. RERANK-02 confirmed an alternative
cross-encoder (`Alibaba-NLP/gte-multilingual-reranker-base`) can rescue the q10
gold target into the top-5 on the bounded q05/q10 pool. A `src/*` reranker swap
cannot proceed until a **full gold/silver-set regression eval** proves the swap
does not regress the other 18 queries.

This eval is **model-backed** and requires a **pipeline replay** (retrieval +
RRF pool capture) for all 20 queries. Per the automation rules, that long job
must be Human-authorized with a recorded cost/time budget before it runs.

**This plan does not unblock Phase 5 and does not edit `src/*`.** Even a PASS
verdict from this eval only makes a *Phase 5 plan* eligible to be authored — it
does not by itself authorize a model swap. The model swap is a product-level
architecture decision reserved for the Human.

The plan is authored autonomously; its **execution is deferred to**
`docs/superpowers/MANUAL_REVIEW_QUEUE.md` pending Human authorization.

---

## 1. Why this ticket exists

RERANK-02 (`f516d15`) compared `bge-reranker-v2-m3` (baseline) against two
alternative cross-encoders on the q05/q10 extended pools:

| target / arm | baseline rank0 | Alibaba gte rank0 | MiniLM-L6 rank0 |
|---|---:|---:|---:|
| q05 / no_llm | 5 | 7 | 5 |
| q10 / no_llm | 7 | 1 | 3 |

Decision: `model_capability_confirmed` — the alternative model rescues **q10**
into the top-5. **It does not rescue q05** (Alibaba ranks q05 *worse* than the
baseline). So the candidate swap is, at best, a partial fix.

The open question this ticket answers: **if the production reranker is swapped
from `bge-reranker-v2-m3` to `Alibaba-NLP/gte-multilingual-reranker-base`, does
the full 20-query gold/silver eval improve, hold, or regress?** A swap that
fixes q10 but silently demotes correct answers on other queries is a net loss.

---

## 2. Data-availability constraint (read before designing)

The run directory `eval/runs/2026-05-19-1846-nogit/` does **not** contain the
reranker-input pools needed for an offline full-set re-score:

- `candidates.jsonl` — only the **final top-15 union** per query (220 rows),
  not the rerank-input pool. A reranker swap can lift a candidate from *below*
  the final cut into the top-5, so the final union is insufficient.
- `analysis/decomp/q05_q10_pool_decomposition.json` — pools for **q05/q10 only**.
- `analysis/hybrid_stage_trace/` — traces for **q03/q08 only**.
- The other 16 queries have **no captured rerank pool**.

The reranker (`src/retrieval/reranker.py:rerank`) scores `deduped[:RERANK_TOP_K]`
where `RERANK_TOP_K = 50` (`src/config.py:36`). So the eval needs, for every
query and every mode, that up-to-50-candidate pool with full document fields.
**That requires a pipeline replay** — there is no offline shortcut.

---

## 3. Pipeline facts the harness must respect

From `eval/scripts/run_pipelines.py` and `src/retrieval/reranker.py`:

- `run_pipelines.run()` calls `src.pipelines.{basic,advanced,hybrid}.run(query,
  top_k=15)` per query. Each pipeline does retrieval → fusion → `rerank()`.
- `rerank(query, movies, top_k=FINAL_TOP_K=5, rerank_pool=RERANK_TOP_K=50)`:
  1. `deduped = deduplicate_movies(movies, prefer_score="final_score")`, sorted
     by `final_score` desc; `pool = deduped[:50]`.
  2. `reranker = get_reranker()` (`src/models.py` → `sentence_transformers
     .CrossEncoder("BAAI/bge-reranker-v2-m3", device=_device)`).
  3. `pairs = [[query, build_movie_document(m)] for m in pool]`;
     `scores = reranker.predict(pairs, show_progress_bar=False)`.
  4. **Final blend** per candidate:
     `final_score = rerank_score
        + RERANK_VOTE_COUNT_WEIGHT(0.08) * vote_prior
        + RERANK_UPSTREAM_WEIGHT(0.20) * upstream_prior
        + RERANK_SOURCE_AGREEMENT_BONUS(0.10) * source_agreement`
     where `vote_prior = log1p(vote_count)/max_vote_log`,
     `upstream_prior = upstream_raw/max_upstream`,
     `source_agreement ∈ {0,1}`.
  5. Dedup again, sort by `final_score` desc, return `pool[:top_k]`.
- `build_movie_document(m)` renders title/year/genres/tagline/overview(≤600)/
  keywords(≤200) — this is the **exact** document text the cross-encoder sees.
- The final rank is driven by `final_score`, **not** raw `rerank_score`. The
  harness must reproduce the blend, not just the model score.

LLM-variance note: `advanced`/`hybrid` use LLM query expansion (`llama3.2`),
which is the documented source of hybrid instability (HY-STAB-01). To isolate
the **reranker** effect, the headline comparison must hold retrieval fixed — see
§4 Stage 1.

---

## 4. Harness design — two stages

A new script `eval/scripts/rerank_regression_eval.py`, run-id parameterized.

### Stage 1 — pool capture (`--stage capture`)

Goal: capture, for all 20 queries × 3 modes, the exact pool that `rerank()`
receives, plus per-candidate document fields and the blend inputs
(`vote_count`, `upstream_*`, `semantic_rank`, `bm25_rank`).

Method (no `src/*` edit):

- Wrap the `rerank` symbol **as the pipelines actually call it**.
  `src/pipelines/advanced.py:25` and `src/pipelines/hybrid.py:27` both do
  `from src.retrieval.reranker import rerank`, which binds the name into each
  pipeline module's own namespace — so the eval script must monkeypatch
  `src.pipelines.advanced.rerank` **and** `src.pipelines.hybrid.rerank`
  (patching `src.retrieval.reranker.rerank` alone would be bypassed by the
  already-bound references). `src/pipelines/basic.py` does **not** call the
  reranker. Each wrapper records the `pool`, the `pairs`, and the
  per-candidate blend inputs, then delegates to the real `rerank`. The harness
  must assert each patched name resolved to a real callable before the run.
  Monkeypatching a reference from the eval process is eval-only; it edits no
  `src/*` file.
- Because `basic` mode does not rerank, its metrics are **invariant** under a
  reranker swap — Stage 2 must confirm `basic` baseline and alt metrics are
  identical as a sanity check (any difference means a harness bug).
- Drive the capture with the **deterministic arm**: pin query expansion exactly
  as DECOMP-01 / HY-STAB did (reuse the recorded deterministic-arm queries so
  no live `llama3.2` call is made and retrieval is reproducible). The headline
  eval arm is the deterministic `pinned` arm; this removes LLM variance so the
  only variable between baseline and alt is the reranker model.
- Output: `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/
  full_set_pool_snapshot.json` — schema `rerank-regression-pool.v1`, one entry
  per `(qid, mode)` with the ordered pool, each member's `movie_key`,
  `tmdb_id`, `document_text` (from `build_movie_document`), and blend inputs.

Stage 1 is model-backed (the embedder runs on GPU for retrieval) but invokes
**no** reranker comparison and **no** LLM.

### Stage 2 — dual-model re-score + metric recompute (`--stage score`)

Goal: for every captured pool, compute the final top-k under the baseline model
and under the alternative model, recompute metrics, and compare.

Method (no `src/*` edit):

1. For each `(qid, mode)` pool, score `pairs` with:
   - **baseline** `BAAI/bge-reranker-v2-m3` via `sentence_transformers
     .CrossEncoder` (the same loader `src/models.py` uses), and
   - **alternative** `Alibaba-NLP/gte-multilingual-reranker-base` via the
     RERANK-02B adapter (re-register `position_ids`, `list[tuple]`
     tokenization, `AutoModelForSequenceClassification`,
     `trust_remote_code=True`, fp16 on CUDA).
   Re-scoring the baseline (rather than reusing recorded scores) keeps both
   models on an identical code path; assert the re-scored baseline reproduces
   the recorded q05/q10 ranks within tolerance as a self-check.
2. Apply the **exact §3 final-score blend** to each model's `rerank_score`,
   then rank the full pool by `final_score`. Retain at least the **top-15**
   ranked records per `(qid, mode)` per model — `compute_metrics.py` evaluates
   `@5`, `@10`, and `@15`, so a top-5 list is insufficient for the
   `strict_hit_at_10` headline metric.
3. Recompute metrics with the **existing** `eval/scripts/compute_metrics.py`
   logic (import it; do not fork it) against the **existing**
   `gold_labels.jsonl` + `silver_labels.jsonl` — labels are **read-only**.
4. Output: `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/
   regression_comparison.json` — schema `rerank-regression-comparison.v1`,
   with baseline vs alt metrics per mode, per-query deltas, and the gate
   verdict (§5).
5. Report: `docs/superpowers/reports/rerank-regression-eval.md`.

---

## 5. Mechanical gate criteria (no judgment)

The artifact ends with exactly one `gate_verdict`, computed mechanically:

Headline metrics, per mode (`basic`, `advanced`, `hybrid`): `strict_hit_at_5`,
`strict_hit_at_10`, `mrr_at_5`. Per-query unit: `strict_hit_at_5` hit/miss.
The reranker swap can only move `advanced` and `hybrid` (`basic` does not
rerank — §4); `basic` metrics must come back unchanged, and a non-zero `basic`
delta is itself a `gate_inconclusive` harness-bug signal.

- **`gate_pass`** — ALL of:
  1. No aggregate headline metric regresses in any mode
     (`alt >= baseline` for every metric × mode), within a tolerance of `0.0`
     (exact non-regression; metrics are deterministic).
  2. Per-query `strict_hit_at_5` regressions (hit→miss) summed across all modes
     `== 0`.
  3. The q10 gold target reaches `strict_hit_at_5` under the alt model in the
     **`hybrid` mode** — the mode where the q10 defect was identified (the
     hybrid strict-ranking gap). The intended fix must land in the mode it was
     meant to fix.
- **`gate_fail`** — any aggregate headline metric regresses, OR any per-query
  `strict_hit_at_5` flips hit→miss, OR q10 is not fixed in `hybrid` mode.
- **`gate_inconclusive`** — Stage 1 or Stage 2 could not produce a complete
  artifact (missing pools, model load failure, baseline self-check mismatch,
  non-zero `basic`-mode delta), **or** `compute_metrics.py` returns a `None` /
  null-excluded value for any headline metric in either run (e.g.
  `queries_excluded_null` differs between baseline and alt). An undefined
  metric must never be silently scored as a pass or a fail.

`gate_pass` does **not** unblock Phase 5. It makes a Phase 5 reranker-swap plan
*eligible to be authored and Human-reviewed*. `gate_fail` / `gate_inconclusive`
keep Phase 5 blocked and escalate (see §9).

---

## 6. Codex handoff

### 6.1 Goal
Produce a complete two-stage full-set reranker-swap regression eval with one
mechanical `gate_verdict`. "Done" = both artifacts written and schema-valid;
the report follows §4/§5; `compileall` + `unittest discover` pass;
`git diff --name-only -- src/` empty; expected vs actual cost/time/VRAM
recorded.

### 6.2 Files to CREATE (allowed)
- `eval/scripts/rerank_regression_eval.py`
- `eval/tests/test_rerank_regression_eval.py`
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/full_set_pool_snapshot.json`
- `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/regression_comparison.json`
- `docs/superpowers/reports/rerank-regression-eval.md`

### 6.3 Files to MODIFY (allowed)
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — append the checkpoint(s).

### 6.4 Files to READ but not change
- `eval/scripts/run_pipelines.py`, `eval/scripts/compute_metrics.py`,
  `eval/scripts/rerank_model_comparison.py`, `eval/scripts/_run_io.py`,
  `eval/scripts/_schemas.py`.
- `src/retrieval/reranker.py`, `src/models.py`, `src/config.py`,
  `src/pipelines/*` — **read-only**.
- `eval/runs/2026-05-19-1846-nogit/{candidates.jsonl,gold_labels.jsonl,
  silver_labels.jsonl,metrics.json}`, the DECOMP-01 and RERANK-02 artifacts.

### 6.5 Files FORBIDDEN
- `src/**` — **no edits.** The reranker swap is simulated by an eval-process
  monkeypatch only.
- Any **LLM** call in the scoring path (use the recorded deterministic-arm
  queries; do not call `expand_query` / `llama3.2`).
- `eval/queries/**`, any `*_labels.jsonl`, anything q07,
  `eval/scripts/merge_labels.py`.

### 6.6 Acceptance criteria
1. Stage 1 captures pools for **all 20 queries × 3 modes**; the snapshot
   records each member's `document_text` and blend inputs; a unit test asserts
   the pool-capture wrapper makes no `src/*` file edit.
2. Stage 2 re-scores every pool with baseline + alt and reproduces the §3
   blend; a self-check asserts the re-scored baseline matches the recorded
   q05/q10 ranks within tolerance.
3. Metrics are recomputed via the **imported** `compute_metrics.py` logic
   against the existing labels (labels unmodified — `git diff` proves it).
4. The artifact carries baseline vs alt metrics per mode, per-query
   `strict_hit_at_5` deltas, and exactly one `gate_verdict` from §5 with
   `evidence[]` citing concrete values.
5. `git diff --name-only -- src/` empty; no LLM call in the scoring path.
6. Expected cost/time/VRAM recorded **before** the run, actual **after**.
7. `compileall` passes; `unittest discover -s eval/tests` passes
   (≥ 223 baseline + new tests).

### 6.7 Validation commands
```powershell
git status --short --branch
./venv/Scripts/python.exe -m compileall eval/scripts
./venv/Scripts/python.exe -m unittest discover -s eval/tests
./venv/Scripts/python.exe -m eval.scripts.rerank_regression_eval --run 2026-05-19-1846-nogit --stage capture
./venv/Scripts/python.exe -m eval.scripts.rerank_regression_eval --run 2026-05-19-1846-nogit --stage score
git diff --name-only -- src/
```
GPU run: `ollama serve` with `CUDA_VISIBLE_DEVICES=-1` (keeps `llama3.2` on
CPU; this eval makes no LLM call regardless); use the project venv.

### 6.8 Dependencies
- The deterministic-arm queries from HY-STAB/DECOMP must be present (Stage 1
  reuses them — no live LLM).
- `Alibaba-NLP/gte-multilingual-reranker-base` is already cached locally
  (RERANK-02B, revision `8215cf04918ba6f7b6a62bb44238ce2953d8831c`,
  ~0.59 GB). `BAAI/bge-reranker-v2-m3` is the production model, already cached.
- GPU: 8 GB RTX 4070. Pool re-score peak VRAM in RERANK-02B was < 0.7 GB per
  model; the embedder for Stage 1 retrieval is the larger consumer (~5 GB,
  per DECOMP-01) — run stages sequentially, not concurrently.

### 6.9 Cost/time budget (expected — record actual after)
- Stage 1: 20 queries × 3 modes retrieval replay; expected ≤ 15 min, ≤ 6 GB
  VRAM, `$0.00`, no network.
- Stage 2: ≤ 60 pools × ≤ 50 pairs × 2 models ≈ ≤ 6000 inference pairs;
  expected ≤ 15 min, ≤ 1 GB VRAM, `$0.00`, no network (models cached).
- Hard cap: 60 min total wall clock. STOP and checkpoint if exceeded.

### 6.10 Risk
**Medium-high.** Model-backed pipeline replay; reproduces a non-trivial blend;
its verdict gates a product decision. No `src/*` behavior changes — the swap is
an eval-process monkeypatch. Main risks: monkeypatch fidelity (Stage 1 must
capture the *real* pool), blend-reproduction drift, and metric-recompute
divergence from `compute_metrics.py` — all mitigated by the §6.6.2 baseline
self-check.

### 6.11 Stop conditions
- STOP before any `src/*` edit.
- STOP if the scoring path would make an LLM call.
- STOP if the baseline self-check (§6.6.2) fails — emit `gate_inconclusive`,
  do not proceed to a verdict.
- STOP if a model exceeds the VRAM budget — re-scope, record, or stop.
- STOP if Stage 1 cannot capture all 60 pools — emit `gate_inconclusive`.
- STOP and emit `gate_inconclusive` rather than overstating a `gate_pass`.
- STOP if Codex would edit a file outside §6.2/§6.3.

### 6.12 Commit policy
- Stage 1 and Stage 2 may be separate checkpoint commits.
- `git add` only: `eval/scripts/rerank_regression_eval.py`,
  `eval/tests/test_rerank_regression_eval.py`,
  `docs/superpowers/reports/rerank-regression-eval.md`,
  `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
- The two `analysis/rerank_regression/*.json` artifacts are gitignored under
  `eval/runs/` — leave on disk, do not `git add -f`.
- **Never stage `src/*`, `graphify-out/`, or `codex-rerank02-last.txt`.**

### 6.13 Risk level / Reviewer
- Risk: **medium-high** — model-backed long job whose verdict gates Phase 5.
- Reviewer: Codex self-review for mechanics; **Claude gate-reviews the
  `gate_verdict`**; **Human authorizes the GPU run and owns the Phase 5
  product decision.**

---

## 7. Codex-ready prompt

> **Do not run until the Human has authorized the GPU run (§6.9 budget) and
> confirmed the candidate model `Alibaba-NLP/gte-multilingual-reranker-base`.**
>
> Implement ticket RERANK-REGRESSION-EVAL per
> `docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md` (§4–§6).
> Create only the §6.2 files; append checkpoints to the ledger; do not edit
> `src/*`.
>
> Stage 1 (`--stage capture`): wrap `src.retrieval.reranker.rerank` from the
> eval process to record, for all 20 queries × 3 modes, the exact pool passed
> to the cross-encoder with each member's `document_text`
> (`build_movie_document`) and blend inputs. Drive it with the recorded
> deterministic-arm queries — no live `llama3.2` call. Write
> `full_set_pool_snapshot.json` (schema `rerank-regression-pool.v1`).
>
> Stage 2 (`--stage score`): score every captured pool with the baseline
> `BAAI/bge-reranker-v2-m3` and the alternative
> `Alibaba-NLP/gte-multilingual-reranker-base` (RERANK-02B adapter:
> `position_ids` repair, `list[tuple]` tokenization, fp16 CUDA). Reproduce the
> exact final-score blend from `src/retrieval/reranker.py` (§3). Recompute
> metrics via the imported `compute_metrics.py` against the existing
> gold/silver labels (read-only). Self-check that the re-scored baseline
> reproduces the recorded q05/q10 ranks. Write `regression_comparison.json`
> (schema `rerank-regression-comparison.v1`) ending with one mechanical
> `gate_verdict` (`gate_pass` / `gate_fail` / `gate_inconclusive`, §5) and
> `evidence[]`.
>
> Record expected vs actual cost/time/VRAM. Ship unit tests for the pure
> functions (blend reproduction, metric recompute glue, gate logic) on offline
> fixtures, plus a test asserting no `src/*` edit and no LLM import in the
> scoring path. Run every §6.7 validation command and paste output. Commit
> Stage 1 and Stage 2 as separate checkpoints staging only the script, test,
> report, and ledger. Never stage `src/*`, `graphify-out/`, or
> `codex-rerank02-last.txt`.
>
> Hard stops per §6.11. Phase 5 remains BLOCKED — a `gate_pass` only makes a
> Phase 5 plan eligible to be authored; it does not authorize a model swap.

---

## 8. Scope boundaries — what this ticket is NOT

- **Not** a Phase 5 ticket. It edits no `src/*` and changes no pipeline
  behavior. The reranker swap is simulated only.
- **Not** a q05 fix. RERANK-02 already showed no approved alternative model
  rescues q05; this eval measures whether swapping for q10's sake regresses
  the set. q05 remains a separate (likely upstream / query-expansion)
  investigation.
- **Not** a label or query change. `gold_labels.jsonl`, `silver_labels.jsonl`,
  and `eval/queries/*` are read-only.
- **Not** Human approval. Even a `gate_pass` is mechanical evidence only; the
  swap decision is the Human's.

---

## 9. After the eval — Phase 5 paths

- **`gate_pass`** → the alt model fixes q10 and regresses nothing. A Phase 5
  reranker-swap plan becomes eligible to be authored and Human-reviewed. Phase
  5 stays BLOCKED until that plan is reviewed READY and the Human authorizes it.
- **`gate_fail`** → the swap regresses other queries. Do not swap the model.
  Escalate to a broader reranker/architecture decision; q10 needs a different
  remedy. Phase 5 stays BLOCKED.
- **`gate_inconclusive`** → repair the harness (≤ 3 attempts) or escalate.
  Phase 5 stays BLOCKED.

**No `src/*` edit occurs until a separate Phase 5 plan is authored, reviewed
READY, and Human-authorized.** Phase 5 remains BLOCKED.

---

## 10. Self-review — coverage

- Data-availability gap stated; pipeline replay justified — §2. ✓
- Pipeline + blend facts pinned from source — §3. ✓
- Two-stage harness, no `src/*` edit, no LLM in scoring path — §4. ✓
- Mechanical gate criteria, no judgment — §5. ✓
- Full Codex handoff: goal, allowed/forbidden files, acceptance, validation,
  dependencies, cost/time, risk, stop conditions, commit policy, prompt —
  §6–§7. ✓
- Phase 5 stays BLOCKED; a `gate_pass` does not auto-unblock it — banner, §5,
  §8, §9. ✓
- Execution deferred to the Human via the manual review queue — banner. ✓
