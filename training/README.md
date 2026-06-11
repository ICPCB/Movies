# training/ — Llama intent-parser LoRA datasets

Dataset home for the unified LoRA intent-parser adapter.
Spec (authoritative): `docs/superpowers/specs/2026-06-11-llama-intent-parser-lora.md`.

## Layout

```text
training/
  build_intent_dataset.py     deterministic generator (interface stub; implementation
                              is a Codex/Gemini ticket — spec §7)
  mood_user_only.jsonl        "feeling X" → map-derived mood intent
  mood_film_only.jsonl        "want something warm" → desired film moods only
  mood_user_and_film.jsonl    feeling clause + want clause, merged per spec §3.3
  avoid_preferences.jsonl     explicit "nothing scary" → avoid_film_moods
  plot_description.jsonl      explicit AND implicit plot pairs (spec §3.5/§3.7)
  hybrid_queries.jsonl        feeling + plot → hybrid mode
  final_intent_train.jsonl    merged, train/val/test split markers — the ONE
                              file the unified adapter trains on
```

Generated `.jsonl` files are committed only after Claude gate review of the
generator run (determinism + validation evidence in the ledger).

## Record shape

```json
{"text": "...", "intent": {<full engine/intent_schema.py intent>},
 "category": "mood_user_only", "provenance": "deterministic_rules", "split": "train"}
```

## Rules (non-negotiable)

- Every record passes `engine.intent_schema.validate_intent`.
- Implicit plot records: the canonical concept phrase must NOT appear in `text`
  (asserted by the generator).
- Provenance is honest: `deterministic_rules` or `ai_draft` — never `human_gold`.
- No record may share its text with an `eval/queries/intent_v1.jsonl` query
  (eval is held out).
- One unified adapter trains on `final_intent_train.jsonl` — never per-category
  models.
- Training runs on the owner PC against the local `cinematch-llama/` weights
  (gitignored); weights and adapters are never committed.
