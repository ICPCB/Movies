Verdict: PASS / NEEDS_REVIEW

Files created:
- `eval/scripts/phase8_regression_attribution.py`
- `eval/tests/test_phase8_regression_attribution.py`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.json`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.md`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/review_queue.jsonl`
- `.agents/outbox/codex/8-I_result.md`

Classification summary:
- q02: basic=`label_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- q26: basic=`candidate_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- q49: basic=`candidate_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- q58: basic=`candidate_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`
- q59: basic=`candidate_only`, advanced=`insufficient_labels`, hybrid=`insufficient_labels`

Label conflicts:
- q02/basic: `245881 2->1`, `656561 2->1`
- q02/advanced: `10193 2->3`
- q26/basic: `453 2->1`
- q49/basic: `13354 1->2`
- q59/basic: `474994 2->1`, `500688 1->2`

Review queue:
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/review_queue.jsonl`
- 86 rows
- provenance is `ai_draft`
- review status is `pending_human`

Commands run:
- `.\venv\Scripts\python.exe -m pytest eval/tests/test_phase8_regression_attribution.py -q --basetemp="$env:TEMP\cinematch-8i"`
- `.\venv\Scripts\python.exe eval/scripts/phase8_regression_attribution.py --baseline-run 2026-06-07-combined-nogit --candidate-run 2026-06-08-phase8-mood-nogit --queries eval/queries/all.jsonl --qids q02,q26,q49,q58,q59 --output-dir eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution`
- `.\venv\Scripts\python.exe -c "import json; from pathlib import Path; p=Path('eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.json'); d=json.loads(p.read_text(encoding='utf-8')); c=d['by_qid']['q02']['by_mode']['basic']['classification']; assert c in {'label_only','candidate_only','mixed','insufficient_labels'}; print(f'q02/basic classification: {c}')"`

Validation:
- Focused tests: PASS, 6 passed.
- Real artifact generation: PASS.
- q02/basic assertion: PASS, classification=`label_only`.
- Existing run candidate, label, metrics, and manifest artifacts were not modified.

Accuracy decisions deferred:
- Yes. Advanced/hybrid evidence for q02/q26/q49/q58/q59 is `insufficient_labels`, so no production accuracy fix is recommended by this ticket.
- Human review is required before any q49/q59 or advanced/hybrid fix ticket.

Commit:
- None. Ticket 8-I did not explicitly authorize commit.

Next safe action:
- Claude review of `attribution.json`, `attribution.md`, and `review_queue.jsonl`.
- After review, decide whether to authorize 8-H isolation repair and/or 8-J q49 mood detection.
