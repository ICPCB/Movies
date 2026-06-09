---
ticket_id: q53-H
phase: 8
depends_on: [q53-T]
human_gate: satisfied
status: ACTIVE
---

Goal:
Apply the human's explicit q53 judgments for tmdb 5070 and 86828 using
honest provenance, regenerate merged labels and metrics, and record the
checkpoint. Do not change production behavior or run an evaluation.

Human decisions:
- q53:5070 Pee-wee's Big Adventure: grade 3.
- q53:86828 Absolutely Anything: grade 1.
- Provenance: human_reviewed_ai_assisted, not human_gold.

Files allowed to change:
- eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_manifest.json
- eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_sheet.jsonl
- eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_check.json
- eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl
- eval/runs/2026-06-07-combined-nogit/metrics.json
- .agents/inbox/codex/q53-human-label-approval.md
- .agents/inbox/codex/current.md
- .agents/outbox/codex/q53-H-result.md
- .agents/locks/active_ticket.lock
- .agents/ledger.md
- docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md
- .remember/remember.md

Files forbidden to change:
- src/*
- eval/scripts/*
- eval/tests/*
- eval/queries/*
- any silver_labels.jsonl
- any candidates.jsonl
- all other run artifacts

Implementation rules:
1. Add exactly q53:5070 and q53:86828 to the regrade manifest and sheet.
2. Preserve baseline silver grades 2 and 3.
3. Set gold grades to 3 and 1 respectively.
4. Set both provenance values to human_reviewed_ai_assisted.
5. Run the checker before merge, then merge labels.
6. Do not write human_gold.
7. Do not run pipelines, model grading, network calls, or full evals.

Acceptance criteria:
- Regrade checker reports complete=true with 16/16 rows.
- q53:5070 is merged as gold grade 3.
- q53:86828 is merged as gold grade 1.
- Provenance counts are human_reviewed_ai_assisted=15,
  null_parse_error_fixed=1, silver_llm_pregrade=628.
- No human_gold value exists.
- No forbidden file changes.

Validation:
- check_regrade_sheet.py for run 2026-06-07-combined-nogit
- merge_labels.py for run 2026-06-07-combined-nogit
- deterministic q53 and provenance assertions
- git diff --name-only
- git status --short

Reviewer:
SELF-REVIEWED against explicit human judgment and deterministic validation.
