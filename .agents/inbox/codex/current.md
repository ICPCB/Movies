# Ticket LORA-TRAIN-1 — implement prompt format + dataset generator, clean cinematch-llama/, train + eval the unified LoRA adapter

## 1. Goal

Execute the local training ticket in `docs/superpowers/specs/2026-06-11-llama-intent-parser-lora.md` section 7. The model-verification stop condition (criterion 1) is already RESOLVED: the local weights at `cinematch-llama/Llama-3.2-1B/` are confirmed the BASE variant and the owner chose to train them with the fixed prompt format defined in spec section 6.1. Do NOT download Llama-3.2-1B-Instruct.

## 2. Current repo state

- Branch `main` @ 59405c5, clean tree.
- Spec, eval set (`eval/queries/intent_v1.jsonl`, 84 records, 7 slices), eval harness (`eval/scripts/intent_parser_eval.py --intent-v1`), and generator interface stub (`training/build_intent_dataset.py`) are committed.
- `cinematch-llama/` is gitignored (local only). It contains the base weights, `mood_examples_seed_v1_120.jsonl`, a prior smoke run (`scripts/train_stage1.py`, `test_stage1.py`, `config/stage1_smoke.yaml`, `stage1/data/`, `outputs/stage1_smoke_lora/`).
- Python must run under the venv: `venv\Scripts\python.exe` (global python lacks deps).

## 3. Files to read (do not change)

- docs/superpowers/specs/2026-06-11-llama-intent-parser-lora.md (the authoritative spec — read fully, especially sections 3, 4, 5, 6, 6.1)
- engine/intent_schema.py, engine/intent_parser.py
- labels/user_mood_map.json, labels/user_mood_vocab.json, labels/film_mood_vocab.json
- eval/queries/intent_v1.jsonl, eval/scripts/intent_parser_eval.py
- training/README.md

## 4. Files allowed to change/create

- training/prompt_format.py (new — implement exactly the module surface in spec section 6.1)
- training/test_prompt_format.py (new — round-trip, determinism, prompt/completion boundary tests; no model load)
- training/build_intent_dataset.py (implement the committed interface stub)
- training/mood_user_only.jsonl, training/mood_film_only.jsonl, training/mood_user_and_film.jsonl, training/avoid_preferences.jsonl, training/plot_description.jsonl, training/hybrid_queries.jsonl, training/final_intent_train.jsonl (generated outputs)
- cinematch-llama/** (local, untracked: training script, config, outputs/, cleanup below)

## 5. Files forbidden to change

Everything else. Explicitly: src/*, engine/*, api/*, web/*, eval/*, labels/*, docs/*, AGENTS.md, CLAUDE.md, .remember/*, .agents/* (except your outbox report).

## 6. Exact implementation rules

a. ORDER: inventory -> prompt_format -> generator -> dataset -> train -> eval. Stop at the first failed step and report.
b. cinematch-llama/ inventory ONLY — DO NOT DELETE ANYTHING. Disk cleanup is the owner's manual call (ULTRAPLAN section 14.3), not automated. In your final report, list the paths + sizes the spec marks as cleanup candidates (Llama-3.2-1B/original/, outputs/stage1_smoke_lora/, stage1/data/, stale configs) so the owner can decide. Write new training outputs under cinematch-llama/outputs/intent_lora/ so they never collide with the old smoke run.
c. training/prompt_format.py: implement PROMPT_TEMPLATE, canonical_json, build_prompt, build_example exactly per spec section 6.1. BOS added by tokenizer only; EOS <|end_of_text|> (128001) appended at tokenization; canonical_json = json.dumps(intent, ensure_ascii=False, sort_keys=True, separators=(",", ":")). This module is the ONLY place the template exists — generator, trainer, and eval glue must import it.
d. training/build_intent_dataset.py: implement per the committed stub interface and spec sections 3-4. Deterministic given the seed: two runs byte-identical. ~3,600 pairs across the six category files merged into final_intent_train.jsonl with split markers. Every record passes engine.intent_schema.validate_intent. Implicit plot records pass the no-literal-keyword assertion. Exclude any pair whose text matches an intent_v1 query. Provenance honest (deterministic_rules / ai_draft) — never human_gold. NO LLM/API/Ollama/network calls in generation.
e. Training (local, cinematch-llama/): PEFT LoRA on the base weights, r=16, alpha=32, dropout 0.05, target q/k/v/o projections, 2-3 epochs, loss masked over prompt tokens (completion + EOS only). Build examples via training.prompt_format.build_example. Adapter saved under cinematch-llama/outputs/ — NEVER committed. Adapt the prior train_stage1.py if useful.
f. Eval: run `venv\Scripts\python.exe -m eval.scripts.intent_parser_eval --intent-v1` (tier-1 baseline) and an adapter-backed run (greedy decoding, parse to JSON, validate_intent). Report per-slice validity/mode_acc/F1 side by side against the spec section 5 gate. Do NOT modify eval/scripts — if the harness cannot load the adapter, write a local sidecar runner under cinematch-llama/ and report.
g. No network calls of any kind. No model downloads. Everything runs from local files.

## 7. Acceptance criteria

1. cinematch-llama/ inventory reported (cleanup-candidate paths + sizes); NOTHING deleted.
2. training/prompt_format.py matches spec 6.1 exactly; test_prompt_format.py passes.
3. Dataset: two consecutive builds byte-identical; ~3,600 pairs; 100% validate_intent pass; implicit no-literal-keyword assertion passes; zero overlap with intent_v1.
4. LoRA training completes with the spec hyperparameters; adapter under cinematch-llama/outputs/.
5. Side-by-side eval table (tier-1 baseline vs adapter) for all 7 intent_v1 slices vs the section 5 gate.

## 8. Validation commands (run exactly)

```
venv\Scripts\python.exe -m pytest api/tests eval/tests training -q
venv\Scripts\python.exe training/build_intent_dataset.py --seed-examples cinematch-llama/mood_examples_seed_v1_120.jsonl
venv\Scripts\python.exe training/build_intent_dataset.py --seed-examples cinematch-llama/mood_examples_seed_v1_120.jsonl   (second run; verify byte-identical)
venv\Scripts\python.exe -m eval.scripts.intent_parser_eval --intent-v1
```

## 9. Stop conditions

- Prompt template text appearing anywhere other than training/prompt_format.py.
- ANY deletion inside cinematch-llama/ or anywhere else (inventory/report only).
- Dataset validity < 0.99, non-deterministic rebuild, or intent_v1 overlap.
- Training failure you cannot fix inside ticket scope (e.g., missing torch/peft in venv — STOP and report, do not pip install new packages without reporting first).
- Gate not met: report the numbers; do NOT wire the adapter into serving. Serving changes are out of scope regardless.

## 10. Required final report (write to .agents/outbox/codex/current_result.md)

1. Verdict: PASS / FAIL / STOPPED / NEEDS_REVIEW
2. Files changed
3. Artifacts created (incl. adapter path, dataset counts per category)
4. Validation commands and results (incl. the byte-identical diff proof and the side-by-side eval table)
5. Git status summary
6. Risks or caveats
7. Whether anything was committed (you must NOT commit — leave that to Claude review)
8. Exact next recommended step
