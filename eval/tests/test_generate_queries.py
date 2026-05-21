import json
import tempfile
import unittest
from pathlib import Path

from eval.tests import conftest as _conftest
from eval.scripts import _diversity, _schemas, generate_queries


EXPECTED_ERA = {"pre-1980": 4, "1980-2000": 5, "2000-2015": 6, "2015+": 5}
EXPECTED_VOCAB = {"high": 8, "medium": 8, "low": 4}
EXPECTED_LENGTH = {"short": 8, "medium": 8, "long": 4}
EXPECTED_AMBIGUITY = {"low": 4, "medium": 12, "high": 4}
REQUIRED_GENRES = ("drama", "thriller", "sf", "animation", "horror", "comedy")


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class GenerateQueriesTest(unittest.TestCase):
    def test_record_count_and_qids_are_ordered(self):
        records = generate_queries.build_records(seed=42)
        self.assertEqual(len(records), 20)
        self.assertEqual([record["qid"] for record in records], [f"q{i:02d}" for i in range(1, 21)])

    def test_every_record_is_schema_valid(self):
        for record in generate_queries.build_records(seed=42):
            self.assertIs(_schemas.validate_query_record(record), record)

    def test_diversity_counts_match_phase1_plan(self):
        summary = _diversity.summarize(generate_queries.build_records(seed=42))
        self.assertEqual({key: summary["era"][key] for key in EXPECTED_ERA}, EXPECTED_ERA)
        self.assertEqual(
            {key: summary["vocab_distance"][key] for key in EXPECTED_VOCAB},
            EXPECTED_VOCAB,
        )
        self.assertEqual({key: summary["length"][key] for key in EXPECTED_LENGTH}, EXPECTED_LENGTH)
        self.assertEqual(
            {key: summary["ambiguity"][key] for key in EXPECTED_AMBIGUITY},
            EXPECTED_AMBIGUITY,
        )
        for genre in REQUIRED_GENRES:
            self.assertGreaterEqual(summary["genre"][genre], 2)

    def test_length_summary_recomputes_from_query_text(self):
        record = {
            "qid": "q01",
            "query": "one two three four five six seven eight nine",
            "tags": {
                "era": "2000-2015",
                "genre": ["drama"],
                "vocab_distance": "medium",
                "length": "short",
                "specificity": "medium",
                "ambiguity": "medium",
            },
            "notes": "",
        }
        summary = _diversity.summarize([record])
        self.assertEqual(summary["length"]["medium"], 1)
        self.assertEqual(summary["length"]["short"], 0)

    def test_same_seed_produces_byte_identical_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.jsonl"
            second = Path(tmp) / "second.jsonl"
            generate_queries.main(["--seed", "17", "--out", str(first)])
            generate_queries.main(["--seed", "17", "--out", str(second)])
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_out_override_writes_requested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "custom" / "queries.jsonl"
            generate_queries.main(["--out", str(out)])
            self.assertTrue(out.is_file())
            records = load_jsonl(out)
            self.assertEqual(len(records), 20)
            for record in records:
                _schemas.validate_query_record(record)

    def test_summarize_file_matches_summarize(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "queries.jsonl"
            generate_queries.main(["--seed", "42", "--out", str(out)])
            records = load_jsonl(out)
            self.assertEqual(_diversity.summarize_file(out), _diversity.summarize(records))


if __name__ == "__main__":
    unittest.main()
