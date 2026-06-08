Verdict: PASS

Files changed:
- [eval/scripts/compute_metrics.py](D:/ICPCB/OneDrive/Documents/Code/Project/Movies/eval/scripts/compute_metrics.py)
- [eval/tests/test_compute_metrics.py](D:/ICPCB/OneDrive/Documents/Code/Project/Movies/eval/tests/test_compute_metrics.py)

Artifacts created:
- `eval/runs/2026-06-07-combined-nogit/metrics_provisional.json` length `28228`
- `eval/runs/2026-06-07-combined-nogit/analysis/error_report/per_query_mode.jsonl` length `125935`, `180` rows
- `eval/runs/2026-06-07-combined-nogit/analysis/error_report/summary.json` length `1934`

Validation results:
- `pytest eval/tests/test_compute_metrics.py -v`: `22 passed`
- `pytest eval/tests/ -v`: `345 passed`
- Mood axes assertion: `PASS: mood axes present`
- Error report assertion: `label_source == "silver"`
- Note: due sandbox cwd/temp restrictions, full-suite pytest was run from repo cwd with `--rootdir=eval/tests` and sandbox temp outside repo.

Mood axis buckets:
- `mood_emotion`: `anxious`, `bored`, `heartbroken`, `lonely`, `none`, `sad`, `stressed`, `tired`
- `mood_direction`: `calm_me_down`, `cheer_me_up`, `comfort_me`, `give_me_hope`, `help_me_cry`, `make_me_laugh`, `none`
- `mood_safety`: `dark_intended`, `neutral`, `none`, `safe_hopeful`

Error report:
- `mood_miss_qids`: `q21`, `q22`, `q53`, `q60`
- `mood_miss_rate`: `0.4`
- `non_mood_miss_rate`: `0.08`

Git status:
- My tracked diffs: `eval/scripts/compute_metrics.py`, `eval/tests/test_compute_metrics.py`
- `git diff --name-only -- src`: empty
- Unrelated dirty/untracked files remain in `.agents/*`, `eval/runs/2026-05-19-1846-nogit/...`, and prior Codex artifacts; ignored per ticket.

Committed: no

Next: 7-B triage

