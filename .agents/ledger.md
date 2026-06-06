# .agents/ Dispatch Ledger

Append-only log of agent dispatches and results.

---

## Dep #3b — Merge Accepted Labels into gold_labels.jsonl

- **Date**: 2026-06-06
- **Ticket**: `.agents/inbox/codex/dep-3b-label-merge.md`
- **Agent**: Codex CLI attempted → STOPPED (sandbox shell errors). Claude Code Pro executed directly.
- **Verdict**: PASS
- **Files created**:
  - `eval/scripts/rerank_regression_merge_accepted_labels.py`
  - `eval/tests/test_rerank_regression_merge_accepted_labels.py`
  - `eval/runs/2026-05-19-1846-nogit/analysis/rerank_regression/merge_summary.json`
- **Files updated**:
  - `eval/runs/2026-05-19-1846-nogit/gold_labels.jsonl` (220 → 675 rows)
- **Validation**:
  - Syntax check: PASS
  - 10/10 unit tests: PASS
  - Real merge: PASS (220 + 455 = 675)
  - Schema check: PASS (all 675 rows have 7 fields)
  - Provenance: gold=55, silver=165, human_reviewed_ai_assisted=455
  - Original 220 rows preserved unchanged: PASS
  - No `human_gold` labels: PASS
  - No `src/*` changes: PASS
  - merge_summary.json: PASS
- **Committed**: not yet (awaiting human review)
- **Next safe action**: Human review → commit → update state.json gates → author Dep #4 regression eval ticket
