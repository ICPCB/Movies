# Dep #3b — Merge Accepted Labels into gold_labels.jsonl

## Goal

Create a deterministic offline sidecar merge script that reads 455 human-reviewed
AI-assisted labels from the accepted-label artifact and merges them into
`gold_labels.jsonl` with honest provenance (`label_source=human_reviewed_ai_assisted`).

This is a sidecar script — it deliberately does NOT use the existing `merge_labels.py`
because that script rejects `label_source=human_reviewed_ai_assisted`.

---

## Current state

- Branch: `automation/cinematch-accuracy-audit-full`
- HEAD: `5b67e5d`
- Phase 5: BLOCKED (not affected by this ticket)
- Existing `gold_labels.jsonl`: 220 rows, `label_source` values: `gold`, `silver`
- Accepted labels: 455 rows, `label_source`: `human_reviewed_ai_assisted`
- Key overlap between the two files: **0** (verified)
- Key identity: `(qid, tmdb_id)`

---

## Files to read (do not change)

```
AGENTS.md
CLAUDE.md
eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl              (read schema + keys before merge)
eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue_accepted.jsonl
eval/scripts/merge_labels.py                                    (read only — understand what NOT to reuse)
```

---

## Files allowed to change/create

```
eval/scripts/rerank_regression_merge_accepted_labels.py         (CREATE — merge script)
eval/tests/test_rerank_regression_merge_accepted_labels.py      (CREATE — unit tests)
eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl               (UPDATE — append merged labels)
eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/merge_summary.json  (CREATE — summary artifact)
```

---

## Files forbidden to change

```
src/*                                       (no production code changes)
eval/scripts/merge_labels.py                (read only)
eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue_accepted.jsonl  (input, read only)
eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv             (read only)
AGENTS.md
CLAUDE.md
.remember/*
.agents/*
docs/*
```

---

## Schemas

### gold_labels.jsonl — existing schema (7 fields)

```json
{
  "qid": "q01",
  "tmdb_id": 1930,
  "grade": 1,
  "label_source": "silver",
  "silver_grade": 1,
  "gold_grade": null,
  "gold_notes": null
}
```

Field order in output: `qid, tmdb_id, grade, label_source, silver_grade, gold_grade, gold_notes`

Existing `label_source` values: `"gold"`, `"silver"`

### missing_label_review_queue_accepted.jsonl — input schema (13 fields)

```json
{
  "ai_assisted": true,
  "ai_confidence": "high",
  "ai_suggested_grade": 1,
  "grade": 1,
  "grader_notes": "HUMAN_REVIEWED_AI_ASSISTED: ...",
  "human_acceptance": "accepted_all",
  "label_source": "human_reviewed_ai_assisted",
  "movie_key": "title:spider man 2|year:2004",
  "qid": "q01",
  "queue_position": 0,
  "reviewed_by": "human",
  "title": "Spider-Man 2",
  "tmdb_id": 558
}
```

---

## Exact merge rules

1. **Key identity**: `(qid, tmdb_id)` — a pair uniquely identifies a label row.

2. **No duplicates within accepted labels**: If any two accepted-label rows share the
   same `(qid, tmdb_id)`, the script MUST abort with an error. Do not silently deduplicate.

3. **No overwrite of existing rows**: If an accepted-label key already exists in
   `gold_labels.jsonl`, the script MUST abort with an error. The verified overlap is 0,
   but the script must enforce this at runtime. Do not silently skip or overwrite.

4. **Grade validation**: Every accepted-label `grade` must be in `{0, 1, 2, 3}`.
   Abort on any invalid grade.

5. **Required fields in accepted labels**: Each accepted-label row must contain at least:
   `qid`, `tmdb_id`, `grade`, `label_source`. Abort on any row missing these fields.

6. **label_source validation**: Every accepted-label row must have
   `label_source == "human_reviewed_ai_assisted"`. Abort if any row has a different value.

7. **Field mapping** — each accepted-label row maps to a gold_labels row as follows:

   | gold_labels field | Source                                    |
   |-------------------|-------------------------------------------|
   | `qid`             | accepted `qid`                            |
   | `tmdb_id`         | accepted `tmdb_id`                        |
   | `grade`           | accepted `grade`                          |
   | `label_source`    | `"human_reviewed_ai_assisted"` (verbatim) |
   | `silver_grade`    | `null`                                    |
   | `gold_grade`      | `null`                                    |
   | `gold_notes`      | accepted `grader_notes`                   |

8. **Output ordering**: Group all rows by `qid` in natural sort order (`q01`, `q02`, …, `q20`).
   Within each qid group, preserve the original relative order of existing rows first,
   then append new accepted-label rows in their original file order.

9. **Output format**: One JSON object per line, no trailing comma, no trailing newline
   after the last row. Field order in each JSON object: `qid`, `tmdb_id`, `grade`,
   `label_source`, `silver_grade`, `gold_grade`, `gold_notes`.
   Use `json.dumps(row, ensure_ascii=False)` — no pretty-printing.

10. **Atomic write**: Write merged output to a `.tmp` file first, then rename over
    `gold_labels.jsonl`. Do not write in-place.

---

## Exact provenance rules

- New rows MUST use `label_source = "human_reviewed_ai_assisted"`.
- New rows MUST NOT use `label_source = "human_gold"` or `"gold"`.
- Existing rows MUST retain their original `label_source` value unchanged.
- The script MUST NOT silently convert any `label_source` value.

---

## Implementation rules

1. Script: `eval/scripts/rerank_regression_merge_accepted_labels.py`
   - Python 3.10+ stdlib only (json, pathlib, argparse, sys, os, tempfile).
   - No third-party imports. No pandas, no numpy.
   - CLI interface: `python eval/scripts/rerank_regression_merge_accepted_labels.py --run-dir eval/runs/2026-05-19-1846-nogit`
   - `--run-dir` is the only required argument.
   - The script derives paths:
     - gold: `{run_dir}/gold_labels.jsonl`
     - accepted: `{run_dir}/analysis/rerank_regression/missing_label_review_queue_accepted.jsonl`
     - summary: `{run_dir}/analysis/rerank_regression/merge_summary.json`
   - Exit 0 on success, exit 1 on any validation failure.
   - Print a one-line summary to stdout on success.
   - Print specific error messages to stderr on failure.
   - The script must be idempotent: running it twice on an already-merged file must either
     detect the overlap and abort (preferred) or produce the same output. It must NOT
     double-append.

2. Tests: `eval/tests/test_rerank_regression_merge_accepted_labels.py`
   - Use `unittest` or `pytest` (stdlib preferred).
   - Test with synthetic fixture data, not the real run directory.
   - Required test cases:
     - Happy path: 2 existing + 3 accepted → 5 merged, correct schema, correct order.
     - Duplicate key within accepted → abort with error.
     - Overlap with existing → abort with error.
     - Invalid grade (e.g., 5) → abort with error.
     - Missing required field → abort with error.
     - Wrong label_source in accepted → abort with error.
     - Idempotency: run merge, then run again → abort on overlap (not double-append).
     - Field mapping: verify `silver_grade=null`, `gold_grade=null`, `gold_notes` = grader_notes.
     - Output field order is correct.
     - Existing row label_source values are preserved unchanged.

3. Summary artifact: `merge_summary.json`
   - Written by the script on successful merge.
   - Schema:
     ```json
     {
       "existing_count": 220,
       "accepted_count": 455,
       "merged_count": 675,
       "overlap_count": 0,
       "label_sources": {
         "gold": <count>,
         "silver": <count>,
         "human_reviewed_ai_assisted": <count>
       },
       "qids": ["q01", ..., "q20"],
       "run_dir": "eval/runs/2026-05-19-1846-nogit",
       "script": "eval/scripts/rerank_regression_merge_accepted_labels.py"
     }
     ```

---

## Acceptance criteria

1. `eval/scripts/rerank_regression_merge_accepted_labels.py` exists and is valid Python.
2. `eval/tests/test_rerank_regression_merge_accepted_labels.py` exists and all tests pass.
3. Running the merge script against `eval/runs/2026-05-19-1846-nogit` exits 0.
4. Post-merge `gold_labels.jsonl` has exactly 675 rows.
5. Post-merge `gold_labels.jsonl` contains exactly 3 distinct `label_source` values:
   `gold`, `silver`, `human_reviewed_ai_assisted`.
6. All 455 new rows have `label_source == "human_reviewed_ai_assisted"`.
7. All 220 original rows are unchanged (same key, same grade, same label_source).
8. Every row in post-merge `gold_labels.jsonl` has exactly 7 fields matching the schema.
9. `merge_summary.json` exists with correct counts.
10. `git diff -- src` is empty (no `src/*` changes).
11. No network/LLM/API calls were made.

---

## Validation commands

Run these in order after implementation:

```powershell
# 1. Syntax check
python -m py_compile eval/scripts/rerank_regression_merge_accepted_labels.py

# 2. Unit tests
python -m pytest eval/tests/test_rerank_regression_merge_accepted_labels.py -v

# 3. Backup gold_labels before merge (safety)
Copy-Item "eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl" "eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl.bak"

# 4. Run the merge
python eval/scripts/rerank_regression_merge_accepted_labels.py --run-dir eval/runs/2026-05-19-1846-nogit

# 5. Post-merge row count (expect 675)
python -c "print(sum(1 for _ in open(r'eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl')))"

# 6. Post-merge label_source distribution
python -c "
import json, collections
c = collections.Counter()
for l in open(r'eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl'):
    c[json.loads(l)['label_source']] += 1
for k,v in sorted(c.items()): print(f'  {k}: {v}')
print(f'  total: {sum(c.values())}')
"

# 7. Post-merge schema check (all rows have exactly 7 fields)
python -c "
import json
expected = {'qid','tmdb_id','grade','label_source','silver_grade','gold_grade','gold_notes'}
for i,l in enumerate(open(r'eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl'),1):
    d = json.loads(l)
    assert set(d.keys()) == expected, f'Row {i} schema mismatch: {set(d.keys())}'
print(f'All {i} rows have correct schema')
"

# 8. Verify merge_summary.json exists and has correct merged_count
python -c "
import json
s = json.load(open(r'eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/merge_summary.json'))
assert s['merged_count'] == 675, f'Expected 675, got {s[\"merged_count\"]}'
print('merge_summary.json OK:', json.dumps(s, indent=2))
"

# 9. No src changes
git diff -- src

# 10. Git status
git status --short
```

---

## Stop conditions

Stop and report immediately if:

- Any accepted-label row has `label_source` other than `"human_reviewed_ai_assisted"`
- Key overlap is detected between accepted and existing labels
- Duplicate keys are found within accepted labels
- Any grade is outside `{0, 1, 2, 3}`
- Any required field is missing
- Schema mismatch in either input file
- Any validation command fails
- Any `src/*` files are modified
- Any network/LLM/API call is needed
- The post-merge row count is not exactly 675
- The existing 220 rows are altered in any way

---

## Required Codex final report format

```
Verdict: PASS | FAIL | STOPPED | NEEDS_REVIEW
Files changed:
Artifacts created:
Validation commands and results:
Git status summary:
Risks or caveats:
Whether anything was committed:
Exact next recommended step:
```

---

## Codex dispatch command (DO NOT RUN — reference only)

```powershell
Get-Content .agents\inbox\codex\dep-3b-label-merge.md -Raw |
  codex exec `
    --cd . `
    --sandbox workspace-write `
    --output-last-message .agents\outbox\codex\dep-3b-label-merge-result.md `
    -
```

---

## Dependencies

- Dep #3 grading: COMPLETE (455 labels accepted as `human_reviewed_ai_assisted`)
- Accepted-label artifact: EXISTS at the specified path
- Orchestration infra: READY (commit `5b67e5d`)

## Risk level

LOW — offline deterministic merge, no `src/*` changes, no network calls.

## Reviewer

Claude Code Pro (post-Codex review before commit).
