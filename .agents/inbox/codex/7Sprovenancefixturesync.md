---
ticket_id: 7-S
phase: 7
depends_on: [7-R]
human_gate: no
status: READY_AFTER_CLAUDE_REVIEW
---

Goal:
Restore the eval suite to green by adding the required `label_provenance`
field to stale synthetic gold-label fixtures. Preserve the strict production
artifact schema and make no production behavior change.

Current repo state:
- Phase 7-R added `label_provenance` to `GOLD_LABEL_KEYS`.
- The full eval suite currently reports 344 passed and 12 failed.
- Each failure is caused by a synthetic gold row missing that field.
- Claude reviewed the evidence and approved a fixture-only repair.

Files to read but not change:
- eval/scripts/merge_labels.py
- eval/scripts/error_report.py
- eval/tests/test_merge_labels.py

Files allowed to change:
- .agents/inbox/codex/7Sprovenancefixturesync.md
- eval/tests/test_error_report.py
- eval/tests/test_hybrid_gap_trace.py
- eval/tests/test_hybrid_expansion_stability.py
- eval/tests/test_hybrid_live_trace.py
- .agents/outbox/codex/7-S_result.md
- .agents/ledger.md
- docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md
- .remember/remember.md
- .agents/locks/active_ticket.lock

Files forbidden to change:
- src/*
- eval/scripts/*
- eval/queries/*
- all other eval/tests/*
- run artifacts

Exact implementation rules:
1. Confirm the pre-fix suite has exactly 12 failures caused by missing
   `label_provenance`.
2. Add `label_provenance` immediately after `label_source` in each affected
   fixture row.
3. Use `silver_llm_pregrade` when `label_source == "silver"`.
4. Use `human_reviewed_ai_assisted` when `label_source == "gold"`.
5. Do not weaken `error_report._load_gold_labels`.
6. Do not change assertions or non-fixture behavior.

Acceptance criteria:
- All 12 prior failures pass.
- Full eval suite passes.
- Fixture row key sets equal `merge_labels.GOLD_LABEL_KEYS`.
- Only the four listed test files and required checkpoint files change.

Validation commands:
- `.\venv\Scripts\python.exe -m pytest eval/tests -q --basetemp="$env:TEMP\cinematch-7s-eval"`
- fixture key-set assertion for all four helpers
- `git diff --name-only`
- `git status --short`

Stop conditions:
- A failure has a cause other than missing provenance.
- Any production, eval-script, query, or run-artifact change is needed.
- Any previously passing test regresses.

Risk level:
Low. Test fixtures only.

Reviewer:
Claude Code Pro reviewed the plan; Codex owns implementation.

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
