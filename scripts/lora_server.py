"""Persistent local HTTP sidecar for the CineMatch intent LoRA adapter."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from training.prompt_format import EOS_TOKEN_ID, build_prompt  # noqa: E402

MODEL_DIR = REPO / "cinematch-llama" / "Llama-3.2-1B"
ADAPTER_DIR = REPO / "cinematch-llama" / "outputs" / "intent_lora_v6_e4"
MAX_NEW_TOKENS = 320


def _load_base_model() -> AutoModelForCausalLM:
    # 4-bit NF4 keeps the 1B base under ~1 GB VRAM so the sidecar can share
    # an 8 GB GPU with the BGE-M3 embedder and the cross-encoder reranker.
    # CINEMATCH_LORA_4BIT=0 forces the original bf16 load.
    if os.getenv("CINEMATCH_LORA_4BIT", "1") != "0" and torch.cuda.is_available():
        try:
            from transformers import BitsAndBytesConfig

            return AutoModelForCausalLM.from_pretrained(
                MODEL_DIR,
                quantization_config=BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16,
                ),
                device_map="auto",
            )
        except Exception as error:
            print(f"[lora-server] 4-bit load failed ({error}); using bf16", flush=True)
    return AutoModelForCausalLM.from_pretrained(
        MODEL_DIR,
        dtype=torch.bfloat16,
        device_map="auto",
    )


class IntentModel:
    def __init__(self) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = PeftModel.from_pretrained(_load_base_model(), ADAPTER_DIR)
        self.model.eval()
        self._lock = threading.Lock()

    def parse(self, text: str) -> dict:
        inputs = self.tokenizer(build_prompt(text), return_tensors="pt")
        inputs = {name: tensor.to(self.model.device) for name, tensor in inputs.items()}
        with self._lock, torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                eos_token_id=EOS_TOKEN_ID,
                pad_token_id=EOS_TOKEN_ID,
            )
        completion = self.tokenizer.decode(
            output[0][inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
        )
        intent = json.loads(completion)
        if not isinstance(intent, dict):
            raise ValueError("adapter output is not a JSON object")
        return intent


class Handler(BaseHTTPRequestHandler):
    model: IntentModel

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok", "adapter": str(ADAPTER_DIR)})
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/shutdown":
            self._json(200, {"status": "stopping"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path != "/parse":
            self._json(404, {"detail": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("text must be a non-empty string")
            self._json(200, {"intent": self.model.parse(text.strip())})
        except Exception as error:
            self._json(500, {"detail": str(error)})

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not MODEL_DIR.is_dir():
        raise SystemExit(f"base model not found: {MODEL_DIR}")
    if not (ADAPTER_DIR / "adapter_model.safetensors").is_file():
        raise SystemExit(f"adapter not found: {ADAPTER_DIR}")

    Handler.model = IntentModel()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"intent LoRA ready at http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
