import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from eval.scripts import _run_io, error_report


def _full_candidate(qid, tmdb_id, per_mode):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "movie_key": f"title:movie {tmdb_id}|year:2000",
        "title": f"Movie {tmdb_id}",
        "year": 2000,
        "overview": "Synthetic overview.",
        "genres": "Drama",
        "keywords": "synthetic",
        "tagline": "",
        "per_mode": per_mode,
        "in_top_k_of": list(per_mode),
        "source": "union",
    }


def _silver(qid, tmdb_id, grade):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "confidence": "low" if grade is None else "high",
        "reason": "Synthetic label.",
        "model": "test-model",
        "ts": "2026-05-19T12:00:00Z",
    }


def _gold(
    qid,
    tmdb_id,
    grade,
    *,
    silver_grade=None,
    gold_grade=None,
    label_source="gold",
):
    if silver_grade is None:
        silver_grade = grade
    if label_source == "gold" and gold_grade is None:
        gold_grade = grade
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "label_source": label_source,
        "label_provenance": (
            "human_reviewed_ai_assisted"
            if label_source == "gold"
            else "silver_llm_pregrade"
        ),
        "silver_grade": silver_grade,
        "gold_grade": gold_grade,
        "gold_notes": None,
    }


def _gold_from_silver(labels, overrides=None):
    overrides = overrides or {}
    rows = []
    for label in labels:
        key = (label["qid"], label["tmdb_id"])
        if key in overrides:
            rows.append(
                _gold(
                    label["qid"],
                    label["tmdb_id"],
                    overrides[key],
                    silver_grade=label["grade"],
                    gold_grade=overrides[key],
                    label_source="gold",
                )
            )
        else:
            rows.append(
                _gold(
                    label["qid"],
                    label["tmdb_id"],
                    label["grade"],
                    silver_grade=label["grade"],
                    gold_grade=None,
                    label_source="silver",
                )
            )
    return rows


def _write_jsonl(path, rows):
    text = "\n".join(json.dumps(row, ensure_ascii=True) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


@contextmanager
def _temporary_run(candidates, labels, gold_labels=None):
    old_project_root = _run_io.PROJECT_ROOT
    old_eval_dir = _run_io.EVAL_DIR
    old_runs_dir = _run_io.RUNS_DIR

    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp)
        _run_io.PROJECT_ROOT = project_root
        _run_io.EVAL_DIR = project_root / "eval"
        _run_io.RUNS_DIR = _run_io.EVAL_DIR / "runs"
        try:
            run_id = "2026-05-19-1200-nogit"
            run_dir = _run_io.ensure_run_dir(run_id)
            _write_jsonl(run_dir / "candidates.jsonl", candidates)
            _write_jsonl(run_dir / "silver_labels.jsonl", labels)
            if gold_labels is not None:
                _write_jsonl(run_dir / "gold_labels.jsonl", gold_labels)
            yield run_id, run_dir
        finally:
            _run_io.PROJECT_ROOT = old_project_root
            _run_io.EVAL_DIR = old_eval_dir
            _run_io.RUNS_DIR = old_runs_dir


def _fixture():
    candidates = [
        _full_candidate(
            "q_a",
            101,
            {
                "basic": {"rank": 0},
                "advanced": {"rank": 0},
                "hybrid": {"rank": 0},
            },
        ),
        _full_candidate(
            "q_a",
            102,
            {
                "basic": {"rank": 1},
                "advanced": {"rank": 1},
                "hybrid": {"rank": 1},
            },
        ),
        _full_candidate(
            "q_a",
            103,
            {
                "basic": {"rank": 2},
                "advanced": {"rank": 2},
                "hybrid": {"rank": 2},
            },
        ),
        _full_candidate(
            "q_b",
            201,
            {
                "basic": {"rank": 0},
                "advanced": {"rank": 0},
                "hybrid": {"rank": 6},
            },
        ),
        _full_candidate(
            "q_b",
            202,
            {
                "basic": {"rank": 1},
                "advanced": {"rank": 1},
                "hybrid": {"rank": 0},
            },
        ),
        _full_candidate(
            "q_b",
            203,
            {
                "basic": {"rank": 2},
                "advanced": {"rank": 2},
                "hybrid": {"rank": 1},
            },
        ),
        _full_candidate(
            "q_c",
            301,
            {
                "basic": {"rank": 0},
                "advanced": {"rank": 0},
                "hybrid": {"rank": 0},
            },
        ),
        _full_candidate(
            "q_c",
            302,
            {
                "basic": {"rank": 1},
                "advanced": {"rank": 1},
                "hybrid": {"rank": 1},
            },
        ),
        _full_candidate(
            "q_c",
            303,
            {
                "basic": {"rank": 2},
                "advanced": {"rank": 2},
                "hybrid": {"rank": 2},
            },
        ),
    ]
    labels = [
        _silver("q_a", 101, 0),
        _silver("q_a", 102, 1),
        _silver("q_a", 103, 0),
        _silver("q_b", 201, 2),
        _silver("q_b", 202, 0),
        _silver("q_b", 203, 1),
        _silver("q_c", 301, 1),
        _silver("q_c", 302, 1),
        _silver("q_c", 303, 2),
    ]
    return candidates, labels


def _records_by_qid_mode(records):
    return {(record["qid"], record["mode"]): record for record in records}


class ErrorReportTest(unittest.TestCase):
    def _run_fixture(self):
        candidates, labels = _fixture()
        with _temporary_run(candidates, labels) as (run_id, _run_dir):
            _actual, per_query_path, _summary_path, summary = error_report.run(
                run_id=run_id,
                k=5,
            )
            records = [
                json.loads(line)
                for line in per_query_path.read_text(encoding="utf-8").splitlines()
            ]
            return records, summary

    def test_per_query_mode_record_shape(self):
        records, _summary = self._run_fixture()

        expected_record_keys = {
            "qid",
            "mode",
            "k",
            "top",
            "hit_at_k",
            "strict_hit_at_k",
            "first_relevant_rank",
            "first_perfect_rank",
            "null_grades_in_top_k",
        }
        expected_top_keys = {
            "rank",
            "tmdb_id",
            "title",
            "year",
            "grade",
            "confidence",
        }

        self.assertEqual(len(records), 9)
        for record in records:
            self.assertEqual(set(record), expected_record_keys)
            for top_row in record["top"]:
                self.assertEqual(set(top_row), expected_top_keys)

    def test_first_relevant_rank_uses_grade_ge_2(self):
        records, _summary = self._run_fixture()
        by_qid_mode = _records_by_qid_mode(records)

        record = by_qid_mode[("q_c", "basic")]
        self.assertEqual(record["first_relevant_rank"], 3)
        self.assertIsNone(record["first_perfect_rank"])

    def test_summary_hybrid_only_miss_qids(self):
        _records, summary = self._run_fixture()

        self.assertEqual(summary["hybrid_only_miss_qids"], ["q_b"])

    def test_summary_all_modes_miss_qids(self):
        _records, summary = self._run_fixture()

        self.assertEqual(summary["all_modes_miss_qids"], ["q_a"])

    def test_cli_rejects_invalid_k(self):
        stderr = io.StringIO()

        with self.assertRaises(SystemExit) as raised:
            with redirect_stderr(stderr):
                error_report.main(["--run", "rid", "--k", "7"])

        self.assertNotEqual(raised.exception.code, 0)
        self.assertIn("--k", stderr.getvalue())

    def test_gold_mode_writes_gold_suffixed_artifacts(self):
        candidates, labels = _fixture()
        gold_labels = _gold_from_silver(labels)

        with _temporary_run(candidates, labels, gold_labels=gold_labels) as (
            run_id,
            run_dir,
        ):
            _actual, per_query_path, summary_path, summary = error_report.run(
                run_id=run_id,
                k=5,
                labels="gold",
            )

            self.assertEqual(per_query_path.name, "per_query_mode.gold.jsonl")
            self.assertEqual(summary_path.name, "summary.gold.json")
            self.assertTrue(per_query_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertFalse(
                (run_dir / "analysis" / "error_report" / "per_query_mode.jsonl").exists()
            )
            self.assertFalse(
                (run_dir / "analysis" / "error_report" / "summary.json").exists()
            )
            self.assertEqual(summary["label_source"], "merged_gold_over_silver")

    def test_gold_mode_missing_gold_labels_exits_nonzero(self):
        candidates, labels = _fixture()
        stderr = io.StringIO()

        with _temporary_run(candidates, labels) as (run_id, run_dir):
            with redirect_stderr(stderr):
                exit_code = error_report.main(["--run", run_id, "--labels", "gold"])

            output_dir = run_dir / "analysis" / "error_report"
            self.assertNotEqual(exit_code, 0)
            self.assertIn("gold_labels.jsonl", stderr.getvalue())
            self.assertFalse((output_dir / "per_query_mode.gold.jsonl").exists())
            self.assertFalse((output_dir / "summary.gold.json").exists())

    def test_gold_grade_overrides_silver_in_miss_lists(self):
        candidates, labels = _fixture()
        gold_labels = _gold_from_silver(labels, {("q_a", 101): 3})

        with _temporary_run(candidates, labels, gold_labels=gold_labels) as (
            run_id,
            _run_dir,
        ):
            _actual, _per_query_path, _summary_path, silver_summary = (
                error_report.run(run_id=run_id, k=5)
            )
            _actual, _per_query_path, _summary_path, gold_summary = error_report.run(
                run_id=run_id,
                k=5,
                labels="gold",
            )

            silver_misses = silver_summary["by_mode"]["basic"]["strict_miss_qids"]
            gold_misses = gold_summary["by_mode"]["basic"]["strict_miss_qids"]
            self.assertIn("q_a", silver_misses)
            self.assertNotIn("q_a", gold_misses)
            self.assertNotEqual(silver_misses, gold_misses)

    def test_summary_envelope_records_label_source(self):
        candidates, labels = _fixture()
        gold_labels = _gold_from_silver(labels)

        with _temporary_run(candidates, labels, gold_labels=gold_labels) as (
            run_id,
            _run_dir,
        ):
            _actual, _per_query_path, _summary_path, silver_summary = (
                error_report.run(run_id=run_id, k=5)
            )
            _actual, _per_query_path, _summary_path, gold_summary = error_report.run(
                run_id=run_id,
                k=5,
                labels="gold",
            )

            self.assertEqual(silver_summary["label_source"], "silver")
            self.assertEqual(silver_summary["labels_file"], "silver_labels.jsonl")
            self.assertEqual(gold_summary["label_source"], "merged_gold_over_silver")
            self.assertEqual(gold_summary["labels_file"], "gold_labels.jsonl")

    def test_gold_mode_confidence_comes_from_silver(self):
        candidates, labels = _fixture()
        gold_labels = _gold_from_silver(labels, {("q_a", 101): 3})

        with _temporary_run(candidates, labels, gold_labels=gold_labels) as (
            run_id,
            _run_dir,
        ):
            _actual, per_query_path, _summary_path, _summary = error_report.run(
                run_id=run_id,
                k=5,
                labels="gold",
            )
            records = [
                json.loads(line)
                for line in per_query_path.read_text(encoding="utf-8").splitlines()
            ]
            top_rows = _records_by_qid_mode(records)[("q_a", "basic")]["top"]
            overridden = next(row for row in top_rows if row["tmdb_id"] == 101)

            self.assertEqual(overridden["grade"], 3)
            self.assertEqual(overridden["confidence"], "high")

    def test_silver_mode_per_query_schema_unchanged(self):
        records, _summary = self._run_fixture()
        expected_top_keys = ("rank", "tmdb_id", "title", "year", "grade", "confidence")

        for record in records:
            self.assertEqual(tuple(record), error_report._REPORT_KEYS)
            for top_row in record["top"]:
                self.assertEqual(tuple(top_row), expected_top_keys)


if __name__ == "__main__":
    unittest.main()
