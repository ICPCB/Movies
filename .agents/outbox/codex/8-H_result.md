Verdict: PASS / SELF-REVIEWED

Files changed:
- `src/llm/prompts.py`
- `src/llm/langchain_ollama.py`
- `src/retrieval/safety_filter.py`
- `src/pipelines/advanced.py`
- `src/pipelines/hybrid.py`
- `src/tests/test_safety_filter.py`
- `src/tests/test_mood_pipeline_integration.py`
- `.agents/outbox/codex/8-H_result.md`
- `.agents/ledger.md`
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
- `.remember/remember.md`

Confirmed defects repaired:
- No-mood advanced/hybrid retrieval now keeps the original query path and passes `mood_aware=False` to LLM retrieval helpers.
- Mood-detected advanced/hybrid retrieval uses `cleaned_query` and passes `mood_aware=True`.
- Base prompt constants preserve the pre-8-C prompt path: `EXPAND_SYSTEM_BASE`, `HYDE_SYSTEM_BASE`.
- Mood prompt constants preserve the current mood-aware text: `EXPAND_SYSTEM_MOOD`, `HYDE_SYSTEM_MOOD`.
- Backwards-compatible aliases remain: `EXPAND_SYSTEM = EXPAND_SYSTEM_BASE`, `HYDE_SYSTEM = HYDE_SYSTEM_BASE`.
- `_is_dark_candidate()` now reads only genres and keywords, with token/phrase boundaries.
- Existing one-argument monkeypatch/caller compatibility is preserved for `expand_query` and `hyde_generate` pipeline call sites.

No-mood isolation evidence:
- Mocked integration tests cover q02, q26, and q58 no-mood controls.
- Advanced no-mood test proves original query is passed to normalize, LLM expansion, and HyDE paths with `mood_aware=False`.
- Hybrid no-mood test proves original query is passed to normalize and LLM expansion with `mood_aware=False`.
- Prompt API test proves default LLM retrieval uses base prompts and mood-aware retrieval uses mood prompts.
- Neutral safety filter test proves neutral intent is a stable no-op.

Deferred accuracy work:
- q49/q59 and advanced/hybrid attribution remain blocked on human label review where 8-I reported `insufficient_labels`.
- 8-J is not started.
- No 8-G/full eval run was performed.

Commands run:
- `.\venv\Scripts\python.exe -m pytest src/tests/test_safety_filter.py src/tests/test_mood_pipeline_integration.py -q`
- `.\venv\Scripts\python.exe -m pytest src/tests -q --basetemp="$env:TEMP\cinematch-8h-src"`
- `.\venv\Scripts\python.exe -m pytest eval/tests -q --basetemp="$env:TEMP\cinematch-8h-eval"`
- `.\venv\Scripts\python.exe -c "import src.pipelines.advanced as advanced; import src.pipelines.hybrid as hybrid; print('pipeline imports PASS')"`
- `git diff --name-only`
- `git status --short`

Validation:
- Focused 8-H tests: PASS, 16 passed.
- Source tests: PASS, 23 passed.
- Eval tests: PASS, 352 passed.
- Pipeline import smoke test: PASS.

Risks:
- 8-H is a behavior-affecting contract repair; ranking outputs for no-mood and dark-candidate queries may change.
- Ranking impact is unmeasured by this ticket.
- Existing unrelated dirty file remains: `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv`.

Accuracy claims not made:
- No claim that 8-H fixes 8-G accuracy flips.
- No claim that q49/q59 are fixed.
- No claim that no-mood aggregate metrics improved.

Ranking impact measurement:
- Deferred to a separate gated eval ticket. 8-H ran tests only, not pipeline eval.

Commit:
- `2a1f640`

Next safe action:
- Commit the scoped 8-I/8-H work if the staged set excludes unrelated dirty files.
- Keep 8-J blocked until human approval of q49 review evidence is recorded.
