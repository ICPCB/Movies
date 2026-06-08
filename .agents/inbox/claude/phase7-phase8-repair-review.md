# Claude Review Request: Phase 7/8 Repair Sequence

Claude Code Pro is the project lead, reviewer, and planner. Codex remains the
sole implementation owner.

## Review scope

Review these proposed Codex tickets:

- `.agents/inbox/codex/7Rphase7compliancerepair.md`
- `.agents/inbox/codex/8Hphase8isolationrepair.md`
- `.agents/inbox/codex/8Iregressionattribution.md`

Also inspect:

- `AGENTS.md`
- `.remember/remember.md`
- `docs/superpowers/reports/phase8-regression-investigation-request.md`
- the original 7-C, 7-D, and 8-A through 8-G tickets
- the current diffs for every file listed by the proposed tickets
- baseline and Phase 8 candidate/label rows for q02, q26, q49, q58, q59

## Confirmed evidence to verify

1. q02/basic has identical top-five IDs in both runs, but:
   - Alien Xmas grade changed 2 to 1;
   - Scooby-Doo! Haunted Holidays grade changed 2 to 1.
   This is a label-only hit flip.

2. q26 and q58 have no detected mood. The current 8-C prompt strings are used
   globally, so advanced/hybrid no-mood retrieval is not isolated from Phase 8.

3. The exact q49 query:

   `super stressed from work need something light and funny to just zone out`

   currently returns `current_emotion=None`, so cleaned-query and safety behavior
   do not activate.

4. q59 is detected as `lonely` and `safe_hopeful`. Its Phase 8 hybrid top five
   are already in descending final_score order, so its miss occurs before the
   safety filter.

5. The two runs were independently retrieved and independently LLM-pregraded.
   Current hit flips therefore cannot be used directly as proof of a production
   accuracy regression.

6. The safety filter scans title and overview although 8-D authorizes only
   genres and keywords.

## Required review output

For each proposed ticket, return:

- `APPROVE`, `REVISE`, or `REJECT`;
- contract or safety defects;
- exact requested edits to the ticket;
- whether its validation proves its acceptance criteria;
- whether any allowed file is unnecessary or any required file is missing.

Then return:

- approved execution order;
- whether Codex may start 7-R immediately;
- explicit statement that Claude will review implementation diffs and results
  but will not implement production code;
- exact stop condition before another full 8-G run.

Do not edit production, eval, report, ledger, state, or remember files.
Do not implement any ticket.

