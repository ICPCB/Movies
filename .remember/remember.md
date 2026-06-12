# Handoff

## State
LoRA v6 GATE PASSED 2026-06-12. Dataset v6 (trope bucket for iv38: object-less falls-in-love + trailing setting + bare-start genre prefix; 2-AI panel PASS) trained by owner at 4 epochs -> cinematch-llama/outputs/intent_lora_v6_e4/. Spec section 5 gate verified against artifacts: validity+mode 1.0 all 7 slices; plot 0.9583>0.9412, hybrid 0.7179>0.7027 (slim +0.015), implicit 0.88>0.0; mood clause vs PHASE-7 baseline 0.96/1.0/0.9714 (avoid margin only 0.0034). iv38 now exact. Generalization probe (20 novel-vocab queries, ai_draft): 17/20 exact, plot F1 0.9348 - generalizes, not memorized. Ledger through LORA-PROBE-6. Adapter still NOT wired into serving (verified: zero adapter refs in src/ + engine/).

## Next
1. Owner decision: wire adapter v6 e4 into the serving path - requires an explicit src/* ticket naming exact files (spec section 5 now permits it); 4-epoch deviation from spec 6 (2-3) is owner-accepted, recorded in LORA-GATE-REVIEW-6.
2. Known non-blocking: iv45 "alien" vs "alien creature" clip (regressed vs v5); avoid-slice mood over-prediction (iv69/iv72); probe misses pg05 (4-element trope sentence), pg11 (grumpy not in evaluative list), pg13 (bakery->bakeries).
3. Owner items still open: iv52 'animals' plural gold quirk; iv38 lowercase 'animation' eval-gold edit (owner-only).

## Context
Adapter v5-era outputs remain at cinematch-llama/outputs/intent_lora/ (Claude-trained 3-epoch v6 also landed there 11:00 AM - superseded by owner's e4 run). Probe artifacts: cinematch-llama/probe/ (gitignored, ai_draft provenance, never merge into authoritative artifacts). Two venvs: repo venv (pytest/eval, no torch) vs cinematch-llama/.venv (torch, no jsonschema). Dataset must stay byte-identical on double build + audit all-zeros before commit. Codex was usage-limited this session; Claude implemented per CLAUDE.md failure protocol; Gemini used read-only as reviewer C.
