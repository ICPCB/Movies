"""Intent-parser eval (ULTRAPLAN phase 7).

Gold sets are deterministic by construction:
- eval/queries/mood_v1.jsonl: gold user-mood categories + desired/avoid film
  moods were generated from the vocabulary, so the lexicon parser is measured
  on exact field recovery.
- eval/queries/all.jsonl (content queries): gold = NO mood fields; any mood
  the parser extracts there is a false positive.

Metrics: schema-validity rate, micro precision/recall/F1 per mood field,
mode accuracy on mood_v1, and mood false-positive rate on content queries.
With --tier2, each query also goes through the few-shot Ollama extractor and
we report its JSON-validity rate (target >=99%: tier-2 failures fall back to
tier 1, so end-to-end validity stays 100% by design).

Usage:
    python eval/scripts/intent_parser_eval.py [--tier2] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from engine import intent_parser  # noqa: E402
from engine.intent_schema import validate_intent  # noqa: E402

MOOD_QUERIES = ROOT / "eval" / "queries" / "mood_v1.jsonl"
CONTENT_QUERIES = ROOT / "eval" / "queries" / "all.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier2", action="store_true", help="also eval the Ollama extractor")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    mood_rows = _read_jsonl(MOOD_QUERIES)
    content_rows = _read_jsonl(CONTENT_QUERIES)

    counts = {
        field: {"tp": 0, "fp": 0, "fn": 0}
        for field in ("user_moods", "desired_film_moods", "avoid_film_moods")
    }
    gold_fields = {
        "user_moods": "user_mood_categories",
        "desired_film_moods": "desired_film_moods",
        "avoid_film_moods": "avoid_film_moods",
    }
    valid = 0
    mode_correct = 0
    per_query_failures: list[dict] = []
    for row in mood_rows:
        intent = intent_parser.parse_tier1(row["query"])
        if validate_intent(intent)[0]:
            valid += 1
        if intent["mode"] == row["tags"]["mode"]:
            mode_correct += 1
        miss = {}
        for field, gold_key in gold_fields.items():
            predicted = set(intent[field])
            gold = set(row["tags"][gold_key])
            counts[field]["tp"] += len(predicted & gold)
            counts[field]["fp"] += len(predicted - gold)
            counts[field]["fn"] += len(gold - predicted)
            if predicted != gold:
                miss[field] = {
                    "predicted": sorted(predicted),
                    "gold": sorted(gold),
                }
        if miss:
            per_query_failures.append({"qid": row["qid"], "query": row["query"], **miss})

    content_false_positives = []
    content_valid = 0
    for row in content_rows:
        intent = intent_parser.parse_tier1(row["query"])
        if validate_intent(intent)[0]:
            content_valid += 1
        if intent["user_moods"]:
            content_false_positives.append(
                {"qid": row.get("qid"), "query": row["query"], "user_moods": intent["user_moods"]}
            )

    report = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "tier1": {
            "mood_v1": {
                "queries": len(mood_rows),
                "schema_validity_rate": round(valid / len(mood_rows), 4),
                "mode_accuracy": round(mode_correct / len(mood_rows), 4),
                "fields": {
                    field: _prf(c["tp"], c["fp"], c["fn"])
                    for field, c in counts.items()
                },
                "queries_with_field_mismatch": per_query_failures,
            },
            "content_queries": {
                "queries": len(content_rows),
                "schema_validity_rate": round(content_valid / len(content_rows), 4),
                "mood_false_positive_rate": round(
                    len(content_false_positives) / len(content_rows), 4
                ),
                "false_positives": content_false_positives,
            },
        },
    }

    if args.tier2:
        tier2_valid = 0
        tier2_total = 0
        tier2_failures: list[dict] = []
        for row in mood_rows + content_rows:
            tier2_total += 1
            try:
                extracted = intent_parser._ollama_chat(row["query"], 30.0)
                assert isinstance(extracted.get("plot_elements", []), list)
                assert isinstance(extracted.get("genres_include", []), list)
                tier2_valid += 1
            except Exception as cause:  # noqa: BLE001 - eval counts every failure kind
                tier2_failures.append({"qid": row.get("qid"), "error": str(cause)[:120]})
        report["tier2"] = {
            "model": intent_parser.OLLAMA_MODEL,
            "queries": tier2_total,
            "json_validity_rate": round(tier2_valid / tier2_total, 4),
            "failures": tier2_failures,
            "note": "end-to-end validity is 100% by design: tier-2 failures fall back to tier 1",
        }

    out_path = (
        Path(args.out)
        if args.out
        else ROOT
        / "eval"
        / "runs"
        / f"{datetime.now():%Y-%m-%d}-intent-parser-nogit"
        / "report.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    t1 = report["tier1"]["mood_v1"]
    print(f"tier1 mood_v1: validity={t1['schema_validity_rate']} mode_acc={t1['mode_accuracy']}")
    for field, stats in t1["fields"].items():
        print(f"  {field}: P={stats['precision']} R={stats['recall']} F1={stats['f1']}")
    t1c = report["tier1"]["content_queries"]
    print(
        f"tier1 content: validity={t1c['schema_validity_rate']} "
        f"mood_false_positive_rate={t1c['mood_false_positive_rate']}"
    )
    if args.tier2:
        print(f"tier2: json_validity={report['tier2']['json_validity_rate']}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
