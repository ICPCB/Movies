---
ticket_id: 7-A
phase: 7
depends_on: Phase 6 combined run
human_gate: no
status: READY
---

1. Goal
   Add 3 mood sub-axes to compute_metrics.py AXES, extend _bucket_qids
   for nested mood tags with null/partial/missing robustness, add 9 unit
   tests, recompute metrics_provisional.json with --queries all.jsonl,
   run error_report.py --labels silver.

2. Current repo state
   Branch: main, HEAD: a5c6fed
   Phase 6 combined run must exist: eval/runs/<combined-run-id>/
   with candidates.jsonl, silver_labels.jsonl, run_manifest.json.
   Existing lock: CLOSED. Unrelated dirty files: IGNORE.

3. Files to read
   AGENTS.md
   eval/scripts/compute_metrics.py
   eval/scripts/_schemas.py
   eval/scripts/error_report.py
   eval/scripts/_run_io.py
   eval/tests/test_compute_metrics.py
   eval/queries/all.jsonl
   eval/runs/<combined-run-id>/candidates.jsonl
   eval/runs/<combined-run-id>/silver_labels.jsonl

4. Files allowed to change/create
   eval/scripts/compute_metrics.py
   eval/tests/test_compute_metrics.py
   eval/runs/<combined-run-id>/metrics_provisional.json (script output)
   eval/runs/<combined-run-id>/analysis/error_report/per_query_mode.jsonl (script output)
   eval/runs/<combined-run-id>/analysis/error_report/summary.json (script output)

5. Files forbidden to change
   src/* — all production code
   eval/scripts/_schemas.py
   eval/scripts/error_report.py
   eval/scripts/merge_labels.py
   eval/queries/*
   AGENTS.md, CLAUDE.md, .remember/remember.md
   Any unrelated dirty/untracked files

6. Exact implementation rules

   6a. AXES change (line 30):
       AXES = ("era", "genre", "vocab_distance", "length", "ambiguity",
               "mood_emotion", "mood_direction", "mood_safety")

   6b. _bucket_qids change (lines 378-392):
       Add mood_* handling before the genre branch:

       if axis.startswith("mood_"):
           mood = tags.get("mood")
           if mood is None:
               buckets["none"].append(qid)
           elif not isinstance(mood, dict):
               buckets["unknown"].append(qid)
           else:
               field_map = {
                   "mood_emotion": "current_emotion",
                   "mood_direction": "desired_direction",
                   "mood_safety": "safety_sensitivity",
               }
               sub_key = field_map.get(axis)
               if sub_key is None:
                   buckets["unknown"].append(qid)
               else:
                   value = mood.get(sub_key, "unknown")
                   buckets[str(value)].append(qid)
       elif axis == "genre":
           ...existing code...

       Behavior:
       - tags without "mood" key -> "none"
       - mood is None -> "none"
       - mood is non-dict -> "unknown"
       - mood dict missing sub-field -> "unknown"
       - valid mood sub-field -> bucket by value
       - genre + non-mood axes unchanged

   6c. Add 9 unit tests to test_compute_metrics.py.
       Call _bucket_qids DIRECTLY with synthetic inline dicts.
       Do NOT use _load_queries or schema validation.

       Tests:
       - test_bucket_qids_mood_null_goes_to_none
       - test_bucket_qids_mood_full_dict_correct_bucket
       - test_bucket_qids_mood_missing_current_emotion
       - test_bucket_qids_mood_missing_desired_direction
       - test_bucket_qids_mood_missing_safety_sensitivity
       - test_bucket_qids_mood_non_dict
       - test_bucket_qids_mood_key_absent_from_tags
       - test_bucket_qids_genre_multi_bucket_unchanged
       - test_bucket_qids_non_mood_axes_unchanged

   6d. Recompute metrics:
       .\venv\Scripts\python.exe eval/scripts/compute_metrics.py
         --run <combined-run-id>
         --queries eval/queries/all.jsonl
         --bootstrap-b 1000 --seed 42

   6e. Run error_report silver:
       .\venv\Scripts\python.exe eval/scripts/error_report.py
         --run <combined-run-id> --k 5 --labels silver

   6f. No LLM/API/Ollama/network calls.
   6g. No _schemas.py changes.

7. Acceptance criteria
   - AXES has mood_emotion, mood_direction, mood_safety
   - _bucket_qids handles mood_* with null/partial/non-dict robustness
   - 9 new tests pass, all existing tests pass (zero regressions)
   - metrics_provisional.json has mood_emotion, mood_direction, mood_safety in by_axis
   - per_query_mode.jsonl and summary.json exist with label_source: "silver"

8. Validation commands
   .\venv\Scripts\python.exe -m pytest eval/tests/test_compute_metrics.py -v
   .\venv\Scripts\python.exe -m pytest eval/tests/ -v
   .\venv\Scripts\python.exe -c "import json; d=json.load(open('eval/runs/<combined-run-id>/metrics_provisional.json')); assert 'mood_emotion' in d['by_axis']; assert 'mood_direction' in d['by_axis']; assert 'mood_safety' in d['by_axis']; print('PASS: mood axes present')"
   .\venv\Scripts\python.exe -c "import json; s=json.load(open('eval/runs/<combined-run-id>/analysis/error_report/summary.json')); assert s['label_source']=='silver'; mood={'q21','q22','q29','q49','q50','q53','q54','q55','q59','q60'}; miss=set(s.get('any_mode_miss_qids',[])); print(f'Mood miss: {sorted(mood&miss)} ({len(mood&miss)}/10)'); print(f'Non-mood miss: {len(miss-mood)}/50')"

9. Stop conditions
   - Combined run missing -> BLOCKED
   - Any test fails -> FAIL
   - Script exits non-zero -> FAIL
   - src/* modified -> HARD STOP
   - LLM/API call -> HARD STOP

10. Required final report format
    Verdict:
    Files changed:
    Artifacts created:
    Validation results:
    Mood axis buckets: {mood_emotion: {buckets}, mood_direction: {buckets}, mood_safety: {buckets}}
    Error report: {mood_miss_qids, mood_miss_rate, non_mood_miss_rate}
    Git status:
    Committed: no
    Next: 7-B triage
