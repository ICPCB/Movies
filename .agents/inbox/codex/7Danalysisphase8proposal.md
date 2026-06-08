---
ticket_id: 7-D
phase: 7
depends_on: 7-C
human_gate: yes — Approve Phase 8 scope before implementation begins
status: READY
---

1. Goal
   Write mood-intent analysis report and Phase 8 proposal document.
   No code changes.

2. Files to read
   eval/runs/<combined-run-id>/metrics_provisional.json
   eval/runs/<combined-run-id>/metrics.json
   eval/runs/<combined-run-id>/analysis/error_report/summary.json
   eval/runs/<combined-run-id>/analysis/error_report/summary.gold.json
   docs/superpowers/reports/phase7-mood-triage.md
   eval/queries/all.jsonl
   src/llm/prompts.py (read only, for gap analysis)
   src/llm/langchain_ollama.py (read only)
   src/retrieval/reranker.py (read only)
   src/pipelines/hybrid.py (read only)

3. Files allowed to change/create
   docs/superpowers/reports/phase7-mood-analysis.md (new)
   docs/superpowers/plans/phase8-mood-retrieval-fixes.md (new)

4. Files forbidden to change
   src/*, eval/scripts/*, eval/queries/*, eval/tests/*

5. Contents
   Analysis report covers:
   - Mood vs non-mood miss rate comparison
   - Per-sub-field breakdown (all 5: current_emotion, desired_direction,
     energy_level, intensity, safety_sensitivity) with n-per-bucket caveat
   - User-state vs movie-tone distinction (why "I'm exhausted" != search for exhaustion)
   - Safety-sensitivity analysis (safe_hopeful vs dark_intended results)
   - Pipeline gap analysis (what src/ code would need to change)

   Phase 8 proposal covers:
   - Mood preprocessor spec
   - Prompt rewriting spec
   - Safety filter spec
   - Synonym group expansion spec
   - Multi-constraint stress test queries
   - Exact src/* files per intervention
   - Expected metric impact + regression risk

6-10. Standard analysis ticket format (no code validation needed).
