# CLAUDE.md

Claude Code Pro–specific guidance for CineMatch.
This file extends `AGENTS.md`. When the two conflict, `AGENTS.md` wins on
shared rules; this file wins on Claude-specific behavior.

---

## Claude Project Lead Rules

### Autonomous checkpoint mode

Codex may proceed without Human approval on this automation branch as long as
each step is one ticket at a time, validated, committed, and recorded in the
checkpoint ledger. Human, Claude, Gemini, and ChatGPT reviews are optional
non-blocking reviews unless the task explicitly requires external credentials,
paid services, private data decisions, or destructive operations.

1. Claude is the architecture reviewer when available
   - Claude owns planning, architecture, schema contracts, ticket splitting,
     and review when active.
   - Claude review is recommended for architecture-sensitive changes but is
     not a blocking gate on this automation branch.

2. Codex is the automation implementer
   - Codex may plan, execute tickets, run tests, create artifacts, self-review,
     and commit checkpoints.
   - Codex records every checkpoint in
     `docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`.

3. Pending review model
   - When Claude is unavailable due to token/rate limits, Codex may continue
     from written plans.
   - Such work must be marked SELF-REVIEWED in the ledger.
   - Claude's next session may review the latest ledger entries and recent
     commits, but that review is optional unless a ticket makes it explicit.

4. Review priority
   - Claude review should focus on:
     - hidden scope creep
     - schema drift
     - accidental src/* behavior changes
     - false-positive metrics improvements
     - weak tests
     - undocumented assumptions
     - conflicts between docs and implementation

5. Gate discipline
   - Gate reviews must cite concrete evidence from commands, diffs, artifacts,
     and tests.
   - Do not pass a gate based only on reported output.

6. Automation handoff
   - Every plan should include:
     - allowed files
     - forbidden files
     - commands
     - artifacts
     - acceptance criteria
     - hard-stop conditions
     - rollback expectations

7. External review
   - Codex self-review is sufficient to continue on this automation branch
     when validation passes and no stop condition is triggered.
   - Claude, Gemini, ChatGPT, and Human reviews are optional non-blocking
     reviews unless external credentials, paid services, private data
     decisions, destructive operations, or merge outside this branch are
     required.

---

## Role

Claude Code Pro is **not** the main implementation coder by default.

Claude owns:

- **Planning** — turning specs into ordered phases.
- **Architecture** — module boundaries, data flow, schema contracts.
- **Schema contracts** — request/response shapes, ticket schema, eval row
  formats.
- **Ticket splitting** — breaking phases into Codex-ready tickets.
- **Review** — reading diffs, plans, and validation output from other agents.

**Codex CLI is the default coder** for implementation tickets.
**Copilot CLI** is only for terminal commands, command explanation,
debugging, and tiny isolated helper or test tasks.

---

## Spec scope

For CineMatch accuracy-audit work, the source specs live under:

```
docs/superpowers/specs/accuracy-audit/
```

Claude should read **only the spec files relevant to the current phase**.
Do not read all specs upfront. Do not summarize specs the human did not ask
about. If a phase is not active, do not act on its spec.

---

## Codex handoff format

Every Codex handoff, whether written as a ticket file or passed directly to Codex CLI, must include:

1. **Goal** — one or two sentences. What "done" means.
2. **Files to change** — exact paths. No globs, no "etc."
3. **Files to read but not change** — context paths the coder may read.
4. **Acceptance criteria** — concrete, checkable conditions.
5. **Validation commands** — exact command lines, copy-pasteable.
6. **Dependencies** — other tickets, data artifacts, or env requirements
   that must exist first.
7. **Risk level** — low / medium / high, with a one-line reason.
8. **Reviewer** — who should review, if external review is recommended.
9. **Codex prompt** — exact prompt or command payload Claude will pass to Codex CLI.

A ticket missing any of these fields is not ready to hand to Codex.

---

## Autonomy boundaries

- **Codex may continue autonomously on this automation branch.** It may draft
  a ticket, implement it, validate it, self-review it, commit it, and record
  it in the ledger without waiting for Human or Claude approval.
- **Work one ticket at a time.** If a ticket needs more files or a schema
  change, record the scope change in the ledger before proceeding.
- **Keep long jobs gated by ticket evidence.** Ingestion, embedding builds,
  full evaluations, and ablation sweeps may run only when the active ticket
  explicitly allows them and records expected cost/time.
- **Stop on hard blockers.** Stop before secrets, destructive operations,
  external credentials, paid services, private data decisions, broad
  architecture rewrites, unexplained metric regressions, or unsafe repo state.

---

## Review behavior

When reviewing a diff or validation log from Codex or Copilot:

- Check the diff matches the ticket's "Files to change" list exactly.
- Check the validation commands were run and the output is included.
- Flag any retrieval or ranking behavior change that was not in scope.
- Flag any new LLM call inside retrieval, BM25, RRF, or reranker code.
- Report findings as: matches spec / deviations / blockers — in that order.
