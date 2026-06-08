---
ticket_id: pre-7-C
phase: 7
depends_on: 7-B
human_gate: yes — Human chooses fix option before dispatch
status: READY
---

1. Goal
   Fix merge_labels.py line 273 to support 60-query runs.
   Add --queries CLI arg, default to all.jsonl.

2. Current repo state
   merge_labels.py hardcodes v1.jsonl at line 273.

3. Files to read
   eval/scripts/merge_labels.py
   eval/scripts/compute_metrics.py (for _load_queries signature)
   eval/tests/test_merge_labels.py

4. Files allowed to change/create
   eval/scripts/merge_labels.py
   eval/tests/test_merge_labels.py

5. Files forbidden to change
   src/*, eval/scripts/compute_metrics.py, eval/queries/*

6. Exact implementation rules
   a. Add --queries arg to _parse_args:
      parser.add_argument("--queries", default=None, type=Path,
          help="Path to queries JSONL. Default: eval/queries/all.jsonl")
   b. Change line 273 from:
      queries = compute_metrics._load_queries(_run_io.EVAL_DIR / "queries" / "v1.jsonl")
      to:
      queries_file = queries_path or (_run_io.EVAL_DIR / "queries" / "all.jsonl")
      queries = compute_metrics._load_queries(queries_file)
   c. Thread queries_path through merge_labels() function signature.
   d. Add test: 60-query merge works when queries=all.jsonl.
   e. Ensure existing tests still pass (v1 queries are a subset of all.jsonl).

7. Acceptance criteria
   - --queries flag exists, defaults to all.jsonl
   - Existing tests pass
   - merge_labels no longer hardcodes v1.jsonl

8. Validation commands
   .\venv\Scripts\python.exe -m pytest eval/tests/test_merge_labels.py -v
   .\venv\Scripts\python.exe -m pytest eval/tests/ -v

9. Stop conditions
   - src/* modified -> HARD STOP
   - Existing test regression -> FAIL

10. Required final report format
    Verdict:
    Files changed:
    Validation:
    Next: 7-C
