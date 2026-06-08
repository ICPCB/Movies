---
ticket_id: 8-C
phase: 8
depends_on: [8-A, 8-B]
human_gate: no
status: READY
---

1. Goal
   Modify EXPAND_SYSTEM and HYDE_SYSTEM in src/llm/prompts.py to
   handle emotional preamble correctly. When mood_preprocessor
   detects user emotional state, the prompt should instruct the LLM
   to use cleaned_query (movie intent only) and ignore emotional
   state words as retrieval terms.

2. Current repo state
   8-A, 8-B PASS. mood_preprocessor.py exists.

3. Files to read
   src/llm/prompts.py
   src/retrieval/mood_preprocessor.py

4. Files allowed to change/create
   src/llm/prompts.py

5. Files forbidden to change
   src/retrieval/*, src/pipelines/*, eval/*

6. Exact implementation rules
   6a. Add to EXPAND_SYSTEM (after existing rules, before output format):

       "- If the query contains the user's emotional state (e.g. 'I'm sad',
         'feeling stressed', 'exhausted'), treat this as context for TONE
         only, not as plot keywords. Extract what KIND of movie they want.
         Example: 'I'm exhausted and want something cozy' =>
         expand 'cozy gentle warm lighthearted', NOT 'exhaustion fatigue'.
       - If the user explicitly requests dark/disturbing/intense content,
         preserve that intent fully. Do NOT soften intentional requests."

   6b. Add to HYDE_SYSTEM (after existing rules):

       "- If the request describes the user's emotional state, write a
         TMDB overview for the kind of movie they want, not a movie about
         their emotional state. A tired user wanting 'something cozy'
         gets an overview of a warm gentle film, not a film about fatigue."

   6c. Do NOT add new functions or imports. Only modify prompt strings.

7. Acceptance criteria
   - EXPAND_SYSTEM contains mood-aware instruction
   - HYDE_SYSTEM contains mood-aware instruction
   - No new imports or function changes
   - All existing tests pass

8. Validation commands
   .\venv\Scripts\python.exe -m pytest src/tests/ -v
   .\venv\Scripts\python.exe -m pytest eval/tests/ -v
   .\venv\Scripts\python.exe -c "from src.llm.prompts import EXPAND_SYSTEM, HYDE_SYSTEM; assert 'emotional state' in EXPAND_SYSTEM; assert 'emotional state' in HYDE_SYSTEM; print('PASS')"

9. Stop conditions
   - New imports added -> FAIL (prompt-only change)
   - eval/* modified -> HARD STOP
   - src/retrieval/* modified -> HARD STOP

10. Required final report format
    Verdict:
    Prompt diff summary:
    Next: 8-D
