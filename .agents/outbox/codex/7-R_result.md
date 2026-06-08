Verdict: PASS / NEEDS_HUMAN_REVIEW

Files changed:
- `eval/scripts/merge_labels.py`
- `eval/tests/test_merge_labels.py`
- `eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_sheet.jsonl`
- `eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl`
- `eval/runs/2026-06-07-combined-nogit/metrics.json`
- `docs/superpowers/reports/phase7-mood-analysis.md`
- `docs/superpowers/plans/phase8-mood-retrieval-fixes.md`
- `.agents/outbox/codex/7-R_result.md`

Provenance counts:
- `ai_draft`: 13
- `null_parse_error_fixed`: 1
- `silver_llm_pregrade`: 630
- total merged labels: 644
- `human_gold`: 0

Analysis additions:
- Added energy_level table to `phase7-mood-analysis.md`.
- Added intensity table to `phase7-mood-analysis.md`.
- Added explicit warning that small buckets are directional debugging evidence, not reliable population estimates.
- Reconciled `phase8-mood-retrieval-fixes.md` with approved contracts:
  - exact six 8-B synonym groups
  - 8-D stable move-to-bottom safety demotion based only on genres/keywords
  - q61-q65 summaries from 8-F
  - 8-G stopped pending deterministic attribution and human review
  - no safety-demotion config constant

Commands run:
- `.\venv\Scripts\python.exe -m pytest eval/tests/test_merge_labels.py -q --basetemp="$env:TEMP\cinematch-7r-merge"`
- `.\venv\Scripts\python.exe eval/scripts/merge_labels.py --run 2026-06-07-combined-nogit --queries eval/queries/all.jsonl`
- `.\venv\Scripts\python.exe -c "import json; from pathlib import Path; rows=[json.loads(x) for x in Path('eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl').read_text(encoding='utf-8').splitlines()]; assert rows and all(r.get('label_provenance') for r in rows); assert not any(r.get('label_provenance') == 'human_gold' for r in rows); m=json.loads(Path('eval/runs/2026-06-07-combined-nogit/metrics.json').read_text(encoding='utf-8')); counts=m['label_provenance']['counts']; assert isinstance(counts, dict) and counts; assert sum(counts.values()) == len(rows); print('provenance PASS')"`
- `git diff --name-only`
- `git status --short`

Validation:
- Merge tests: PASS, 15 passed.
- Real merge command: PASS.
- Provenance assertion: PASS.

Artifacts:
- `eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_sheet.jsonl`
- `eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl`
- `eval/runs/2026-06-07-combined-nogit/metrics.json`

Risks:
- Existing regrade rows remain `ai_draft` unless human review is explicitly recorded.
- `eval/runs/**` artifacts are gitignored; they were regenerated and validated locally but are not part of the normal commit.
- Existing unrelated dirty file remains: `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv`.

Human decision still required:
- Review and approve or revise the 13 `ai_draft` regrades before representing them as human-reviewed.
- Review 8-I `review_queue.jsonl` before authorizing 8-J.

Commit:
- `bad023d`

Next safe action:
- Commit scoped 7-R tracked changes if staged set excludes unrelated dirty files.
- Stop 8-J until human approval of q49 evidence is recorded.
