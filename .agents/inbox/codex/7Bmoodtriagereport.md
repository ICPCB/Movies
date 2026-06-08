---
ticket_id: 7-B
phase: 7
depends_on: 7-A
human_gate: yes — Claude stops and presents triage for human review
status: READY
---

1. Goal
   Inspect error_report per-query results for all 10 mood queries.
   Classify each as: label issue, retrieval gap, both, or not-a-failure.
   Write triage report. Treat classifications as HYPOTHESES until
   validated against top-5 evidence.

2. Current repo state
   7-A PASS. error_report artifacts exist.

3. Files to read
   eval/runs/<combined-run-id>/analysis/error_report/per_query_mode.jsonl
   eval/runs/<combined-run-id>/analysis/error_report/summary.json
   eval/queries/all.jsonl (for mood tag reference)

4. Files allowed to change/create
   docs/superpowers/reports/phase7-mood-triage.md (new)

5. Files forbidden to change
   src/*, eval/scripts/*, eval/queries/*, eval/tests/*

6. Exact implementation rules
   For each mood qid (q21, q22, q29, q49, q50, q53, q54, q55, q59, q60):
   a. Find its records in per_query_mode.jsonl (3 records: basic, advanced, hybrid)
   b. Inspect top-5 results: titles, grades, null counts
   c. Check if qid appears in summary miss lists
   d. Classify: LABEL (wrong/null grade), RETRIEVAL (wrong movies returned),
      BOTH, or OK (no failure)
   e. For RETRIEVAL failures, note what went wrong (e.g., horror returned
      for safe_hopeful, emotional preamble treated as search terms)
   f. For LABEL failures, note which (qid, tmdb_id) pairs need review
   g. Flag q55 specifically: check if silver label is null (parse error)

7. Acceptance criteria
   - Triage report exists with per-query classification + evidence
   - Each classification cites specific top-5 results or grades
   - q55 null status confirmed or denied
   - Report explicitly states these are hypotheses

8. Validation commands
   Test-Path docs/superpowers/reports/phase7-mood-triage.md
   .\venv\Scripts\python.exe -c "print('Manual review required')"

9. Stop conditions
   - error_report artifacts missing -> BLOCKED
   - src/* modified -> HARD STOP

10. Required final report format
    Verdict:
    Triage table: {qid, classification, evidence_summary, top5_snapshot}
    q55 null status:
    Recommended label fixes:
    Next: HUMAN GATE -> 7-C
