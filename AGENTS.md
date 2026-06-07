# AGENTS.md

Shared rules for all AI agents working on CineMatch.

This file defines repo-wide operating rules for:

* Claude Code Pro
* Codex CLI
* Copilot CLI
* ChatGPT Plus
* Gemini or other external reviewers
* Any Claude subagents / agent teammates

---

## Rule precedence

For shared repo-wide behavior, this file wins.

Precedence:

1. Safety / destructive-operation constraints
2. `AGENTS.md`
3. `.remember/remember.md` for current project state
4. Active ticket for current allowed work scope
5. Tool-specific files such as `CLAUDE.md`
6. Conversation context

Important:

* `.remember/remember.md` records current state; it does not override hard safety rules.
* An active ticket may authorize scoped work, but only for exact files and commands named in the ticket.
* If files disagree, stop and report. Do not average conflicting instructions.

---

## Roles

* **Claude Code Pro** — plan owner, repo architect, schema owner, reviewer.
  Owns planning, ticket splitting, schema contracts, and code review.
  Not the default implementation coder.

* **Codex CLI** — main implementation coder.
  Works one ticket at a time, on one branch at a time.

* **Copilot CLI** — shell and debug helper only.
  Used for terminal commands, command explanation, debugging, and tiny isolated helper/test snippets.
  Not used for feature implementation.

* **ChatGPT Plus** — external reviewer.
  Reviews pasted plans, diffs, artifacts, and result logs.
  Does not edit the repo.

* **Human** — owner of decisions requiring private judgment, external credentials, paid services, destructive operations, or merge outside the automation branch.

---

## Core operating rules

### 1. Read before acting

Before editing, every agent must inspect:

* `.remember/remember.md`
* active ticket, if any
* relevant plans/reports/artifacts
* relevant neighboring code/tests
* current git status

No edits without understanding the current state.

---

### 2. Active ticket required

No agent may edit files unless there is an active ticket or a direct rules-only human request.

A valid implementation ticket must include:

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

* Exact paths only.
* No globs.
* No “etc.”
* No implied permissions.
* No opportunistic edits.

---

### 3. One ticket at a time

Work one ticket at a time.

Do not mix unrelated tasks in one branch.

If scope expands:

1. stop,
2. report the scope change,
3. open or request a new ticket.

---

### 4. Files to change are exclusive

Agents may edit only files listed under:

```text
Files to change
```

Agents must not edit files listed under:

```text
Files to read but not change
```

If a needed file is not listed, stop and report.

---

### 5. No two agents edit the same file

Parallel agents/subagents may inspect the same file.

They may not edit the same file at the same time.

The lead agent must assign file ownership before any write action.

---

### 6. Surgical changes only

Prefer the smallest deterministic change that satisfies the ticket.

Avoid:

* broad refactors
* speculative abstractions
* framework changes
* style-only edits
* opportunistic cleanup
* unrelated test rewrites

Every edit must map to:

* an acceptance criterion
* a failing test
* a trace finding
* a documented plan requirement

---

### 7. Production behavior protection

Do not change retrieval or ranking behavior unless the active ticket explicitly authorizes the exact change.

Protected areas include:

* embedding model
* ChromaDB path
* dataset path
* BM25
* RRF fusion
* semantic retrieval
* reranker model
* reranker thresholds
* reranker pool size
* final blending
* ranking weights
* candidate generation
* `src/*` production code

No `src/*` edits unless exact `src/*` files are listed in the active ticket.

---

### 8. Model / network / API restrictions

Prefer deterministic scripts, tests, traces, and file inspection.

Do not call any of the following unless the active ticket explicitly authorizes it:

* LLM APIs
* Ollama
* external APIs
* network services
* paid services
* model download
* embedding build
* reranker model download
* full-corpus scoring
* long evaluation jobs

Movie-label semantic judgment is allowed only when the active ticket explicitly requires label judgment.

---

### 9. Label provenance

Labels must preserve provenance honestly.

Allowed examples:

```text
human_gold
silver_llm_pregrade
ai_draft
human_reviewed_ai_assisted
```

Rules:

* AI-generated or AI-suggested labels must not be recorded as pure `human_gold`.
* If a human reviews and accepts AI-assisted labels, use `human_reviewed_ai_assisted` or the provenance value specified by the active ticket.
* Do not silently overwrite provenance fields.
* Do not merge labels into authoritative artifacts unless the active ticket explicitly authorizes the merge.
* If provenance is unclear, stop and report.

---

### 10. Gate discipline

A gate may pass only when there is concrete evidence.

Evidence may include:

* commands run
* test output
* artifact paths
* schema checks
* diffs
* git status
* ledger entries
* inspected file contents

Do not pass a gate based only on a verbal report.

If evidence is missing, verdict must be:

```text
INCOMPLETE
```

or

```text
BLOCKED
```

---

### 11. Validation required

After completing a ticket, every agent must run the ticket’s validation commands exactly as written.

Then report:

```text
Files changed:
Commands run:
Test results:
Artifacts:
Failures:
Assumptions:
Git status:
```

If any validation command fails, stop and report.

Do not fix outside ticket scope.

---

### 12. Checkpoint required

After every gate, plan, analysis ticket, or implementation ticket:

1. run validation
2. inspect outputs
3. run `git status --short`
4. run `git diff --name-only`
5. commit only if validation passes and changed files are allowed
6. append checkpoint to:

```text
docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md
```

7. update `.remember/remember.md` if current handoff changes

Checkpoint entry must include:

```text
Ticket/Gate:
Verdict:
Files changed:
Commands run:
Test results:
Artifacts:
Failures:
Assumptions:
Commit:
Next safe action:
```

---

## Autonomous checkpoint mode

Codex may proceed without Human approval on the automation branch only when:

* there is a complete active ticket
* the work is one ticket at a time
* changed files match the ticket
* validation passes
* outputs are inspected
* no hard-stop condition triggers
* checkpoint is recorded in the ledger
* commit is created when appropriate

External review by Claude, ChatGPT, Gemini, or Human is optional and non-blocking unless the active ticket says otherwise or the work requires private judgment, paid services, external credentials, destructive operations, or merge outside the automation branch.

Autonomous work should be marked:

```text
SELF-REVIEWED
```

when no external reviewer is available.

---

## Overnight automation protocol

During overnight automation:

* Continue one ticket at a time.
* Do not wait for Claude token recovery if written plans are sufficient.
* Stop at a validated stopping point or hard-stop condition.
* Mark continued work `SELF-REVIEWED` in the ledger.
* Do not begin a new class of work without a ticket.
* Do not run long jobs unless the ticket explicitly authorizes cost/time.
* Do not make private data, paid-service, or destructive decisions.

---

## Fan-out / subagent protocol

Fan-out is allowed for bounded independent checks.

Default fan-out mode is read-only.

Before fan-out, the lead must restate:

* current state from `.remember/remember.md`
* active ticket
* allowed files
* forbidden files
* stop conditions
* whether writes are allowed

Subagents may inspect files and report findings.

Subagents may not:

* edit files
* commit
* dispatch Codex
* change production behavior
* run long jobs
* call LLM/API/Ollama/network
* modify governance files
* resolve conflicts silently

unless the active ticket explicitly allows it and the lead assigns the task.

Every subagent report must include:

```text
Scope checked:
Evidence inspected:
Findings:
Blockers:
Recommended next action:
```

---

## Hard stop conditions

Stop and report before:

* committing secrets
* destructive operations
* deleting user data
* force reset
* force push
* rewriting history
* broad architecture rewrite
* unplanned `src/*` behavior change
* unauthorized retrieval/ranking/reranker change
* unauthorized LLM/API/Ollama/network call
* unauthorized long ingestion/embedding/full eval/ablation
* model file/vector DB/cache/heavy artifact commit
* failed validation that cannot be fixed inside scope
* unexplained metric regression
* unsafe or ambiguous repo state
* stale/conflicting `.remember`, ledger, ticket, docs, or artifacts
* private data judgment
* paid-service decision
* external credential use
* label provenance ambiguity

---

## Out of scope without active ticket

Agents may not do the following without an active ticket:

* edit `src/*`
* change embedding model
* change ChromaDB path
* change dataset path
* change retrieval behavior
* change ranking behavior
* change reranker behavior
* add LLM calls inside retrieval/BM25/RRF/reranker loops
* run ablations
* run ingestion
* run full evaluations
* generate labels with LLM/API/Ollama
* merge labels into authoritative gold/silver artifacts
* edit `AGENTS.md`
* edit `CLAUDE.md`
* commit heavy artifacts, model files, vector DBs, caches, or temp files

A direct human request to update `AGENTS.md` or `CLAUDE.md` counts as a rules-only ticket for those files only.

---

## File map

Read-only context unless active ticket says otherwise:

```text
.remember/remember.md
docs/ARCHITECTURE.md
docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md
docs/superpowers/specs/accuracy-audit/
docs/superpowers/plans/
docs/superpowers/reports/
eval/runs/
eval/scripts/
eval/tests/
```

For accuracy-audit work:

* read only files relevant to the active phase/ticket
* do not read all specs upfront unless doing cross-phase review
* do not act on inactive phases
* do not start Phase 5 implementation unless current handoff and active ticket explicitly say the regression-eval gate has passed

---

## Required report format

Use this compact report format:

```text
Verdict:
Current state:
Files changed:
Commands run:
Validation:
Artifacts:
Risks:
Assumptions:
Commit:
Next safe action:
Codex status:
```

Keep reports compact.

Do not paste large files unless explicitly requested.

Prefer exact paths and short evidence summaries.


## Multi-Agent Orchestration Protocol

### Roles

* Claude Code is the primary orchestrator, planner, reviewer, and gatekeeper.
* Codex CLI is the implementation sub-agent.
* Copilot CLI is the shell/debug/review helper only.
* Human approval is only required for hard-stop conditions, destructive operations, external credentials, paid services, private data decisions, or Phase 5 unblock decisions.

### Communication model

Agents communicate through repository-local mailbox files under:

```text
.agents/
  inbox/
    codex/
    copilot/
  outbox/
    codex/
    copilot/
  prompts/
  logs/
  locks/
  state.json
  ledger.md
```

Claude must write a complete ticket prompt before invoking Codex or Copilot.

Codex and Copilot must return a final report to their assigned outbox file.

Claude must read the returned report, inspect the working tree, run or verify validation commands, and record the result in `.agents/ledger.md`.

### Codex as implementation sub-agent

Claude may invoke Codex only for one bounded ticket at a time.

Codex may:

* read repository files needed for the ticket;
* create or edit only files explicitly allowed by the ticket;
* run validation commands explicitly listed by the ticket;
* produce artifacts explicitly listed by the ticket;
* commit only when the ticket explicitly allows commit.

Codex must not:

* edit `src/*` unless the active ticket explicitly allows it;
* run model/network/LLM calls unless the active ticket explicitly allows it;
* run full evals unless the active ticket explicitly allows it;
* modify retrieval/ranking/reranker behavior unless the active ticket explicitly allows it;
* start Phase 5 work unless the regression eval gate has passed and the Phase 5 ticket explicitly allows it;
* overwrite existing human-gold labels;
* represent AI-assisted labels as pure human-gold.

### Copilot as shell/debug helper

Claude may invoke Copilot for:

* explaining command failures;
* proposing safe shell commands;
* debugging test failures;
* reviewing logs;
* suggesting isolated helper snippets.

Copilot must not be used as the primary implementation coder.

Copilot must not make feature-level code changes unless Claude explicitly scopes a tiny isolated debug/helper change.

### Locking rule

Only one write-capable agent may run at a time.

Before dispatching Codex, Claude must create:

```text
.agents/locks/active_ticket.lock
```

The lock must contain:

* ticket id;
* agent name;
* start timestamp;
* allowed files;
* stop conditions.

After the ticket completes or fails, Claude must remove or mark the lock as closed.

### Required Codex ticket format

Every Codex ticket must include:

1. Goal.
2. Current repo state.
3. Files to read.
4. Files allowed to change/create.
5. Files forbidden to change.
6. Exact implementation rules.
7. Acceptance criteria.
8. Validation commands.
9. Stop conditions.
10. Required final report format.

### Required Codex final report

Codex must return:

1. Verdict: PASS / FAIL / STOPPED / NEEDS_REVIEW.
2. Files changed.
3. Artifacts created.
4. Validation commands and results.
5. Git status summary.
6. Risks or caveats.
7. Whether anything was committed.
8. Exact next recommended step.

### CineMatch current hard gates

* Phase 5 COMPLETE (5-A: q10 fixed commit `5a7da48`, 5-B: q05 fixed commit `dcedad1`).
* Dep #3 grading is accepted as `human_reviewed_ai_assisted`, not `human_gold`.
* Phase 6 IN_PROGRESS: eval expansion (no `src/*` changes).
* No `src/*` edits unless an active ticket explicitly authorizes it.
