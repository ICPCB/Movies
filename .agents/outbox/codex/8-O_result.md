Verdict: NEEDS_REVIEW

Current state:
- Phase 8 remains `NEEDS_REVIEW`.
- The June 9 final-gate run was used only as diagnostic evidence.
- The live `.remember/remember.md` PASS claim conflicts with the active 8-O
  lock, `.agents/state.json`, recovered checkpoint, and 8-N plan.

Files changed:
- `docs/superpowers/reports/phase8-o-hybrid-stage-trace.md`
- `.agents/outbox/codex/8-O_result.md`

Commands run:
- Read-only inspection of governance, source/tests, trace scripts/tests,
  queries, candidates, labels, metrics, manifests, configs, and error reports.
- Deterministic PowerShell JSON/JSONL parsing of the three saved runs.
- Side-effect-free `extract_mood_intent` calls for q59, q49, and q53.
- `git diff --name-only`
- `git status --short`

Validation:
- No sidecar was created.
- No existing script was run because saved-artifact scripts write under
  `eval/runs/`, and the live trace executes prohibited retrieval/model paths.
- Final Git boundary checks completed; only the two 8-O outputs were added by
  Codex. Pre-existing unrelated dirty/untracked files remain untouched.

Artifacts:
- `docs/superpowers/reports/phase8-o-hybrid-stage-trace.md`
- `.agents/outbox/codex/8-O_result.md`

q59 hybrid finding:
- Approved target `Someone, Somewhere` is baseline advanced rank 1 and hybrid
  rank 2, then absent from the entire persisted candidate union in both later
  runs.
- Earliest observed loss is the persisted candidate/per-mode output boundary.
- Semantic, BM25, fusion, and pre-rerank membership are `NOT OBSERVABLE`.

q49 hybrid finding:
- Approved target `Office Space` has no persisted hybrid block in any compared
  run.
- The authorized hybrid HIT came from a different silver-only grade-2 row and
  disappeared in the diagnostic run.
- Retrieval/fusion loss and label/pregrade instability cannot be separated
  into an exact production owner.

q49 advanced context:
- `Office Space` moves from baseline advanced rank 2 to absent in both later
  runs while basic remains rank 4 with unchanged score.
- The current `stressed -` prefix did not restore it in the diagnostic run, so
  mood preprocessing is not proven as the sole owner.

q53 guard:
- q53-H B+C is preserved: `Pee-wee's Big Adventure` grade 3 and
  `Absolutely Anything` grade 1, both `human_reviewed_ai_assisted`.
- Authorized `Pee-wee` hybrid rank moves 1 to 3 with unchanged rerank score;
  its silver `2 -> 1` change is pregrade drift, not retrieval loss.
- The diagnostic run is HIT in all modes, but is not PASS evidence.
- No q53 implementation change is proposed.

Ownership decision:
- Direct evidence supports persisted-output recall loss.
- Exact ownership among query shaping, retrieval recall, fusion, and
  pre-rerank selection remains insufficient.
- Minimal localized implementation is not defensible.

Proposed exact implementation files:
- q59 hybrid: `NEEDS_REVIEW`
- q49 hybrid: `NEEDS_REVIEW`
- q49 advanced: `NEEDS_REVIEW`
- q53: none

Risks:
- Persisted candidate score fields are not complete intermediate-stage pools.
- Silver-only positives can change HIT/MISS without approved label continuity.
- The live handoff is stale/conflicting and must not be used to close Phase 8.

Assumptions:
- Stored candidate ranks are zero-based.
- q53-H human-reviewed grades supersede later silver pregrades for guard
  disposition.
- Existing unrelated dirty/untracked files are user-owned.

Commit:
- None.

Next safe action:
- Human reviews the 8-O report. A further trace would require separately
  authorized live stage capture; do not create an implementation ticket from
  the current evidence.

Codex status:
- Read-only trace complete; stopped at `NEEDS_REVIEW`.
