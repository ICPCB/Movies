# Current handoff — CineMatch web-app ULTRAPLAN run

Updated: 2026-06-11 (restored AGAIN: file was found wiped to 0 bytes a second time at session start; rebuilt from HEAD version + ledger. Root cause of the wipes unknown — treat any 0-byte remember.md as an incident, restore from git, and note it here)
Branch: main
Mode: Human-approved single-approval autonomous run (plan: CINEMATCH_ULTRAPLAN.md, commit 8a4bc15; extended 2026-06-11 by owner-approved closeout/architecture/LoRA-scaffold plan)

## State

- Phase 0 cleanup: DONE (f402156)
- Phase 1 master plan: DONE (8a4bc15, CINEMATCH_ULTRAPLAN.md)
- Phase 2 backend (api/, engine/, requirements-api.txt): DONE (83d5df4, Codex WEB-2A, lead-verified)
- Phase 3 mood label layer (labels/, 27,758 movie labels): DONE (5af4ec0)
- Phase 4 frontend (web/ React+Vite+Tailwind, verified live): DONE (d320b15)
- Phase 5 speed pass (warm-up, async explanations, latency benchmark): DONE (0545010)
- Phase 6 eval extension (mood_v1 queries + serving-path mood layer): DONE (11f5315)
- Phase 7 intent parser (tier-1 lexicon + tier-2 Ollama few-shot): DONE (c089913) — 24 api tests pass, eval validity 1.0 / mode_acc 0.98 / F1 0.86-0.97, web build clean
- Phase 8 final docs (README.md + PROJECT_OVERVIEW.md): DONE (e48fda0) — facts re-verified post-hoc 2026-06-11 (27,762 = src/config.py; 16 routes = 9+7 decorators; src/ diff vs f402156 empty)
- LoRA intent-parser training (plan section 14): PENDING — ACTIVE NEXT TRACK (owner directive 2026-06-11: not deferred; run is NOT closed until the adapter track is delivered). Spec + dataset scaffold land this session; training runs on the owner PC.

## This session (2026-06-11, owner-approved plan) — DONE

1. Governance repair: remember.md restored, PHASE-8 ledger entry added.
2. Agent architecture pipeline: docs/AGENT_PIPELINE.md — Claude = head reviewer/planner; Codex CLI + Gemini CLI = implementation coders; Kiro AI = additional terminal-callable agent; AGENTS.md/CLAUDE.md role updates.
3. Full wipe of unnecessary files (owner approved): old accuracy-audit artifacts (3 run dirs + 2 docs), legacy Gradio app.py (+doc scrubs), stale query drafts, stale codex mailbox, orphaned eval/scripts/_diversity.py. Kept: eval tests, final query files, 2026-06-07 baseline run, all regression scripts. 132 tests pass post-wipe.
4. LoRA track scaffold: spec docs/superpowers/specs/2026-06-11-llama-intent-parser-lora.md (incl. ready-to-dispatch local training ticket in §7), training/ structure + generator interface stub, eval/queries/intent_v1.jsonl (84 records, 7 slices incl. implicit plot descriptions), intent_parser_eval.py --intent-v1 per-slice harness with tier-1 baseline recorded.

## Next safe action (owner PC)

Dispatch the spec §7 ticket to Codex or Gemini: (1) verify D:\...\cinematch-llama\Llama-3.2-1B is the Instruct variant (ULTRAPLAN §14 recorded BASE — stop and report if so); (2) clean cinematch-llama/ per ticket keep/delete lists; (3) implement training/build_intent_dataset.py; (4) train the ONE unified LoRA adapter on final_intent_train.jsonl; (5) eval vs the §5 gate (--intent-v1) — adapter ships only if it beats the few-shot baseline without regressing mood slices.

## Run notes

- API MUST run under venv: venv\Scripts\python.exe -m uvicorn api.main:app --port 8000 (global python lacks rank_bm25)
- Frontend dev: npm run dev --prefix web (port 5173, proxies /api to 8000)
- Intent parser eval: python -m eval.scripts.intent_parser_eval [--tier2 calls Ollama 115x — only with authorization] [--out PATH]; writes eval/runs/<date>-intent-parser-nogit/report.json
- engine/recommender.py serializes first pipeline call (ChromaDB cold-start fix)

## Locks / tickets

- .agents/locks/active_ticket.lock: WEB-2A CLOSED (PASS)
- No active Codex/Gemini ticket.

## Standing rules for this run

- No src/* edits; engine reads src read-only (get_movie_key, lazy hybrid pipeline).
- All local: Ollama llama3.2 for explanations + tier-2 intent parse; no external APIs.
- Label provenance honest (human_provided / authored_static_table / deterministic_rules; never human_gold).
- On any model rate/usage limit: wait and resume from this file + ledger; never abort.
- cinematch-llama/, graphify-out/, archive/ stay untracked.

## Untracked locals never to commit

- data/cinematch.db(+shm/wal), .playwright-mcp/, home-*.png, results-grid.png, root package-lock.json, .agents inbox/outbox transcripts
