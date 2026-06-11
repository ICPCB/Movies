"""Tests for the fixed prompt-format contract (spec section 6.1).

No model load — these tests pin the exact strings so train/inference drift
is caught by pytest, not by a silently degraded adapter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.intent_schema import empty_intent, validate_intent  # noqa: E402
from training.prompt_format import (  # noqa: E402
    EOS_TOKEN,
    EOS_TOKEN_ID,
    PROMPT_TEMPLATE,
    build_example,
    build_prompt,
    canonical_json,
)


def test_template_exact_text():
    assert PROMPT_TEMPLATE == (
        "### Task: Parse the movie request into CineMatch intent JSON.\n"
        "### Request:\n{text}\n"
        "### Intent:\n"
    )


def test_build_prompt_boundary():
    prompt = build_prompt("feeling gloomy tonight")
    assert prompt.startswith("### Task: Parse the movie request")
    assert "feeling gloomy tonight" in prompt
    assert prompt.endswith("### Intent:\n")
    # BOS is the tokenizer's job — never in the template.
    assert "<|begin_of_text|>" not in prompt
    assert EOS_TOKEN not in prompt


def test_eos_convention():
    assert EOS_TOKEN == "<|end_of_text|>"
    assert EOS_TOKEN_ID == 128001


def test_canonical_json_deterministic_and_compact():
    intent = empty_intent("a heist movie", "content")
    first = canonical_json(intent)
    # Key order in the input dict must not matter.
    shuffled = json.loads(first)
    assert canonical_json(shuffled) == first
    # Compact separators, sorted keys.
    assert ": " not in first.replace('": ', "")  # no padded separators
    assert first.index('"avoid_film_moods"') < first.index('"mode"')


def test_canonical_json_round_trip_stays_valid():
    intent = empty_intent("something warm and funny", "mood")
    intent["desired_film_moods"] = ["funny", "warm"]
    round_tripped = json.loads(canonical_json(intent))
    ok, errors = validate_intent(round_tripped)
    assert ok, errors
    assert round_tripped == intent


def test_build_example_is_prompt_plus_completion():
    intent = empty_intent("x", "content")
    example = build_example("x", intent)
    prompt = build_prompt("x")
    assert example.startswith(prompt)
    completion = example[len(prompt):]
    assert completion == canonical_json(intent)
    # The prompt/completion boundary is recoverable — required for loss masking.
    assert json.loads(completion) == intent
