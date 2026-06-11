"""Fixed prompt format for the Llama-3.2-1B BASE intent adapter.

Single source of truth (spec docs/superpowers/specs/
2026-06-11-llama-intent-parser-lora.md section 6.1): the dataset generator,
the training script, and the eval adapter glue must all import from this
module. The template must not be copied anywhere else — the base model has
no chat template, so any train/inference drift in this exact string silently
destroys adapter quality.

Conventions (spec section 6.1):
- BOS <|begin_of_text|> (128000) is added by the tokenizer, never written
  into the template.
- EOS/stop = <|end_of_text|> (128001), appended after the JSON during
  tokenization; generation stops at EOS.
- Training loss is masked over the prompt tokens; loss is computed only on
  the completion (canonical JSON + EOS).
- Eval/inference decoding is greedy; generated text up to EOS is parsed with
  json.loads and then engine.intent_schema.validate_intent.
- canonical_json is the ONLY serializer for training targets so reruns stay
  byte-identical.
"""

from __future__ import annotations

import json

PROMPT_TEMPLATE = (
    "### Task: Parse the movie request into CineMatch intent JSON.\n"
    "### Request:\n{text}\n"
    "### Intent:\n"
)

EOS_TOKEN = "<|end_of_text|>"
EOS_TOKEN_ID = 128001


def canonical_json(intent: dict) -> str:
    """Deterministic serialization of an intent object."""
    return json.dumps(intent, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_prompt(text: str) -> str:
    """Inference-time prompt — ends exactly at '### Intent:\\n'."""
    return PROMPT_TEMPLATE.format(text=text)


def build_example(text: str, intent: dict) -> str:
    """Training-time example text (EOS appended by the tokenizer)."""
    return build_prompt(text) + canonical_json(intent)
