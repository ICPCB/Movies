---
ticket_id: 8-I
phase: 8
depends_on: [8-G-stopped]
human_gate: yes
status: REVISED_AFTER_CLAUDE_REVIEW
---

1. Goal

   Produce deterministic, reproducible attribution evidence for the Phase 8-G
   q02, q26, q49, q58, and q59 changes. Separate candidate/rank drift from
   silver-label drift before any accuracy-oriented production fix.

2. Current repo state

   - Baseline run: `eval/runs/2026-06-07-combined-nogit`
   - Phase 8 run: `eval/runs/2026-06-08-phase8-mood-nogit`
   - The runs were independently retrieved and independently LLM-pregraded.
   - Therefore direct hit-to-miss comparison confounds code, retrieval
     nondeterminism, and label drift.

3. Files to read

   - `AGENTS.md`
   - `.remember/remember.md`
   - `docs/superpowers/reports/phase8-regression-investigation-request.md`
   - both runs' `candidates.jsonl`
   - both runs' `silver_labels.jsonl`
   - baseline run `gold_labels.jsonl`
   - both runs' `metrics_provisional.json`
   - `eval/scripts/_schemas.py`
   - `eval/tests/conftest.py`

4. Files allowed to create/change

   - `eval/scripts/phase8_regression_attribution.py`
   - `eval/tests/test_phase8_regression_attribution.py`
   - `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.json`
   - `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.md`
   - `eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/review_queue.jsonl`
   - `.agents/outbox/codex/8-I_result.md`
   - `.agents/ledger.md`
   - `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`
   - `.remember/remember.md`

5. Files forbidden to change

   - `src/*`
   - `eval/queries/*`
   - existing run candidates, labels, metrics, and manifests
   - all other scripts and tests

6. Exact implementation rules

   6a. Script CLI:

       ```text
       --baseline-run <run-id>
       --candidate-run <run-id>
       --queries <path>
       --qids q02,q26,q49,q58,q59
       --output-dir <path>
       ```

   6b. For every qid and mode, report:
       - ordered baseline top-five IDs;
       - ordered candidate-run top-five IDs;
       - exact-order equality;
       - set equality;
       - lost and gained IDs;
       - rank changes for common IDs;
       - baseline and candidate silver grades;
       - baseline gold grade where present;
       - grade conflicts for the same `(qid, tmdb_id)`;
       - hit status using each run's own labels;
       - hit status using frozen baseline labels on the union where available.

   6c. Classification rules:
       - `label_only`: ordered top-five IDs equal and own-label hit changes;
       - `candidate_only`: candidate IDs/ranks change, no common-pair grade
         conflicts affect the result;
       - `mixed`: both candidate drift and relevant common-pair grade drift;
       - `insufficient_labels`: union contains candidates without an accepted
         frozen label needed to decide.

   6d. Reconstruct pre-safety order for Phase 8 advanced/hybrid using
       descending `final_score`. Report whether stored rank differs from score
       rank. Label this reconstruction explicitly as an inference.

   6e. `review_queue.jsonl` must include every union candidate needed to decide
       q49/q59 (and any unresolved q02/q26/q58 case) with:
       - qid, tmdb_id, title, metadata;
       - baseline grade if present;
       - candidate-run grade if present;
       - `label_provenance: "ai_draft"`;
       - `review_status: "pending_human"`.

   6f. Do not call an LLM, Ollama, Chroma, embeddings, reranker, or network.
       This ticket is artifact-only.

   6g. Tests must use synthetic fixtures and cover all four classifications,
       rank changes, grade conflicts, missing labels, and stable deterministic
       output ordering.

   6h. Real artifact classifications must be reported exactly as computed. Do
       not force q02/basic to classify as `label_only`; if it does not, record
       that as a finding and stop for review.

7. Acceptance criteria

   - Attribution is reproducible from existing artifacts.
   - q02/basic real-data classification is reported without being pre-judged.
   - No accuracy fix is recommended where evidence is
     `insufficient_labels`.
   - Review queue provenance remains honest.
   - Existing run artifacts are not modified.
   - All tests pass.

8. Validation commands

   ```powershell
   .\venv\Scripts\python.exe -m pytest eval/tests/test_phase8_regression_attribution.py -q --basetemp="$env:TEMP\cinematch-8i"
   .\venv\Scripts\python.exe eval/scripts/phase8_regression_attribution.py --baseline-run 2026-06-07-combined-nogit --candidate-run 2026-06-08-phase8-mood-nogit --queries eval/queries/all.jsonl --qids q02,q26,q49,q58,q59 --output-dir eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution
   .\venv\Scripts\python.exe -c "import json; from pathlib import Path; p=Path('eval/runs/2026-06-08-phase8-mood-nogit/analysis/regression_attribution/attribution.json'); d=json.loads(p.read_text(encoding='utf-8')); c=d['by_qid']['q02']['by_mode']['basic']['classification']; assert c in {'label_only','candidate_only','mixed','insufficient_labels'}; print(f'q02/basic classification: {c}')"
   git diff --name-only
   git status --short
   ```

9. Stop conditions

   - A model, retrieval engine, or network call is required.
   - Existing run artifacts would need to be overwritten.
   - The evidence cannot support the required classification without human
     labels. Mark it `insufficient_labels`; do not guess.
   - Any production behavior change is proposed.

10. Required final report format

    Verdict:
    Files created:
    Classification summary:
    Label conflicts:
    Review queue:
    Commands run:
    Validation:
    Accuracy decisions deferred:
    Commit:
    Next safe action:
