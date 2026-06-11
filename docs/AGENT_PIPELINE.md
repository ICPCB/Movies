# Agent Architecture Pipeline

The mandatory pipeline for every AI agent working on CineMatch.
Rule details live in `AGENTS.md` (repo-wide rules) and `CLAUDE.md` (Claude-specific behavior); this file defines **who does what, in what order**. If this file and `AGENTS.md` disagree, `AGENTS.md` wins.

---

## Roles

| Agent | Role | May edit repo? |
|---|---|---|
| **Claude Code** | Head reviewer, planner, gatekeeper. Owns plans, tickets, schema contracts, label/dataset specs, gate reviews, ledger. **Not** the default implementation coder. | Only governance/docs/specs, or when a ticket records a coder STOPPED and Claude implements after failure. |
| **Codex CLI** | Implementation coder. | Yes — only files the active ticket allows. |
| **Gemini CLI** | Implementation coder. | Yes — only files the active ticket allows. |
| **Kiro AI** | Additional terminal-callable implementation/subagent option. | Yes — only files the active ticket allows. |
| **Copilot CLI** | Shell/debug helper only. | No feature code; tiny scoped debug snippets at most. |
| **ChatGPT Plus** | External reviewer. | No. |
| **Claude subagents** | Bounded read-only checks (discovery, audits, scope/risk checks). Writes only when the lead assigns exactly one subagent to one file under an active ticket. | Default no. |
| **Human (owner)** | Final authority: destructive ops, paid services, credentials, private data, merges outside the automation branch. | Yes. |

Claude picks the implementation coder (Codex, Gemini, or Kiro) **per ticket** in the plan. Never two write-capable agents at once.

---

## Pipeline

```text
Human request
     │
     ▼
Claude (head planner/reviewer)
     │  writes ticket — AGENTS.md rule-2 format, exact paths, no globs
     │  creates .agents/locks/active_ticket.lock
     │  picks ONE coder for the ticket
     ├──────────────► Codex CLI  ─┐
     ├──────────────► Gemini CLI ─┤   one write-capable agent at a time
     └──────────────► Kiro AI    ─┘
                                  │  implements + runs ticket validation
                                  │  writes report to .agents/outbox/<agent>/
                                  ▼
Claude gate review (evidence-based — AGENTS.md rule 10)
     │  optional non-blocking review: ChatGPT / Human
     │
     ├─ PASS ──► ledger checkpoint (rule 12) ──► .remember/remember.md update ──► commit ──► close lock
     │
     └─ FAIL / BLOCKED / STOPPED ──► stop, record in ledger, report to owner; no commit
```

Stages in order — none may be skipped:

1. **Plan** — Claude defines goal, files to change, files read-only, acceptance criteria, validation commands, dependencies, risk, reviewer, coder prompt.
2. **Lock** — create `.agents/locks/active_ticket.lock` (ticket id, agent, timestamp, allowed files, stop conditions).
3. **Dispatch** — ticket written to `.agents/inbox/<agent>/current.md`; coder invoked non-interactively.
4. **Implement** — coder edits only allowed files, runs the ticket's validation commands exactly.
5. **Report** — coder writes its final report to `.agents/outbox/<agent>/current_result.md`.
6. **Gate review** — Claude verifies with concrete evidence: diff scope, validation output, artifacts, git status. No evidence → INCOMPLETE/BLOCKED, never PASS.
7. **Checkpoint** — ledger entry in `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`, `.remember/remember.md` updated, commit created, lock closed.

---

## Mailboxes

```text
.agents/
  inbox/
    codex/
    gemini/
    copilot/
  outbox/
    codex/
    gemini/
    copilot/
  prompts/
  locks/
```

Mailbox contents are transient: a closed ticket's `current.md` / `current_result.md` are cleared after the ledger checkpoint records the outcome (the ledger is the permanent record).

---

## Subagent cleanup protocol

For repo-hygiene work (file wipes, audits), Claude fans out **read-only discovery** subagents first; each reports `Scope checked / Evidence inspected / Findings / Blockers / Recommended next action`. The lead Claude synthesizes a single exact deletion list, records it in the ledger entry, and executes it itself or assigns one writer per file. Anything ambiguous is flagged and kept — never silently deleted.

---

## Standing constraints (see AGENTS.md for the full lists)

- One ticket at a time; ticket scope is exclusive.
- No `src/*` edits, retrieval/ranking changes, LLM/network calls, or long jobs without explicit ticket authorization.
- Honest label provenance, always.
- Hard stops: destructive ops, history rewrites, secrets, heavy-artifact commits, conflicting repo state.
- Every completed ticket ends with a ledger checkpoint — no exceptions.
