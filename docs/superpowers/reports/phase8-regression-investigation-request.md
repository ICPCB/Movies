# Phase 8-G Regression Investigation Request

## Verdict

NEEDS_REVIEW / STOPPED.

Phase 8-G produced a fresh 65-query run, but the result is not clean enough to close Phase 8.

The formal 8-G aggregate non-mood gate passes: non-mood hit@5 does not drop by more than 0.05 in any mode. However, 8-E also required no-mood behavior to remain identical, and the fresh run shows concrete no-mood hit-to-miss flips. Mood regressions also appear in hybrid.

Claude should investigate root cause and recommend the next ticket. Codex remains implementation owner and should apply any follow-up code ticket after review.

## Runs Compared

- Baseline: `eval/runs/2026-06-07-combined-nogit`
- Phase 8 run: `eval/runs/2026-06-08-phase8-mood-nogit`
- Query file: `eval/queries/all.jsonl` (`q01`-`q65`)
- Labels: silver

## Commands Run

```powershell
cmd /c "cd /d D:\ICPCB\OneDrive\Documents\Code\Project\Movies && set PYTHONPATH=D:\ICPCB\OneDrive\Documents\Code\Project\Movies&& set HF_HUB_OFFLINE=1&& set TRANSFORMERS_OFFLINE=1&& venv\Scripts\python.exe eval\scripts\run_pipelines.py --queries eval\queries\all.jsonl --top-k 15 --seed 42 --run-id 2026-06-08-phase8-mood-nogit"
cmd /c "cd /d D:\ICPCB\OneDrive\Documents\Code\Project\Movies && set PYTHONPATH=D:\ICPCB\OneDrive\Documents\Code\Project\Movies&& venv\Scripts\python.exe eval\scripts\llm_pregrade.py --run 2026-06-08-phase8-mood-nogit --queries eval\queries\all.jsonl --seed 42"
cmd /c "cd /d D:\ICPCB\OneDrive\Documents\Code\Project\Movies && set PYTHONPATH=D:\ICPCB\OneDrive\Documents\Code\Project\Movies&& venv\Scripts\python.exe eval\scripts\compute_metrics.py --run 2026-06-08-phase8-mood-nogit --queries eval\queries\all.jsonl --bootstrap-b 1000 --seed 42"
cmd /c "cd /d D:\ICPCB\OneDrive\Documents\Code\Project\Movies && set PYTHONPATH=D:\ICPCB\OneDrive\Documents\Code\Project\Movies&& venv\Scripts\python.exe eval\scripts\error_report.py --run 2026-06-08-phase8-mood-nogit --labels silver"
```

## Artifact Summary

- `eval/runs/2026-06-08-phase8-mood-nogit/candidates.jsonl`: 722 candidates
- `eval/runs/2026-06-08-phase8-mood-nogit/silver_labels.jsonl`: 722 rows
- LLM pregrade parse rate: 721/722 successful parses
- Null label: `q59`, `tmdb_id=115442`
- `eval/runs/2026-06-08-phase8-mood-nogit/metrics_provisional.json`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/error_report/per_query_mode.jsonl`
- `eval/runs/2026-06-08-phase8-mood-nogit/analysis/error_report/summary.json`

## Aggregate Metrics

| Mode | Baseline hit@5 | Phase 8 hit@5 | Delta | Baseline sh@5 | Phase 8 sh@5 |
|---|---:|---:|---:|---:|---:|
| basic | 0.933 | 0.938 | +0.005 | 0.617 | 0.523 |
| advanced | 0.933 | 0.892 | -0.041 | 0.627 | 0.531 |
| hybrid | 0.900 | 0.862 | -0.038 | 0.525 | 0.508 |

## Non-Mood Gate

Non-mood query set used from query tags: `q01-q20`, `q23-q28`, `q30-q48`, `q51-q52`, `q56-q58` (`n=50`).

| Mode | Baseline non-mood hit@5 | Phase 8 non-mood hit@5 | Delta | Gate |
|---|---:|---:|---:|---|
| basic | 0.940 | 0.940 | +0.000 | PASS |
| advanced | 0.960 | 0.940 | -0.020 | PASS |
| hybrid | 0.940 | 0.900 | -0.040 | PASS |

Although the aggregate gate passes, hit-to-miss flips violate the 8-E no-mood-identical acceptance criterion:

- basic flips: `q02`
- advanced flips: `q58`
- hybrid flips: `q02`, `q26`, `q58`

## Mood Query Changes

| QID | Basic | Advanced | Hybrid |
|---|---|---|---|
| q21 | 1 -> 1 | 1 -> 1 | 0 -> 1 |
| q22 | 0 -> 0 | 0 -> 0 | 0 -> 0 |
| q29 | 1 -> 1 | 1 -> 1 | 1 -> 1 |
| q49 | 1 -> 1 | 1 -> 1 | 1 -> 0 |
| q50 | 1 -> 1 | 1 -> 1 | 1 -> 1 |
| q53 | 1 -> 1 | 0 -> 1 | 1 -> 1 |
| q54 | 1 -> 1 | 1 -> 1 | 1 -> 1 |
| q55 | 1 -> 1 | 1 -> 1 | 1 -> 1 |
| q59 | 1 -> 1 | 1 -> 1 | 1 -> 0 |
| q60 | 1 -> 1 | 1 -> 1 | 0 -> 1 |

Mood improvements: `q21` hybrid, `q53` advanced, `q60` hybrid.

Mood regressions: `q49` hybrid, `q59` hybrid.

## Stress Query Baseline

| QID | Basic | Advanced | Hybrid |
|---|---:|---:|---:|
| q61 | 1 | 0 | 1 |
| q62 | 1 | 1 | 1 |
| q63 | 1 | 1 | 1 |
| q64 | 1 | 0 | 1 |
| q65 | 1 | 0 | 0 |

## Investigation Questions For Claude

1. Are q02/q26/q58 flips caused by mood integration, prompt wording, LLM nondeterminism, label drift, or unrelated retrieval variance?
2. Did 8-E's use of `cleaned_query` for mood queries indirectly alter non-mood behavior, or are the non-mood flips due to the new silver labeling pass?
3. For q49/q59 hybrid regressions, did the cleaned query, synonym groups, or safety filter remove useful candidates from the top five?
4. Should Phase 8 proceed with a targeted fix ticket, a stricter deterministic no-mood equivalence test, or rollback of pipeline integration while preserving 8-A/8-B/8-C/8-D modules?

## Recommended Next Ticket Shape

Claude should author a bounded investigation ticket that allows Codex to:

- read the baseline and Phase 8 run artifacts listed above;
- trace q02, q26, q49, q58, and q59 through `advanced.py`/`hybrid.py`;
- run small targeted pipeline traces only for those qids;
- avoid broad production edits;
- propose a minimal follow-up implementation ticket if the root cause is confirmed.

No broad `src/*` behavior changes should be made until that investigation is reviewed.
