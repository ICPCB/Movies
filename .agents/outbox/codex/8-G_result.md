# Gate 8-G Result - Full Eval Regression Check

Verdict: PASS / NEEDS_REVIEW

Non-mood regression check:
- Baseline run: `2026-06-07-combined-nogit`
- New run: `2026-06-08-phase8j-gated-nogit`
- Required aggregate validation:
  - basic: 0.933 -> 0.908 (-0.026) OK
  - advanced: 0.933 -> 0.892 (-0.041) OK
  - hybrid: 0.900 -> 0.892 (-0.008) OK
- Literal ticket non-mood set:
  - basic: 0.941176 -> 0.921569 (-0.019607) OK
  - advanced: 0.960784 -> 0.980392 (+0.019608) OK
  - hybrid: 0.941176 -> 0.960784 (+0.019608) OK
- Effective non-mood set excluding explicit mood q29 overlap:
  - basic: 0.94 -> 0.92 (-0.02) OK
  - advanced: 0.96 -> 0.98 (+0.02) OK
  - hybrid: 0.94 -> 0.96 (+0.02) OK

Mood query improvement:
- q21: basic 1->1, advanced 1->1, hybrid 0->1
- q22: basic 0->0, advanced 0->0, hybrid 0->0
- q29: basic 1->1, advanced 1->1, hybrid 1->1
- q49: basic 1->1, advanced 1->0, hybrid 1->1
- q50: basic 1->1, advanced 1->1, hybrid 1->1
- q53: basic 1->1, advanced 0->0, hybrid 1->0
- q54: basic 1->1, advanced 1->1, hybrid 1->1
- q55: basic 1->1, advanced 1->1, hybrid 1->1
- q59: basic 1->1, advanced 1->0, hybrid 1->0
- q60: basic 1->1, advanced 1->1, hybrid 0->1

Stress-test baseline:
- q61: basic 0, advanced 0, hybrid 0
- q62: basic 1, advanced 1, hybrid 1
- q63: basic 1, advanced 1, hybrid 1
- q64: basic 1, advanced 1, hybrid 1
- q65: basic 1, advanced 0, hybrid 0

Artifacts created:
- `eval/runs/2026-06-08-phase8j-gated-nogit/candidates.jsonl`
- `eval/runs/2026-06-08-phase8j-gated-nogit/silver_labels.jsonl`
- `eval/runs/2026-06-08-phase8j-gated-nogit/metrics_provisional.json`
- `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/error_report/per_query_mode.jsonl`
- `eval/runs/2026-06-08-phase8j-gated-nogit/analysis/error_report/summary.json`
- `eval/runs/2026-06-08-phase8j-gated-nogit/gate_8g_regression_comparison.json`

Validation commands and results:
- `.\venv\Scripts\python.exe eval/scripts/run_pipelines.py --queries eval/queries/all.jsonl --top-k 15 --seed 42 --run-id 2026-06-08-phase8j-gated-nogit`: PASS, candidates generated. Wrapper command timed out after 60 minutes, but the underlying process continued and completed candidate generation.
- `.\venv\Scripts\python.exe eval/scripts/llm_pregrade.py --run 2026-06-08-phase8j-gated-nogit --queries eval/queries/all.jsonl --seed 42`: PASS, rows_written=694, parse_rate=1.000.
- `.\venv\Scripts\python.exe eval/scripts/compute_metrics.py --run 2026-06-08-phase8j-gated-nogit --queries eval/queries/all.jsonl --bootstrap-b 1000 --seed 42`: PASS, queries_total=65.
- `.\venv\Scripts\python.exe eval/scripts/error_report.py --run 2026-06-08-phase8j-gated-nogit --k 5 --labels silver`: PASS.
- Required baseline/new metrics comparison: PASS for basic, advanced, hybrid.

Reviewer:
- Claude Opus 4.6 read-only review was requested with `claude --model claude-opus-4-6`.
- Claude review artifact: `C:\Users\Minh Nguyen\.claude\plans\you-are-claude-code-toasty-lagoon.md`
- Claude verdict: PASS for non-mood safety gate, NEEDS_REVIEW for mood regressions.

Risks or caveats:
- q29 appears in both the ticket's non-mood range and explicit mood list; both literal and mood-excluded checks were recorded.
- q49 advanced, q53 hybrid, and q59 advanced/hybrid regressed. Claude recommends opening a follow-up investigation ticket before declaring Phase 8 complete.

Git status summary:
- New 8-G eval run artifacts and this result report are expected changes.
- Pre-existing unrelated dirty file remains: `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/missing_label_review_queue.csv`.

Commit:
- `707cab5`

Exact next recommended step:
- Open a follow-up ticket for q59 first, plus q49/q53 and q61/q65 triage, before Phase 8 completion.
