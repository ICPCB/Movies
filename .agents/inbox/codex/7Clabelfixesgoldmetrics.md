---
ticket_id: 7-C
phase: 7
depends_on: pre-7-C
human_gate: yes — Label provenance decisions require human review
status: READY
---

1. Goal
   Fix q55 null label and any labels flagged in triage.
   Run merge_labels.py + error_report.py --labels gold.

2. Current repo state
   pre-7-C PASS. merge_labels.py supports --queries.
   Regrade artifacts must exist in analysis/regrade/.

3. Files to read
   eval/runs/<combined-run-id>/analysis/regrade/regrade_sheet.jsonl
   eval/runs/<combined-run-id>/analysis/regrade/regrade_manifest.json
   eval/runs/<combined-run-id>/analysis/regrade/regrade_check.json
   docs/superpowers/reports/phase7-mood-triage.md

4. Files allowed to change/create
   eval/runs/<combined-run-id>/analysis/regrade/regrade_sheet.jsonl
   eval/runs/<combined-run-id>/gold_labels.jsonl (merge_labels output)
   eval/runs/<combined-run-id>/metrics.json (merge_labels output)
   eval/runs/<combined-run-id>/analysis/error_report/per_query_mode.gold.jsonl
   eval/runs/<combined-run-id>/analysis/error_report/summary.gold.json

5. Files forbidden to change
   src/*, eval/scripts/*, eval/queries/*

6. Exact implementation rules
   a. Fix q55 label in regrade_sheet.jsonl if null confirmed.
      Use provenance: null_parse_error_fixed (if parse error) or
      human_reviewed_ai_assisted (if AI-suggested).
      NEVER use human_gold for AI-assisted labels.
   b. Fix any other labels flagged in triage.
   c. Run: .\venv\Scripts\python.exe eval/scripts/merge_labels.py
        --run <combined-run-id> --queries eval/queries/all.jsonl
   d. Run: .\venv\Scripts\python.exe eval/scripts/error_report.py
        --run <combined-run-id> --k 5 --labels gold
   e. No LLM calls unless explicitly authorized in this ticket.

7. Acceptance criteria
   - q55 has non-null grade with honest provenance
   - gold_labels.jsonl + metrics.json exist
   - Gold error report exists
   - Label provenance is honest throughout

8. Validation commands
   .\venv\Scripts\python.exe -c "import json; m=json.load(open('eval/runs/<combined-run-id>/metrics.json')); assert m['provisional']==False; print(f'label_source: {m[\"label_source\"]}')"
   .\venv\Scripts\python.exe -c "import json; s=json.load(open('eval/runs/<combined-run-id>/analysis/error_report/summary.gold.json')); assert s['label_source']=='merged_gold_over_silver'; print('PASS')"

9. Stop conditions
   - Regrade artifacts missing -> BLOCKED
   - merge_labels exits non-zero -> FAIL
   - AI label recorded as human_gold -> HARD STOP
   - src/* modified -> HARD STOP

10. Required final report format
    Verdict:
    Labels fixed: {qid, tmdb_id, old_grade, new_grade, provenance}
    Gold metrics vs silver metrics delta:
    Next: 7-D
