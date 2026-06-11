# Current handoff — CineMatch web-app ULTRAPLAN run

Updated: 2026-06-11 (restored: file was found wiped to 0 bytes at session start; rebuilt from HEAD version + ledger)
Branch: main
Mode: Human-approved single-approval autonomous run (plan: CINEMATCH_ULTRAPLAN.md, commit 8a4bc15)

## State

- Phase 0 cleanup: DONE (f402156)
- Phase 1 master plan: DONE (8a4bc15, CINEMATCH_ULTRAPLAN.md)
- Phase 2 backend (api/, engine/, requirements-api.txt): DONE (83d5df4, Codex WEB-2A, lead-verified)
- Phase 3 mood label layer (labels/, 27,758 movie labels): DONE (5af4ec0)
- Phase 4 frontend (web/ React+Vite+Tailwind, verified live): DONE (d320b15)
- Phase 5 speed pass (warm-up, async explanations, latency benchmark): DONE (0545010)
- Phase 6 eval extension (mood_v1 queries + serving-path mood layer): DONE (11f5315)
- Phase 7 intent parser (tier-1 lexicon + tier-2 Ollama few-shot): DONE (c089913) — 24 api tests pass, eval validity 1.0 / mode_acc 0.98 / F1 0.86-0.97, web build clean
- Phase 8 final docs (README.md + PROJECT_OVERVIEW.md): NEXT (docs-only, last phase)
- LoRA intent-parser training (plan section 14): DEFERRED — few-shot baseline shipped; adapter only if it beats few-shot field-F1

## Run notes

- API MUST run under venv: venv\Scripts\python.exe -m uvicorn api.main:app --port 8000 (global python lacks rank_bm25)
- Frontend dev: npm run dev --prefix web (port 5173, proxies /api to 8000)
- Intent parser eval: python -m eval.scripts.intent_parser_eval [--tier2 calls Ollama 115x — only with authorization] [--out PATH]; writes eval/runs/<date>-intent-parser-nogit/report.json
- engine/recommender.py serializes first pipeline call (ChromaDB cold-start fix)

## Locks / tickets

- .agents/locks/active_ticket.lock: WEB-2A CLOSED (PASS)
- No active Codex ticket.

## Standing rules for this run

- No src/* edits; engine reads src read-only (get_movie_key, lazy hybrid pipeline).
- All local: Ollama llama3.2 for explanations + tier-2 intent parse; no external APIs.
- Label provenance honest (human_provided / authored_static_table / deterministic_rules; never human_gold).
- On any model rate/usage limit: wait and resume from this file + ledger; never abort.
- cinematch-llama/, graphify-out/, archive/ stay untracked.

## Pre-existing unrelated dirt (do not touch)

- docs/superpowers/plans/phase8-mood-retrieval-fixes.md (M) — old accuracy-audit track
- eval/runs/2026-05-19-1846-nogit/.../missing_label_review_queue.csv (M)
- Untracked locals never to commit: data/cinematch.db(+shm/wal), .playwright-mcp/, home-*.png, results-grid.png, root package-lock.json, .agents inbox/outbox transcripts
