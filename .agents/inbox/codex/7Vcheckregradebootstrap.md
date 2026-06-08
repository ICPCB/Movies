---
ticket_id: 7-V
phase: 7
depends_on: [7-U]
human_gate: no
status: READY
---

Goal:
Allow `eval/scripts/check_regrade_sheet.py` to run by direct script path from
the repo root, matching the validation command used by the label-approval
ticket.

Files allowed to change:
- eval/scripts/check_regrade_sheet.py
- .agents/inbox/codex/7Vcheckregradebootstrap.md
- .agents/outbox/codex/7-V_result.md
- .agents/ledger.md
- docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md

Files forbidden to change:
- src/*
- eval/tests/*
- eval/queries/*
- label artifacts

Validation:
- `.\venv\Scripts\python.exe eval/scripts/check_regrade_sheet.py --run 2026-06-07-combined-nogit`

Stop conditions:
- Any behavior change beyond import bootstrap is needed.
