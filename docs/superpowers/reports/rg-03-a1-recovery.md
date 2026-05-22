# RG-03 A1 — q07 regrade batch tooling + sheet recovery

Status: A1 COMPLETE / SELF-REVIEWED — A2 (human regrade) pending
Date: 2026-05-22
Branch: `automation/cinematch-accuracy-audit-full`
Ticket: RG-03 (Track A), phase A1
Plan: `docs/superpowers/plans/2026-05-22-post-ql-01-tracks-a-b.md`

## Summary

RG-03 A1 adds an additive, non-destructive q07 "batch 3" to the existing
regrade flow so a human can re-grade the q07 top-5 union — QL-01 classified q07
as a `silver_label_issue`. During A1 the run's `regrade_sheet.jsonl` was found
rebuilt-from-scratch, with the 45 batch-1/batch-2 human gold grades dropped from
the sheet. Those grades survived in `gold_labels.jsonl`; a one-time recovery
restored them. No `src/*` change; `merge_labels.py` unchanged.

## A1 tooling

- `eval/scripts/build_regrade_sheet.py` — `add_q07_batch()` appends batch 3
  (`batch_purpose: ql_01_label_followup`) with an append-only write; existing
  rows are never rewritten. `_build_union_batch()` is the shared helper for
  batch 2 and batch 3. New `--add-q07-batch` CLI flag, idempotent guard, and a
  guard requiring an existing base sheet.
- `eval/scripts/check_regrade_sheet.py` — reconstructs batch 3 when the
  manifest reports it; `q07` added to `PREFERRED_QID_ORDER`.
- `eval/tests/test_build_regrade_sheet.py` — `AddQ07BatchTests` (7 tests),
  including a byte-identical preservation test for existing rows.

## Sheet recovery

Finding: `regrade_sheet.jsonl` on disk had 55 rows but 0 filled `gold_grade` —
it had been deleted and rebuilt during prior A1 work. The 45 batch-1/2 grades
(q03/q08/q12/q13) survived in `gold_labels.jsonl` (`label_source: gold`, with
`gold_notes`); `metrics.json` stayed non-provisional.

Recovery — `eval/scripts/rehydrate_regrade_sheet.py` (one-time):

1. Backed up the current sheet with a UTC timestamp; verified backup SHA256.
2. Joined `gold_labels.jsonl` on `(qid, tmdb_id)`; restored `gold_grade` /
   `gold_notes` for the 45 batch-1/2 rows only. q07 batch-3 left `null` for A2.
3. Wrote `regrade_sheet.rehydrated_from_gold_labels.jsonl`; self-verified
   (55 rows, 45 gold, q07 10×null, no duplicate `(qid, tmdb_id)`, q07 rows
   byte-unchanged, key sets intact, no join/integrity problems).
4. Replaced the live sheet only after verification passed.

SHA256:

- pre-recovery sheet / backup: `de5c2fd58d439717d36d6218857e175ff2e8b88c82d46955a5458d479804cbd1`
- rehydrated / new live sheet: `89911e74d9a6ca45197bc1cb4149bfa348d20c4feb9db315453cf9fc3db3bc1e`

Backup: `eval/runs/2026-05-19-1846-nogit/analysis/regrade/regrade_sheet.jsonl.pre_rehydrate.20260522T103233Z.bak`

The sheet, backup, rehydrated intermediate, and `regrade_check.json` live under
the gitignored `eval/runs/` tree and are not committed.

## Validation

- `python -m compileall eval/scripts` — passed.
- `python -m unittest discover -s eval/tests` — 190 tests OK (183 prior + 7).
- `python -m eval.scripts.check_regrade_sheet --run 2026-05-19-1846-nogit` —
  `rows_total 55`, `rows_filled 45`, `pending_by_batch {1:0, 2:0, 3:10}`,
  `complete false`. Structurally accepted (batch-3 reconstruction matches).
- `git diff --name-only -- src/` — empty.

## State / next

- Phase 5 remains BLOCKED. A2/A3 not started; DECOMP-01 not started.
- A2 (human): fill `gold_grade` + `gold_notes` for the 10 q07 batch-3 rows
  only — tmdb 9945, 30885, 34223, 63700, 73935, 120092, 164052, 246741,
  317981, 411354. QL-01 targets: 246741 (What We Do in the Shadows, 2014),
  63700 (My Babysitter's a Vampire). Where `gold_grade != silver_grade`,
  `gold_notes` must be a non-empty string. Do not edit batch-1/2 rows.
- A3 (`check_regrade_sheet` must report `complete: true`, then `merge_labels`)
  is separately gated and changes authoritative metrics — external review
  required before merge outside this branch.
