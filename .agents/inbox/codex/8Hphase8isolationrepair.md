---
ticket_id: 8-H
phase: 8
depends_on: [8-A, 8-B, 8-C, 8-D, 8-E, 8-F, 8-G-stopped]
human_gate: no
status: REVISED_AFTER_CLAUDE_REVIEW
---

1. Goal

   Repair confirmed Phase 8 contract defects and isolate mood-aware LLM
   behavior so no-mood queries retain the pre-Phase-8 prompt path. Do not tune
   ranking weights and do not claim that the observed 8-G accuracy flips are
   fixed by this ticket.

2. Current repo state

   - 8-G is stopped.
   - q02 basic has identical top-five candidate IDs across runs but different
     silver grades, proving at least one label-only flip.
   - q26 and q58 are no-mood queries, yet the 8-C prompt strings changed
     globally for every advanced/hybrid LLM retrieval call.
   - q49 is mood-tagged but `extract_mood_intent()` fails to detect
     `"super stressed from work need ..."`. That new detection behavior is
     deferred to human-gated ticket 8-J after attribution evidence.
   - q59 is detected as safe_hopeful; its hybrid loss occurs before safety
     filtering.
   - `_is_dark_candidate()` currently scans title and overview, exceeding the
     8-D genres-or-keywords contract.
   - `eval/tests/test_generate_queries_v2.py` was changed by 8-F but was not
     listed in the original 8-F allowed files.

3. Files to read

   - `AGENTS.md`
   - `.remember/remember.md`
   - `.agents/inbox/codex/8Amoodpreprocessor.md`
   - `.agents/inbox/codex/8Cpromptrewriting.md`
   - `.agents/inbox/codex/8Dsafetyfilter.md`
   - `.agents/inbox/codex/8Epipelineintegration.md`
   - `.agents/inbox/codex/8Fstresstestqueries.md`
   - `docs/superpowers/reports/phase8-regression-investigation-request.md`
   - all files listed in section 4

4. Files allowed to change

   - `src/llm/prompts.py`
   - `src/llm/langchain_ollama.py`
   - `src/retrieval/safety_filter.py`
   - `src/pipelines/advanced.py`
   - `src/pipelines/hybrid.py`
   - `src/tests/test_safety_filter.py`
   - `src/tests/test_mood_pipeline_integration.py`
   - `eval/tests/test_generate_queries_v2.py`
   - `.agents/outbox/codex/8-H_result.md`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `.remember/remember.md`

5. Files forbidden to change

   - `src/pipelines/basic.py`
   - `src/retrieval/reranker.py`
   - `src/retrieval/query_processor.py`
   - `src/config.py`
   - `eval/queries/*`
   - `eval/scripts/*`
   - `eval/runs/*`
   - ranking weights, candidate pool sizes, model choices, and data paths

6. Exact implementation rules

   6a. Preserve byte-equivalent pre-8-C prompt text as:
       - `EXPAND_SYSTEM_BASE`
       - `HYDE_SYSTEM_BASE`

   6b. Keep the current mood-aware text as:
       - `EXPAND_SYSTEM_MOOD`
       - `HYDE_SYSTEM_MOOD`

   6c. Keep backwards-compatible aliases:
       - `EXPAND_SYSTEM = EXPAND_SYSTEM_BASE`
       - `HYDE_SYSTEM = HYDE_SYSTEM_BASE`

   6d. Change public APIs without breaking existing callers:

       ```python
       def expand_query(query: str, *, mood_aware: bool = False) -> str
       def hyde_generate(query: str, *, mood_aware: bool = False) -> str
       ```

       Select the mood prompt only when `mood_aware=True`.

   6e. In advanced and hybrid:
       - `mood_detected = mood.current_emotion is not None`;
       - use `cleaned_query` only when mood_detected;
       - pass `mood_aware=mood_detected` to LLM retrieval functions;
       - no-mood calls must receive the original query and base prompts.

   6f. Restrict `_is_dark_candidate()` matching to genres and keywords only.
       Use token/phrase boundary matching so `"terror"` does not match an
       unrelated substring. Title or overview alone must not demote a movie.

   6g. Add safety tests for:
       - dark term in title only: not demoted;
       - dark term in overview only: not demoted;
       - exact genre match: demoted;
       - exact keyword phrase match: demoted;
       - substring false positive: not demoted.

   6h. Add mocked integration tests that make no model/network calls and prove:
       - q02, q26, and q58 pass their exact original string to normalize,
         expansion, and HyDE paths;
       - no-mood calls use base prompts;
       - safety filter remains a stable no-op for neutral intent;
       - basic.py remains unchanged.

   6i. Retain the q66 rejection test in
       `eval/tests/test_generate_queries_v2.py`. This ticket explicitly adopts
       that existing 8-F test update into allowed scope; do not make any other
       change in that file.

7. Acceptance criteria

   - No-mood paths use pre-Phase-8 prompt behavior.
   - Safety matching obeys the exact 8-D contract.
   - Existing callers remain compatible.
   - No ranking or model configuration changes.
   - All source and eval tests pass.

8. Validation commands

   ```powershell
   .\venv\Scripts\python.exe -m pytest src/tests/test_safety_filter.py src/tests/test_mood_pipeline_integration.py -q
   .\venv\Scripts\python.exe -m pytest src/tests -q --basetemp="$env:TEMP\cinematch-8h-src"
   .\venv\Scripts\python.exe -m pytest eval/tests -q --basetemp="$env:TEMP\cinematch-8h-eval"
   .\venv\Scripts\python.exe -c "from src.pipelines.advanced import run; from src.pipelines.hybrid import run; print('pipeline imports PASS')"
   git diff --name-only
   git status --short
   ```

9. Stop conditions

   - Any ranking weight, model, data, or candidate-pool change is proposed.
   - A no-mood test observes a mood prompt or cleaned query.
   - A model/network call is needed for validation.
   - Any forbidden file changes.
   - Existing tests fail outside allowed scope.
   - A full or partial 8-G eval run is proposed from this ticket.

10. Required final report format

    Verdict:
    Files changed:
    Confirmed defects repaired:
    No-mood isolation evidence:
    Deferred accuracy work:
    Commands run:
    Validation:
    Risks:
    Accuracy claims not made:
    Commit:
    Next safe action:
