# .agents/ — Multi-Agent Orchestration Directory

File-based communication layer for CineMatch multi-agent workflows.

## Roles

| Agent | Role | Writes to | Reads from |
|-------|------|-----------|------------|
| Claude Code Pro | Orchestrator, planner, reviewer, gatekeeper | `inbox/`, `locks/`, `state.json`, `ledger.md` | Everything |
| Codex CLI | Implementation sub-agent | `outbox/codex/` | `inbox/codex/`, repo files per ticket |
| Copilot CLI | Shell/debug helper only | `outbox/copilot/` | `inbox/copilot/`, repo files |
| Human | Decision owner | Any | Any |

## Directory structure

```
.agents/
  README.md           # This file
  state.json          # Current orchestration state (Claude-maintained)
  ledger.md           # Append-only dispatch/result log
  inbox/
    codex/            # Claude writes ticket prompts here for Codex
    copilot/          # Claude writes helper prompts here for Copilot
  outbox/
    codex/            # Codex writes final reports here
    copilot/          # Copilot writes results here
  prompts/            # Reusable prompt templates
  logs/               # Raw execution logs (optional)
  locks/              # Active ticket locks (one at a time)
```

## Mailbox protocol

1. Claude writes a complete ticket to `inbox/<agent>/current.md`.
2. Claude creates `locks/active_ticket.lock` before dispatch.
3. Agent executes and writes result to `outbox/<agent>/current_result.md`.
4. Claude reads the result, inspects the working tree, runs validation.
5. Claude records the outcome in `ledger.md` and updates `state.json`.
6. Claude closes the lock (deletes or marks closed).

## Lock protocol

Only one write-capable agent runs at a time.

Lock file: `locks/active_ticket.lock`

Lock contents:

```json
{
  "ticket_id": "dep-3b",
  "agent": "codex",
  "started": "2026-06-06T12:00:00Z",
  "allowed_files": ["eval/data/silver_labels.jsonl"],
  "forbidden_files": ["src/*"],
  "stop_conditions": ["validation failure", "src/* edit detected"]
}
```

Rules:
- Check lock before dispatch. If locked, do not dispatch.
- Lock must be created by Claude before any dispatch.
- Lock must be closed by Claude after result review.
- Stale locks (>2 hours) may be force-closed by Claude with a ledger note.

## Codex dispatch — Windows PowerShell

```powershell
Get-Content .agents\inbox\codex\current.md -Raw |
  codex exec `
    --cd . `
    --sandbox workspace-write `
    --ask-for-approval on-request `
    --output-last-message .agents\outbox\codex\current_result.md `
    -
```

For safe offline-only tickets:

```powershell
Get-Content .agents\inbox\codex\current.md -Raw |
  codex exec `
    --cd . `
    --sandbox workspace-write `
    --ask-for-approval never `
    --output-last-message .agents\outbox\codex\current_result.md `
    -
```

Never use `--dangerously-bypass-approvals-and-sandbox`.

## Copilot helper — Windows PowerShell

```powershell
copilot --prompt "Read the failing command/log below and suggest the safest next shell/debug step. Do not edit files unless explicitly asked."
```

## Required Codex final report schema

Codex must write to `outbox/codex/current_result.md`:

```text
Verdict: PASS | FAIL | STOPPED | NEEDS_REVIEW
Files changed:
Artifacts created:
Validation commands run:
Validation results:
Git status:
Risks:
Committed: yes | no
Next recommended step:
```

## CineMatch hard gates (current)

- Phase 5: BLOCKED.
- Accepted labels provenance: `human_reviewed_ai_assisted` (not `human_gold`).
- Next safe ticket: Dep #3b only (label merge into silver_labels.jsonl).
- Regression eval: deferred until Dep #3b succeeds.
- Phase 5 unblock: only after regression eval gate passes.

## Governing rules

All agents must follow `AGENTS.md` and their tool-specific config.
Claude must follow `CLAUDE.md`.
`.remember/remember.md` is the current-state source of truth.
