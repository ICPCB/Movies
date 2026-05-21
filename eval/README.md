# CineMatch Eval Harness

This directory contains the Phase 1 evaluation harness. It is additive only:
scripts may import `src.*`, but no eval script should edit `src/` or change
retrieval, ranking, embedding, reranking, or LLM behavior.

## Layout

```text
eval/
  README.md
  queries/
    v1.jsonl
  runs/
    <run_id>/
      run_manifest.json
      config_snapshot.json
      candidates.jsonl
      silver_labels.jsonl
      metrics_provisional.json
  scripts/
    _run_io.py
    _schemas.py
    hybrid_gap_trace.py
    hybrid_expansion_stability.py
    hy_fix_localize.py
    hybrid_live_trace.py
    hybrid_stage_trace.py
    build_regrade_sheet.py
    check_regrade_sheet.py
    error_report.py
    merge_labels.py
  tests/
```

All artifact paths under `eval/runs/<run_id>/` must be computed through
`eval.scripts._run_io`. Other modules should not build run-directory paths by
hand. Phase 1 does not write `eval/runs/current_run.txt`; that pointer is for
the later non-provisional metrics flow.

## Run Lifecycle

1. A script asks `_run_io.new_run_id()` for a no-git run id.
2. `_run_io.ensure_run_dir(run_id)` creates `eval/runs/<run_id>/`.
3. `_run_io.write_manifest(run_id)` writes `run_manifest.json`.
4. `_run_io.write_config_snapshot(run_id)` writes `config_snapshot.json`.
5. `run_pipelines.py` writes `candidates.jsonl`.
6. `llm_pregrade.py` writes `silver_labels.jsonl`.
7. `compute_metrics.py` writes `metrics_provisional.json`.
8. Human review stops Phase 1 before any Phase 2 gold-label workflow begins.

## No-Git Mode

This repository is currently in no-git mode. Run manifests must record:

```json
{
  "git_sha": null,
  "git_dirty": null,
  "git_mode": "no_git"
}
```

Run ids use UTC minute precision and the `nogit` suffix:
`YYYY-MM-DD-HHMM-nogit`.

## V1 Baseline Recipe

1. PowerShell/POSIX: `python -m compileall eval/scripts`
2. PowerShell/POSIX: `python -m unittest discover -s eval/tests -t .`
3. PowerShell/POSIX: `python scripts/quality_smoke_test.py --no-llm`
4. PowerShell/POSIX: `python eval/scripts/run_pipelines.py --queries eval/queries/v1.jsonl --top-k 15`
5. PowerShell/POSIX: `python eval/scripts/llm_pregrade.py`
6. PowerShell/POSIX: `python eval/scripts/compute_metrics.py`
7. PowerShell: `$run = Get-ChildItem eval/runs -Directory -Filter "*-nogit" | Sort-Object Name | Select-Object -Last 1`
8. PowerShell: `python -c "import json,os; p=os.path.join(r'$($run.FullName)','metrics_provisional.json'); d=json.load(open(p, encoding='utf-8')); assert d['provisional'] is True and len(d['by_mode'])==3 and 'vocab_distance' in d['by_axis']; print('ok', r'$($run.FullName)')"`
9. POSIX: `run="$(find eval/runs -maxdepth 1 -type d -name '*-nogit' | sort | tail -n 1)"`
10. POSIX: `python -c "import json,os; p=os.path.join('$run','metrics_provisional.json'); d=json.load(open(p, encoding='utf-8')); assert d['provisional'] is True and len(d['by_mode'])==3 and 'vocab_distance' in d['by_axis']; print('ok', '$run')"`
11. PowerShell/POSIX: `python -m eval.scripts.error_report --run <run_id> --k 5`
12. PowerShell/POSIX: `python -m eval.scripts.audit_silver_labels --run <run_id>`
