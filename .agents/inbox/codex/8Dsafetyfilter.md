---
ticket_id: 8-D
phase: 8
depends_on: [8-A]
human_gate: no
status: READY
---

1. Goal
   Create src/retrieval/safety_filter.py that demotes dark/horror/
   disturbing candidates when MoodIntent.safety_sensitivity is
   "safe_hopeful". Does NOT demote when "dark_intended" or "neutral".

2. Current repo state
   8-A PASS. MoodIntent dataclass exists.

3. Files to read
   src/retrieval/mood_preprocessor.py (for MoodIntent)
   src/retrieval/reranker.py (for scoring pattern reference)
   src/config.py (for config pattern reference)

4. Files allowed to change/create
   src/retrieval/safety_filter.py (new)
   src/tests/test_safety_filter.py (new)

5. Files forbidden to change
   src/retrieval/reranker.py
   src/pipelines/*
   eval/*

6. Exact implementation rules
   6a. Define DARK_GENRE_KEYWORDS:
       {"horror", "thriller", "slasher", "gore", "torture",
        "serial killer", "psychological thriller", "disturbing",
        "violent", "brutal", "nightmare", "terror"}

   6b. Public API:
       def apply_safety_filter(
           candidates: list[dict],
           mood_intent: MoodIntent,
       ) -> list[dict]:
           If mood_intent.safety_sensitivity == "safe_hopeful":
               Demote (move to bottom, don't remove) candidates whose
               genres or keywords match DARK_GENRE_KEYWORDS.
           If "dark_intended" or "neutral": return candidates unchanged.
           Return reordered list.

   6c. Demotion, not removal -- dark candidates move to bottom of
       list but are not deleted. User can still scroll to find them.

   6d. Tests:
       - safe_hopeful + horror candidate -> demoted to bottom
       - safe_hopeful + comedy candidate -> stays in position
       - dark_intended + horror candidate -> NOT demoted
       - neutral + horror candidate -> NOT demoted
       - safe_hopeful + mixed list -> only dark ones move down
       - empty candidate list -> no crash

7. Acceptance criteria
   - apply_safety_filter() correctly demotes for safe_hopeful only
   - Never removes candidates, only reorders
   - No LLM calls
   - All tests pass

8. Validation commands
   .\venv\Scripts\python.exe -m pytest src/tests/test_safety_filter.py -v
   .\venv\Scripts\python.exe -m pytest src/tests/ -v

9. Stop conditions
   - Candidates removed instead of demoted -> FAIL
   - reranker.py modified -> HARD STOP
   - pipelines/* modified -> HARD STOP

10. Required final report format
    Verdict:
    Files created:
    Test results:
    Next: 8-E
