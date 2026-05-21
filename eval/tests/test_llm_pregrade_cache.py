import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from eval.scripts import _run_io, _schemas
from eval.scripts import llm_pregrade


VALID_REPLY = json.dumps(
    {
        "grade": 2,
        "confidence": "high",
        "reason": "Metadata clearly matches the query.",
    }
)


def _candidate(qid="q01", tmdb_id=100, title=None):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "movie_key": f"title:movie-{tmdb_id}|year:2000",
        "title": title or f"Movie {tmdb_id}",
        "year": 2000,
        "overview": "A test movie overview.",
        "genres": "Drama",
        "keywords": "test",
        "tagline": "",
        "per_mode": {"basic": {"rank": 0, "final_score": 0.5}},
        "in_top_k_of": ["basic"],
        "source": "union",
    }


def _query(qid="q01"):
    return {
        "qid": qid,
        "query": f"query text for {qid}",
        "tags": {
            "era": "2000-2015",
            "genre": ["drama"],
            "vocab_distance": "low",
            "length": "short",
            "specificity": "medium",
            "ambiguity": "medium",
        },
        "notes": "",
    }


def _silver(qid="q01", tmdb_id=100, grade=2, confidence="high"):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "confidence": confidence,
        "reason": "cached row",
        "model": "llama3.2",
        "ts": "2026-05-19T15:30:42Z",
    }


class LlmPregradeCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.old_project_root = _run_io.PROJECT_ROOT
        self.old_eval_dir = _run_io.EVAL_DIR
        self.old_runs_dir = _run_io.RUNS_DIR
        _run_io.PROJECT_ROOT = self.project_root
        _run_io.EVAL_DIR = self.project_root / "eval"
        _run_io.RUNS_DIR = _run_io.EVAL_DIR / "runs"
        self.run_id = "2026-05-19-1530-nogit"
        _run_io.ensure_run_dir(self.run_id)
        _run_io.write_manifest(self.run_id)

    def tearDown(self):
        _run_io.PROJECT_ROOT = self.old_project_root
        _run_io.EVAL_DIR = self.old_eval_dir
        _run_io.RUNS_DIR = self.old_runs_dir
        self._tmp.cleanup()

    @property
    def run_dir(self):
        return _run_io.run_dir(self.run_id)

    def write_queries(self, qids):
        path = _run_io.EVAL_DIR / "queries" / "v1.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for qid in qids:
                handle.write(json.dumps(_query(qid), ensure_ascii=True) + "\n")

    def write_candidates(self, records):
        path = self.run_dir / "candidates.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                _schemas.validate_candidate_record(record)
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    def write_silver(self, records):
        path = self.run_dir / "silver_labels.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                _schemas.validate_silver_record(record)
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    def read_manifest(self):
        with (self.run_dir / "run_manifest.json").open(
            "r", encoding="utf-8"
        ) as handle:
            return json.load(handle)

    def read_silver_rows(self):
        path = self.run_dir / "silver_labels.jsonl"
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_cache_skips_existing_successful_rows(self):
        self.write_queries(["q01"])
        self.write_candidates([_candidate(tmdb_id=100), _candidate(tmdb_id=200)])
        self.write_silver([_silver(tmdb_id=100, grade=2, confidence="high")])
        llm = Mock(return_value=VALID_REPLY)

        llm_pregrade.run(run_id=self.run_id, llm_caller=llm)

        self.assertEqual(1, llm.call_count)

    def test_failure_rows_are_not_cached(self):
        self.write_queries(["q01"])
        self.write_candidates([_candidate(tmdb_id=100)])
        self.write_silver([_silver(tmdb_id=100, grade=None, confidence="low")])
        llm = Mock(return_value=VALID_REPLY)

        llm_pregrade.run(run_id=self.run_id, llm_caller=llm)

        self.assertEqual(1, llm.call_count)

    def test_json_parse_rate_gate_aborts_below_threshold(self):
        self.write_queries(["q01"])
        self.write_candidates([_candidate(tmdb_id=i) for i in range(1, 26)])
        replies = [
            "not json" if index in (0, 1) else VALID_REPLY
            for index in range(25)
        ]
        llm = Mock(side_effect=replies)

        exit_code = llm_pregrade.main(["--run", self.run_id], llm_caller=llm)

        manifest = self.read_manifest()
        self.assertEqual(2, exit_code)
        self.assertTrue(
            any(
                warning.startswith("llm_pregrade aborted: parse_rate=")
                for warning in manifest["warnings"]
            )
        )
        self.assertIsNone(manifest["timestamps"]["silver_done"])
        self.assertEqual(20, llm.call_count)

    def test_records_validate_against_schema(self):
        self.write_queries(["q01"])
        self.write_candidates([_candidate(tmdb_id=100), _candidate(tmdb_id=200)])
        llm = Mock(return_value=VALID_REPLY)

        llm_pregrade.run(run_id=self.run_id, llm_caller=llm)

        for row in self.read_silver_rows():
            _schemas.validate_silver_record(row)

    def test_silver_done_only_on_full_completion(self):
        self.write_queries(["q01"])
        self.write_candidates([_candidate(tmdb_id=i) for i in range(1, 21)])
        llm = Mock(return_value=VALID_REPLY)

        result = llm_pregrade.run(run_id=self.run_id, llm_caller=llm)

        manifest = self.read_manifest()
        self.assertEqual(0, result.exit_code)
        self.assertFalse(result.aborted)
        self.assertEqual(1.0, result.parse_rate)
        self.assertIsNotNone(manifest["timestamps"]["silver_done"])


if __name__ == "__main__":
    unittest.main()
