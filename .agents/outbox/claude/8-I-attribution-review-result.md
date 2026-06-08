Verdict: 8-I ACCEPT (PASS). 8-H GO with two minor edits. 8-J correctly BLOCKED on human approval.

8-I acceptance:
- Accepted as deterministic attribution evidence. No revision required.
- q02/basic `label_only` is sound because ordered top-five IDs are identical and own-label hit changes.
- q26/q49/q58/q59 basic `candidate_only` and advanced/hybrid `insufficient_labels` are internally consistent with the artifacts.
- Review queue provenance is honest: `ai_draft`, `pending_human`.
- No production accuracy claim is supported or made.

8-H go/no-go:
- GO as a contract/isolation repair, SELF-REVIEWED, after two required ticket edits.
- 8-H restores prompt/safety behavior to approved Phase 8 contracts.
- Caveat: 8-H changes production ranking outputs for no-mood and dark-candidate queries. That is acceptable as spec-restoring repair, but ranking impact measurement must be deferred to a separate gated eval ticket.

8-J gate:
- BLOCKED on human approval.
- 8-J introduces new q49 mood-detection behavior, not a contract repair.
- q49 advanced/hybrid attribution is `insufficient_labels`; the need for q49 handling is not fully evidence-backed until human review records approval.

Required ticket revisions:
- 8-H: add acceptance/report language that production ranking outputs may change and measurement is deferred to a separate gated eval ticket.
- 8-H: fix smoke-import validation command so `run` is not shadowed by importing both pipeline `run` names.
- 8-J: require recorded human approval of `review_queue.jsonl` in ledger and `.remember`, including confirmation of q49 labels needed to justify the fix.

Risks:
- Do not merge `review_queue.jsonl` into gold/silver without a separate human-gated merge ticket.
- Advanced/hybrid regressions remain unattributable until labels exist.
- 8-H output change is unmeasured by design; no accuracy claim may be made from 8-H alone.

Next Codex action:
- Revise 8-H and 8-J tickets as above.
- Dispatch 8-H under `.agents/locks/active_ticket.lock`.
- Hold 8-J until human approval is recorded.
- Do not run 8-G/full eval or label-merge work without a new ticket.
