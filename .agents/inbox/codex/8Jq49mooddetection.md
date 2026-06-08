---
ticket_id: 8-J
phase: 8
depends_on: [8-I]
human_gate: yes
status: PROPOSED_AFTER_CLAUDE_REVIEW
---

1. Goal

   If 8-I attribution and human review confirm q49 needs mood-intent handling,
   extend deterministic mood detection for adjective-led user-state queries
   such as:

   `super stressed from work need something light and funny to just zone out`

   This ticket must not run full eval and must not tune ranking.

2. Current repo state

   - q49 is tagged as mood in `eval/queries/all.jsonl`.
   - Current `extract_mood_intent()` returns `current_emotion=None` for q49.
   - Claude review classified this as a new behavior, not a pure 8-H contract
     repair.
   - 8-J may proceed only after 8-I attribution and human approval.

3. Files to read

   - `AGENTS.md`
   - `.remember/remember.md`
   - `.agents/outbox/codex/8-I_result.md`
   - `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.md`
   - `src/retrieval/mood_preprocessor.py`
   - `src/tests/test_mood_preprocessor.py`
   - `src/pipelines/advanced.py`
   - `src/pipelines/hybrid.py`

4. Files allowed to change

   - `src/retrieval/mood_preprocessor.py`
   - `src/tests/test_mood_preprocessor.py`
   - `src/tests/test_mood_pipeline_integration.py`
   - `.agents/outbox/codex/8-J_result.md`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `.remember/remember.md`

5. Files forbidden to change

   - `src/pipelines/basic.py`
   - `src/pipelines/advanced.py`
   - `src/pipelines/hybrid.py`
   - `src/llm/*`
   - `src/retrieval/reranker.py`
   - `src/retrieval/query_processor.py`
   - `src/retrieval/safety_filter.py`
   - `eval/*`
   - ranking weights, model choices, data paths, and candidate pool sizes

6. Exact implementation rules

   6a. Add deterministic recognition for adjective-led user-state prefixes
       only when a later movie-intent marker exists:

       - `super stressed from work need ...`
       - `really tired today and want ...`
       - `very lonely tonight looking for ...`

   6b. Do not classify movie descriptions such as `a stressed detective`,
       `a lonely hero`, or `a tired cop` as user state.

   6c. Keep no-mood controls unchanged:

       - q02: `animated toys fear being replaced`
       - q26: `brilliant janitor hides from his own genius`
       - q58: `a fairy tale with sword fights, miracles, pirates, and true love read by a grandfather to his sick grandson`

   6d. Add the exact q49 query as a regression test:

       `super stressed from work need something light and funny to just zone out`

       Expected:
       - `current_emotion == "stressed"`;
       - `safety_sensitivity == "safe_hopeful"`;
       - cleaned query excludes `stressed` and `work`;
       - cleaned query retains `light`, `funny`, and `zone out`.

   6e. Add negative tests for movie-description phrases so this detector does
       not widen mood handling to non-user-state descriptions.

   6f. Do not run Ollama, Chroma, embeddings, reranker, or full pipeline eval.

7. Acceptance criteria

   - q49 is detected as mood with a correct cleaned query.
   - No-mood controls remain neutral and unchanged.
   - Movie-description negative cases remain neutral.
   - No production pipeline, ranking, model, query, or eval artifact changes.
   - All validation commands pass.

8. Validation commands

   ```powershell
   .\venv\Scripts\python.exe -m pytest src/tests/test_mood_preprocessor.py src/tests/test_mood_pipeline_integration.py -q --basetemp="$env:TEMP\cinematch-8j"
   .\venv\Scripts\python.exe -m pytest src/tests -q --basetemp="$env:TEMP\cinematch-8j-src"
   .\venv\Scripts\python.exe -c "from src.retrieval.mood_preprocessor import extract_mood_intent; q='super stressed from work need something light and funny to just zone out'; i=extract_mood_intent(q); assert i.current_emotion == 'stressed'; assert i.safety_sensitivity == 'safe_hopeful'; assert 'stressed' not in i.cleaned_query.lower(); assert 'work' not in i.cleaned_query.lower(); print(i)"
   git diff --name-only
   git status --short
   ```

9. Stop conditions

   - 8-I attribution is missing or not human-approved.
   - Any forbidden file must change.
   - A no-mood control changes.
   - A model/retrieval/full-eval call is needed.
   - Validation fails outside allowed scope.

10. Required final report format

    Verdict:
    Files changed:
    q49 detection evidence:
    No-mood control evidence:
    Commands run:
    Validation:
    Accuracy claims not made:
    Commit:
    Next safe action:
