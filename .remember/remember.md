# Current handoff — CineMatch web-app ULTRAPLAN run

Updated: 2026-06-11
Branch: main
Mode: Human-approved single-approval autonomous run (plan: CINEMATCH_ULTRAPLAN.md, commit 8a4bc15)

## State

- Phase 0 cleanup: DONE (f402156)
- Phase 1 master plan: DONE (8a4bc15, CINEMATCH_ULTRAPLAN.md)
- Phase 2 backend (api/, engine/, requirements-api.txt): DONE (83d5df4, Codex WEB-2A, 14 tests pass, lead-verified)
- Phase 3 mood label layer (labels/, 27,758 movie labels, validator OK): DONE (5af4ec0)
- Phase 4 frontend (web/ React+Vite+Tailwind, verified live in browser): DONE (d320b15)
- Phase 5 speed pass: NEXT (pre-warm, /api/explain async, latency benchmark p50/p95)
- Phase 6 eval extension, Phase 7 intent parser (few-shot Ollama + LoRA on cinematch-llama/Llama-3.2-1B), Phase 8 final docs (README.md + PROJECT_OVERVIEW.md): PENDING

## Run notes

- API MUST run under venv: venv\Scripts\python.exe -m uvicorn api.main:app --port 8000 (global python lacks rank_bm25)
- Frontend dev: npm run dev --prefix web (port 5173, proxies /api to 8000)
- Servers may still be running in background from the 2026-06-11 session (user was live-testing)
- engine/recommender.py cold-start lock fixed concurrent ChromaDB init 500s; running server picks it up on next restart

## Locks / tickets

- .agents/locks/active_ticket.lock: WEB-2A CLOSED (PASS)
- No active Codex ticket.

## Standing rules for this run

- No src/* edits; engine reads src read-only (get_movie_key, lazy hybrid pipeline).
- All local: Ollama llama3.2 for explanations; no external APIs.
- Label provenance honest (human_provided / authored_static_table / deterministic_rules; never human_gold).
- On any model rate/usage limit: wait and resume from this file + ledger; never abort.
- cinematch-llama/, graphify-out/, archive/ stay untracked.

## Pre-existing unrelated dirt (do not touch)

- docs/superpowers/plans/phase8-mood-retrieval-fixes.md (M)
- eval/runs/2026-05-19-1846-nogit/.../missing_label_review_queue.csv (M)
- .agents inbox/outbox phase-8 audit files (untracked)
- docs/superpowers/plans/phase8-final-gate-blocker-fix-plan.md (untracked)

## Next safe action

Phase 4: scaffold web/ (Vite + React + Tailwind), build cinematic UI against api/ endpoints, use frontend-design skill. Then commit + ledger entry.
