---
ticket_id: 7-U
phase: 7
depends_on: [7-T-8J-LABEL-APPROVAL]
human_gate: no
status: READY
---

Goal:
Repair `check_regrade_sheet.py` so it can validate the Phase 7 batch-4
regrade sheet with `label_provenance`, without weakening checks for the
older generated batch-1/2/3 sheets.

Files allowed to change:
- eval/scripts/check_regrade_sheet.py
- eval/tests/test_check_regrade_sheet.py
- .agents/inbox/codex/7Uregradecheckerphase7.md
- .agents/outbox/codex/7-U_result.md
- .agents/ledger.md
- docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md
- .remember/remember.md
- .agents/locks/active_ticket.lock

Files forbidden to change:
- src/*
- eval/scripts/merge_labels.py
- eval/scripts/build_regrade_sheet.py
- eval/queries/*
- label artifacts except by subsequent 7-T validation

Implementation rules:
1. Keep exact RG-01 non-gold reconstruction checks for manifests with the
   legacy `q12_q13_sheet` / `q03_q08_source` inputs.
2. For custom Phase 7 manifests with `built_from.phase7_mood_triage`, validate
   row count, order, key set, batch/qid counts, silver snapshot, gold fields,
   and `label_provenance` values, but do not require unavailable RG-01 source
   reconstruction.
3. Accept `label_provenance` only when present in all rows; never accept
   `human_gold`.
4. Add focused tests for the custom Phase 7 shape.

Validation commands:
- `.\venv\Scripts\python.exe -m pytest eval/tests/test_check_regrade_sheet.py -q --basetemp="$env:TEMP\cinematch-7u-check"`
- `.\venv\Scripts\python.exe -m eval.scripts.check_regrade_sheet --run 2026-06-07-combined-nogit`

Stop conditions:
- Legacy checker tests regress.
- Any label grade must change.
- `human_gold` would be accepted.
