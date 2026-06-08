---
ticket_id: 7-R
phase: 7
depends_on: [7-A, 7-B, pre-7-C, 7-C, 7-D]
human_gate: yes
status: REVISED_AFTER_CLAUDE_REVIEW
---

1. Goal

   Repair the remaining Phase 7 contract gaps without changing any retrieval,
   ranking, or production behavior:

   - preserve honest per-label provenance;
   - add the missing energy_level and intensity analysis;
   - reconcile the Phase 8 plan with the approved 8-A through 8-G tickets.

2. Current repo state

   - The combined run is `eval/runs/2026-06-07-combined-nogit`.
   - `metrics.json` exists and is non-provisional.
   - Regraded rows currently use operational `label_source: "gold"` but do not
     preserve a separate provenance value.
   - AI-assisted notes must not be represented as pure human gold.
   - `phase7-mood-analysis.md` omits energy_level and intensity breakdowns.
   - `phase8-mood-retrieval-fixes.md` conflicts with the approved ticket
     contracts for 8-B, 8-D, and 8-F.

3. Files to read

   - `AGENTS.md`
   - `.remember/remember.md`
   - `.agents/inbox/codex/7Clabelfixesgoldmetrics.md`
   - `.agents/inbox/codex/7Danalysisphase8proposal.md`
   - `.agents/inbox/codex/8Bsynonymgroups.md`
   - `.agents/inbox/codex/8Dsafetyfilter.md`
   - `.agents/inbox/codex/8Fstresstestqueries.md`
   - `eval/scripts/merge_labels.py`
   - `eval/tests/test_merge_labels.py`
   - `eval/queries/all.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_sheet.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/metrics.json`
   - `docs/superpowers/reports/phase7-mood-analysis.md`
   - `docs/superpowers/plans/phase8-mood-retrieval-fixes.md`

4. Files allowed to change

   - `eval/scripts/merge_labels.py`
   - `eval/tests/test_merge_labels.py`
   - `eval/runs/2026-06-07-combined-nogit/analysis/regrade/regrade_sheet.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl`
   - `eval/runs/2026-06-07-combined-nogit/metrics.json`
   - `docs/superpowers/reports/phase7-mood-analysis.md`
   - `docs/superpowers/plans/phase8-mood-retrieval-fixes.md`
   - `.agents/outbox/codex/7-R_result.md`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `.remember/remember.md`

5. Files forbidden to change

   - `src/*`
   - `eval/queries/*`
   - all other `eval/scripts/*`
   - all other `eval/tests/*`
   - baseline candidates and silver labels

6. Exact implementation rules

   6a. Keep `label_source` as the operational merge selector:
       - `gold` for an overriding regrade;
       - `silver` for an untouched pregrade.

   6b. Add a separate required `label_provenance` field to regrade rows and
       merged gold rows.

   6c. Allowed regrade provenance values:
       - `ai_draft`
       - `human_reviewed_ai_assisted`
       - `null_parse_error_fixed`

   6d. Do not invent human review:
       - existing AI-assisted regrades remain `ai_draft` unless an explicit
         human decision is already recorded in repository evidence;
       - the q55 row that repairs the prior null parse may use
         `null_parse_error_fixed`;
       - never write `human_gold`.

   6e. Silver fallback rows use `label_provenance: "silver_llm_pregrade"`.

   6f. `metrics.json["label_provenance"]` must preserve existing summary keys
       and include a nested `counts` object keyed by provenance value. Only
       `label_provenance["counts"]` is summed for count validation, and the
       counts must sum to total labels.

   6g. Add tests covering:
       - missing provenance rejected for regrade rows;
       - unsupported provenance rejected;
       - `human_gold` rejected;
       - provenance copied into merged rows;
       - silver fallback provenance;
       - metrics `label_provenance.counts` sums to total.

   6h. Regenerate `gold_labels.jsonl` and `metrics.json` with the existing
       merge command. Do not manually patch generated rows.

   6i. Extend `phase7-mood-analysis.md` with:
       - energy_level table: bucket, n, misses, miss rate;
       - intensity table: bucket, n, misses, miss rate;
       - explicit warning that very small buckets are directional evidence,
         not reliable population estimates.

   6j. Reconcile the Phase 8 plan to the approved tickets:
       - use the exact six 8-B synonym groups;
       - describe 8-D as stable move-to-bottom demotion based only on genres
         or keywords, with no config constant;
       - list the exact q61-q65 definitions from the approved 8-F ticket;
       - describe 8-G as stopped pending deterministic attribution.

7. Acceptance criteria

   - No label is represented as pure human gold.
   - Every merged label has honest `label_provenance`.
   - Provenance counts are internally consistent.
   - Both missing Phase 7 subfield analyses are present with n caveats.
   - Phase 8 plan matches approved ticket contracts.
   - No production or query behavior changes.
   - All validation commands pass.

8. Validation commands

   ```powershell
   .\venv\Scripts\python.exe -m pytest eval/tests/test_merge_labels.py -q --basetemp="$env:TEMP\cinematch-7r-merge"
   .\venv\Scripts\python.exe eval/scripts/merge_labels.py --run 2026-06-07-combined-nogit --queries eval/queries/all.jsonl
   .\venv\Scripts\python.exe -c "import json; from pathlib import Path; rows=[json.loads(x) for x in Path('eval/runs/2026-06-07-combined-nogit/gold_labels.jsonl').read_text(encoding='utf-8').splitlines()]; assert rows and all(r.get('label_provenance') for r in rows); assert not any(r.get('label_provenance') == 'human_gold' for r in rows); m=json.loads(Path('eval/runs/2026-06-07-combined-nogit/metrics.json').read_text(encoding='utf-8')); counts=m['label_provenance']['counts']; assert isinstance(counts, dict) and counts; assert sum(counts.values()) == len(rows); print('provenance PASS')"
   git diff --name-only
   git status --short
   ```

9. Stop conditions

   - Any evidence would need to be relabeled as human-reviewed without an
     explicit human decision.
   - Any `src/*` or query change is required.
   - Generated metrics disagree with the source labels.
   - A validation command fails outside the allowed files.

10. Required final report format

    Verdict:
    Files changed:
    Provenance counts:
    Analysis additions:
    Commands run:
    Validation:
    Artifacts:
    Risks:
    Human decision still required:
    Commit:
    Next safe action:
