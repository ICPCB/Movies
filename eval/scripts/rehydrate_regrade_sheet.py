"""One-time RG-03 recovery: rehydrate regrade_sheet.jsonl from gold_labels.jsonl.

RG-03 A1 work rebuilt regrade_sheet.jsonl from scratch, dropping the 45
batch-1/batch-2 human gold grades. Those grades survive in gold_labels.jsonl
(label_source == "gold"). This script restores gold_grade/gold_notes onto the
batch-1/batch-2 q03/q08/q12/q13 rows by a (qid, tmdb_id) join, leaves the q07
batch-3 rows ungraded for A2, backs up the current sheet, and writes the result
to a separate file. It never replaces the live sheet.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.scripts import _run_io
from eval.scripts.build_regrade_sheet import ROW_KEYS

RUN_ID = "2026-05-19-1846-nogit"
RESTORE_BATCHES = {1, 2}
RESTORE_QIDS = {"q03", "q08", "q12", "q13"}
EXPECTED_ROWS_TOTAL = 55
EXPECTED_GOLD_ROWS = 45
EXPECTED_Q07_BATCH3_ROWS = 10


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _row_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return (row.get("qid"), row.get("tmdb_id"))


def rehydrate() -> int:
    run_dir = _run_io.run_dir(RUN_ID)
    regrade_dir = run_dir / "analysis" / "regrade"
    sheet_path = regrade_dir / "regrade_sheet.jsonl"
    gold_path = run_dir / "gold_labels.jsonl"
    out_path = regrade_dir / "regrade_sheet.rehydrated_from_gold_labels.jsonl"

    if not sheet_path.exists():
        print(f"ERROR: {sheet_path} not found", file=sys.stderr)
        return 1
    if not gold_path.exists():
        print(f"ERROR: {gold_path} not found", file=sys.stderr)
        return 1

    # 1. Back up the current sheet with a timestamp before anything else.
    sha_before = _sha256(sheet_path)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = regrade_dir / f"regrade_sheet.jsonl.pre_rehydrate.{ts}.bak"
    backup_path.write_bytes(sheet_path.read_bytes())
    sha_backup = _sha256(backup_path)

    print("== backup ==")
    print(f"  source           : {sheet_path}")
    print(f"  backup           : {backup_path}")
    print(f"  sha256 (current) : {sha_before}")
    print(f"  sha256 (backup)  : {sha_backup}")
    if sha_before != sha_backup:
        print("ERROR: backup SHA256 does not match source", file=sys.stderr)
        return 1

    # 2. Build the gold map from gold_labels.jsonl.
    gold_map: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in _load_jsonl(gold_path):
        if row.get("label_source") == "gold":
            gold_map[_row_key(row)] = row

    # 3. Rehydrate batch-1/batch-2 q03/q08/q12/q13 rows; q07 batch-3 untouched.
    original_rows = _load_jsonl(sheet_path)
    sheet_rows = _load_jsonl(sheet_path)
    problems: list[str] = []
    restored = 0

    for row in sheet_rows:
        if row.get("batch") not in RESTORE_BATCHES:
            continue
        if row.get("qid") not in RESTORE_QIDS:
            continue
        key = _row_key(row)
        gold = gold_map.get(key)
        if gold is None:
            problems.append(f"no gold label for batch-{row.get('batch')} row {key}")
            continue
        gold_grade = gold.get("gold_grade")
        gold_notes = gold.get("gold_notes")
        if gold_grade is None:
            problems.append(f"{key}: gold label has null gold_grade")
            continue
        if gold.get("silver_grade") != row.get("silver_grade"):
            problems.append(
                f"{key}: silver_grade mismatch sheet={row.get('silver_grade')} "
                f"gold={gold.get('silver_grade')}"
            )
        if gold_grade != row.get("silver_grade") and (
            not isinstance(gold_notes, str) or not gold_notes.strip()
        ):
            problems.append(f"{key}: gold_grade changes silver but gold_notes is empty")
        row["gold_grade"] = gold_grade
        row["gold_notes"] = gold_notes
        restored += 1

    # 4. Write the rehydrated candidate file — never the live sheet.
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        for row in sheet_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    # 5. Verify.
    q07_batch3 = [r for r in sheet_rows if r.get("qid") == "q07" and r.get("batch") == 3]
    q07_batch3_graded = sum(1 for r in q07_batch3 if r.get("gold_grade") is not None)
    gold_count = sum(1 for r in sheet_rows if r.get("gold_grade") is not None)
    keys = [_row_key(r) for r in sheet_rows]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    original_batch3 = [r for r in original_rows if r.get("batch") == 3]
    bad_key_rows = [_row_key(r) for r in sheet_rows if set(r) != set(ROW_KEYS)]

    checks: list[tuple[str, bool, str]] = [
        ("row count == 55", len(sheet_rows) == EXPECTED_ROWS_TOTAL,
         f"got {len(sheet_rows)}"),
        ("exactly 45 rows have gold_grade", gold_count == EXPECTED_GOLD_ROWS,
         f"got {gold_count}"),
        ("q07 batch-3 has 10 rows", len(q07_batch3) == EXPECTED_Q07_BATCH3_ROWS,
         f"got {len(q07_batch3)}"),
        ("q07 batch-3 has 0 gold_grade", q07_batch3_graded == 0,
         f"got {q07_batch3_graded}"),
        ("no duplicate (qid, tmdb_id)", not dupes, f"dupes={dupes}"),
        ("q07 batch-3 rows unchanged", q07_batch3 == original_batch3, ""),
        ("all rows keep the expected key set", not bad_key_rows,
         f"bad={bad_key_rows}"),
        ("no join / integrity problems", not problems,
         f"{len(problems)} problem(s)"),
    ]

    print()
    print("== rehydration ==")
    print(f"  gold labels available : {len(gold_map)}")
    print(f"  rows restored         : {restored}")
    print(f"  rehydrated file       : {out_path}")
    if problems:
        print("  problems:")
        for problem in problems:
            print(f"    - {problem}")

    print()
    print("== verification ==")
    all_ok = True
    for name, ok, detail in checks:
        suffix = "" if ok or not detail else f" ({detail})"
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{suffix}")
        all_ok = all_ok and ok

    print()
    if all_ok:
        print("VERIFICATION PASSED — rehydrated file is ready to replace the sheet.")
        return 0
    print("VERIFICATION FAILED — do not replace regrade_sheet.jsonl.", file=sys.stderr)
    return 1


def main() -> int:
    return rehydrate()


if __name__ == "__main__":
    raise SystemExit(main())
