"""Client and lifecycle helpers for the local intent-LoRA sidecar."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from engine.intent_schema import validate_intent

REPO = Path(__file__).resolve().parent.parent
LORA_URL = os.getenv("CINEMATCH_LORA_URL", "http://127.0.0.1:8765")
LORA_TIMEOUT_SECONDS = float(os.getenv("CINEMATCH_LORA_TIMEOUT", "30"))
LORA_ENABLED = os.getenv("CINEMATCH_LORA_ENABLED", "1") != "0"

_PYTHON = REPO / "cinematch-llama" / ".venv" / "Scripts" / "python.exe"
_SERVER = REPO / "scripts" / "lora_server.py"
_ADAPTER = (
    REPO
    / "cinematch-llama"
    / "outputs"
    / "intent_lora_v6_e4"
    / "adapter_model.safetensors"
)


def _request(path: str, payload: dict | None = None, timeout: float = 2.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{LORA_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def is_ready(timeout: float = 0.5) -> bool:
    try:
        health = _request("/health", timeout=timeout)
        return health.get("status") == "ok" and Path(health.get("adapter", "")) == _ADAPTER.parent
    except Exception:
        return False


def parse(text: str, timeout: float = LORA_TIMEOUT_SECONDS) -> dict[str, Any]:
    if not LORA_ENABLED:
        raise RuntimeError("LoRA intent parser is disabled")
    response = _request("/parse", {"text": text}, timeout=timeout)
    intent = response.get("intent")
    valid, errors = validate_intent(intent)
    if not valid:
        raise ValueError(f"invalid LoRA intent: {errors}")
    return intent


def start_local_sidecar() -> subprocess.Popen | None:
    if not LORA_ENABLED or is_ready():
        return None
    if not (_PYTHON.is_file() and _SERVER.is_file() and _ADAPTER.is_file()):
        return None
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [str(_PYTHON), str(_SERVER)],
        cwd=str(REPO),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def wait_until_ready(timeout: float = 45.0) -> bool:
    if not LORA_ENABLED:
        return False
    if not is_ready() and not (_PYTHON.is_file() and _SERVER.is_file() and _ADAPTER.is_file()):
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_ready():
            return True
        time.sleep(0.25)
    return False


def stop_local_sidecar(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    try:
        _request("/shutdown", {}, timeout=2.0)
        process.wait(timeout=5.0)
    except Exception:
        if process.poll() is None:
            process.terminate()
