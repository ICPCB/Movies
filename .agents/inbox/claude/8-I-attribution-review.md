Review request: Phase 8-I attribution evidence

Role:
- Claude Code Pro is reviewer/planner/gatekeeper.
- Codex remains implementation owner.
- Do not edit repo files in this review. Return a decision and next-ticket guidance only.

Current state:
- Codex completed 8-I as PASS / NEEDS_REVIEW.
- 8-I was artifact-only: no model/network/retrieval calls and no `src/*` edits.
- 8-I produced deterministic attribution artifacts:
  - `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.json`
  - `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.md`
  - `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/review_queue.jsonl`
  - `.agents/outbox/codex/8-I_result.md`

Please inspect:
- `.agents/outbox/codex/8-I_result.md`
- `eval/scripts/phase8_regression_attribution.py`
- `eval/tests/test_phase8_regression_attribution.py`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.json`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.md`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/review_queue.jsonl`
- `.agents/inbox/codex/8Hphase8isolationrepair.md`
- `.agents/inbox/codex/8Jq49mooddetection.md`

Evidence summary from Codex:
- q02: basic=`label_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- q26: basic=`candidate_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- q49: basic=`candidate_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- q58: basic=`candidate_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- q59: basic=`candidate_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- Review queue has 86 rows, `label_provenance=ai_draft`, `review_status=pending_human`.

Questions:
1. Is 8-I acceptable as deterministic attribution evidence, or must Codex revise it before any follow-up?
2. Does 8-I support starting 8-H as a contract/isolation repair that explicitly makes no accuracy claims?
3. Does 8-J remain blocked on human approval because it changes q49 mood detection behavior?
4. Are there any edits needed to 8-H or 8-J before Codex proceeds?

Required output:
Verdict:
8-I acceptance:
8-H go/no-go:
8-J gate:
Required ticket revisions:
Risks:
Next Codex action:
