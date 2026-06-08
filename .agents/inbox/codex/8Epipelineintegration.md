---
ticket_id: 8-E
phase: 8
depends_on: [8-C, 8-D]
human_gate: no
status: READY
---

1. Goal
   Integrate mood_preprocessor and safety_filter into hybrid.py
   and advanced.py pipelines. Query flow becomes:
   raw_query -> extract_mood_intent -> expand(cleaned_query) ->
   retrieve -> rerank -> safety_filter -> explain.

2. Current repo state
   8-A, 8-B, 8-C, 8-D PASS. All mood modules exist.

3. Files to read
   src/retrieval/mood_preprocessor.py
   src/retrieval/safety_filter.py
   src/pipelines/hybrid.py
   src/pipelines/advanced.py
   src/pipelines/basic.py

4. Files allowed to change/create
   src/pipelines/hybrid.py
   src/pipelines/advanced.py

5. Files forbidden to change
   src/pipelines/basic.py (keep simple pipeline unchanged)
   src/retrieval/reranker.py
   src/retrieval/query_processor.py
   eval/*

6. Exact implementation rules
   6a. In hybrid.py run():
       - After line 53 (normalize), add:
         mood_intent = extract_mood_intent(query)
       - Replace expansion input with mood_intent.cleaned_query
         (if mood detected, else use original query)
       - After rerank (line 90), add:
         results = apply_safety_filter(results, mood_intent)

   6b. In advanced.py run():
       - Same pattern: extract mood before expansion,
         use cleaned_query, apply safety_filter after rerank.

   6c. Import only:
       from src.retrieval.mood_preprocessor import extract_mood_intent
       from src.retrieval.safety_filter import apply_safety_filter

   6d. basic.py is NOT modified (simple pipeline stays simple).

   6e. When mood_intent.current_emotion is None (no mood detected),
       behavior must be identical to pre-change. Safety filter
       returns candidates unchanged for "neutral" safety.

7. Acceptance criteria
   - hybrid.py and advanced.py call extract_mood_intent + apply_safety_filter
   - basic.py unchanged
   - No-mood queries produce identical results to before
   - All existing tests pass

8. Validation commands
   .\venv\Scripts\python.exe -m pytest src/tests/ -v
   .\venv\Scripts\python.exe -m pytest eval/tests/ -v
   .\venv\Scripts\python.exe -c "from src.pipelines.hybrid import run; print('hybrid import OK')"
   .\venv\Scripts\python.exe -c "from src.pipelines.advanced import run; print('advanced import OK')"

9. Stop conditions
   - basic.py modified -> HARD STOP
   - reranker.py modified -> HARD STOP
   - No-mood query behavior changes -> FAIL (regression)
   - eval/* modified -> HARD STOP

10. Required final report format
    Verdict:
    Files changed:
    Integration points: {hybrid.py lines, advanced.py lines}
    No-mood regression check:
    Next: 8-F
