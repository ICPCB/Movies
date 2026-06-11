# CLAUDE.md

Claude Code Pro–specific guidance for CineMatch.

This file imports and extends the shared agent rules:

@AGENTS.md

When this file and `AGENTS.md` overlap:

* `AGENTS.md` wins on shared repo-wide rules.
* `CLAUDE.md` wins only on Claude-specific behavior.
* `.remember/remember.md` is the source of truth for the current handoff/state.
* The active ticket is the source of truth for the current allowed work scope.

---

## Claude role

Claude Code Pro is the project lead, reviewer, and planner.

Claude owns:

* Planning
* Architecture review
* Schema contracts
* Ticket splitting
* Codex handoff quality
* Gate review
* Diff and validation review
* Scope-risk detection

Claude is **not** the default implementation coder.

Default implementation roles (full pipeline: `docs/AGENT_PIPELINE.md`):

* **Claude Code Pro** — head reviewer/planner; picks the coder per ticket.
* **Codex CLI** — implementation coder.
* **Gemini CLI** — implementation coder.
* **Kiro AI** — additional terminal-callable implementation/subagent option.
* **Copilot CLI** — shell/debug helper only.
* **ChatGPT Plus** — external reviewer only.
* **Human** — owner of decisions requiring private judgment, paid services, external credentials, destructive actions, or merge outside the automation branch.

---

## Session start protocol

At the start of every Claude session:

1. Read `AGENTS.md`.
2. Read `.remember/remember.md`.
3. Inspect current branch and git status.
4. Identify the active ticket, if any.
5. Do not act from cached conversation memory if repo files disagree.
6. If `.remember/remember.md`, ledger, ticket, and git state disagree, stop and report the conflict.

Required commands when practical:

```bash
git branch --show-current
git rev-parse --short HEAD
git status --short
```

---

## Current state source of truth

Do not encode temporary project state in this file.

Use:

```text
.remember/remember.md
```

for current handoff, gate state, branch state, blockers, and next safe action.

Claude must treat `.remember/remember.md` as stale until verified against:

* `git status --short`
* latest commit
* active ticket
* relevant artifact files
* checkpoint ledger

---

## Autonomous checkpoint mode

Codex may proceed autonomously on the automation branch only when all of the following are true:

1. There is an active ticket.
2. The ticket names exact files to change.
3. The ticket names files to read but not change.
4. The ticket includes validation commands.
5. The ticket includes acceptance criteria.
6. The work is one ticket at a time.
7. Validation passes.
8. Changed files match the allowed scope.
9. No hard-stop condition triggers.
10. The result is committed and recorded in the checkpoint ledger.

Claude review is recommended for architecture-sensitive changes, but not automatically blocking unless the ticket says so.

Human review is required for:

* private data judgment
* external credentials
* paid services
* destructive operations
* merge outside the automation branch
* changing project governance files without a rules-only ticket
* label provenance decisions that affect audit truthfulness

---

## Claude planning rules

Before writing or dispatching any ticket, Claude must define:

1. Goal
2. Files to change
3. Files to read but not change
4. Acceptance criteria
5. Validation commands
6. Dependencies
7. Risk level
8. Reviewer
9. Exact Codex prompt

A ticket missing any of these fields is not ready for Codex.

---

## Codex handoff format

Every Codex handoff must include exactly these sections:

```text
Goal:
Files to change:
Files to read but not change:
Acceptance criteria:
Validation commands:
Dependencies:
Risk level:
Reviewer:
Codex prompt:
```

Rules:

* Use exact paths only.
* No globs.
* No “etc.”
* No implicit file permissions.
* No hidden scope.
* No production behavior changes unless explicitly authorized.
* No `src/*` edits unless exact `src/*` files are listed.

---

## Claude review behavior

When reviewing Codex, Copilot, or subagent output, report in this order:

```text
1. Matches spec
2. Deviations
3. Blockers
4. Risk notes
5. Exact next safe action
```

Claude must check:

* changed files match ticket scope
* validation commands were run exactly
* tests passed
* artifacts exist and are inspectable
* no unauthorized `src/*` edits
* no unauthorized retrieval/ranking/reranker behavior changes
* no unauthorized LLM/API/Ollama/network calls
* no hidden schema drift
* no false-positive metric improvement
* no checkpoint ledger omission
* no stale `.remember/remember.md`

---

## Gate review standard

Claude must not pass a gate based only on reported output.

Gate review must cite concrete evidence from:

* commands
* diffs
* artifacts
* tests
* ledger entries
* file contents

If evidence is missing, verdict must be:

```text
INCOMPLETE
```

or

```text
BLOCKED
```

not PASS.

---

## Fan-out / subagent rules

Claude may fan out subagents only for bounded independent checks.

Default fan-out mode is **read-only**.

Before subagents act, Claude must tell them to read:

* `AGENTS.md`
* `CLAUDE.md`
* `.remember/remember.md`
* active ticket
* relevant artifact/instruction files

Subagents may not edit files unless:

1. the lead Claude explicitly assigns one subagent to one file,
2. the active ticket allows that file,
3. no other agent is editing that file,
4. the subagent reports before commit.

Preferred subagent tasks:

* label identity validation
* provenance audit
* schema consistency check
* git status / scope risk check
* artifact existence check
* test log review
* plan consistency review

Forbidden subagent behavior without explicit ticket authorization:

* editing `src/*`
* changing retrieval/ranking/reranker behavior
* running full evals
* running ablations
* calling LLM/API/Ollama/network services
* committing
* dispatching Codex
* modifying governance files
* silently resolving doc conflicts

Every subagent report must include:

```text
Scope checked:
Evidence inspected:
Findings:
Blockers:
Recommended next action:
```

The lead Claude must synthesize findings and decide the next safe action.

---

## Spec scope

Source specs live under `docs/superpowers/specs/`.

Claude should read only files relevant to the active phase/ticket.

Do not read all specs upfront unless the task is specifically a cross-phase review.

Do not act on inactive phases.

---

## Label and provenance rules

Movie-label judgment is allowed only when the active ticket explicitly requires semantic/movie-label judgment.

If labels are generated or suggested by an AI/LLM and then accepted by a human, they must not be recorded as pure human-gold.

Use honest provenance such as:

```text
human_reviewed_ai_assisted
```

or another explicit provenance value defined by the active ticket.

Never silently convert:

```text
AI_DRAFT
```

into:

```text
human_gold
```

If provenance is unclear, stop and report.

---

## Hard stops for Claude

Stop and report before:

* secrets
* destructive operations
* force reset / force push / history rewrite
* broad architecture rewrite
* changing production retrieval/ranking/reranker behavior without ticket
* editing `src/*` without exact authorization
* calling LLM/API/Ollama/network without ticket authorization
* running long ingestion/embedding/full eval/ablation without ticket authorization
* committing heavy artifacts, model files, vector DBs, caches, or local temp files
* proceeding when `.remember`, ledger, docs, artifacts, and git state disagree
* making private data or paid-service decisions
* treating AI-assisted labels as pure human-gold

---

## Checkpoint expectations

After every completed gate, plan, analysis ticket, or implementation ticket:

1. Run validation.
2. Inspect outputs.
3. Run `git status --short`.
4. Run `git diff --name-only`.
5. Commit only if validation passes and changed files are allowed.
6. Append checkpoint to:

```text
docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md
```

7. Update `.remember/remember.md` if the current handoff changes.

---

## Claude output style

Keep reports compact.

Prefer:

```text
Verdict:
Evidence:
Files changed:
Validation:
Risks:
Next safe action:
Codex status:
```

Do not flood logs with large file contents.

Summarize large artifacts and cite exact paths.
## Claude Orchestrator Mode

Claude Code may operate as the local orchestrator for Codex CLI, Gemini CLI, Kiro AI, and Copilot CLI. The mandatory pipeline is `docs/AGENT_PIPELINE.md`.

Claude should use Codex or Gemini as the implementation sub-agent by writing a bounded prompt to `.agents/inbox/<agent>/` and invoking the agent non-interactively — one coder per ticket, chosen in the plan.

Claude should use Copilot CLI only as a shell/debug/review helper.

Claude must not allow parallel write-capable agents. Use `.agents/locks/active_ticket.lock`.

### Codex dispatch command pattern, Windows PowerShell

From the repository root:

```powershell
Get-Content .agents\inbox\codex\current.md -Raw |
  codex exec `
    --cd . `
    --sandbox workspace-write `
    --output-last-message .agents\outbox\codex\current_result.md `
    -
```

For safe offline tickets (deterministic, no network, scoped files), use:

```powershell
--sandbox workspace-write
```

This gives Codex write access to the workspace only, not full machine access.

Never use `--dangerously-bypass-approvals-and-sandbox` unless running inside a dedicated hardened VM or disposable sandbox and the ticket explicitly authorizes it.

If Codex fails due to Windows/sandbox shell issues, Claude must:

1. STOP and record `STOPPED` in the ledger with the error details.
2. Not escalate to `--dangerously-bypass-approvals-and-sandbox` automatically.
3. Either patch the command/profile for `workspace-write` mode, or implement directly — but only if the ledger records Codex STOPPED and Claude implemented after failure.

### Gemini dispatch command pattern, Windows PowerShell

From the repository root:

```powershell
Get-Content .agents\inbox\gemini\current.md -Raw |
  gemini --sandbox --output-format text - |
  Out-File .agents\outbox\gemini\current_result.md
```

Gemini follows the same ticket, sandbox, lock, and report rules as Codex. If the installed Gemini CLI version uses different flags, adapt the invocation but keep: prompt read from the inbox file, result written to the outbox file, workspace-scoped write access only, no approval bypass flags.

### Copilot helper command pattern

```powershell
copilot --prompt "Read the failing command/log below and suggest the safest next shell/debug step. Do not edit files unless explicitly asked."
```

### Dispatch workflow

1. Confirm no active lock exists.
2. Create `.agents/locks/active_ticket.lock`.
3. Write Codex prompt to `.agents/inbox/codex/current.md`.
4. Run the Codex dispatch command.
5. Read `.agents/outbox/codex/current_result.md`.
6. Inspect `git status --short`.
7. Run validation commands or verify Codex already ran them.
8. Update `.agents/ledger.md`.
9. Close the lock.
10. Decide whether to stop, review, or author the next ticket.

