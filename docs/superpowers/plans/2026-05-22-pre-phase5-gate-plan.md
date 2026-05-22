# Pre-Phase-5 Gate Plan — RG-03 review → DECOMP-01 → Phase 5 gate

Status: READY FOR EXECUTION — not yet started
Date: 2026-05-22
Owner: Codex automation (DECOMP-01 ticket) + Claude (gate reviews)
Branch: `automation/cinematch-accuracy-audit-full`
Predecessors: QL-01; RG-03 (A1+A2+A3 complete, closeout commit `c7998c5`)
Extends: `docs/superpowers/plans/2026-05-22-post-ql-01-tracks-a-b.md`

This plan defines **every step between "RG-03 closed" and the Phase 5 gate
decision**. It reaches exactly one of two end states:

- **Phase 5 UNBLOCKED** (ready, not started) — only if DECOMP-01 *proves* a
  safe localized fix.
- **Phase 5 STAYS BLOCKED** — if DECOMP-01 *rules one out* or is
  *inconclusive*; the project then escalates to a broader architecture
  decision.

It contains **no Phase 5 implementation prompts** — see the placeholder at the
end.

---

## 1. Current state summary

- Branch `automation/cinematch-accuracy-audit-full` at `c7998c5`
  (`docs: close out RG-03 q07 regrade`).
- **RG-03 (q07 targeted regrade) — A1 + A2 + A3 complete and closed:**
  - A1 tooling + tests committed `80e53d7`; closeout docs committed `c7998c5`.
  - `check_regrade_sheet` → `complete: true` (55/55 rows filled).
  - `merge_labels` (unmodified) → refreshed `gold_labels.jsonl` (55 gold) and
    `metrics.json` (`provisional: false`) on disk. The `eval/runs/` tree is
    gitignored; those data artifacts are not committed.
  - q07 regrade: 6 of 10 rows changed; all metric deltas are q07-attributable
    and ≥ 0 (no regression). 190 unit tests OK. No `src/*` change.
- **QL-01 classifications stand:** q05 and q10 = `reranker_blend_issue_later_eval`
  (genuine pipeline defects — query/label/expansion sound); q07 =
  `silver_label_issue` (now closed by RG-03).
- **DECOMP-01 (Track B) — not started.**
- **Phase 5 — BLOCKED** pending the gate in this plan.
- Working tree: only `graphify-out/` untracked (pre-existing, unrelated).

---

## 2. Ticket / gate queue up to Phase 5

| # | ID | Type | Owner | Relation to Phase 5 |
|---|----|------|-------|---------------------|
| G1 | `RG-03-REVIEW` | Gate review | Claude (Codex self-review fallback) | Required before merge outside branch |
| T1 | `DECOMP-01` | Codex ticket (model-backed, GPU) | Codex | The gate ticket — produces the decisive evidence |
| G2 | `DECOMP-01-REVIEW` | Gate review | Claude (Codex self-review fallback) | Gates the Phase 5 decision |
| GATE | Phase 5 readiness gate | Decision | Claude + Human | Opens or keeps Phase 5 blocked |

**Independence:** G1 (RG-03 = Track A data correction) and T1 (DECOMP-01 =
Track B instrumentation) are independent and **may run in parallel**. G2
depends on T1. GATE depends on G1, T1, and G2.

G1 and G2 are **review gates, not Codex coding tickets** — they have a review
checklist + evidence commands instead of a Codex prompt. T1 is the only Codex
ticket and is the only one with a Codex prompt (Section 4).

---

## G1 — `RG-03-REVIEW` (review step after RG-03)

### Goal

Independently verify RG-03 stayed in scope before its label change and
recomputed metrics are relied on by any downstream Phase 5 work or merged
outside the branch.

### Why required

RG-03 changed labels and recomputed authoritative metrics — a **private-data
decision** under the automation rules (`CLAUDE.md`). It is **non-blocking to
continue on-branch** (Codex self-review is sufficient to start DECOMP-01) but
**required before merge outside this branch**.

### Reviewer

Claude (architecture reviewer per `CLAUDE.md`). Codex self-review is the
fallback if Claude is unavailable. Gemini / ChatGPT / Human are optional.
Gate discipline (`CLAUDE.md`): the review must cite concrete evidence from
commands, diffs, and artifacts — not reported output alone.

### Review checklist (each item must cite evidence)

1. **Committed footprint is eval-harness only.**
   `git show --stat 80e53d7` and `git show --stat c7998c5` — tooling + tests
   + docs only; no `src/*`.
2. **Only q07 labels changed.** Run:
   ```powershell
   ./venv/Scripts/python.exe -c "import json; load=lambda p:{(r['qid'],r['tmdb_id']):r for r in (json.loads(l) for l in open(p,encoding='utf-8') if l.strip())}; new=load('eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl'); old=load('eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl.pre_a3.20260522T140111Z.bak'); assert set(new)==set(old),'KEY DRIFT'; diff=[k for k in new if new[k]!=old[k]]; print('changed rows:',len(diff)); print('all q07:',all(k[0]=='q07' for k in diff))"
   ```
   Expected: `changed rows: 10`, `all q07: True`.
3. **No q03/q08/q12/q13 grade drift.** Implied by check 2 (the only changed
   rows are q07). Confirm explicitly that no q03/q08/q12/q13 row appears in
   `diff`.
4. **No `src/*` change across RG-03.**
   `git diff --name-only 5af5362 c7998c5 -- src/` — must be empty (covers both
   RG-03 commits `80e53d7` and `c7998c5`).
5. **`merge_labels.py` unchanged.**
   `git diff 5af5362 c7998c5 -- eval/scripts/merge_labels.py` — must be empty.
6. **`metrics.json` integrity.** `provisional: false`,
   `label_source: merged_gold_over_silver`, `label_provenance` gold 55 /
   silver 165, `regraded_queries` includes `q07`; all `by_mode` deltas vs
   `metrics.json.pre_a3.20260522T140111Z.bak` are ≥ 0.
7. **Sheet integrity.** `regrade_check.json` `complete: true`; the 45
   batch-1/2 rows of `regrade_sheet.jsonl` are byte-identical to
   `regrade_sheet.jsonl.pre_a2.20260522T105003Z.bak`.
8. **Tests green.**
   `./venv/Scripts/python.exe -m unittest discover -s eval/tests` → 190 OK.

### Validation commands

```powershell
git show --stat 80e53d7
git show --stat c7998c5
git diff --name-only 5af5362 c7998c5 -- src/
git diff 5af5362 c7998c5 -- eval/scripts/merge_labels.py
./venv/Scripts/python.exe -m unittest discover -s eval/tests
# plus the q07-only diff one-liner from checklist item 2
```

### Allowed files

- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — append the
  `RG-03-REVIEW` verdict.
- `docs/superpowers/reports/rg-03-review.md` — optional review record (new).

### Forbidden files

`src/**` · `eval/**` (read-only for review) · `eval/queries/**` · any
`*_labels.jsonl` · `eval/scripts/*regrade*.py`, `merge_labels.py`,
`compute_metrics.py`.

### Commit policy

One checkpoint commit: `git add` the ledger (and `rg-03-review.md` if
written); `git commit -m "docs: record RG-03 review"`. No `eval/runs/`
artifact is committed. No `src/*` edit.

### Stop condition

STOP and escalate (do **not** proceed to GATE; reopen RG-03) if the review
finds any of: a non-q07 grade changed; a `src/*` diff; `merge_labels.py`
modified; a metric regression not attributable to q07; failing tests; or the
45 batch-1/2 sheet rows not byte-identical to the pre-A2 backup.

### Outcome

PASS → RG-03 evidence is sound; G1 satisfied. FAIL → reopen RG-03; the gate
cannot open.

---

## T1 — `DECOMP-01` (the pre-Phase-5 ticket)

This is the **only ticket required before the Phase 5 gate**. It is the
Track B ticket from `docs/superpowers/plans/2026-05-22-post-ql-01-tracks-a-b.md`;
its handoff is restated here in full so this plan is self-contained.

### Is DECOMP-01 still needed? — Yes

QL-01 left q05 and q10 as genuine `reranker_blend_issue_later_eval` defects.
Every HY-FIX iteration stopped on "the artifact lacks full-pool
decomposition." That decomposition genuinely does not exist and cannot be
derived from current artifacts: `candidates.jsonl` stores per-stage scores
only for the ~10–15-row per-query top-k **union**, not the full rerank pool;
the HY-STAB-01 / HY-FIX-02A traces captured only the target plus its RRF
neighborhood. DECOMP-01 is the **only** ticket that produces the evidence the
Phase 5 gate needs. It is required and not optional.

### Goal

For q05 (Thanatomorphose) and q10 ([REC]), produce a full rerank-pool and
final-blend score decomposition that lets an analyst **prove or rule out** a
safe localized Phase 5 fix — i.e. answer the question HY-FIX could not: does a
bounded rerank-cutoff increase or final-blend reweight pull the target into
the top 5 **without** broadly re-ordering other results?

### Method

A new analysis script re-runs the deterministic hybrid arms (`pinned`,
`no_llm`) for q05/q10, reusing the HY-STAB-01 arm machinery and
`_decompose_pool` (`eval/scripts/hybrid_expansion_stability.py:629`) and the
HY-FIX-02A pool logic (`eval/scripts/hy_fix_rrf_pool_trace.py`). For each arm
it dumps, for **every member of an extended rerank pool** (at least through
the target's RRF rank — q05 pinned RRF ≈ 66, q10 pinned RRF ≈ 53, so the
target is always captured): `semantic_score`, `bm25_score`, `rrf_score`,
`rerank_score`, `final_score`, plus the final-blend formula inputs and
weights. From that it computes, per candidate localized policy (rerank cutoff
increase; final-blend reweight): (a) does the target reach top 5; (b) the
**collateral** — how many non-target pool members change rank and by how much.
A policy is "safe" only if it rescues the target with bounded, quantified
collateral.

### Files to CREATE (allowed)

- `eval/scripts/decomp_pool_q05_q10.py` — model-backed decomposition runner +
  policy/collateral analysis.
- `eval/tests/test_decomp_pool_q05_q10.py` — unit tests for the pure functions
  (decomposition aggregation, policy rescue check, collateral count) on
  offline fixtures.
- `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
  — the decomposition + policy/collateral artifact (the gate evidence).
- `docs/superpowers/reports/decomp-01-q05-q10.md` — the prove/rule-out report.

### Files to MODIFY (allowed)

- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — append the DECOMP-01
  checkpoint(s).

### Files to READ but not change

- `eval/scripts/hybrid_expansion_stability.py` — deterministic-arm machinery;
  `_decompose_pool` at line 629.
- `eval/scripts/hy_fix_rrf_pool_trace.py` — RRF-pool trace logic.
- `eval/scripts/hy_fix_localize.py` — localization producer.
- `eval/scripts/_run_io.py`, `eval/scripts/_schemas.py` — path/schema helpers.
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_localize/localization.json`
  — q05/q10 target ids and per-arm stage table.
- `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_trace.json`
  — HY-FIX-02A RRF-pool trace.
- `eval/runs/2026-05-19-1846-nogit/analysis/hybrid_expansion_stability/stability_diagnosis.json`
  — HY-STAB-01 arm diagnosis.
- `eval/runs/2026-05-19-1846-nogit/candidates.jsonl` — recorded top-k union.
- `src/**` — **read-only**, only to run the existing
  retrieval/BM25/RRF/reranker pipeline through the eval harness.

### Files FORBIDDEN

- `src/**` — **no edits**, and **no new LLM call** inside
  retrieval/BM25/RRF/reranker code.
- `eval/queries/**`.
- Any `*_labels.jsonl` (gold or silver).
- Anything q07 — q07 is Track A / RG-03, already closed.
- `eval/scripts/merge_labels.py`, `build_regrade_sheet.py`,
  `check_regrade_sheet.py`, `compute_metrics.py` — not part of DECOMP-01.

### Acceptance criteria

1. `decomp_pool_q05_q10.py` imports `src` only to run the existing pipeline;
   it adds **no new LLM call** inside retrieval/BM25/RRF/reranker code and
   makes **no `src/*` edit**.
2. The artifact contains, for q05 and q10, for both deterministic arms
   (`pinned`, `no_llm`), a full extended-pool decomposition with all five
   stage scores per member and the final-blend formula.
3. For each candidate localized policy the artifact records: `target_rescued`
   (bool) and a quantified collateral measure (count and magnitude of
   non-target rank changes).
4. The artifact carries an explicit `decision`: `safe_localized_fix_proven`
   (with the exact bounded change and its allowed `src/*` file),
   `safe_localized_fix_ruled_out` (with the reason), or `inconclusive`.
5. Unit tests pass offline; the model-backed run is recorded with its actual
   cost/time; `git diff --name-only -- src/` is empty.

### Validation commands

```powershell
./venv/Scripts/python.exe -m compileall eval/scripts
./venv/Scripts/python.exe -m unittest discover -s eval/tests
# Model-backed, GPU — gated long-running job (see Dependencies):
./venv/Scripts/python.exe -m eval.scripts.decomp_pool_q05_q10 --run 2026-05-19-1846-nogit
git diff --name-only -- src/
```

### Dependencies — gated long-running job

- GPU: BGE-M3 + `bge-reranker-v2-m3` on the 8 GB RTX 4070. Per project notes,
  run `ollama serve` with `CUDA_VISIBLE_DEVICES=-1` to keep `llama3.2` on CPU
  and free VRAM; use the project venv (`./venv/Scripts/python.exe`).
- The extended rerank pool means more cross-encoder calls than the standard
  `RERANK_TOP_K=50` run. The ticket **must record expected cost/time before
  the run and actual cost/time after** (automation rule for long jobs).
- HY-STAB-01 / HY-FIX-02A artifacts and `localization.json` — all present and
  path-verified.

### Risk

**Medium** — model-backed GPU run; reads `src` but never edits it. The risk is
runtime/VRAM, not `src` correctness; the decomposition is read-only
instrumentation.

### Commit policy

- Commit **only after** `compileall` and `unittest discover` pass **and**
  `decomp_pool_q05_q10` has produced the artifact.
- One checkpoint commit. `git add` the tracked deliverables:
  `eval/scripts/decomp_pool_q05_q10.py`,
  `eval/tests/test_decomp_pool_q05_q10.py`,
  `docs/superpowers/reports/decomp-01-q05-q10.md`,
  `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
- Commit message: `eval: decompose q05 q10 rerank pool (DECOMP-01)`.
- **Gate-evidence artifact decision (confirm before committing):**
  `analysis/decomp/q05_q10_pool_decomposition.json` lives under the gitignored
  `eval/runs/` tree. Prior tickets (QL-01, HY-FIX-02B/03/04) force-added their
  single analysis JSON with `git add -f` so the gate evidence is in the audit
  trail; the RG-03 closeout instead kept `eval/runs/` artifacts uncommitted.
  This is a repo-policy decision — **confirm with the Human** whether to
  `git add -f` this one file. Either way the artifact must exist on disk for
  G2. Recommendation: force-add it, because it is the Phase 5 gate evidence.
- **No `src/*` file is ever staged.**

### Stop conditions

- STOP before any `src/*` edit. DECOMP-01 produces evidence and a decision; it
  does not implement the fix.
- STOP if the run would add an LLM call inside retrieval/BM25/RRF/reranker.
- STOP if the extended pool size or VRAM would exceed the recorded budget —
  re-scope the pool depth, record the new budget, then continue.
- STOP and report `inconclusive` if the decomposition does not clearly prove
  or rule out a safe fix — do **not** force a `safe_localized_fix_proven`
  decision. Inconclusive keeps Phase 5 blocked.
- STOP and report if a deterministic arm's behavior diverges unexplained from
  the recorded HY-FIX / HY-STAB traces.

### Reviewer

Codex self-review is sufficient for the DECOMP-01 *mechanics* on this branch
(no `src/*` edit, no label change). The **decision** is gate-reviewed in G2.

---

## G2 — `DECOMP-01-REVIEW` (review step before the gate)

### Goal

Gate-review the DECOMP-01 decision and its supporting decomposition before the
Phase 5 readiness gate.

### Reviewer

Claude (architecture reviewer). Codex self-review fallback. External review
(Gemini / ChatGPT / Human) is recommended before any Phase 5 plan that
DECOMP-01 might unblock. Gate discipline: cite concrete evidence.

### Review checklist (each item must cite evidence)

1. **No `src/*` change.** `git diff --name-only -- src/` empty across the
   DECOMP-01 commit; `git show --stat <DECOMP-01 commit>` shows no `src/`
   path.
2. **No new LLM call in retrieval/BM25/RRF/reranker.** Inspect the
   `decomp_pool_q05_q10.py` diff — it imports `src` read-only to run the
   existing pipeline.
3. **Artifact completeness.** `q05_q10_pool_decomposition.json` has, for q05
   and q10, both arms, every pool member through the target's RRF rank, all
   five stage scores per member, and the final-blend formula.
4. **Decision soundness.** `decision` is one of the three allowed values. If
   `safe_localized_fix_proven`, it names the **exact bounded change**, the
   **exact allowed `src/*` file**, and the quantified collateral is genuinely
   bounded (not hand-waved). If `safe_localized_fix_ruled_out`, the reason is
   evidenced by the decomposition. If `inconclusive`, Phase 5 stays blocked.
5. **Collateral honesty.** The collateral metric counts non-target rank
   changes and their magnitudes; spot-check it against the raw pool
   decomposition for at least one policy.
6. **Long-job accounting.** Expected vs actual cost/time is recorded; unit
   tests pass.
7. **Scope.** q07 untouched; no `*_labels.jsonl` or `eval/queries/*` touched.

### Validation commands

```powershell
git show --stat <DECOMP-01 commit>
git diff --name-only -- src/
./venv/Scripts/python.exe -m unittest discover -s eval/tests
# schema/contents spot-check of analysis/decomp/q05_q10_pool_decomposition.json
```

### Allowed files

- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` — append the
  `DECOMP-01-REVIEW` verdict.
- `docs/superpowers/reports/decomp-01-review.md` — optional review record
  (new).

### Forbidden files

`src/**` · `eval/**` (read-only for review) · `eval/queries/**` · any
`*_labels.jsonl`.

### Commit policy

One checkpoint commit: `git add` the ledger (and `decomp-01-review.md` if
written); `git commit -m "docs: record DECOMP-01 review"`. No `src/*`, no
`eval/runs/` artifact.

### Stop condition

STOP if the artifact is incomplete, the decision is unsupported by the
decomposition, or collateral is not quantified. A `safe_localized_fix_proven`
decision that does **not** name an exact bounded change + an exact `src/*`
file + bounded quantified collateral **fails the review** → treat as
`inconclusive` → Phase 5 stays blocked.

---

## GATE — Phase 5 readiness gate

The gate has exactly two exits. Whoever evaluates it (Claude + Human) records
the verdict in `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.

### Exit A — Phase 5 UNBLOCKED (ready, not started)

Phase 5 **may** start **if and only if all** of the following hold:

- **G1 `RG-03-REVIEW` = PASS.**
- **T1 `DECOMP-01` = complete, validated, committed, ledger-recorded.**
- **G2 `DECOMP-01-REVIEW` = PASS**, with `decision == safe_localized_fix_proven`
  naming an **exact bounded change**, an **exact allowed `src/*` file**, and
  **bounded quantified collateral**.

→ Phase 5 is UNBLOCKED. A **new, separately-gated Phase 5 plan** must then be
written for that exact bounded change. **Phase 5 is not started by this plan.**

### Exit B — Phase 5 STAYS BLOCKED

If DECOMP-01's `decision` is `safe_localized_fix_ruled_out` or `inconclusive`
(or G2 fails), Phase 5 **stays BLOCKED**. No localized `src/*` fix is
dispatched. The project escalates q05/q10 to a broader architecture decision
under a new, separate ticket.

### Note on G1 timing

G1 is required before merge **outside** the branch; it does not by itself gate
Phase 5 *starting* on-branch. It is listed in Exit A because Phase 5 work
would eventually merge. If G1 has not completed when DECOMP-01 finishes,
complete G1 before opening the gate.

---

## Phase 5 — placeholder

**Phase 5 starts after this gate.** Phase 5 implementation prompts are
intentionally **not** written in this plan.

- If the gate opens (Exit A), a new, separately-gated Phase 5 plan is authored
  for the exact bounded change DECOMP-01 proved safe — with its own
  allowed/forbidden files, validation commands, rollback expectations, and
  reviewer.
- If the gate stays closed (Exit B), no Phase 5 plan is written; the project
  escalates instead.

---

## Self-review — coverage against the requested plan scope

- Current state summary — Section 1. ✓
- Review steps after RG-03 — G1 (and G2 for DECOMP-01). ✓
- Required pre-Phase-5 ticket — T1 DECOMP-01, with a "still needed"
  justification. ✓
- Exact Codex prompt per pre-Phase-5 ticket — DECOMP-01 prompt below; G1/G2
  are review gates (checklist, not a Codex coding prompt). ✓
- Allowed / forbidden files per ticket — in every G1/T1/G2 section. ✓
- Validation commands — in every G1/T1/G2 section. ✓
- Commit policy — in every G1/T1/G2 section. ✓
- Stop condition per ticket — in every G1/T1/G2 section. ✓
- Final gate condition — GATE section (Exit A / Exit B). ✓
- No Phase 5 implementation prompts; placeholder only — above. ✓

---

## Codex prompt — T1 `DECOMP-01` (the only pre-Phase-5 Codex ticket)

> Implement ticket DECOMP-01 per
> `docs/superpowers/plans/2026-05-22-pre-phase5-gate-plan.md` (Section "T1 —
> DECOMP-01"). Create only these files:
> `eval/scripts/decomp_pool_q05_q10.py`,
> `eval/tests/test_decomp_pool_q05_q10.py`,
> `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`,
> `docs/superpowers/reports/decomp-01-q05-q10.md`; and append a DECOMP-01
> checkpoint to `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.
>
> Build a model-backed decomposition runner that re-runs the deterministic
> `pinned` and `no_llm` hybrid arms for q05 and q10, reusing
> `hybrid_expansion_stability.py` arm machinery and `_decompose_pool`
> (line 629) and the `hy_fix_rrf_pool_trace.py` pool logic. For each arm dump,
> for every member of an extended rerank pool (at least through the target's
> RRF rank — q05 pinned RRF ≈ 66, q10 pinned RRF ≈ 53): `semantic_score`,
> `bm25_score`, `rrf_score`, `rerank_score`, `final_score`, plus the
> final-blend formula inputs and weights. Then, for each candidate localized
> policy (rerank cutoff increase; final-blend reweight), record
> `target_rescued` (bool) and a quantified collateral measure (count and
> magnitude of non-target rank changes).
>
> Never edit `src/*`; add no LLM call inside retrieval/BM25/RRF/reranker code
> — `src` is imported read-only only to run the existing pipeline. Use the
> project venv (`./venv/Scripts/python.exe`); for the GPU run, `ollama serve`
> with `CUDA_VISIBLE_DEVICES=-1`. Record expected cost/time before the run and
> actual cost/time after.
>
> End the artifact with an explicit `decision`: `safe_localized_fix_proven`
> (naming the exact bounded change and its allowed `src/*` file),
> `safe_localized_fix_ruled_out` (with the reason), or `inconclusive`. Do not
> force a `proven` decision — `inconclusive` is a valid, expected outcome and
> keeps Phase 5 blocked.
>
> Run all validation commands and paste their output:
> `./venv/Scripts/python.exe -m compileall eval/scripts`;
> `./venv/Scripts/python.exe -m unittest discover -s eval/tests`;
> `./venv/Scripts/python.exe -m eval.scripts.decomp_pool_q05_q10 --run 2026-05-19-1846-nogit`;
> `git diff --name-only -- src/`. Commit only after validation passes, with
> message `eval: decompose q05 q10 rerank pool (DECOMP-01)`, staging only the
> tracked deliverables (script, test, report, ledger) — confirm with the Human
> whether to `git add -f` the `analysis/decomp/q05_q10_pool_decomposition.json`
> gate-evidence artifact. Never stage `src/*`.
>
> Hard stops: stop before any `src/*` edit; stop if a run would add an LLM
> call inside retrieval/BM25/RRF/reranker; stop if pool size or VRAM would
> exceed the recorded budget (re-scope and record); stop and report
> `inconclusive` rather than overstating the evidence. Append the DECOMP-01
> ledger checkpoint with files changed, commands, validation results, the
> artifact decision, cost/time, and next action.
