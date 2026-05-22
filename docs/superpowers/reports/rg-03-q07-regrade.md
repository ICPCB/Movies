# RG-03 — q07 targeted label regrade (closeout)

Status: RG-03 COMPLETE (A1 + A2 + A3) / SELF-REVIEWED — external review
required before merge outside this branch
Date: 2026-05-22
Branch: `automation/cinematch-accuracy-audit-full`
Ticket: RG-03 (Track A)
Plan: `docs/superpowers/plans/2026-05-22-post-ql-01-tracks-a-b.md`
Predecessor: QL-01 (`docs/superpowers/reports/ql-01-query-label-review.md`)
A1 detail: `docs/superpowers/reports/rg-03-a1-recovery.md`

## Summary

QL-01 classified q07 as a `silver_label_issue`: the LLM silver pregrade
crowned the wrong film for the q07 query (vampire housemates / mockumentary /
shared chores, rent, eternal grudges). RG-03 added q07 to the human regrade
set (A1 tooling), a human re-graded the 10-row q07 top-5 union (A2), and A3
re-merged authoritative labels and metrics. The regrade confirms QL-01:
**What We Do in the Shadows (2014)** is the strict grade-3 literal answer, and
**My Babysitter's a Vampire** was silver-overgraded and drops to grade 1. No
`src/*` change at any phase; `merge_labels.py` ran unmodified.

## A2 — human regrade result (q07 batch-3)

A human filled `gold_grade` / `gold_notes` for the 10 q07 batch-3 rows only
(batch-1/2 rows untouched; A2 verification passed 7/7 per the A2 handoff). Of
the 10 q07 rows, **6 changed** vs silver (4 downgrades, 2 upgrades):

| tmdb_id | Title / note | silver | gold | Δ | gold_notes (abridged) |
|--------:|--------------|:-----:|:----:|:-:|-----------------------|
| 246741 | What We Do in the Shadows (2014) | 2 | **3** | +1 | Exact strict hit — vampire housemates in a mockumentary, rent/chores/grudges. |
| 411354 | Mockumentary short, 3 vampire flatmates | 1 | 2 | +1 | Close related hit; less exact than the 2014 feature. |
| 63700 | My Babysitter's a Vampire | **3** | 1 | −2 | Overgraded by silver; not a mockumentary, no shared chores/rent/grudges. |
| 73935 | Vampire comedy/relationship | 2 | 1 | −1 | Lacks the core mockumentary-housemate premise. |
| 317981 | Vampire office horror-comedy | 2 | 1 | −1 | Not a mockumentary, not vampire housemates; weak tonal overlap only. |
| 164052 | Not relevant | 1 | 0 | −1 | No vampires/mockumentary/roommate life in metadata. |
| 9945 | Vampire hunters + relic | 1 | 1 | 0 | Weak vampire-only match. |
| 30885 | Predatory vampires | 1 | 1 | 0 | Weak vampire match only. |
| 34223 | Fraternity pledges at vampire bar | 1 | 1 | 0 | Weak comedy/horror/vampire overlap. |
| 120092 | Sci-fi vampire coexistence | 1 | 1 | 0 | Weak vampire-world match only. |

q07 threshold crossings (5): 246741 `silver<3->gold==3`; 63700
`silver>=2->gold<2; silver==3->gold<3`; 73935 `silver>=2->gold<2`; 317981
`silver>=2->gold<2`; 411354 `silver<2->gold>=2`.

Whole-sheet agreement (55 rows, all five regraded queries): exact 0.527,
within-1 0.964, disagree≥1 = 26, disagree≥2 = 2. The two ≥2 disagreements are
q12:27205 (1→3) and q07:63700 (3→1). The q07 batch is silver-generous on
balance (4 downgrades vs 2 upgrades), consistent with the QL-01
`silver_label_issue` finding.

## A3 — commands run

```powershell
# pre-A3 backup of the authoritative artifacts (rollback evidence)
cp metrics.json      metrics.json.pre_a3.20260522T140111Z.bak
cp gold_labels.jsonl gold_labels.jsonl.pre_a3.20260522T140111Z.bak

# A3 step 1 — check
./venv/Scripts/python.exe -m eval.scripts.check_regrade_sheet --run 2026-05-19-1846-nogit
# A3 step 2 — merge
./venv/Scripts/python.exe -m eval.scripts.merge_labels       --run 2026-05-19-1846-nogit

# A3 step 3 — validation
./venv/Scripts/python.exe -m compileall eval/scripts
./venv/Scripts/python.exe -m unittest discover -s eval/tests
git diff --name-only -- src/
git status --short
```

`build_regrade_sheet` was deliberately **not** re-run at A3 — it is an A1-only
tool, and re-running it risks the from-scratch sheet rebuild that A1 already
had to recover from. A3's two tools (`check_regrade_sheet`, `merge_labels`)
only read `regrade_sheet.jsonl`.

## check_regrade_sheet — `complete: true`

`regrade_check.json` refreshed: `complete` was `false` (A1 state, q07 batch-3
pending) and is now **`true`**.

- `rows_total: 55`, `rows_filled: 55`, `pending_by_batch: {1:0, 2:0, 3:0}`.
- `by_qid` q07: `filled: 10, changed: 6`.
- CLI output: `complete=true`, exit 0.

## merge_labels result

CLI output: `merged 55 gold over 220 silver; metrics.json provisional=false`,
exit 0. `merge_labels.py` ran **unmodified** (it reads `rows_total` from the
manifest and its merge is qid-agnostic, as the plan predicted).

- `gold_labels.jsonl`: all 10 `(q07, tmdb_id)` rows now `label_source: gold`
  with the human `gold_grade` and `gold_notes`.
- `metrics.json`: `provisional: false`, `label_source:
  merged_gold_over_silver`.
- `label_provenance`: gold `45 → 55`, silver `175 → 165`, total `220`;
  `regraded_queries` `[q03, q08, q12, q13] → [q03, q07, q08, q12, q13]`.

## Files changed

Artifacts under the gitignored `eval/runs/2026-05-19-1846-nogit/` tree (not
committed):

| File | Changed by | Note |
|------|-----------|------|
| `analysis/regrade/regrade_check.json` | A3 `check_regrade_sheet` | `complete: false → true` |
| `gold_labels.jsonl` | A3 `merge_labels` | re-merged; 55 gold rows |
| `metrics.json` | A3 `merge_labels` | recomputed; non-provisional |
| `metrics.json.pre_a3.20260522T140111Z.bak` | A3 backup | pre-A3 snapshot |
| `gold_labels.jsonl.pre_a3.20260522T140111Z.bak` | A3 backup | pre-A3 snapshot |

`regrade_sheet.jsonl` was **not** modified at A3 — both A3 tools read it
read-only. It carries the A2 human grades (45 batch-1/2 + 10 q07 batch-3).

Committed docs (this closeout):

- `docs/superpowers/reports/rg-03-q07-regrade.md` (this report).
- `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` (RG-03-A3 checkpoint).

## Metrics — before vs after

The q07 regrade is the **only** label change between the two snapshots, so
every delta below is attributable to q07. **No metric regressed; all deltas
are ≥ 0.**

### by_mode (top-5 / top-10)

| Mode | Metric | Before | After | Δ |
|------|--------|-------:|------:|---:|
| basic | hit@5 | 0.9000 | 0.9000 | 0 |
| basic | strict_hit@5 | 0.5000 | 0.5000 | 0 |
| basic | mrr@5 | 0.7542 | 0.7792 | +0.0250 |
| basic | strict_mrr@5 | 0.2867 | 0.2933 | +0.0067 |
| basic | ndcg@5 | 0.7504 | 0.7585 | +0.0081 |
| basic | strict_hit@10 | 0.5500 | 0.5500 | 0 |
| basic | mrr@10 | 0.7592 | 0.7842 | +0.0250 |
| basic | ndcg@10 | 0.6362 | 0.6409 | +0.0047 |
| advanced | hit@5 | 1.0000 | 1.0000 | 0 |
| advanced | **strict_hit@5** | **0.5000** | **0.5500** | **+0.0500** |
| advanced | mrr@5 | 0.8325 | 0.8575 | +0.0250 |
| advanced | strict_mrr@5 | 0.3142 | 0.3392 | +0.0250 |
| advanced | ndcg@5 | 0.7728 | 0.7940 | +0.0213 |
| advanced | **strict_hit@10** | **0.5000** | **0.5500** | **+0.0500** |
| advanced | mrr@10 | 0.8325 | 0.8575 | +0.0250 |
| advanced | ndcg@10 | 0.6559 | 0.6713 | +0.0153 |
| hybrid | hit@5 | 0.9500 | 0.9500 | 0 |
| hybrid | strict_hit@5 | 0.2500 | 0.2500 | 0 |
| hybrid | mrr@5 | 0.7850 | 0.8250 | +0.0400 |
| hybrid | strict_mrr@5 | 0.1917 | 0.1917 | 0 |
| hybrid | ndcg@5 | 0.7246 | 0.7319 | +0.0073 |
| hybrid | **strict_hit@10** | **0.4000** | **0.4500** | **+0.0500** |
| hybrid | mrr@10 | 0.7850 | 0.8250 | +0.0400 |
| hybrid | strict_mrr@10 | 0.2090 | 0.2174 | +0.0083 |
| hybrid | ndcg@10 | 0.6255 | 0.6353 | +0.0099 |

### label_provenance

| Field | Before | After |
|-------|-------:|------:|
| gold | 45 | 55 |
| silver | 175 | 165 |
| total | 220 | 220 |
| regraded_queries | q03, q08, q12, q13 | q03, q07, q08, q12, q13 |

### Reading the q07-attributable deltas

- The corrected grade-3 (246741, What We Do in the Shadows 2014) lifts
  `advanced` `strict_hit@5/@10` by +0.05 — advanced ranks the true answer in
  its top 5.
- `hybrid` `strict_hit@5` stays 0.25 while `hybrid strict_hit@10` rises +0.05:
  even with the corrected label, hybrid places the true grade-3 answer in its
  top 10 but **not** its top 5. This is consistent with QL-01 treating q07 as
  a label issue *separate from* the q05/q10 ranking defect — the q07 label fix
  is now applied; any remaining q07 hybrid top-5 gap is a ranking question and
  is **out of RG-03 scope**.
- MRR gains across all three modes reflect both the promotion of 246741/411354
  and the demotion of the silver-overgraded 63700/73935/317981.

## QL-01 conclusion — confirmed by the human regrade

- **What We Do in the Shadows (2014)** (tmdb 246741) is the strict grade-3
  literal answer for q07: vampire housemates in a mockumentary dealing with
  mundane modern life — rent, chores, and interpersonal grudges. Silver had it
  at grade 2; the human regrade corrects it to 3.
- **My Babysitter's a Vampire** (tmdb 63700) was silver-overgraded at grade 3
  and drops to **grade 1**: it has a vampire/fantasy-comedy element but is not
  a mockumentary and does not match the shared-chores / rent / roommate-grudges
  premise. This is one of only two ≥2 disagreements on the whole 55-row sheet.

RG-03 thus closes q07 as a corrected `silver_label_issue`. q07 stays a
label/data correction and is excluded from Track B (DECOMP-01).

## No `src/*` changes

`git diff --name-only -- src/` is **empty**. No `src/*` file was created or
modified at any RG-03 phase. `merge_labels.py` ran unmodified. `git status`
shows only the pre-existing untracked `graphify-out/` (unrelated to RG-03).

## DECOMP-01 and Phase 5 — not started

- **DECOMP-01 (Track B)** has **not** started. q05/q10 decomposition remains
  unaddressed; it is a separate, model-backed (GPU) ticket.
- **Phase 5** (any `src/*` accuracy change) remains **BLOCKED**. RG-03
  (Track A) is data/eval correction only and does not unblock Phase 5 — per
  the gate, Phase 5 unblocks only on a decisive DECOMP-01 outcome.

## Validation

- `python -m compileall eval/scripts` — passed (exit 0).
- `python -m unittest discover -s eval/tests` — **190 tests OK**.
- `python -m eval.scripts.check_regrade_sheet --run 2026-05-19-1846-nogit` —
  `complete=true`, exit 0.
- `python -m eval.scripts.merge_labels --run 2026-05-19-1846-nogit` —
  `merged 55 gold over 220 silver; provisional=false`, exit 0.
- `git diff --name-only -- src/` — empty.

## State / next

- RG-03 is COMPLETE across A1 + A2 + A3. Authoritative `gold_labels.jsonl` and
  `metrics.json` for run `2026-05-19-1846-nogit` now reflect the q07 regrade.
- External review is **required before merge outside this branch** — RG-03
  changes labels and recomputes authoritative metrics (a private-data decision
  under the automation rules).
- Next ticket (separately gated, not started here): DECOMP-01 (Track B) for
  q05/q10.
