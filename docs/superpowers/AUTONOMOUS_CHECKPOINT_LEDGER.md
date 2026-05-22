# Autonomous Checkpoint Ledger

This ledger is the central audit trail for autonomous work on the
`automation/cinematch-accuracy-audit-full` branch.

Every ticket/checkpoint appended below must include:

- timestamp
- branch
- phase/ticket id
- status
- files changed
- artifacts written
- commands run
- validation results
- commit hash
- failures/blockers
- assumptions
- next action
- whether external review is optional or still recommended

## Checkpoints

### 2026-05-21T21:12:28Z - GOV-AUTO-01

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `GOV-AUTO-01`
- **Status:** PASS / SELF-REVIEWED
- **Files changed:**
  - `AGENTS.md`
  - `CLAUDE.md`
  - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
- **Artifacts written:**
  - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
- **Commands run:**
  - `git status --short --branch`
  - `git log --oneline --decorate -8`
  - `Select-String -Path 'AGENTS.md','CLAUDE.md' -Pattern 'Autonomous checkpoint mode|Human approval|final approval|final review|required before merging|waits for human approval|optional non-blocking|AUTONOMOUS_CHECKPOINT_LEDGER' -CaseSensitive:$false`
  - `Select-String -Path 'AGENTS.md','CLAUDE.md' -Pattern 'final approval|final review is still required|waits for human approval|without explicit human approval|human-run|PENDING CLAUDE REVIEW' -CaseSensitive:$false`
  - `git diff --name-only`
  - `git diff -- AGENTS.md CLAUDE.md docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
  - `git add -- AGENTS.md CLAUDE.md docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
  - `git commit -m "docs: enable autonomous checkpoint mode"`
- **Validation results:**
  - Governance diff was scoped to the two governance files and the new ledger.
  - Required autonomous checkpoint text is present in `AGENTS.md` and
    `CLAUDE.md`.
  - Search found no remaining blocking phrases for Human final approval,
    required Claude final review, waiting for Human approval, or
    `PENDING CLAUDE REVIEW`.
- **Commit hash:** `8328534`
- **Failures/blockers:** None.
- **Assumptions:** The heartbeat instruction is the active governance ticket
  for this automation branch.
- **Next action:** Continue to `HY-FIX-02B-VALIDATE`.
- **External review:** Optional non-blocking; recommended for governance
  awareness before merge outside this branch.

### 2026-05-21T21:22:46Z - HY-FIX-02B-VALIDATE

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `HY-FIX-02B-VALIDATE`
- **Status:** PASS / SELF-REVIEWED / IMPLEMENTATION NOT JUSTIFIED
- **Files changed:**
  - `docs/superpowers/plans/2026-05-22-hy-fix-02b-validate-rrf-pool-policy.md`
  - `eval/scripts/hy_fix_rrf_pool_validate.py`
  - `eval/tests/test_hy_fix_rrf_pool_validate.py`
  - `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_policy_validation.json`
- **Artifacts written:**
  - `docs/superpowers/plans/2026-05-22-hy-fix-02b-validate-rrf-pool-policy.md`
  - `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_policy_validation.json`
- **Commands run:**
  - `git status --short --branch`
  - `git log --oneline --decorate -8`
  - `python -m compileall eval/scripts`
  - `python -m unittest discover -s eval/tests -v`
  - `python -m eval.scripts.hy_fix_rrf_pool_validate --run 2026-05-19-1846-nogit`
  - `git status --ignored --short -- 'eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_policy_validation.json'`
  - `git add -- docs/superpowers/plans/2026-05-22-hy-fix-02b-validate-rrf-pool-policy.md eval/scripts/hy_fix_rrf_pool_validate.py eval/tests/test_hy_fix_rrf_pool_validate.py`
  - `git add -f -- eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_policy_validation.json`
  - `git commit -m "eval: validate HY-FIX-02B RRF pool policy"`
- **Validation results:**
  - `python -m compileall eval/scripts` passed.
  - `python -m unittest discover -s eval/tests -v` passed: 157 tests OK.
  - HY-FIX-02B CLI passed and wrote
    `rrf_pool_policy_validation.json`.
  - Artifact decision: `implementation_recommended=false`,
    `recommended_policy=null`, `decision=implementation_not_justified`,
    `next_action=continue_to_hy_fix_03_reranker_scoring_q07`.
  - Policy evidence: `cutoff_only_top_80` rescues q08 `no_llm` only;
    pinned q08 needs minimum cutoff 184, so the first listed cutoff rescuing
    both arms is 200 and is classified high risk.
- **Commit hash:** `5a2a6d1`
- **Failures/blockers:** No remaining validation failure. Initial unit-test
  run failed because the new test harness asserted temp output paths after
  cleanup; corrected within ticket scope and reran validation successfully.
  HY-FIX-02B implementation is blocked because no minimal bounded-risk
  policy was proven.
- **Assumptions:** HY-FIX-02A q08 trace and HY-FIX-01 localization artifacts
  are authoritative for this analysis-only checkpoint.
- **Next action:** Continue to `HY-FIX-03` reranker scoring analysis for q07.
- **External review:** Optional non-blocking; recommended before any future
  `src/*` implementation.

### 2026-05-21T21:29:10Z - HY-FIX-03-Q07

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `HY-FIX-03-Q07`
- **Status:** PASS / SELF-REVIEWED / IMPLEMENTATION NOT JUSTIFIED
- **Files changed:**
  - `docs/superpowers/plans/2026-05-22-hy-fix-03-reranker-scoring-q07-analysis.md`
  - `eval/scripts/hy_fix_reranker_scoring_q07.py`
  - `eval/tests/test_hy_fix_reranker_scoring_q07.py`
  - `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_reranker_scoring/q07_reranker_scoring_analysis.json`
- **Artifacts written:**
  - `docs/superpowers/plans/2026-05-22-hy-fix-03-reranker-scoring-q07-analysis.md`
  - `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_reranker_scoring/q07_reranker_scoring_analysis.json`
- **Commands run:**
  - `git status --short --branch`
  - `git log --oneline --decorate -8`
  - `python -m compileall eval/scripts`
  - `python -m unittest discover -s eval/tests -v`
  - `python -m eval.scripts.hy_fix_reranker_scoring_q07 --run 2026-05-19-1846-nogit`
  - `git status --ignored --short -- 'eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_reranker_scoring/q07_reranker_scoring_analysis.json'`
  - `git add -- docs/superpowers/plans/2026-05-22-hy-fix-03-reranker-scoring-q07-analysis.md eval/scripts/hy_fix_reranker_scoring_q07.py eval/tests/test_hy_fix_reranker_scoring_q07.py`
  - `git add -f -- eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_reranker_scoring/q07_reranker_scoring_analysis.json`
  - `git commit -m "eval: analyze HY-FIX-03 q07 reranker scoring"`
- **Validation results:**
  - `python -m compileall eval/scripts` passed.
  - `python -m unittest discover -s eval/tests -v` passed: 164 tests OK.
  - HY-FIX-03 q07 CLI passed and wrote
    `q07_reranker_scoring_analysis.json`.
  - Artifact decision: `implementation_recommended=false`,
    `recommended_policy=null`, `decision=implementation_not_justified`,
    `next_action=continue_to_mixed_q05_q10_analysis`.
  - q07 evidence: pinned rerank rank 20/final rank 25; no_llm rerank rank
    17/final rank 29; basic has first perfect rank 5 while hybrid has no
    perfect top-5 hit.
- **Commit hash:** `7d6b73d`
- **Failures/blockers:** No validation failures. A scorer or reranker
  implementation remains blocked because the available artifacts do not
  include full q07 pool score decomposition or alternative model scores.
- **Assumptions:** Existing localization, stability trace, candidate union,
  and gold error report artifacts are authoritative for q07.
- **Next action:** Continue to mixed q05/q10 analysis.
- **External review:** Optional non-blocking; recommended before any future
  reranker or scoring implementation.

### 2026-05-21T21:33:43Z - HY-FIX-04-Q05-Q10

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `HY-FIX-04-Q05-Q10`
- **Status:** PASS / SELF-REVIEWED / IMPLEMENTATION NOT JUSTIFIED
- **Files changed:**
  - `docs/superpowers/plans/2026-05-22-hy-fix-04-mixed-q05-q10-analysis.md`
  - `eval/scripts/hy_fix_mixed_q05_q10.py`
  - `eval/tests/test_hy_fix_mixed_q05_q10.py`
  - `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_mixed/q05_q10_mixed_analysis.json`
- **Artifacts written:**
  - `docs/superpowers/plans/2026-05-22-hy-fix-04-mixed-q05-q10-analysis.md`
  - `eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_mixed/q05_q10_mixed_analysis.json`
- **Commands run:**
  - `git status --short --branch`
  - `git log --oneline --decorate -8`
  - `python -m compileall eval/scripts`
  - `python -m unittest discover -s eval/tests -v`
  - `python -m eval.scripts.hy_fix_mixed_q05_q10 --run 2026-05-19-1846-nogit`
  - `git status --ignored --short -- 'eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_mixed/q05_q10_mixed_analysis.json'`
  - `git add -- docs/superpowers/plans/2026-05-22-hy-fix-04-mixed-q05-q10-analysis.md eval/scripts/hy_fix_mixed_q05_q10.py eval/tests/test_hy_fix_mixed_q05_q10.py`
  - `git add -f -- eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_mixed/q05_q10_mixed_analysis.json`
  - `git commit -m "eval: analyze HY-FIX-04 mixed q05 q10"`
- **Validation results:**
  - `python -m compileall eval/scripts` passed.
  - `python -m unittest discover -s eval/tests -v` passed: 171 tests OK.
  - HY-FIX-04 CLI passed and wrote `q05_q10_mixed_analysis.json`.
  - Artifact decision: `implementation_recommended=false`,
    `recommended_policy=null`, `decision=implementation_not_justified`,
    `next_action=final_closeout_no_safe_localized_fixes_remaining`.
  - q05/q10 evidence: q05 pinned needs rerank top-k 67 while no_llm is
    rerank rank 4/final rank 9; q10 pinned needs rerank top-k 54 while
    no_llm is rerank rank 6/final rank 7.
- **Commit hash:** `05eef28`
- **Failures/blockers:** No validation failures. A single mixed-defect
  implementation remains blocked because q05/q10 require different recall,
  final-blend, and reranker-scoring changes, and prior HY-FIX-02B/HY-FIX-03
  artifacts rejected safe global cutoff and scorer changes.
- **Assumptions:** The remaining q05/q10 defects should not be fixed by a
  broad product rewrite inside this automation branch.
- **Next action:** Write final closeout; no safe localized fixes remain.
- **External review:** Optional non-blocking; recommended for deciding whether
  query/label review or a broader architecture ticket is warranted.

### 2026-05-21T21:35:40Z - FINAL-CLOSEOUT

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `FINAL-CLOSEOUT`
- **Status:** CLOSED / SELF-REVIEWED / READY FOR OPTIONAL EXTERNAL REVIEW
- **Files changed:**
  - `docs/superpowers/reports/hybrid-fix-autonomous-closeout.md`
- **Artifacts written:**
  - `docs/superpowers/reports/hybrid-fix-autonomous-closeout.md`
- **Commands run:**
  - `git status --short --branch`
  - `git log --oneline --decorate -16`
  - `git diff --name-only 7598e37..HEAD`
  - `python -m compileall eval/scripts`
  - `python -m unittest discover -s eval/tests -v`
  - `python -m eval.scripts.hy_fix_rrf_pool_validate --run 2026-05-19-1846-nogit`
  - `python -m eval.scripts.hy_fix_reranker_scoring_q07 --run 2026-05-19-1846-nogit`
  - `python -m eval.scripts.hy_fix_mixed_q05_q10 --run 2026-05-19-1846-nogit`
  - `git add -- docs/superpowers/reports/hybrid-fix-autonomous-closeout.md`
  - `git commit -m "docs: add hybrid fix autonomous closeout report"`
- **Validation results:**
  - Latest full validation from HY-FIX-04 passed: 171 tests OK.
  - All final analysis artifacts report `implementation_recommended=false`.
  - Working tree was clean before the closeout report was written.
  - Closeout report added a concise audit trail and ready-for-review status.
- **Commit hash:** `b634c4d`
- **Failures/blockers:** No remaining test failures. No safe localized
  `src/*` implementation remains; broader work requires a new explicit ticket.
- **Assumptions:** Optional Gemini/Claude/ChatGPT review is the appropriate
  next step before any broader architecture or query/label changes.
- **Next action:** Optional external review, then create a new ticket for any
  broader experiment or implementation.
- **External review:** Optional non-blocking; recommended for project
  governance and next-ticket selection.

### 2026-05-22T04:12:00Z - QL-01

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `QL-01`
- **Status:** COMPLETE / SELF-REVIEWED
- **Files changed:**
  - `docs/superpowers/plans/2026-05-22-ql-01-query-label-review.md`
  - `eval/scripts/ql_query_label_review.py`
  - `eval/tests/test_ql_query_label_review.py`
  - `eval/runs/2026-05-19-1846-nogit/analysis/query_label_review/q05_q07_q10_review.json`
  - `docs/superpowers/reports/ql-01-query-label-review.md`
  - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
- **Artifacts written:**
  - `eval/runs/2026-05-19-1846-nogit/analysis/query_label_review/q05_q07_q10_review.json`
  - `docs/superpowers/reports/ql-01-query-label-review.md`
- **Commands run:**
  - `python -m compileall eval/scripts`
  - `python -m unittest discover -s eval/tests`
  - `python -m eval.scripts.ql_query_label_review --run 2026-05-19-1846-nogit`
  - `python -c` schema check on `q05_q07_q10_review.json`
  - `git diff --name-only -- src/`
  - `git add` / `git add -f` / `git commit`
- **Validation results:**
  - `python -m compileall eval/scripts` passed.
  - `python -m unittest discover -s eval/tests` passed: 183 tests OK
    (171 prior + 12 QL-01).
  - QL-01 CLI passed and wrote `q05_q07_q10_review.json`; schema check
    passed (`schema_version=ql-01-query-label-review.v1`, qids q05/q07/q10,
    `label_provenance_note` present, all leans within the allowed set).
  - `git diff --name-only -- src/` empty; no `*_labels.jsonl` or
    `eval/queries/*` modified.
- **Final classification (QL-01 report):**
  - q05 -> `reranker_blend_issue_later_eval` (genuine pipeline defect;
    query/label/expansion all sound).
  - q07 -> `silver_label_issue` (LLM pregrade crowned the wrong film;
    What We Do in the Shadows 2014 is the real answer, mislabelled grade 2).
  - q10 -> `reranker_blend_issue_later_eval` (cleanest genuine pipeline
    defect; label correct, target retrieved, hybrid still demotes it).
- **Commit hash:** `34f9972` (evidence commit); report + ledger commit
  follows.
- **Failures/blockers:** No validation failures. Scope note: the script
  sources `deterministic_arms` / `consolidated_fix_category` from
  `localization.json` (canonical, and the pattern of the reference script
  `hy_fix_mixed_q05_q10.py`) rather than the derived q07/mixed hy_fix
  artifacts; equivalent data, fewer inputs. For q07 the final report
  classification (`silver_label_issue`) intentionally differs from the
  script's mechanical R1 lean (`reranker_blend_issue_later_eval`) — the
  two-layer design assigns that judgment to the report.
- **Assumptions:** The QL-01 plan and the existing run artifacts under
  `2026-05-19-1846-nogit` are authoritative; the five-way classification is
  analyst judgment recorded in the report.
- **Next action:** Do not enter Phase 5 yet. Open Track A (RG-style human
  regrade of q07) and Track B (decomposition-enriched eval for q05/q10) as
  two new external-review-gated tickets; they can run in parallel.
- **External review:** Optional non-blocking for QL-01 itself; required for
  any follow-up ticket that changes a label or query (Track A) before merge
  outside this branch.

### 2026-05-22T10:36:00Z - RG-03-A1

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `RG-03` phase A1 (+ one-time sheet recovery)
- **Status:** COMPLETE / SELF-REVIEWED
- **Files changed:**
  - `eval/scripts/build_regrade_sheet.py`
  - `eval/scripts/check_regrade_sheet.py`
  - `eval/scripts/rehydrate_regrade_sheet.py`
  - `eval/tests/test_build_regrade_sheet.py`
  - `docs/superpowers/reports/rg-03-a1-recovery.md`
  - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
- **Artifacts written (gitignored under `eval/runs/`, not committed):**
  - `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_sheet.jsonl`
    (rehydrated — 45 batch-1/2 gold grades restored)
  - `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_sheet.jsonl.pre_rehydrate.20260522T103233Z.bak`
  - `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_sheet.rehydrated_from_gold_labels.jsonl`
  - `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_check.json`
- **Commands run:**
  - `python -m compileall eval/scripts`
  - `python -m unittest discover -s eval/tests`
  - `python -m eval.scripts.rehydrate_regrade_sheet`
  - `python -m eval.scripts.check_regrade_sheet --run 2026-05-19-1846-nogit`
  - `git diff --name-only -- src/`
  - `git add` / `git commit`
- **Validation results:**
  - `python -m compileall eval/scripts` passed.
  - `python -m unittest discover -s eval/tests` passed: 190 tests OK
    (183 prior + 7 `AddQ07BatchTests`).
  - Recovery `rehydrate_regrade_sheet.py` self-verified 8/8: 55 rows,
    45 gold restored, q07 batch-3 10 rows all `null`, no duplicate
    `(qid, tmdb_id)`, q07 batch-3 rows byte-unchanged, key sets intact,
    no join/integrity problems. Backup SHA256 `de5c2fd5…`; new live sheet
    SHA256 `89911e74…`.
  - `check_regrade_sheet`: `rows_total 55`, `rows_filled 45`,
    `pending_by_batch {1:0, 2:0, 3:10}`, `complete false` — batch-3
    reconstruction structurally accepted.
  - `git diff --name-only -- src/` empty; no `src/*`, no `merge_labels.py`,
    no `eval/queries/*`, no `*_labels.jsonl` modified.
- **Commit hash:** recorded by the checkpoint commit that carries this entry
  (see `git log`).
- **Failures/blockers:** A1 implementation found the run's
  `regrade_sheet.jsonl` had been rebuilt empty (0/55 `gold_grade`), dropping
  the 45 batch-1/2 human grades from the sheet. The grades survived in
  `gold_labels.jsonl`; the one-time `rehydrate_regrade_sheet.py` recovery
  restored them by `(qid, tmdb_id)` join. No data lost; no metric change.
- **Assumptions:** `gold_labels.jsonl` (45 `label_source: gold` rows, each
  with `gold_grade` and `gold_notes`) is the authoritative source for the
  batch-1/2 grades; `regrade_manifest.json` needed no change (row count,
  silver snapshot, batch/qid counts unchanged by the recovery).
- **Next action:** A2 — a human fills `gold_grade` / `gold_notes` for the
  10 q07 batch-3 rows only. Then A3 (`check_regrade_sheet` → `merge_labels`),
  separately gated. Phase 5 stays BLOCKED; DECOMP-01 not started.
- **External review:** Required before merge outside this branch — RG-03
  Track A changes labels and recomputes authoritative metrics at A3. A1 +
  recovery is self-reviewed; the recovery restored prior human grades and
  created no new label judgments.

### 2026-05-22T14:05:00Z - RG-03-A3

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `RG-03` phase A3 (check + merge + closeout docs)
- **Status:** COMPLETE / SELF-REVIEWED — RG-03 closed (A1 + A2 + A3)
- **Files changed:**
  - `docs/superpowers/reports/rg-03-q07-regrade.md` (new)
  - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` (this entry)
- **Artifacts written (gitignored under `eval/runs/`, not committed):**
  - `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_check.json`
    (refreshed — `complete: false -> true`)
  - `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl` (re-merged — 55 gold)
  - `eval/runs/2026-05-19-1846-nogit/metrics.json` (recomputed —
    non-provisional)
  - `eval/runs/2026-05-19-1846-nogit/metrics.json.pre_a3.20260522T140111Z.bak`
  - `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl.pre_a3.20260522T140111Z.bak`
- **Commands run:**
  - `python -m eval.scripts.check_regrade_sheet --run 2026-05-19-1846-nogit`
  - `python -m eval.scripts.merge_labels --run 2026-05-19-1846-nogit`
  - `python -m compileall eval/scripts`
  - `python -m unittest discover -s eval/tests`
  - `git diff --name-only -- src/`
  - `git status --short`
- **Validation results:**
  - `check_regrade_sheet`: `complete=true`, `rows_total 55`,
    `rows_filled 55`, `pending_by_batch {1:0, 2:0, 3:0}`; q07 `by_qid`
    `filled 10, changed 6`.
  - `merge_labels` (unmodified): `merged 55 gold over 220 silver;
    metrics.json provisional=false`. `label_provenance` gold `45 -> 55`,
    silver `175 -> 165`; `regraded_queries` adds `q07`.
  - `python -m compileall eval/scripts` passed.
  - `python -m unittest discover -s eval/tests` passed: 190 tests OK.
  - `git diff --name-only -- src/` empty; no `src/*` and no
    `merge_labels.py` change.
  - Metric deltas (q07-only, all >= 0; no regressions): advanced
    `strict_hit@5/@10` +0.05; hybrid `strict_hit@10` +0.05; MRR@5 up in
    all three modes (basic +0.025, advanced +0.025, hybrid +0.040).
- **Commit hash:** Not committed — held per explicit "do not commit"
  instruction. The two docs above are staged-ready; `eval/runs/` artifacts
  are gitignored.
- **Failures/blockers:** None. `regrade_sheet.jsonl` was not modified at A3
  (both A3 tools read it read-only); it carries the A2 human grades.
- **Assumptions:** A2 (human regrade of the 10 q07 batch-3 rows) is
  complete and verified 7/7 per the A2 handoff; `regrade_sheet.jsonl` with
  55/55 filled `gold_grade` is authoritative input to A3.
- **Next action:** RG-03 is closed. External review required before merge
  outside this branch (label change + recomputed authoritative metrics).
  DECOMP-01 (Track B) not started; Phase 5 remains BLOCKED.
- **External review:** Required before merge outside this branch — A3
  changes labels and recomputes authoritative metrics (private-data
  decision under the automation rules).

### 2026-05-22T14:50:44Z - DECOMP-01

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `DECOMP-01`
- **Status:** COMPLETE / SELF-REVIEWED / NOT COMMITTED PER HUMAN INSTRUCTION
- **Files changed:**
  - `eval/scripts/decomp_pool_q05_q10.py`
  - `eval/tests/test_decomp_pool_q05_q10.py`
  - `docs/superpowers/reports/decomp-01-q05-q10.md`
  - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
- **Artifacts written (gitignored under `eval/runs/`, not staged):**
  - `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
- **Commands run:**
  - `./venv/Scripts/python.exe -m compileall eval/scripts`
  - `./venv/Scripts/python.exe -m unittest discover -s eval/tests`
  - `$env:CUDA_VISIBLE_DEVICES='-1'; Start-Process -WindowStyle Hidden -FilePath 'ollama' -ArgumentList 'serve'`
  - `nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits`
  - `./venv/Scripts/python.exe -m eval.scripts.decomp_pool_q05_q10 --run 2026-05-19-1846-nogit`
  - `git diff --name-only -- src/`
  - `git status --short`
- **Validation results:**
  - `compileall` passed:
    `Listing 'eval/scripts'...`; compiled
    `eval/scripts\decomp_pool_q05_q10.py`.
  - `unittest discover` passed: 194 tests OK.
  - DECOMP-01 model-backed run passed:
    `decision=safe_localized_fix_ruled_out`,
    `phase5_gate=blocked`, `policy_count=11`.
  - `git diff --name-only -- src/` was empty.
  - `git status --short` before this ledger append showed only untracked
    `docs/superpowers/plans/2026-05-22-pre-phase5-gate-plan.md`,
    `docs/superpowers/reports/decomp-01-q05-q10.md`,
    `eval/scripts/decomp_pool_q05_q10.py`,
    `eval/tests/test_decomp_pool_q05_q10.py`, and pre-existing
    `graphify-out/`.
- **Cost/time accounting:**
  - Expected cost/time: `$0.00`, 900 seconds max runtime, 468 expected rerank
    pairs, max observed VRAM budget 7800 MiB, extended pool depth budget 75.
  - Actual cost/time: `$0.00`, 40.881 seconds, max observed VRAM 5320 MiB.
  - Ollama setup command recorded and run with `CUDA_VISIBLE_DEVICES=-1`;
    DECOMP-01 reused recorded deterministic arm queries and did not call
    `expand_query`.
- **Artifact decision:** `safe_localized_fix_ruled_out`.
  - No evaluated bounded rerank-cutoff or final-blend reweight policy rescued
    q05 and q10 across both `pinned` and `no_llm` deterministic arms.
  - Target extended-pool ranks: q05 pinned RRF 66 / rerank 4 / final 54;
    q05 no_llm RRF 1 / rerank 5 / final 10; q10 pinned RRF 53 / rerank 7 /
    final 12; q10 no_llm RRF 10 / rerank 7 / final 7.
  - All 11 candidate policies had `all_targets_rescued=False`; no safe policy
    id was recommended.
- **Failures/blockers:** None in validation. Phase 5 remains blocked because
  DECOMP-01 ruled out the evaluated safe localized cutoff/reweight fixes.
- **Assumptions:** The existing HY-STAB/HY-FIX artifacts under
  `2026-05-19-1846-nogit` are the authoritative deterministic-arm inputs; a
  67-candidate extended rerank pool is sufficient because it captures the max
  recorded target RRF rank plus one (q05 pinned rank 66).
- **Next action:** Stop after DECOMP-01. Do not commit. Do not start Phase 5.
  Gate-review DECOMP-01 before any unblocking discussion; current evidence
  keeps Phase 5 blocked.
- **External review:** Required for the Phase 5 gate decision; this checkpoint
  is self-reviewed for mechanics only.

### 2026-05-22T15:10:00Z - DECOMP-01-REVIEW

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `DECOMP-01-REVIEW` (G2 gate review per
  `docs/superpowers/plans/2026-05-22-pre-phase5-gate-plan.md`)
- **Status:** PASS — DECOMP-01 evidence valid; Phase 5 gate evaluated
- **Files changed:**
  - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` (this entry)
- **Artifacts written:** None (review-only checkpoint).
- **Commands run:**
  - `git diff --name-only -- src/`
  - `git status --short`
  - `./venv/Scripts/python.exe -m compileall eval/scripts`
  - `./venv/Scripts/python.exe -m unittest discover -s eval/tests`
  - artifact extraction of `decision` / `policy_analysis` / per-target ranks
    from `eval/runs/2026-05-19-1846-nogit/analysis/decomp/q05_q10_pool_decomposition.json`
- **Review verdict:** **PASS.** Verified against source, the artifact, and a
  re-run test suite — not the reported summary.
  - No `src/*` change: `git diff --name-only -- src/` empty; no untracked
    `src/` files. `decomp_pool_q05_q10.py` imports `src` read-only.
  - No new LLM call inside retrieval/BM25/RRF/reranker: deterministic arm
    queries reused from HY-STAB-01 trace rows; `expand_query` not called.
  - Artifact complete: schema `decomp-01-q05-q10.v1`; q05 + q10; both
    `pinned` and `no_llm` arms; extended pool depth 67; every member carries
    five stage scores + the final-blend formula (script raises unless the
    formula reconstructs `final_score` within 1e-6, and `_assert_reproduced`
    confirms the re-run matches recorded HY-STAB tables).
  - Tests: 194 OK (190 prior + 4 new), independently re-run; `compileall` OK.
  - Long-job accounting recorded: expected `$0.00`/900s/468 pairs/7800 MiB;
    actual `$0.00`/40.881s/5320 MiB max VRAM.
  - CUDA/Ollama: `CUDA_VISIBLE_DEVICES=-1` was scoped to the `ollama serve`
    process (keeps `llama3.2` on CPU); the embedder/reranker run in the
    python eval process and correctly use `cuda` — intended design; VRAM
    5320 MiB < 7800 budget. Expected and acceptable.
- **Decision:** `safe_localized_fix_ruled_out` — **supported by the
  artifact.** All 11 evaluated policies `all_targets_rescued=False`;
  `all_targets_rescued_policy_ids=[]`; `recommended_policy=None`. Target
  ranks (0-indexed) in the extended pool: q05 pinned RRF 66 / rerank 4 /
  final 54; q05 no_llm RRF 1 / rerank 5 / final 10; q10 pinned RRF 53 /
  rerank 7 / final 12; q10 no_llm RRF 10 / rerank 7 / final 7. The target's
  own rerank_score ranks it outside top-5 (rank 5/7/7) in 3 of 4
  deterministic-arm combos; even the limiting policy (extended pool + all
  priors zeroed) rescues only q05 pinned. A bounded cutoff increase or
  final-blend reweight cannot lift a target whose rerank_score is itself
  outside top-5.
- **Phase 5 gate status:** **BLOCKED.** Per the gate plan, a
  `safe_localized_fix_ruled_out` decision is Exit B — Phase 5 stays blocked.
  - **Reason:** no bounded localized rerank-cutoff or final-blend reweight
    policy rescues q05 and q10 across both the `pinned` and `no_llm`
    deterministic arms.
  - **Escalation:** the defect lies in the reranker / cross-encoder scoring
    stage (the target's rerank_score itself is outside top-5), not a bounded
    cutoff/blend tweak. This escalates to a broader reranker/cross-encoder
    architecture investigation — **not** a Phase 5 localized fix.
- **Failures/blockers:** None blocking. Minor non-blocking notes: `_decision`
  cannot emit `inconclusive` (here the result is a genuine rule-out, so
  unaffected); `exact_allowed_src_file` is hardcoded in the unused `proven`
  branch; `candidates.jsonl` / `rrf_pool_trace.json` are existence-checked
  but their contents are not consumed.
- **Confirmation:** No `src/*` changes; Phase 5 not started; no Phase 5 work
  performed; `graphify-out/` not staged; the gitignored decomposition
  artifact not force-added.
- **Assumptions:** The HY-STAB / HY-FIX artifacts under
  `2026-05-19-1846-nogit` remain the authoritative deterministic-arm inputs.
- **Next action:** Phase 5 remains BLOCKED. Open a separate ticket for the
  reranker/cross-encoder architecture investigation (not created yet).
- **External review:** Optional non-blocking; recommended before any future
  reranker/cross-encoder architecture change.

### 2026-05-22T15:33:26Z - RERANK-01

- **Branch:** `automation/cinematch-accuracy-audit-full`
- **Phase/ticket id:** `RERANK-01`
- **Status:** INCOMPLETE — analysis_complete=False, superseded pending RERANK-01A
  - **Gate review (Claude, 2026-05-22):** verdict INCOMPLETE. RERANK-01
    mechanics are valid and validation passed; the ticket objective (a
    complete q05/q10 characterization) was not reached because 4 q05
    false-positive document texts could not be safely reconstructed from
    `candidates.jsonl` + `data/movies_clean.csv`. The script correctly
    detected the gap and did not guess. Remedy: ticket RERANK-01A
    (hermetic document-text source repair), then re-run RERANK-01.
    The gitignored characterization JSON is left on disk, NOT force-added,
    because it is incomplete (`failure_mode=inconclusive`).
- **Files changed:**
  - `eval/scripts/rerank_failure_q05_q10.py`
  - `eval/tests/test_rerank_failure_q05_q10.py`
  - `docs/superpowers/reports/rerank-01-q05-q10.md`
  - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
- **Artifacts written (gitignored under `eval/runs/`, not staged):**
  - `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_reranker_characterization.json`
- **Commands run:**
  - `git status --short`
  - `git log --oneline --decorate -6`
  - `./venv/Scripts/python.exe -m compileall eval/scripts`
  - `./venv/Scripts/python.exe -m unittest discover -s eval/tests`
  - `./venv/Scripts/python.exe -m eval.scripts.rerank_failure_q05_q10 --run 2026-05-19-1846-nogit`
  - `git diff --name-only -- src/`
- **Validation results:**
  - `compileall` passed: `Listing 'eval/scripts'...`.
  - `unittest discover` passed: 201 tests OK.
  - RERANK-01 runner passed and wrote the artifact/report:
    `failure_mode=inconclusive`, `analysis_complete=False`,
    `unresolved_text_members=4`, `phase5_gate=blocked`.
  - `git diff --name-only -- src/` was empty.
- **Failure-mode classification:** `inconclusive`.
  - Required q05 false positives above the target could not be safely
    reconstructed from the allowed text sources:
    tmdb 24218 (`The Bold, the Corrupt and the Beautiful`) and tmdb 21993
    (`On the Job`) missing from both `candidates.jsonl` and
    `movies_clean.csv`; tmdb 25394 (`Posse`) missing from both sources;
    tmdb 8353 resolves in `movies_clean.csv` to title `Limite`, contradicting
    DECOMP title `Supernova`.
  - Clean no_llm stage evidence remains recorded: q05 no_llm RRF rank 1 /
    rerank rank 5 / final rank 10; q10 no_llm RRF rank 10 / rerank rank 7 /
    final rank 7.
  - Pinned arms are attributed as RRF recall primary, with final-blend
    secondary context, not as clean reranker losses.
- **Failures/blockers:** No remaining validation failures. One intermediate
  unit-test fixture failed before correction:
  `FAIL: test_document_field_analysis_records_presence_and_truncation
  (test_rerank_failure_q05_q10.RerankFailureQ05Q10Tests.test_document_field_analysis_records_presence_and_truncation)`
  with traceback
  `File "D:\ICPCB\OneDrive\Documents\Code\Project\Movies\eval\tests\test_rerank_failure_q05_q10.py", line 29, in test_document_field_analysis_records_presence_and_truncation`
  and assertion
  `AssertionError: True is not false`. The fixture was corrected to use a
  non-degenerate document length; the full suite then passed.
- **Assumptions:** The DECOMP-01 artifact is authoritative for scores and
  ranks; missing/mismatched text sources must not be guessed from title/year
  alone because that would not reconstruct the exact cross-encoder document.
- **Next action:** Phase 5 remains BLOCKED. Before a model-backed RERANK-02,
  repair or snapshot the missing allowed document sources, then compare the
  same q05/q10 no_llm pairs against an alternative cross-encoder. Confirm
  with the Human whether to force-add the gitignored RERANK-01 JSON artifact
  before committing.
- **External review:** Optional non-blocking for mechanics; recommended before
  scoping RERANK-02 because the classification is intentionally inconclusive.
