# AGENTS.md

Shared rules for all AI agents working on CineMatch.
This file is read by Claude Code Pro, Codex CLI, Copilot CLI, and ChatGPT Plus.

---

## Roles

- **Claude Code Pro** — plan owner, repo architect, schema owner, reviewer.
  Owns planning, ticket splitting, schema contracts, and code review.
  Not the default implementation coder.

- **Codex CLI** — main implementation coder.
  Works one ticket at a time, on one branch at a time.

- **Copilot CLI** — shell and debug helper only.
  Used for terminal commands, command explanation, debugging, and small
  isolated helper or test snippets. Not used for feature implementation.

- **ChatGPT Plus** — external reviewer.
  Reviews pasted plans, diffs, and result logs. Does not edit the repo.

- **Human** — optional external reviewer and owner of decisions that require
  external credentials, paid services, private data judgment, destructive
  operations, or merge outside this automation branch.

---

## Core Agent Operating Rules

### Autonomous checkpoint mode

Codex may proceed without Human approval on this automation branch as long as
each step is one ticket at a time, validated, committed, and recorded in the
checkpoint ledger. Human, Claude, Gemini, and ChatGPT reviews are optional
non-blocking reviews unless the task explicitly requires external credentials,
paid services, private data decisions, or destructive operations.

### Explicit conflicts to preserve

- Existing scope conflict: the "Out of scope" section forbids editing
  `AGENTS.md` or `CLAUDE.md` without a ticket. A direct human request to update
  these files is the ticket for that rules-only change.

1. Think before coding
   - Before editing, state the objective, relevant files, expected artifact,
     and validation command.
   - Do not start coding until the goal and constraints are understood.

2. Simplicity first
   - Prefer the smallest deterministic change that satisfies the ticket.
   - Avoid abstractions, frameworks, broad refactors, or speculative
     generalization.

3. Surgical changes
   - Change only files explicitly allowed by the current ticket or plan.
   - Do not touch src/* unless an implementation ticket explicitly authorizes
     the exact file(s).

4. Goal-driven execution
   - Every edit must map to an acceptance criterion, failing test, trace
     finding, or documented plan requirement.
   - Do not make opportunistic improvements.

5. Use models only for judgment calls
   - Prefer deterministic scripts, tests, traces, and file inspection.
   - Use LLM/model judgment only when the task explicitly requires
     semantic/movie-label judgment.
   - Do not call Ollama, model APIs, network services, or external APIs unless
     explicitly authorized.

6. Token budgets are not advisory
   - Keep prompts, reports, and diffs compact.
   - Summarize instead of pasting large files.
   - Preserve enough evidence for review without flooding logs.

7. Surface conflicts; do not average them
   - If docs, plans, tests, or artifacts disagree, stop or record the conflict
     explicitly.
   - Do not silently choose a compromise.

8. Read before you write
   - Inspect existing conventions, neighboring code, relevant plans, tests, and
     artifacts before editing.
   - Match the project's existing style even if you disagree.

9. Tests verify intent, not incidental behavior
   - Tests should protect the intended contract and acceptance criteria.
   - Avoid brittle tests that only mirror implementation details.

10. Checkpoint after every step
    - After every gate, plan, analysis ticket, or implementation ticket:
      - run validation
      - inspect outputs
      - git status --short
      - git diff --name-only
      - commit if and only if validation passes
      - append the checkpoint to
        `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`

11. Match conventions even if you disagree
    - Follow existing naming, layout, schema, CLI, and artifact conventions.
    - New files should look like they belong to the repo.

12. Fail loud
    - On missing inputs, schema ambiguity, unexpected diffs, validation
      failure, metric regression, or safety concern: stop and report.
    - Do not guess silently.

13. Optional external review model
    - Claude owns architecture review when available, but Claude review is not
      a blocking gate on this automation branch.
    - Gemini and ChatGPT reviews are optional non-blocking reviews.
    - Codex owns planning, implementation, deterministic validation,
      self-review, checkpoint commits, and ledger entries.
    - Autonomous work should be marked SELF-REVIEWED; external review may be
      marked RECOMMENDED when useful.

14. Codex autonomous approval protocol
    - During automation, Codex may approve and checkpoint a gate/ticket only
      when:
      - all written acceptance criteria pass
      - validation commands pass
      - output artifacts are inspected
      - changed files match the allowed scope
      - no hard-stop condition is triggered
      - the checkpoint is recorded in the ledger.
    - External architectural review may be recommended but is not blocking
      unless the active ticket says so.

15. Overnight automation protocol
    - Continue one ticket at a time until a validated stopping point or
      hard-stop condition.
    - Do not wait for Claude token recovery.
    - If Claude is unavailable, continue using written plans as authority.
    - Mark continued work SELF-REVIEWED in the ledger.
    - Stop if the next decision requires private data judgment, external
      credentials, paid services, broad architecture rewrite, destructive
      commands, or unplanned src/* behavior changes.

16. Stop conditions
    - Do not commit secrets.
    - Do not commit model files, vector DBs, embedding caches, generated heavy
      artifacts, or local temp files.
    - Do not call network/Ollama unless an active ticket explicitly allows it.
    - Do not run long ingestion, embedding, or full evaluation jobs unless the
      ticket explicitly allows them and records expected cost/time.
    - Stop if tests fail and cannot be fixed with a small scoped correction.
    - Stop if metrics regress without explanation.
    - Stop if a change requires a broad architecture rewrite.
    - Stop if repo state becomes unsafe or ambiguous.
    - Stop before destructive operations such as deleting large user data,
      force reset, force push, or rewriting history.

---

## Hard rules

1. **Read the active ticket before editing.** No edits without an open ticket
   that names the work.
2. **Only edit files listed under "Files to change"** in the active ticket.
3. **Never edit files listed under "Files to read but NOT change."** They are
   reference context only.
4. **One ticket per branch.** Do not mix tickets in a single branch.
5. **No two agents edit the same file at the same time.** Coordinate via the
   ticket's `reviewer` and `dependencies` fields.
6. **If scope expands, stop and report.** Do not silently grow a ticket.
   Open a new ticket or escalate to Claude Code Pro.
7. **Do not change retrieval or ranking behavior** unless the ticket
   explicitly allows it. This includes BM25, RRF fusion, reranker thresholds,
   embedding model, and ChromaDB query parameters.
---

## Validation

After completing a ticket, every agent must:

1. Run the **validation commands** listed in the ticket exactly as written.
2. Append the following to
   `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md` and include it in any
   user-facing report:
   - **Files changed** — exact paths, no globs.
   - **Commands run** — exact command lines.
   - **Test results** — pass/fail counts, plus any new failures.
   - **Failures** — full error text, not a summary.
   - **Assumptions** — anything inferred that was not stated in the ticket.
3. If any validation command fails, **stop and report.** Do not attempt a
   fix outside the ticket scope.

---

## Out of scope for any agent without a ticket

- Changing the embedding model (`BAAI/bge-m3`).
- Changing the ChromaDB path (`data/chroma_bgem3/`).
- Changing the dataset path (`data/movies_clean.csv`).
- Adding LLM calls inside retrieval, BM25, RRF, or reranker loops.
- Running ablations, ingestion, or full evaluations.
- Editing `AGENTS.md` or `CLAUDE.md` themselves.

---

## File map (read-only context)

- `docs/ARCHITECTURE.md` — system overview.
- `docs/superpowers/specs/accuracy-audit/` — current audit specs and phase
  plans. Read only the file relevant to the active phase.
