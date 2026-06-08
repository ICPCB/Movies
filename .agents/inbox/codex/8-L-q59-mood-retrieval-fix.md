---
ticket_id: 8-L
phase: 8
depends_on: [8-K]
status: READY
title: q59 Mood Retrieval Fix
---

1. Goal
   Fix the q59 advanced/hybrid mood regression by preserving loneliness/comfort context in the retrieval input.
   Keep the change scoped to q59's failure class: `current_emotion="lonely"` and `desired_direction="comfort_me"`.
   Do not fix q49, q53, q61, or q65 in this ticket.

2. Current repo state
   Phase 8-K completed as PASS / NEEDS_REVIEW and committed as `f6551c2`; checkpoint commit `d28d70b`.
   Phase 8-K found q59 advanced/hybrid is primarily retrieval recall loss: reliable target `Someone, Somewhere` disappeared from fresh candidates.
   Gate 8-G non-mood safety passed; Phase 8 remains NEEDS_REVIEW and is not complete.
   q49 and q53 remain separate follow-up items.
   q65 remains inherited 8-F data/ticket issue with mismatched `"bored"` tag.

3. Files to read
   - `.remember/remember.md`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `src/retrieval/mood_preprocessor.py`
   - `src/pipelines/advanced.py`
   - `src/pipelines/hybrid.py`
   - `src/tests/test_mood_preprocessor.py`
   - `src/tests/test_mood_pipeline_integration.py`
   - `src/tests/test_safety_filter.py`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/mood_regression/phase8-k-mood-regression-investigation.md`
   - `AGENTS.md`

4. Files allowed to change/create
   - `src/retrieval/mood_preprocessor.py`
   - `src/tests/test_mood_preprocessor.py`
   - `.agents/inbox/codex/8-L-q59-mood-retrieval-fix.md`
   - `.agents/outbox/codex/8-L_result.md`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `.remember/remember.md`
   - `.agents/locks/active_ticket.lock`

5. Files forbidden to change
   - `src/pipelines/advanced.py`
   - `src/pipelines/hybrid.py`
   - `src/pipelines/basic.py`
   - `src/retrieval/safety_filter.py`
   - `src/tests/test_mood_pipeline_integration.py`
   - `src/tests/test_safety_filter.py`
   - `eval/*`
   - `docs/*` except `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `AGENTS.md`
   - `CLAUDE.md`
   - Any file not listed under "Files allowed to change/create"

6. Exact implementation rules
   a. Make the smallest deterministic change in `src/retrieval/mood_preprocessor.py`.
   b. Preserve or reintroduce the canonical emotion token only for the q59 class:
      - `current_emotion == "lonely"`
      - `desired_direction == "comfort_me"`
      - cleaned query does not already contain `lonely` as a case-insensitive word
   c. Use an ASCII prefix format such as `lonely - {cleaned_query_body}`.
   d. Do not change no-mood queries.
   e. Do not change q49 approved behavior: its cleaned query must remain `something light and funny to just zone out`.
   f. Do not change q53 behavior in this ticket.
   g. Do not add new `MoodIntent` fields, schema fields, ranking weights, retrieval stages, prompts, LLM calls, model calls, Ollama calls, full evals, or network calls.
   h. Do not edit pipeline files; advanced/hybrid already consume `mood.cleaned_query`.

7. Acceptance criteria
   - q59 cleaned query contains `lonely`.
   - q59 cleaned query still contains `warm blanket`, `human connection`, and `empty`.
   - q49 cleaned query remains exactly `something light and funny to just zone out`.
   - A no-mood query such as `animated spider hero` remains unchanged.
   - A no-emotion desired-tone query such as `I want a movie with warm energy` remains `a movie with warm energy`.
   - Focused mood preprocessor tests pass.
   - Existing mood pipeline integration and safety filter tests pass without edits.
   - No forbidden files are modified.

8. Validation commands
   .\venv\Scripts\python.exe -m pytest src/tests/test_mood_preprocessor.py -q
   .\venv\Scripts\python.exe -m pytest src/tests/test_mood_pipeline_integration.py -q
   .\venv\Scripts\python.exe -m pytest src/tests/test_safety_filter.py -q
   .\venv\Scripts\python.exe -c "from src.retrieval.mood_preprocessor import extract_mood_intent; m=extract_mood_intent('I feel lonely tonight and want a movie that wraps around me like a warm blanket and reminds me that human connection is still possible even when everything feels empty'); assert 'lonely' in m.cleaned_query.lower(), m.cleaned_query; assert 'warm blanket' in m.cleaned_query; assert 'human connection' in m.cleaned_query; assert 'empty' in m.cleaned_query; print(m.cleaned_query)"
   .\venv\Scripts\python.exe -c "from src.retrieval.mood_preprocessor import extract_mood_intent; m=extract_mood_intent('super stressed from work need something light and funny to just zone out'); assert m.cleaned_query == 'something light and funny to just zone out', m.cleaned_query; print(m.cleaned_query)"
   .\venv\Scripts\python.exe -c "from src.retrieval.mood_preprocessor import extract_mood_intent; assert extract_mood_intent('animated spider hero').cleaned_query == 'animated spider hero'; assert extract_mood_intent('I want a movie with warm energy').cleaned_query == 'a movie with warm energy'; print('unchanged controls OK')"
   git diff --name-only
   git status --short

9. Stop conditions
   - The fix requires editing pipeline files.
   - The fix requires changing q49 behavior.
   - The fix requires changing q53 behavior.
   - The fix requires changing no-mood behavior.
   - The fix requires new schema fields or broad mood taxonomy changes.
   - Any validation fails and cannot be fixed within allowed files.
   - Any forbidden file change is required.

10. Required final report format
   Verdict:
   Current state:
   Files changed:
   Commands run:
   Validation:
   Artifacts:
   Findings:
   Risks:
   Assumptions:
   Commit:
   Next safe action:
   Codex status:
