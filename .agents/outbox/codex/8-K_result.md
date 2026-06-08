# Phase 8-K Result - Mood Regression Investigation

Verdict: PASS / NEEDS_REVIEW

Current state:
- Gate 8-G non-mood safety remains PASS.
- Phase 8 remains NEEDS_REVIEW and is not complete.
- Investigation report: `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/mood_regression/phase8-k-mood-regression-investigation.md`

Files changed:
- `.agents/inbox/codex/8-K-mood-regression-investigation.md`
- `.agents/outbox/codex/8-K_result.md`
- `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/mood_regression/phase8-k-mood-regression-investigation.md`

Commands run:
- Claude Opus 4.6 planner calls:
  - `claude --model claude-opus-4-6 -p --permission-mode plan --output-format text ...`
- Deterministic artifact parsing with repo venv Python.
- Validation report phrase check.
- `git diff --name-only`
- `git status --short`

Validation:
- Report existence and required phrase check: PASS.
- `git diff --name-only`: only the pre-existing unrelated dirty review queue is tracked dirty.
- `git status --short`: expected new 8-K ticket/report files plus pre-existing unrelated dirty/untracked files.

Artifacts:
- Claude plan stub: `C:\Users\Minh Nguyen\.claude\plans\you-are-claude-code-breezy-sphinx.md`
- Claude ticket-plan artifact: `C:\Users\Minh Nguyen\.claude\plans\create-only-a-compact-reactive-hammock.md`
- Investigation report: `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/mood_regression/phase8-k-mood-regression-investigation.md`

Findings:
- q59 advanced/hybrid: reliable target `Someone, Somewhere` vanished from fresh candidates; `Disconnect` was a silver hit but human-reviewed gold grade is 1.
- q49 advanced: `Office Space` remains a positive label and appears in fresh basic, but disappears from fresh advanced candidates.
- q53 hybrid: mixed issue. `Pee-wee's Big Adventure` remains rank 4 but fresh silver changed grade 2 -> 1; `Absolutely Anything` disappears from fresh candidates.
- q61/q65 are context only. q65 remains inherited 8-F data/ticket issue with mismatched `bored` tag.
- q29 overlap is preserved in reporting.

Failure classes:
- q59: retrieval recall issue; plausible query cleaning issue; silver artifact issue only for `Disconnect`.
- q49: advanced retrieval recall issue; plausible query cleaning issue; not label/provenance.
- q53: mixed retrieval recall plus silver pregrade/eval artifact issue.
- q61: stress-test retrieval/label coverage context.
- q65: inherited 8-F ticket/data issue.

Risks:
- Runtime mood objects are not persisted in run artifacts; mood fields are reconstructed from query tags and deterministic current extractor output.
- q53 should not be treated as a direct mood-cleaning regression because current extractor does not detect `current_emotion` for q53.

Assumptions:
- The 8-K scope is investigation-only and does not authorize fixes.
- Existing unrelated dirty file remains untouched.

Commit:
- Pending.

Next safe action:
- Open a q59-only fix-design ticket first. Then handle q49 advanced and q53 label/artifact triage as separate tickets.

Codex status:
- STOPPED for review after investigation. No fixes implemented.
