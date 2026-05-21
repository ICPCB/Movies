---
title: Prioritization formula and ticket schema
parent: README.md
section: 10, 11
---

# 10. Prioritization · 11. Ticket schema

[Index](README.md) · Prev: [Code audit method](07-code-audit-method.md) · Next: [AI handoff & conflicts](09-ai-handoff-and-conflict-protocol.md)

## 10. Prioritization formula

Each candidate fix gets four numeric inputs:

| Input | Source | Scale |
|---|---|---|
| **measured_impact** | Phase 4 paired bootstrap Δmetric (prefer NDCG@5, then MRR@5, then Hit@5) | absolute Δ, e.g., 0.04 |
| **expected_impact** | Audit hypothesis (used only when no measurement exists) | minor=0.01, moderate=0.03, major=0.06 |
| **confidence** | High=1.0, Medium=0.7 | 0.7–1.0 |
| **implementation_cost** | S=1, M=3, L=8 (effort units) | 1, 3, 8 |

```
impact     = measured_impact if available else expected_impact
base       = (impact × confidence) / implementation_cost
latency_mx = 1.15  if the fix reduces a documented C6 latency risk
             0.85  if the fix introduces new C6 latency risk
             1.00  otherwise
priority   = base × latency_mx
```

Multiplier replaces the earlier flat ±0.2 tax — at typical priority scores (0.01–0.06), a flat 0.2 would dominate the formula.

**Two-tier output:**
- **Tier A** — top ~5–7 tickets by priority. These ship in the iteration.
- **Tier B** — deferred / nice-to-have. Documented but not for this iteration.

## 11. Ticket schema (`audit/tickets/T-NNN.md`)

One self-contained file per ticket. Any AI tool can pick it up cold.

```markdown
# T-NNN: <short title>

**Status:** ready / in_progress / done / blocked
**Tier:** A / B
**Priority score:** <float>
**Risk level:** low / medium / high
**Detection method:** code_reading / eval_metric / ablation / context7 / smoke_test
**Fix owner suggestion:** Claude / Codex / Copilot / ChatGPT Plus / Human-review
**Reviewer:** <tool or human>
**Requires full eval:** true / false
**Requires human run:** true / false
**Blocked by:** <ticket ids or none>
**Blocks:** <ticket ids or none>

## Problem
<one paragraph>

## Evidence
- <bullets with file:line references and/or eval/ablation pointers>

## Files to change
- <explicit list — used for conflict detection>

## Files to read but NOT change
- <explicit list>

## Acceptance criteria
1. ...
2. ...

## Test plan
- ...

## Expected metric impact
- Hit@5: ...
- MRR@5: ...
- NDCG@5: ...

## Rollback plan
- <how to revert if validation regresses; e.g., revert commit, restore config snapshot>

## Validation commands
1. <exact shell commands the implementer/reviewer runs to validate>
2. <e.g., python -m compileall src>
3. <e.g., python scripts/quality_smoke_test.py --no-llm>
4. <e.g., python eval/scripts/run_pipelines.py --queries eval/queries/v1.jsonl --out eval/runs/T-NNN-validation/>
5. <e.g., python eval/scripts/compute_metrics.py --run eval/runs/T-NNN-validation/>
6. <expected outcome / paired-bootstrap delta acceptance criterion>

## Out of scope for this ticket
- ...
```

See [09 — AI handoff & conflict protocol](09-ai-handoff-and-conflict-protocol.md) for the routing matrix and `STATUS.md` coordination workflow.
