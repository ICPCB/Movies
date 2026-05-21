---
title: AI handoff routing and conflict avoidance protocol
parent: README.md
section: 12, 13
---

# 12. AI handoff routing · 13. Conflict avoidance protocol

[Index](README.md) · Prev: [Prioritization & tickets](08-prioritization-and-ticket-schema.md) · Next: [Validation, done, risks](10-validation-done-risks.md)

## 12.1 Tool roles

| Tool | Primary role |
|---|---|
| **Claude Code Pro** | Plan owner; repo auditor; eval harness owner; multi-file implementer; reranker / retrieval ranking changes unless ticket is extremely narrow with clear acceptance criteria |
| **Codex** | Primary executor for narrow, well-scoped coding tickets |
| **ChatGPT Plus** | Architect / reviewer; prompt reviewer; **metrics interpretation**; **report and spec review** |
| **Copilot CLI free** | Small helper tasks; **shell commands**; simple tests; isolated functions only |
| **Human (Nguyễn Hoàng Minh)** | Final approval; manual grading in the review app; branch merges; long-running ChromaDB re-ingestion trigger; explicit override on routing matrix |

## 12.2 Routing matrix by ticket type

| Ticket type | Primary owner | Reviewer |
|---|---|---|
| Single-file, narrow scope | **Codex** or **Copilot CLI** | Claude Code Pro |
| Multi-file ticket touching ≥3 files | **Claude Code Pro** | ChatGPT Plus |
| Eval harness scripts (Phase 1–2) | **Claude Code Pro** | self-test by running |
| Prompt tuning (LLM grader, expansion, explanation) | **ChatGPT Plus** | Claude Code Pro tests against eval |
| Reranker / retrieval ranking changes | **Claude Code Pro** | ChatGPT Plus (unless extremely narrow → Codex with Pro review) |
| Library best-practice fixes (CrossEncoder kwargs, BM25 tokenizer) | **Claude Code Pro** | Codex regression test |
| Audit reading / no-edit tasks | **Claude Code Pro** | none (self-output) |
| Documentation updates | **Claude Code Pro** or **ChatGPT Plus** | Human |
| Metrics interpretation / report drafting | **ChatGPT Plus** | Human approval |
| Shell-command helpers / one-liners / isolated tests | **Copilot CLI free** | Claude Code Pro (lightweight) |
| ChromaDB re-ingestion (if triggered) | **Human-run** | Claude Code Pro verifies |
| Final spec/report approval and branch merges | **Human** | n/a |

**Override rule:** any ticket may set `fix_owner_suggestion` explicitly when the matrix is wrong for the specific case. The matrix is a default, not a law.

## 13. Conflict avoidance protocol

Solo human + 4 AI tools. The risk: two tools editing the same files at the same time.

### 13.1 Default workflow (solo-friendly)

- **One code ticket in progress at a time** unless the human explicitly allows parallel work.
- `audit/tickets/STATUS.md` is still maintained.
- File locks are still respected as a safety mechanism.
- Reviewer never edits the implementation branch directly.

### 13.2 Hard rules

1. **Files-to-change declared upfront in every ticket.** No tool may edit a file not on its ticket's list.
2. **One ticket per branch.** Naming: `fix/T-NNN-<short-slug>`.
3. **Branch lock** while ticket is `in_progress`; no other ticket may modify locked files.

### 13.3 Coordination artifact: `audit/tickets/STATUS.md`

Single source of truth. Updated by the implementer at start and end of work.

```markdown
# Ticket Status

Updated: <timestamp>

## In progress
| Ticket | Owner  | Branch          | Files locked              | Started |
|--------|--------|-----------------|---------------------------|---------|
| T-003  | Codex  | fix/T-003-...   | src/retrieval/fusion.py   | ...     |

## Ready (unblocked, no owner yet)
| Ticket | Priority | Suggested owner | Notes |
| T-001  | 0.045    | Codex           | Quick win |

## Blocked
| Ticket | Blocked by | Reason |

## Done (this iteration)
| Ticket | Owner | Merged | Validation run |
```

### 13.4 Pre-flight check per implementing AI

Before any edits, the tool MUST:

1. Read `audit/tickets/STATUS.md`.
2. Verify target files are not locked.
3. Add itself to "In progress" with timestamp.
4. Make changes only to declared files.
5. On finish: move ticket to "Done", record validation run path.

If a file is locked: stop and write `blocked: file X currently locked by T-NNN` in the ticket.

### 13.5 Reviewer rules

- Reviewer comments in `audit/tickets/T-NNN.review.md`.
- Reviewer never edits the implementation branch.
- Implementer applies review comments and re-validates.
