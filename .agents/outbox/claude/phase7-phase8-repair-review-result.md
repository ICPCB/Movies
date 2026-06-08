# Claude Review - Phase 7/8 Repair Sequence

Source: recovered from Claude transcript
`C:\Users\Minh Nguyen\.claude\projects\D--ICPCB-OneDrive-Documents-Code-Project-Movies\da43e276-a4e9-4b77-bd7e-ca15e081f210.jsonl`.

Claude did not write this file directly before the SDK session exited. Codex
copied the final review text here so the repository-local mailbox contains the
review result required by the lock.

## Evidence Check

All six confirmed evidence items in the review request checked out against code
and artifacts:

- q02 label flip verified in `silver_labels.jsonl`.
- `prompts.py` mood text is global.
- q49 currently returns `current_emotion=None`.
- `_is_dark_candidate` scans title and overview with substring matching.
- `test_generate_queries_v2.py` was edited outside the original 8-F scope.
- Nuance: q02 candidate pool also drifted, so "identical top-five" must be
  reconstructed rather than assumed.

## 7-R

Verdict: REVISE.

- Human gate remains yes.
- The validation command that sums `label_provenance.values()` is defective
  because existing provenance metadata can contain non-count values such as
  lists and overlapping totals.
- Requested edit: nest per-provenance counts under
  `label_provenance.counts` and sum only that object. Preserve existing keys so
  current tests can continue to pass.
- Provenance values and the prohibition on `human_gold` are approved.
- Analysis tables have no machine validation; they remain review evidence.
- Current uncommitted tree must be checkpointed before 7-R implementation so
  the 7-R diff is isolated.

## 8-H

Verdict: REVISE.

- Isolation rules 6a-6e and safety-scope rules 6h-6i are correct, low-risk,
  offline-testable contract repairs.
- q49 adjective-led mood detection is a new capability, not a pure 8-A repair.
  It should not be included in 8-H because it would add an unmeasured retrieval
  change and confound the next run.
- Requested edit: split q49 detection into a new 8-J ticket with human gate,
  gated on 8-I attribution.
- Remove `src/retrieval/mood_preprocessor.py` and
  `src/tests/test_mood_preprocessor.py` from 8-H allowed files after the split.
- Add an explicit stop condition: no full 8-G run from 8-H.

## 8-I

Verdict: REVISE, minor but important.

- Artifact-only attribution is the strongest ticket.
- Remove the dependency on 8-H. 8-I reads frozen artifacts and should run first.
- Do not hard-assert real q02/basic classification as `label_only` in validation.
  Gate classifier behavior on synthetic fixtures, report the real
  classification, and stop/report if it differs.
- Add baseline `gold_labels.jsonl` as a read source for frozen-label reference.

## Approved Execution Order

1. Checkpoint-commit the validated current working tree to isolate future diffs.
2. 8-I revised: attribution evidence.
3. 7-R revised: Phase 7 closeout.
4. 8-H revised: isolation plus safety plus q66 scope adoption.
5. 8-J new: q49 detection, gated on 8-I.
6. Gated decision on fresh 8-G run.

One write-capable ticket at a time via `.agents/locks/active_ticket.lock`.

## May Codex Start 7-R Immediately?

No. 7-R is human-gated, its validation is defective as written, and the
uncommitted tree must be checkpointed first. Revise and checkpoint before
dispatch.

## Implementation Boundary

Claude will review implementation diffs and validation results but will not
implement production code. Codex remains sole implementation owner. This review
edited no production, eval, report, ledger, state, or remember files.

## Stop Condition Before Another 8-G Run

Do not launch `run_pipelines -> llm_pregrade -> compute_metrics` until all hold:

- 8-I attribution is merged and human-reviewed;
- 8-H isolation/safety repairs are committed with passing offline tests;
- a deterministic no-mood prompt-equivalence test exists;
- any q49 change in 8-J is explicitly approved on 8-I evidence.

The full 8-G run also needs explicit human authorization because it uses Ollama
and full eval.
