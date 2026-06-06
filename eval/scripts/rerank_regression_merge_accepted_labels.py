#!/usr/bin/env python3
"""Sidecar merge: fold human_reviewed_ai_assisted labels into gold_labels.jsonl."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REQUIRED_ACCEPTED_FIELDS = {"qid", "tmdb_id", "grade", "label_source"}
VALID_GRADES = {0, 1, 2, 3}
EXPECTED_LABEL_SOURCE = "human_reviewed_ai_assisted"
GOLD_FIELD_ORDER = ["qid", "tmdb_id", "grade", "label_source", "silver_grade", "gold_grade", "gold_notes"]


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"ERROR: {path} line {i}: invalid JSON: {e}", file=sys.stderr)
                sys.exit(1)
    return rows


def validate_accepted(rows):
    seen_keys = set()
    for i, row in enumerate(rows, 1):
        missing = REQUIRED_ACCEPTED_FIELDS - set(row.keys())
        if missing:
            print(f"ERROR: accepted row {i}: missing fields {missing}", file=sys.stderr)
            sys.exit(1)

        if row["label_source"] != EXPECTED_LABEL_SOURCE:
            print(
                f"ERROR: accepted row {i}: label_source={row['label_source']!r}, "
                f"expected {EXPECTED_LABEL_SOURCE!r}",
                file=sys.stderr,
            )
            sys.exit(1)

        if row["grade"] not in VALID_GRADES:
            print(f"ERROR: accepted row {i}: invalid grade={row['grade']!r}", file=sys.stderr)
            sys.exit(1)

        key = (row["qid"], row["tmdb_id"])
        if key in seen_keys:
            print(f"ERROR: accepted row {i}: duplicate key {key}", file=sys.stderr)
            sys.exit(1)
        seen_keys.add(key)

    return seen_keys


def validate_gold_schema(rows, path):
    expected_fields = set(GOLD_FIELD_ORDER)
    for i, row in enumerate(rows, 1):
        if set(row.keys()) != expected_fields:
            print(f"ERROR: {path} row {i}: schema mismatch, fields={set(row.keys())}", file=sys.stderr)
            sys.exit(1)


def map_accepted_to_gold(accepted_row):
    return {
        "qid": accepted_row["qid"],
        "tmdb_id": accepted_row["tmdb_id"],
        "grade": accepted_row["grade"],
        "label_source": EXPECTED_LABEL_SOURCE,
        "silver_grade": None,
        "gold_grade": None,
        "gold_notes": accepted_row.get("grader_notes"),
    }


def serialize_row(row):
    ordered = {k: row[k] for k in GOLD_FIELD_ORDER}
    return json.dumps(ordered, ensure_ascii=False)


def merge(run_dir):
    run_path = Path(run_dir)
    gold_path = run_path / "gold_labels.jsonl"
    accepted_path = run_path / "analysis" / "rerank_regression" / "missing_label_review_queue_accepted.jsonl"
    summary_path = run_path / "analysis" / "rerank_regression" / "merge_summary.json"

    if not gold_path.exists():
        print(f"ERROR: {gold_path} not found", file=sys.stderr)
        sys.exit(1)
    if not accepted_path.exists():
        print(f"ERROR: {accepted_path} not found", file=sys.stderr)
        sys.exit(1)

    existing = load_jsonl(gold_path)
    accepted = load_jsonl(accepted_path)

    validate_gold_schema(existing, gold_path)
    accepted_keys = validate_accepted(accepted)

    existing_keys = set()
    for i, row in enumerate(existing, 1):
        key = (row["qid"], row["tmdb_id"])
        if key in existing_keys:
            print(f"ERROR: {gold_path} row {i}: duplicate key {key}", file=sys.stderr)
            sys.exit(1)
        existing_keys.add(key)

    overlap = existing_keys & accepted_keys
    if overlap:
        examples = sorted(overlap)[:5]
        print(f"ERROR: {len(overlap)} overlapping keys found: {examples}", file=sys.stderr)
        sys.exit(1)

    new_rows = [map_accepted_to_gold(r) for r in accepted]

    existing_by_qid = {}
    for row in existing:
        existing_by_qid.setdefault(row["qid"], []).append(row)

    new_by_qid = {}
    for row in new_rows:
        new_by_qid.setdefault(row["qid"], []).append(row)

    all_qids = sorted(set(list(existing_by_qid.keys()) + list(new_by_qid.keys())))

    merged = []
    for qid in all_qids:
        merged.extend(existing_by_qid.get(qid, []))
        merged.extend(new_by_qid.get(qid, []))

    lines = [serialize_row(row) for row in merged]
    output = "\n".join(lines)

    fd, tmp_path = tempfile.mkstemp(dir=str(run_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(output)
        os.replace(tmp_path, str(gold_path))
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    from collections import Counter
    source_counts = Counter(row["label_source"] for row in merged)
    summary = {
        "existing_count": len(existing),
        "accepted_count": len(accepted),
        "merged_count": len(merged),
        "overlap_count": 0,
        "label_sources": dict(sorted(source_counts.items())),
        "qids": all_qids,
        "run_dir": str(run_dir),
        "script": "eval/scripts/rerank_regression_merge_accepted_labels.py",
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"Merged {len(existing)} existing + {len(accepted)} accepted = {len(merged)} total rows")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Merge accepted labels into gold_labels.jsonl")
    parser.add_argument("--run-dir", required=True, help="Path to the eval run directory")
    args = parser.parse_args()
    sys.exit(merge(args.run_dir))


if __name__ == "__main__":
    main()
