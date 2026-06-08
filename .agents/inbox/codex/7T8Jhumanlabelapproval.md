---
ticket_id: 7-T-8J-LABEL-APPROVAL
phase: 7/8
depends_on: [7-R, 8-I, 7-S]
human_gate: satisfied
status: READY
---

Goal:
Apply the human's explicit approval of the displayed q49 and Phase 7 label
grades using honest provenance. Do not use `human_gold`.

Human decision:
`human_reviewed_ai_assisted I agree to this grade`

Files to read:
- AGENTS.md
- .remember/remember.md
- eval/scripts/check_regrade_sheet.py
- eval/scripts/merge_labels.py
- eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_sheet.jsonl
- eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/review_queue.jsonl

Files allowed to change:
- eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_sheet.jsonl
- eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_check.json
- eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl
- eval/runs/2026-06-07-combined-nogit/metrics.json
- eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/review_queue.jsonl
- .agents/inbox/codex/7T8Jhumanlabelapproval.md
- .agents/outbox/codex/7-T-8J-LABEL-APPROVAL_result.md
- .agents/ledger.md
- docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md
- .remember/remember.md
- .agents/locks/active_ticket.lock

Files forbidden to change:
- src/*
- eval/scripts/*
- eval/tests/*
- eval/queries/*
- all other run artifacts

Exact implementation rules:
1. In the Phase 7 regrade sheet, update only rows whose current
   `label_provenance` is `ai_draft` to `human_reviewed_ai_assisted`.
2. Leave `q55:228150` as `null_parse_error_fixed`.
3. In the Phase 8-I q49 review queue, update only these seven rows to
   `label_provenance=human_reviewed_ai_assisted` and
   `review_status=human_approved`:
   - q49:10503
   - q49:22230
   - q49:773
   - q49:1268
   - q49:15544
   - q49:37735
   - q49:48034
4. Do not change any grade value.
5. Do not write `human_gold`.
6. Rerun `check_regrade_sheet.py`, then `merge_labels.py`.

Validation commands:
- `.\venv\Scripts\python.exe eval/scripts/check_regrade_sheet.py --run 2026-06-07-combined-nogit`
- `.\venv\Scripts\python.exe eval/scripts/merge_labels.py --run 2026-06-07-combined-nogit --queries eval/queries/all.jsonl`
- provenance assertion: Phase 7 counts must include `human_reviewed_ai_assisted=13`, `null_parse_error_fixed=1`, `silver_llm_pregrade=630`, no `ai_draft`, no `human_gold`.
- q49 review assertion: exactly seven q49 rows are `human_approved` / `human_reviewed_ai_assisted`.
- `git diff --name-only`
- `git status --short`

Stop conditions:
- Any grade value would need to change.
- Any `human_gold` value appears.
- Any forbidden file would change.
- Validation fails.

Required final report:
Verdict:
Files changed:
Commands run:
Validation:
Artifacts:
Failures:
Assumptions:
Commit:
Next safe action:
Codex status:
