"""Deterministic intent-parser training-dataset generator — INTERFACE STUB.

Implementation is assigned to Codex/Gemini via the ticket in
docs/superpowers/specs/2026-06-11-llama-intent-parser-lora.md §7.
This stub fixes the contract so the implementation, the spec, and the eval
harness cannot drift: CLI, output files, record shape, and the validation
gate every record must pass.

Contract (spec §4):
- Deterministic: same arguments → byte-identical output across runs
  (sorted iteration + fixed seed, like eval/scripts/build_mood_queries.py).
- Seeds: labels/user_mood_map.json, labels/user_mood_vocab.json,
  labels/film_mood_vocab.json, the spec §3.7 concept-inference table,
  template expansion, and optionally --seed-examples (the 120 local
  cinematch-llama mood examples; provenance "ai_draft" unless stated).
- Emits the six category files plus final_intent_train.jsonl (merged,
  deterministic train/val/test split markers), ~3,600 records total.
- Every record passes engine.intent_schema.validate_intent; implicit plot
  records pass the no-literal-concept assertion; no record text matches an
  eval/queries/intent_v1.jsonl query.

Usage:
    python training/build_intent_dataset.py [--seed-examples PATH]
        [--target-total 3600] [--seed 20260611] [--out-dir training/]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.intent_schema import validate_intent  # noqa: E402

CATEGORY_FILES = (
    "mood_user_only.jsonl",
    "mood_film_only.jsonl",
    "mood_user_and_film.jsonl",
    "avoid_preferences.jsonl",
    "plot_description.jsonl",
    "hybrid_queries.jsonl",
)
MERGED_FILE = "final_intent_train.jsonl"
ALLOWED_PROVENANCE = ("deterministic_rules", "ai_draft")
SPLITS = ("train", "val", "test")
INTENT_V1 = ROOT / "eval" / "queries" / "intent_v1.jsonl"


def validate_record(record: dict, heldout_texts: set[str]) -> list[str]:
    """Gate every generated record. Returns a list of violations (empty = ok)."""
    errors = []
    for key in ("text", "intent", "category", "provenance", "split"):
        if key not in record:
            errors.append(f"missing key: {key}")
    if errors:
        return errors
    if record["category"] + ".jsonl" not in CATEGORY_FILES:
        errors.append(f"unknown category: {record['category']}")
    if record["provenance"] not in ALLOWED_PROVENANCE:
        errors.append(f"dishonest provenance: {record['provenance']}")
    if record["split"] not in SPLITS:
        errors.append(f"unknown split: {record['split']}")
    ok, schema_errors = validate_intent(record["intent"])
    if not ok:
        errors.extend(schema_errors)
    if record["text"].strip().lower() in heldout_texts:
        errors.append("text collides with held-out intent_v1 eval query")
    return errors


def load_heldout_texts() -> set[str]:
    return {
        json.loads(line)["query"].strip().lower()
        for line in INTENT_V1.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-examples", default=None,
                        help="optional local seed jsonl (cinematch-llama 120 mood examples)")
    parser.add_argument("--target-total", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=20260611)
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    raise SystemExit(
        "build_intent_dataset.py is an interface stub - the generator "
        "implementation is the Codex/Gemini ticket in docs/superpowers/specs/"
        "2026-06-11-llama-intent-parser-lora.md section 7. Implementations "
        f"must emit {CATEGORY_FILES + (MERGED_FILE,)} into {args.out_dir} and "
        "pass validate_record() for every record."
    )


if __name__ == "__main__":
    raise SystemExit(main())
