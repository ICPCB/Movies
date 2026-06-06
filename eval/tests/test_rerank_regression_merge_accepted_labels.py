"""Tests for rerank_regression_merge_accepted_labels.py."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "rerank_regression_merge_accepted_labels.py"
GOLD_FIELD_ORDER = ["qid", "tmdb_id", "grade", "label_source", "silver_grade", "gold_grade", "gold_notes"]


def make_gold_row(qid, tmdb_id, grade, label_source="silver", silver_grade=None, gold_grade=None, gold_notes=None):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "label_source": label_source,
        "silver_grade": silver_grade,
        "gold_grade": gold_grade,
        "gold_notes": gold_notes,
    }


def make_accepted_row(qid, tmdb_id, grade, grader_notes="test note"):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "label_source": "human_reviewed_ai_assisted",
        "ai_assisted": True,
        "ai_confidence": "high",
        "ai_suggested_grade": grade,
        "grader_notes": grader_notes,
        "human_acceptance": "accepted_all",
        "movie_key": f"title:test|year:2000",
        "queue_position": 0,
        "reviewed_by": "human",
        "title": "Test Movie",
    }


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def setup_run_dir(tmp, gold_rows, accepted_rows):
    run_dir = Path(tmp) / "run"
    analysis_dir = run_dir / "analysis" / "rerank_regression"
    analysis_dir.mkdir(parents=True)
    write_jsonl(run_dir / "gold_labels.jsonl", gold_rows)
    write_jsonl(analysis_dir / "missing_label_review_queue_accepted.jsonl", accepted_rows)
    return str(run_dir)


def run_merge(run_dir):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--run-dir", run_dir],
        capture_output=True,
        text=True,
    )
    return result


class TestHappyPath(unittest.TestCase):
    def test_merge_2_existing_3_accepted(self):
        gold = [
            make_gold_row("q01", 100, 2, "silver", silver_grade=2),
            make_gold_row("q02", 200, 3, "gold", gold_grade=3, gold_notes="excellent"),
        ]
        accepted = [
            make_accepted_row("q01", 101, 1, "note A"),
            make_accepted_row("q02", 201, 0, "note B"),
            make_accepted_row("q03", 300, 2, "note C"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, accepted)
            result = run_merge(run_dir)
            self.assertEqual(result.returncode, 0, result.stderr)

            merged = read_jsonl(Path(run_dir) / "gold_labels.jsonl")
            self.assertEqual(len(merged), 5)

            for row in merged:
                self.assertEqual(set(row.keys()), set(GOLD_FIELD_ORDER))
                self.assertEqual(list(row.keys()), GOLD_FIELD_ORDER)

            self.assertEqual(merged[0]["tmdb_id"], 100)
            self.assertEqual(merged[0]["label_source"], "silver")
            self.assertEqual(merged[1]["tmdb_id"], 101)
            self.assertEqual(merged[1]["label_source"], "human_reviewed_ai_assisted")
            self.assertEqual(merged[2]["tmdb_id"], 200)
            self.assertEqual(merged[2]["label_source"], "gold")
            self.assertEqual(merged[3]["tmdb_id"], 201)
            self.assertEqual(merged[3]["label_source"], "human_reviewed_ai_assisted")
            self.assertEqual(merged[4]["tmdb_id"], 300)
            self.assertEqual(merged[4]["label_source"], "human_reviewed_ai_assisted")

            summary_path = Path(run_dir) / "analysis" / "rerank_regression" / "merge_summary.json"
            self.assertTrue(summary_path.exists())
            summary = json.load(open(summary_path))
            self.assertEqual(summary["existing_count"], 2)
            self.assertEqual(summary["accepted_count"], 3)
            self.assertEqual(summary["merged_count"], 5)


class TestFieldMapping(unittest.TestCase):
    def test_silver_grade_null_gold_grade_null_gold_notes_mapped(self):
        gold = [make_gold_row("q01", 100, 2, "silver", silver_grade=2)]
        accepted = [make_accepted_row("q01", 999, 1, "my grader note")]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, accepted)
            run_merge(run_dir)
            merged = read_jsonl(Path(run_dir) / "gold_labels.jsonl")
            new_row = [r for r in merged if r["tmdb_id"] == 999][0]
            self.assertIsNone(new_row["silver_grade"])
            self.assertIsNone(new_row["gold_grade"])
            self.assertEqual(new_row["gold_notes"], "my grader note")

    def test_existing_label_source_preserved(self):
        gold = [
            make_gold_row("q01", 100, 2, "silver"),
            make_gold_row("q01", 101, 3, "gold"),
        ]
        accepted = [make_accepted_row("q02", 200, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, accepted)
            run_merge(run_dir)
            merged = read_jsonl(Path(run_dir) / "gold_labels.jsonl")
            sources = {r["tmdb_id"]: r["label_source"] for r in merged}
            self.assertEqual(sources[100], "silver")
            self.assertEqual(sources[101], "gold")
            self.assertEqual(sources[200], "human_reviewed_ai_assisted")


class TestDuplicateKeyInAccepted(unittest.TestCase):
    def test_abort_on_duplicate(self):
        gold = [make_gold_row("q01", 100, 2)]
        accepted = [
            make_accepted_row("q02", 200, 1),
            make_accepted_row("q02", 200, 0),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, accepted)
            result = run_merge(run_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate key", result.stderr.lower())


class TestOverlapWithExisting(unittest.TestCase):
    def test_abort_on_overlap(self):
        gold = [make_gold_row("q01", 100, 2)]
        accepted = [make_accepted_row("q01", 100, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, accepted)
            result = run_merge(run_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("overlapping", result.stderr.lower())


class TestInvalidGrade(unittest.TestCase):
    def test_abort_on_grade_5(self):
        gold = [make_gold_row("q01", 100, 2)]
        accepted_row = make_accepted_row("q02", 200, 5)
        accepted_row["grade"] = 5
        accepted_row["ai_suggested_grade"] = 5

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, [accepted_row])
            result = run_merge(run_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid grade", result.stderr.lower())


class TestMissingField(unittest.TestCase):
    def test_abort_on_missing_qid(self):
        gold = [make_gold_row("q01", 100, 2)]
        accepted_row = make_accepted_row("q02", 200, 1)
        del accepted_row["qid"]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, [accepted_row])
            result = run_merge(run_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing fields", result.stderr.lower())


class TestWrongLabelSource(unittest.TestCase):
    def test_abort_on_wrong_source(self):
        gold = [make_gold_row("q01", 100, 2)]
        accepted_row = make_accepted_row("q02", 200, 1)
        accepted_row["label_source"] = "human_gold"

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, [accepted_row])
            result = run_merge(run_dir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("label_source", result.stderr.lower())


class TestIdempotency(unittest.TestCase):
    def test_second_run_aborts_on_overlap(self):
        gold = [make_gold_row("q01", 100, 2)]
        accepted = [make_accepted_row("q02", 200, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, accepted)
            result1 = run_merge(run_dir)
            self.assertEqual(result1.returncode, 0, result1.stderr)

            result2 = run_merge(run_dir)
            self.assertNotEqual(result2.returncode, 0)
            self.assertIn("overlapping", result2.stderr.lower())

            merged = read_jsonl(Path(run_dir) / "gold_labels.jsonl")
            self.assertEqual(len(merged), 2)


class TestOutputFieldOrder(unittest.TestCase):
    def test_field_order_matches_spec(self):
        gold = [make_gold_row("q01", 100, 2)]
        accepted = [make_accepted_row("q02", 200, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = setup_run_dir(tmp, gold, accepted)
            run_merge(run_dir)
            with open(Path(run_dir) / "gold_labels.jsonl") as f:
                for line in f:
                    row = json.loads(line)
                    self.assertEqual(list(row.keys()), GOLD_FIELD_ORDER)


if __name__ == "__main__":
    unittest.main()
