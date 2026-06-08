---
ticket_id: 8-K
phase: 8
depends_on: [8-G]
status: READY
title: Mood Regression Investigation
---

1. Goal
   Investigate the Phase 8 mood-query regressions found by Gate 8-G without implementing fixes.
   Start with q59 because it regressed in both advanced and hybrid, then triage q49 and q53.
   Include q61/q65 only as context if useful for explaining the Phase 8 mood contract.
   Classify each failure mode and stop for review.

2. Current repo state
   Gate 8-G passed non-mood regression safety, but Phase 8 remains NEEDS_REVIEW and is not complete.
   Fresh run: `eval/runs/2026-06-08-phase8j-gated-nogit/`.
   Baseline run: `eval/runs/2026-06-07-combined-nogit/`.
   Relevant commits:
   - `707cab5` eval: record phase 8-g gated run
   - `be3e731` checkpoint: record phase 8-g commit
   Silver pregrade wrote 694 rows with parse rate 1.000.
   Non-mood checks passed:
   - aggregate: basic -0.026, advanced -0.041, hybrid -0.008
   - literal non-mood set: basic -0.019607, advanced +0.019608, hybrid +0.019608
   - q29-excluded non-mood set also passed
   Mood regressions requiring investigation:
   - q49 advanced: 1 -> 0
   - q53 hybrid: 1 -> 0
   - q59 advanced: 1 -> 0
   - q59 hybrid: 1 -> 0
   q29 overlaps the ticket non-mood range and explicit mood list; preserve both checks in reporting.
   q65 decision remains Option A: keep inherited mismatched `"bored"` tag and record it as inherited 8-F data/ticket issue.
   Existing unrelated dirty file must remain untouched:
   `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv`.

3. Files to read
   - `.remember/remember.md`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `eval/queries/all.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/candidates.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/silver_labels.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/analysis/error_report/per_query_mode.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/analysis/error_report/summary.json`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/candidates.jsonl`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/silver_labels.jsonl`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/error_report/per_query_mode.jsonl`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/error_report/summary.json`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/gate_8g_regression_comparison.json`
   - `eval/scripts/phase8_regression_attribution.py`
   - `src/retrieval/mood_preprocessor.py`

4. Files allowed to change/create
   - `.agents/inbox/codex/8-K-mood-regression-investigation.md`
   - `.agents/outbox/codex/8-K_result.md`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/mood_regression/phase8-k-mood-regression-investigation.md`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `.remember/remember.md`
   - `.agents/locks/active_ticket.lock`

5. Files forbidden to change
   - `src/*`
   - `eval/scripts/*`
   - `eval/runs/2026-06-07-combined-nogit/*`
   - `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv`
   - Any ranking, retrieval, model, prompt, schema, or label provenance behavior file
   - Any unrelated dirty or untracked file

6. Exact implementation rules
   a. Investigation only; do not implement fixes.
   b. Do not run another full eval.
   c. Do not call LLM/Ollama/model services for new scoring.
   d. Compare q59 first, then q49 and q53.
   e. For each investigated qid/mode, report:
      - previous result vs fresh 8-G result
      - expected target label/movie
      - whether the target was retrieved
      - rank movement by mode
      - candidate/rerank/final score movement if present in artifacts
      - mood fields before/after or artifact/code-derived mood fields, including current_emotion, desired_emotional_direction, energy_level, intensity, safety_sensitivity, and cleaned query
      - label grade/provenance comparison
      - likely failure class
      - recommended next ticket if a fix is needed
   f. Use only existing artifacts and deterministic local parsing.
   g. Preserve q29 overlap reporting.
   h. Record q65 as inherited 8-F data/ticket issue only; do not add positive emotion schema support.
   i. If score-stage fields are absent from artifacts, state that explicitly and classify from available ranks/candidates/labels.
   j. Stop after writing the investigation report and checkpoint.

7. Acceptance criteria
   - q59 advanced and hybrid are analyzed first and classified.
   - q49 advanced and q53 hybrid are analyzed and classified.
   - q61/q65 are mentioned only as context, not fixed.
   - q29 overlap is preserved in the report.
   - Report clearly distinguishes candidate drift, label drift, retrieval recall loss, scoring loss, artifact/provenance issues, and inherited data issues.
   - No `src/*`, `eval/scripts/*`, baseline run, or unrelated dirty files are changed.
   - Phase 8 is not declared complete.

8. Validation commands
   .\venv\Scripts\python.exe -c "from pathlib import Path; p=Path('eval/runs/2026-06-08-phase8j-gated-nogit/analysis/mood_regression/phase8-k-mood-regression-investigation.md'); text=p.read_text(encoding='utf-8'); required=['q59','q49','q53','failure class','recommended next ticket','Phase 8 is not complete']; missing=[s for s in required if s not in text]; print('report_exists=', p.exists()); print('missing=', missing); raise SystemExit(1 if missing else 0)"
   git diff --name-only
   git status --short

9. Stop conditions
   - A fix appears necessary before classification can be completed
   - Need to edit `src/*` or `eval/scripts/*`
   - Need another full eval or new model/LLM/Ollama call
   - Need to touch the unrelated dirty review queue
   - Required artifacts are missing or internally inconsistent
   - Validation fails

10. Required final report format
   Verdict:
   Current state:
   Files changed:
   Commands run:
   Validation:
   Artifacts:
   Findings:
   Failure classes:
   Risks:
   Assumptions:
   Commit:
   Next safe action:
   Codex status:
