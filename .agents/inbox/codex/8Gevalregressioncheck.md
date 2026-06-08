---
ticket_id: 8-G
phase: 8
depends_on: [8-E, 8-F]
human_gate: yes (regression review - accept/reject final metrics)
status: READY
---

1. Goal
   Run full eval pipeline on the combined run with mood-aware code.
   Compare metrics before/after. Ensure no regression on non-mood queries.

2. Current repo state
   8-A through 8-F PASS. All mood code integrated.

3. Files to read
   eval/runs/<combined-run-id>/metrics_provisional.json (pre-change baseline)
   eval/scripts/compute_metrics.py
   eval/scripts/error_report.py

4. Files allowed to change/create
   eval/runs/<new-run-id>/  (new eval run directory, all contents)

5. Files forbidden to change
   eval/runs/<combined-run-id>/* (preserve baseline)
   eval/scripts/*, src/*

6. Exact implementation rules
   a. Run fresh eval with mood-aware pipeline (requires Ollama + Chroma).
      This ticket MAY require LLM calls -- explicitly authorized here.
   b. Compute metrics with --queries eval/queries/all.jsonl.
   c. Run error_report --labels silver.
   d. Compare: for non-mood queries (q01-q20, q23-q48, q51-q52, q56-q58),
      hit@5 per mode must not decrease by more than 0.05 from baseline.
   e. For mood queries (q21, q22, q29, q49, q50, q53, q54, q55, q59, q60),
      report hit@5 improvement/regression per query.
   f. For stress-test queries (q61-q65), report hit@5 as new baseline.

7. Acceptance criteria
   - Non-mood hit@5 regression <= 0.05 per mode
   - Mood query metrics reported with per-query breakdown
   - Stress-test query metrics reported
   - New run artifacts exist and are inspectable

8. Validation commands
   .\venv\Scripts\python.exe -c "
   import json
   old = json.load(open('eval/runs/<combined-run-id>/metrics_provisional.json'))
   new = json.load(open('eval/runs/<new-run-id>/metrics_provisional.json'))
   for mode in ('basic','advanced','hybrid'):
       old_hit = old['by_mode'][mode]['hit_at_5']
       new_hit = new['by_mode'][mode]['hit_at_5']
       delta = new_hit - old_hit
       status = 'OK' if delta >= -0.05 else 'REGRESSION'
       print(f'{mode}: {old_hit:.3f} -> {new_hit:.3f} ({delta:+.3f}) {status}')
   "

9. Stop conditions
   - Non-mood regression > 0.05 -> FAIL (report regression details)
   - Ollama/Chroma unavailable -> BLOCKED
   - src/* modified -> HARD STOP

10. Required final report format
    Verdict:
    Non-mood regression check: {mode: old_hit, new_hit, delta, status}
    Mood query improvement: {qid: old_hit, new_hit, delta}
    Stress-test baseline: {qid: hit@5 per mode}
    Phase 8 COMPLETE or NEEDS_REVIEW
