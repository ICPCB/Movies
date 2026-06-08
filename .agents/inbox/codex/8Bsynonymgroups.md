---
ticket_id: 8-B
phase: 8
depends_on: [7-D]
human_gate: no
status: READY
---

1. Goal
   Add mood-aware synonym groups to SYNONYM_GROUPS in
   src/llm/langchain_ollama.py. These map desired MOVIE TONE
   (not user state) to retrieval-relevant terms.

2. Current repo state
   8-A PASS. SYNONYM_GROUPS has 6 groups (L105-112).

3. Files to read
   src/llm/langchain_ollama.py
   src/retrieval/mood_preprocessor.py (for tone vocabulary reference)

4. Files allowed to change/create
   src/llm/langchain_ollama.py

5. Files forbidden to change
   src/retrieval/*, src/pipelines/*, eval/*

6. Exact implementation rules
   Add these groups to SYNONYM_GROUPS (do NOT remove existing groups):

   "cozy": {"cozy", "warm", "gentle", "tender", "comforting",
            "soothing", "calm", "peaceful"},
   "uplifting": {"uplifting", "hopeful", "inspiring", "heartwarming",
                 "feel-good", "encouraging", "optimistic"},
   "funny": {"funny", "comedy", "hilarious", "absurd", "witty",
             "playful", "lighthearted"},
   "dark": {"dark", "disturbing", "intense", "gritty", "devastating",
            "raw", "unflinching", "bleak"},
   "emotional": {"emotional", "moving", "touching", "tender",
                 "vulnerable", "heartbreaking", "bittersweet"},
   "thrilling": {"thrilling", "exciting", "adventurous", "daring",
                 "gripping", "suspenseful", "edge-of-seat"},

   CRITICAL: Do NOT add user-state words (sad, stressed, exhausted,
   anxious, tired) to these groups. Those describe the user, not the movie.

7. Acceptance criteria
   - 6 new synonym groups added, 6 existing groups preserved
   - No user-state emotion words in any group
   - All existing tests pass

8. Validation commands
   .\venv\Scripts\python.exe -m pytest src/tests/ -v
   .\venv\Scripts\python.exe -m pytest eval/tests/ -v
   .\venv\Scripts\python.exe -c "from src.llm.langchain_ollama import SYNONYM_GROUPS; assert 'cozy' in SYNONYM_GROUPS; assert 'dark' in SYNONYM_GROUPS; assert 'dream' in SYNONYM_GROUPS; sad_words={'sad','stressed','exhausted','anxious','tired'}; all_syns={w for g in SYNONYM_GROUPS.values() for w in g}; overlap=sad_words&all_syns; assert not overlap, f'User-state words in synonyms: {overlap}'; print('PASS')"

9. Stop conditions
   - User-state words added to synonym groups -> FAIL
   - Existing synonym groups removed -> FAIL
   - eval/* modified -> HARD STOP

10. Required final report format
    Verdict:
    SYNONYM_GROUPS count: old vs new
    Next: 8-C
