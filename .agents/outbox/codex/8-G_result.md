Verdict: NEEDS_REVIEW / STOPPED

Phase 8-G ran successfully but should not be closed.

Files/artifacts created:
- `eval/runs/2026-06-08-phase8-mood-nogit/candidates.jsonl` (722 candidates)
- `eval/runs/2026-06-08-phase8-mood-nogit/silver_labels.jsonl` (722 labels; 721 successful parses)
- `eval/runs/2026-06-08-phase8-mood-nogit/metrics_provisional.json`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/error_report/per_query_mode.jsonl`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/error_report/summary.json`
- `docs/superpowers/reports/phase8-regression-investigation-request.md`

Non-mood regression check:
- basic: 0.940 -> 0.940 (+0.000) PASS
- advanced: 0.960 -> 0.940 (-0.020) PASS
- hybrid: 0.940 -> 0.900 (-0.040) PASS

Blocking evidence:
- 8-E required no-mood behavior to be identical.
- No-mood hit-to-miss flips occurred:
  - basic: q02
  - advanced: q58
  - hybrid: q02, q26, q58
- Mood hybrid regressions occurred:
  - q49: 1 -> 0
  - q59: 1 -> 0

Mood improvements:
- q21 hybrid: 0 -> 1
- q53 advanced: 0 -> 1
- q60 hybrid: 0 -> 1

Stress-test baseline:
- q61: basic=1 advanced=0 hybrid=1
- q62: basic=1 advanced=1 hybrid=1
- q63: basic=1 advanced=1 hybrid=1
- q64: basic=1 advanced=0 hybrid=1
- q65: basic=1 advanced=0 hybrid=0

Next:
Claude should investigate the q02/q26/q49/q58/q59 regressions and author a bounded follow-up ticket. Codex remains implementation owner and should apply the next code change only after that investigation narrows the cause.
