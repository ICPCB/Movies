
## 2026-06-11 - LORA-TRAIN-1 dispatch attempt 1: Codex STOPPED

- Ticket: .agents/inbox/codex/current.md (spec section 7; inventory-only variant, no deletions)
- Result: STOPPED - Codex CLI hit OpenAI usage limit mid-run ("try again at Jun 15th, 2026 9:46 PM"), exit 1, ~56k tokens used, no outbox report written.
- Repo impact: ZERO file changes (failed during read-only inventory phase; git status clean).
- Gemini fallback evaluated: gemini 0.46.0 present but --sandbox requires docker/podman (neither installed); running yolo unsandboxed would bypass approval+sandbox rules - NOT done.
- Decision per CLAUDE.md Codex-failure protocol: ledger records Codex STOPPED; Claude implements the ticket directly under the same scope/stop conditions. Lock updated to agent=claude.

## 2026-06-11 - LORA-TRAIN-1 completed by Claude (SELF-REVIEWED)

- Verdict: PASS (implementation + training + eval done; serving-path gate decision deferred - see risks)
- Files changed (tracked): training/prompt_format.py (new), training/test_prompt_format.py (new), training/build_intent_dataset.py (implemented), 6 category jsonl + final_intent_train.jsonl (3,600 records)
- Local artifacts (untracked): cinematch-llama/scripts/{train_intent_lora,generate_intent_predictions,grade_intent_predictions}.py, cinematch-llama/outputs/intent_lora/ (adapter 13.6 MB, predictions.jsonl, eval_report.json, final_val_metrics.json)
- Validation: pytest api/tests eval/tests training -q = 138 passed; double dataset build = byte-identical hashes; generator hard-asserts validate_intent on all 3,600 + implicit no-literal-keyword + zero intent_v1 overlap; tier-1 baseline eval reproduced recorded numbers
- Training: 3 epochs, 609 steps, LoRA r=16 a=32 dropout .05 q/k/v/o, bf16, RTX 4070; final eval_loss 0.0066
- Eval (intent_v1, adapter vs tier-1): validity 1.0 all slices; mode_acc 1.0 all slices; film_mood_only desired F1 0.0->1.0; avoid_preferences avoid F1 0.52->0.97; implicit_plot plot F1 0.0->0.92; plot_description 0.0->0.60; hybrid 0.0->0.47; mood slices no regression (0.96/0.965/0.97). Held-out test: validity 1.0 all categories, exact-match 0.67-1.0.
- Deviations: mood_examples_seed_v1_120.jsonl does NOT exist anywhere in cinematch-llama/ (docs stale) - generated without --seed-examples; stage1/data/ already empty. Cleanup candidates for owner: Llama-3.2-1B/original/ (2.36 GB), outputs/stage1_smoke_lora/ (~150 MB).
- Risks: spec section 5 gate clause (b) compares against the few-shot TIER-2 baseline, which requires an Ollama run (115 calls) not authorized by this ticket - gate adjudication vs tier-2 is PENDING; adapter NOT wired into serving (out of scope regardless).
- Committed: yes (this commit)
