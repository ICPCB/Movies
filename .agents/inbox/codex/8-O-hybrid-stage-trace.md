---
ticket_id: 8-O
phase: 8
depends_on: [8-N-PLAN, 4a11cfc]
status: READY_FOR_DISPATCH
title: Hybrid Stage Trace for Phase 8 Final-Gate Blockers
---

1. Goal
   Perform a deterministic, read-only stage trace for q59 hybrid and q49 hybrid, with q49 advanced as supporting context and q53 as a regression guard only. Identify the earliest observable stage where each expected target disappears or moves, classify likely ownership, and decide whether exact minimal implementation ownership is defensible.

   This ticket does not authorize implementation, production changes, a full eval, model execution, LLM/Ollama calls, label changes, provenance changes, or creation of an implementation ticket.

2. Current repo state
   - Phase 8 remains `NEEDS_REVIEW`.
   - Governance recovery commit: `4a11cfc`.
   - 8-N-PLAN verdict: `NEEDS_REVIEW`.
   - 8-N artifacts:
     - `docs/superpowers/plans/phase8-final-gate-blocker-fix-plan.md`
     - `.agents/outbox/codex/8-N-PLAN_result.md`
   - q49 advanced has provisional ownership in `src/retrieval/mood_preprocessor.py` plus focused tests.
   - q59 hybrid and q49 hybrid require stage tracing before exact implementation ownership is defensible.
   - The unauthorized `2026-06-09-phase8-final-gate` run is diagnostic-only and must not be used as PASS evidence.
   - Final blockers: q49 advanced MISS, q49 hybrid MISS, q59 hybrid MISS; q53 must remain HIT in all modes under the approved q53-H guard disposition.

3. Files to read (READ-ONLY)
   - `.remember/remember.md`
   - `.agents/ledger.md`
   - `.agents/state.json`
   - `.agents/locks/active_ticket.lock`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `docs/superpowers/plans/phase8-final-gate-blocker-fix-plan.md`
   - `.agents/outbox/codex/8-N-PLAN_result.md`
   - `.agents/inbox/codex/8-L-q59-mood-retrieval-fix.md`
   - `.agents/outbox/codex/8-L_result.md`
   - `.agents/inbox/codex/8-M-q49-advanced-retrieval-fix.md`
   - `.agents/outbox/codex/8-M_result.md`
   - `.agents/inbox/codex/q53-human-label-approval.md`
   - `.agents/outbox/codex/q53-H-result.md`
   - `src/retrieval/mood_preprocessor.py`
   - `src/tests/test_mood_preprocessor.py`
   - `src/tests/test_mood_pipeline_integration.py`
   - `src/tests/test_safety_filter.py`
   - `eval/queries/all.jsonl`
   - `eval/scripts/hybrid_stage_trace.py`
   - `eval/scripts/hybrid_gap_trace.py`
   - `eval/scripts/hybrid_live_trace.py`
   - `eval/tests/test_hybrid_stage_trace.py`
   - `eval/tests/test_hybrid_gap_trace.py`
   - `eval/tests/test_hybrid_live_trace.py`
   - `eval/runs/2026-06-07-combined-nogit/candidates.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/metrics.json`
   - `eval/runs/2026-06-07-combined-nogit/config_snapshot.json`
   - `eval/runs/2026-06-07-combined-nogit/run_manifest.json`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/candidates.jsonl`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/silver_labels.jsonl`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/metrics_provisional.json`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/config_snapshot.json`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/run_manifest.json`
   - `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/error_report/per_query_mode.jsonl`
   - `eval/runs/2026-06-09-phase8-final-gate/candidates.jsonl`
   - `eval/runs/2026-06-09-phase8-final-gate/silver_labels.jsonl`
   - `eval/runs/2026-06-09-phase8-final-gate/metrics_provisional.json`
   - `eval/runs/2026-06-09-phase8-final-gate/config_snapshot.json`
   - `eval/runs/2026-06-09-phase8-final-gate/run_manifest.json`
   - `eval/runs/2026-06-09-phase8-final-gate/analysis/error_report/per_query_mode.jsonl`
   - `eval/runs/2026-06-09-phase8-final-gate/analysis/error_report/summary.json`

4. Files allowed to change/create
   Required:
   - `.agents/inbox/codex/8-O-hybrid-stage-trace.md`
   - `docs/superpowers/reports/phase8-o-hybrid-stage-trace.md`
   - `.agents/outbox/codex/8-O_result.md`

   Optional only if existing scripts cannot deterministically analyze saved artifacts:
   - `eval/scripts/phase8_o_artifact_stage_trace.py`
   - `eval/tests/test_phase8_o_artifact_stage_trace.py`

   Orchestrator-only after Codex completes:
   - `.agents/locks/active_ticket.lock`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`

5. Files forbidden to change or create
   - Any `src/*` file.
   - Any existing `eval/scripts/*` or `eval/tests/*` file.
   - Any `eval/runs/*` artifact.
   - Any label, provenance, query, candidate, metric, manifest, config snapshot, model, vector DB, or cache artifact.
   - `.agents/state.json`, `.remember/remember.md`, `AGENTS.md`, and `CLAUDE.md`.
   - Any implementation ticket.
   - Any file not explicitly listed under "Files allowed to change/create".

6. Exact trace rules
   a. Use saved artifacts only. Do not execute retrieval pipelines or any code path that loads/calls an embedding model, reranker, LLM, Ollama, network service, or external API.
   b. Prefer existing trace scripts in read-only inspection mode. If they require live retrieval/model execution, do not run them. Use deterministic JSON/JSONL parsing instead.
   c. Add the optional sidecar script/test only if required to parse saved artifacts reproducibly. The sidecar must accept file paths, perform no production imports that initialize models/services, and write no run artifacts.
   d. Trace q59 hybrid first, q49 hybrid second, q49 advanced third as context, and q53 last as guard only.
   e. Compare:
      - authoritative baseline: `2026-06-07-combined-nogit`;
      - last authorized gated run: `2026-06-08-phase8j-gated-nogit`;
      - invalid final-gate run: `2026-06-09-phase8-final-gate`, diagnostic-only.
   f. Clearly distinguish observed persisted stages from inferred stages. If an intermediate semantic/BM25/fusion/pre-rerank stage is not persisted, state `NOT OBSERVABLE`; do not invent evidence.
   g. Candidate ranks in JSONL are zero-based. Report exact stored rank and scores.
   h. Preserve q53 B+C disposition, q65 Option A, and honest provenance. `human_gold` remains 0 unless true human-gold evidence exists; this ticket cannot create such evidence.
   i. Do not claim PASS for Phase 8 or authorize a fix/eval.

   Risk level: LOW
   Reviewer: Human

7. Required report content
   For q59 hybrid and q49 hybrid, and for q49 advanced as supporting context:
   - original query;
   - current mood fields and cleaned query derived deterministically from existing source behavior without editing source;
   - expected target(s) and approved grade/provenance basis;
   - candidate presence in each compared run;
   - earliest observable disappearance stage;
   - exact stored rank movement and available score movement when present;
   - likely owner classification:
     - `mood_preprocessor/query cleaning`
     - `retrieval recall`
     - `candidate union/fusion`
     - `rerank/final scoring`
     - `label/pregrade drift`
     - `inherited data/ticket issue`
   - whether a minimal localized fix is defensible;
   - exact proposed implementation files, or `NEEDS_REVIEW` if ownership remains insufficient.

   For q53:
   - regression-guard evidence only;
   - preserve q53-H B+C disposition;
   - identify any silver/pregrade drift separately from retrieval evidence;
   - propose no q53 implementation change.

8. Acceptance criteria
   - Required report and outbox exist.
   - q59 hybrid and q49 hybrid are traced in the required order.
   - Every ownership claim distinguishes direct evidence from inference.
   - Missing persisted stages are labeled `NOT OBSERVABLE`.
   - Exact implementation files are named only where defensible.
   - No production, run, label, provenance, query, candidate, metric, model, schema, prompt, ranking, or retrieval behavior changes.
   - No model/network/Ollama/LLM/full-eval call.
   - Optional sidecar tests pass if a sidecar is created.
   - No unrelated dirty/untracked file is touched.

9. Validation commands
   If no sidecar is created:
   - `git diff --name-only`
   - `git status --short`

   If sidecar is created:
   - `.\venv\Scripts\python.exe -m pytest eval/tests/test_phase8_o_artifact_stage_trace.py -q`
   - run the sidecar only against explicit saved artifact paths and direct report/stdout output; do not write under `eval/runs/`
   - `git diff --name-only`
   - `git status --short`

10. Stop conditions
   - Any `src/*` edit is required.
   - Any implementation or behavior change is required.
   - Any full eval, pipeline run, model, LLM, Ollama, network, or external API call is required.
   - Any label/provenance/query/candidate/metric/run artifact write is required.
   - Any unrelated dirty/untracked file would be touched.
   - A broader ranking/retrieval/model/schema/prompt change appears necessary.
   - Exact ownership cannot be supported by persisted evidence; report `NEEDS_REVIEW` rather than guessing.

11. Required final report format
   Verdict: PASS / NEEDS_REVIEW / FAIL / STOPPED
   Current state:
   Files changed:
   Commands run:
   Validation:
   Artifacts:
   q59 hybrid finding:
   q49 hybrid finding:
   q49 advanced context:
   q53 guard:
   Ownership decision:
   Proposed exact implementation files:
   Risks:
   Assumptions:
   Commit:
   Next safe action:
   Codex status:

12. Dispatch and closeout
   - Human has explicitly authorized this 8-O read-only trace.
   - Stop after writing the trace report and outbox.
   - Do not create or dispatch an implementation ticket.
   - The orchestrator may append ledger/checkpoint entries and commit only the scoped 8-O ticket, report, outbox, optional sidecar/test, and those required governance entries after validating the result.
