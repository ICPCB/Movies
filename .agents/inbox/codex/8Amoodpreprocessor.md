---
ticket_id: 8-A
phase: 8
depends_on: [7-D]
human_gate: no
status: READY
---

1. Goal
   Create src/retrieval/mood_preprocessor.py that separates user
   emotional state from desired movie tone in a query string.
   Pure Python, no LLM calls, static vocabulary lookup.

2. Current repo state
   Phase 7 COMPLETE. No mood/emotion code exists in src/.

3. Files to read
   AGENTS.md
   src/retrieval/__init__.py
   src/retrieval/query_processor.py (for existing normalization patterns)
   eval/scripts/_schemas.py (for mood field names and allowed values)
   eval/queries/all.jsonl (for real query examples)

4. Files allowed to change/create
   src/retrieval/mood_preprocessor.py (new)
   src/tests/test_mood_preprocessor.py (new)

5. Files forbidden to change
   eval/scripts/*, eval/queries/*, eval/tests/*
   src/retrieval/reranker.py, src/retrieval/query_processor.py
   src/llm/prompts.py, src/llm/langchain_ollama.py
   src/pipelines/*

6. Exact implementation rules

   6a. Define MoodIntent dataclass:
       @dataclass
       class MoodIntent:
           current_emotion: str | None      # user's feeling (sad, tired, etc.)
           emotion_source: str              # "free_text" | "none"
           desired_direction: str | None    # cheer_me_up, calm_me_down, etc.
           desired_movie_tone: list[str]    # [cozy, gentle, warm, ...]
           energy_level: str | None         # light_cozy, slow_gentle, etc.
           safety_sensitivity: str          # safe_hopeful, neutral, dark_intended
           allow_dark_content: bool | None  # explicit dark request?
           cleaned_query: str               # query with emotional preamble stripped

   6b. User-state detection patterns (populate current_emotion):
       "I feel ...", "I'm feeling ...", "I'm ...", "feeling ...",
       "I am in a ... mood", "after work I feel ..."
       These words describe the USER, not the movie.

   6c. Desired movie-tone patterns (populate desired_movie_tone):
       "I want ...", "looking for ...", "give me ...",
       "something ...", "a movie that ..."
       These words describe the MOVIE the user wants.

   6d. Emotion vocabulary (static dict, no LLM):
       VULNERABLE_EMOTIONS = {"sad", "lonely", "stressed", "tired",
           "anxious", "bored", "heartbroken", "exhausted", "depressed",
           "overwhelmed", "burned_out", "drained", "frustrated",
           "hopeless", "grief", "melancholy", "worried", "afraid",
           "helpless", "ashamed", "trapped", "numb", "empty"}
       These map to safety_sensitivity: "safe_hopeful" when detected
       as user state.

   6e. Safety rules:
       - User in VULNERABLE_EMOTIONS + no explicit dark request
         -> safety_sensitivity: "safe_hopeful", allow_dark_content: False
       - User explicitly requests dark/disturbing/horror/devastating
         -> safety_sensitivity: "dark_intended", allow_dark_content: True
       - Contradiction ("I feel anxious but want a horror movie")
         -> preserve explicit movie intent, set safety to "neutral"
       - No emotion detected
         -> safety_sensitivity: "neutral", allow_dark_content: None

   6f. cleaned_query strips the emotional preamble:
       "I'm exhausted and want something cozy"
       -> cleaned_query: "something cozy"
       "I want a devastating raw war film"
       -> cleaned_query: "a devastating raw war film"
       (no stripping -- entire query is movie intent)

   6g. Public API:
       def extract_mood_intent(query: str) -> MoodIntent
       No side effects, no LLM calls, no network, deterministic.

   6h. Tests (src/tests/test_mood_preprocessor.py):
       - "I'm exhausted and want something cozy"
         -> current_emotion: "exhausted", desired_movie_tone: ["cozy"],
            safety: "safe_hopeful", allow_dark: False,
            cleaned_query contains "cozy" not "exhausted"
       - "I want a movie with warm energy"
         -> current_emotion: None, desired_movie_tone: ["warm"],
            safety: "neutral"
       - "I want a dark psychologically disturbing movie"
         -> current_emotion: None, desired_movie_tone: ["dark","disturbing"],
            safety: "dark_intended", allow_dark: True
       - "I feel disturbed and want something gentle"
         -> current_emotion: "disturbed", desired_movie_tone: ["gentle"],
            safety: "safe_hopeful", allow_dark: False
       - "I want a devastating raw war film"
         -> current_emotion: None, safety: "dark_intended",
            allow_dark: True (explicit heavy content request)
       - "animated spider hero" (no mood at all)
         -> current_emotion: None, safety: "neutral",
            cleaned_query == original query
       - "I feel anxious but want a horror movie"
         -> current_emotion: "anxious", safety: "neutral"
            (explicit intent overrides vulnerable-state demotion)

7. Acceptance criteria
   - extract_mood_intent() returns correct MoodIntent for all 7 test cases
   - No LLM/API/network calls in module
   - No imports from src/llm/ or src/pipelines/
   - All existing tests still pass

8. Validation commands
   .\venv\Scripts\python.exe -m pytest src/tests/test_mood_preprocessor.py -v
   .\venv\Scripts\python.exe -m pytest src/tests/ -v
   .\venv\Scripts\python.exe -m pytest eval/tests/ -v

9. Stop conditions
   - Imports LLM/Ollama/API -> HARD STOP
   - Modifies existing src/ files -> HARD STOP (this ticket creates NEW files only)
   - Existing tests fail -> FAIL

10. Required final report format
    Verdict:
    Files created:
    Test results:
    MoodIntent examples: {3 real query examples with output}
    Next: 8-B
