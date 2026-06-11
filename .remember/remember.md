# Handoff

## State
LoRA retrain pipeline mid-flight on main @ e861fb6 + uncommitted v2 dataset work. Ticket 2c VERIFIED PASS by Claude (audit clean, 6 banned strings gone, byte-identical double build, pytest 6/6). Gemini reviewer-C re-audit returned FAIL round 2 with NEW defects: 124 article errors ("a exciting"/"a epic"), bare genres ("a animated about", "a war about"), bad compounds ("an assassin war set in a casino") — all independently confirmed. Ticket LORA-TRAIN-2d DONE: Codex STOPPED on usage limit (resets 4:14 AM) after applying complete build-script fix; Claude verified + finished it (split FINITE/PARTICIPIAL subjectless implicit phrases, "something where" for finite subjectful, audit clause-grammar check). All validation green: audit all-zeros exit 0, byte-identical double build, pytest 6/6, 3600/600 counts. Ledger entry LORA-TRAIN-2d written. Gemini round-3 re-audit dispatched in background.

## Next
1. Read Gemini round-3 verdict (.agents/outbox/gemini/current_result.md) — need VERDICT: PASS. If FAIL, confirm findings, fix, loop.
2. On PASS: commit dataset+spec+ledger, retrain (`cinematch-llama\.venv\Scripts\python.exe cinematch-llama\scripts\train_intent_lora.py`), generate (`generate_intent_predictions.py`), grade (`venv\Scripts\python.exe cinematch-llama\scripts\grade_intent_predictions.py`), re-gate vs tier-2 numbers in eval/runs/2026-06-11-intent-parser-nogit/report.json (gate clause (b): beat tier-2 plot_elements F1 on plot_description 0.9412, hybrid 0.7027, implicit_plot 0.0), ledger + close lock.

## Context
Owner constraints (binding, spec §3.8): fixed vocab only; user mood ≠ film mood; no keyword shortcuts; labels reviewed by 2-3 AIs before training. Two venvs: repo venv (pytest/eval/jsonschema, no torch) vs cinematch-llama/.venv (torch/peft, no jsonschema). Gemini sandbox needs docker (absent) — read-only plan mode only. Lock .agents/locks/active_ticket.lock = LORA-TRAIN-2d OPEN. Don't wire adapter into serving without full gate PASS. Session goal hook active: continue until model passes the gate.
