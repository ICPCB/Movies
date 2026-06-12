from __future__ import annotations

import pytest

from engine import lora
from engine.intent_schema import empty_intent


def test_parse_accepts_schema_valid_sidecar_response(monkeypatch):
    expected = empty_intent("robot in space", "content")
    expected["plot_elements"] = ["robot", "space"]
    monkeypatch.setattr(lora, "LORA_ENABLED", True)
    monkeypatch.setattr(
        lora,
        "_request",
        lambda path, payload, timeout: {"intent": expected},
    )

    assert lora.parse("robot in space") == expected


def test_parse_rejects_invalid_sidecar_response(monkeypatch):
    monkeypatch.setattr(lora, "LORA_ENABLED", True)
    monkeypatch.setattr(
        lora,
        "_request",
        lambda path, payload, timeout: {"intent": {"mode": "content"}},
    )

    with pytest.raises(ValueError, match="invalid LoRA intent"):
        lora.parse("robot in space")
