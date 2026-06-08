import json
import math
import random
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from eval.tests import conftest as _conftest
from eval.scripts import _run_io, compute_metrics


def _candidate(qid, tmdb_id, per_mode):
    return {"qid": qid, "tmdb_id": tmdb_id, "per_mode": per_mode}


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


def _query_record(qid):
    return {
        "qid": qid,
        "query": f"synthetic query {qid}",
        "tags": {
            "era": "2015+",
            "genre": ["drama"],
            "vocab_distance": "low",
            "length": "short",
            "specificity": "low",
            "ambiguity": "low",
        },
        "notes": "Synthetic.",
    }


def _query_records(*qids):
    return {qid: _query_record(qid) for qid in qids}


def _labels(*rows):
    return {(qid, tmdb_id): grade for qid, tmdb_id, grade in rows}


def _write_jsonl(path, rows):
    text = "\n".join(json.dumps(row, ensure_ascii=True) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


@contextmanager
def _temporary_run(candidates, labels, queries):
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
            queries_dir = _run_io.EVAL_DIR / "queries"
            queries_dir.mkdir(parents=True)
            _write_jsonl(queries_dir / "v1.jsonl", queries)

            manifest = {
                "run_id": run_id,
                "git_sha": None,
                "git_dirty": None,
                "git_mode": "no_git",
                "dataset_row_count": len(queries),
                "chroma_collection_count": len(queries),
                "embedding_model": "BAAI/bge-m3",
                "reranker_model": "BAAI/bge-reranker-v2-m3",
                "llm_model": "llama3.2",
                "rng_seed": 42,
                "warnings": [],
                "timestamps": {
                    "start": "2026-05-19T12:00:00Z",
                    "candidates_done": "2026-05-19T12:01:00Z",
                    "silver_done": "2026-05-19T12:02:00Z",
                    "provisional_metrics_done": None,
                },
            }
            (run_dir / "run_manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            _write_jsonl(run_dir / "candidates.jsonl", candidates)
            _write_jsonl(run_dir / "silver_labels.jsonl", labels)
            yield run_id, run_dir
        finally:
            _run_io.PROJECT_ROOT = old_project_root
            _run_io.EVAL_DIR = old_eval_dir
            _run_io.RUNS_DIR = old_runs_dir


def _e2e_fixture():
    candidates = [
        _full_candidate(
            "q01",
            601,
            {
                "basic": {"rank": 0},
                "advanced": {"rank": 0},
                "hybrid": {"rank": 0},
            },
        ),
        _full_candidate(
            "q01",
            602,
            {
                "basic": {"rank": 9},
                "advanced": {"rank": 9},
                "hybrid": {"rank": 9},
            },
        ),
        _full_candidate(
            "q01",
            603,
            {
                "basic": {"rank": 14},
                "advanced": {"rank": 14},
                "hybrid": {"rank": 14},
            },
        ),
    ]
    labels = [
        _silver("q01", 601, 3),
        _silver("q01", 602, 1),
        _silver("q01", 603, 0),
    ]
    queries = [_query_record("q01")]
    return candidates, labels, queries


class ComputeMetricsFormulaTest(unittest.TestCase):
    def test_rank_storage_to_one_based(self):
        candidates = [
            _candidate("q01", 101, {"basic": {"rank": 0}}),
            _candidate("q01", 102, {"basic": {"rank": 1}}),
            _candidate("q01", 103, {"basic": {"rank": 4}}),
        ]
        labels = _labels(
            ("q01", 101, 0),
            ("q01", 102, 1),
            ("q01", 103, 2),
        )

        top5 = compute_metrics._top5_for_mode(candidates, "basic", labels)
        self.assertEqual([row["rank"] for row in top5], [1, 2, 5])

        metrics = compute_metrics._query_mode_metrics(
            candidates,
            "basic",
            labels,
            ideal_dcg=1.0,
        )
        self.assertAlmostEqual(metrics["mrr_at_5"], 1.0 / 5.0)

    def test_hit_at_5_computes_through_later_null(self):
        """Hit@5 itself is defined through a later null; the output null
        counter is a separate one-per-query aggregate across all metrics."""

        candidates = [
            _candidate("q01", 201, {"basic": {"rank": 0}}),
            _candidate("q01", 202, {"basic": {"rank": 1}}),
            _candidate("q01", 203, {"basic": {"rank": 2}}),
        ]
        labels = _labels(("q01", 201, 3), ("q01", 203, 0))
        top5 = compute_metrics._top5_for_mode(candidates, "basic", labels)

        hit, excluded = compute_metrics._hit_at_k(
            top5, lambda grade: grade >= 2
        )
        self.assertEqual(hit, 1.0)
        self.assertFalse(excluded)

    def test_hit_at_5_excluded_when_no_known_relevant_and_a_null(self):
        """queries_excluded_null counts a query once when any null-sensitive
        metric is excluded for that mode, even if several K values exclude."""

        candidates = [
            _candidate("q01", 301, {"basic": {"rank": 0}}),
            _candidate("q01", 302, {"basic": {"rank": 1}}),
            _candidate("q01", 303, {"basic": {"rank": 2}}),
        ]
        labels = [_silver("q01", 301, 0), _silver("q01", 303, 1)]
        per_query = compute_metrics._query_mode_metrics(
            candidates,
            "basic",
            compute_metrics._label_map(labels),
            ideal_dcg=1.0,
        )
        self.assertIsNone(per_query["hit_at_5"])
        self.assertTrue(per_query["hit_excluded_null_at_5"])

        metrics = compute_metrics.compute_metrics(
            run_id="synthetic-run",
            candidates=candidates,
            silver_labels=labels,
            query_records=_query_records("q01"),
            bootstrap_b=10,
            seed=7,
        )
        self.assertEqual(metrics["by_mode"]["basic"]["queries_excluded_null"], 1)

    def test_mrr_at_5_computes_when_relevant_before_null(self):
        candidates = [
            _candidate("q01", 401, {"basic": {"rank": 0}}),
            _candidate("q01", 402, {"basic": {"rank": 1}}),
        ]
        labels = _labels(("q01", 401, 2))
        metrics = compute_metrics._query_mode_metrics(
            candidates,
            "basic",
            labels,
            ideal_dcg=1.0,
        )
        self.assertAlmostEqual(metrics["mrr_at_5"], 1.0)
        self.assertFalse(metrics["mrr_excluded_null_at_5"])

    def test_mrr_at_5_excluded_when_null_before_first_known_relevant(self):
        candidates = [
            _candidate("q01", 501, {"basic": {"rank": 0}}),
            _candidate("q01", 502, {"basic": {"rank": 1}}),
        ]
        labels = _labels(("q01", 502, 3))
        metrics = compute_metrics._query_mode_metrics(
            candidates,
            "basic",
            labels,
            ideal_dcg=1.0,
        )
        self.assertIsNone(metrics["mrr_at_5"])
        self.assertTrue(metrics["mrr_excluded_null_at_5"])

    def test_strict_variants_follow_same_null_rule(self):
        candidates = [
            _candidate("q01", 601, {"basic": {"rank": 0}}),
            _candidate("q01", 602, {"basic": {"rank": 1}}),
        ]
        grade2_before_null = compute_metrics._query_mode_metrics(
            candidates,
            "basic",
            _labels(("q01", 601, 2)),
            ideal_dcg=1.0,
        )
        self.assertEqual(grade2_before_null["hit_at_5"], 1.0)
        self.assertIsNone(grade2_before_null["strict_hit_at_5"])
        self.assertTrue(grade2_before_null["strict_hit_excluded_null_at_5"])

        grade3_before_null = compute_metrics._query_mode_metrics(
            candidates,
            "basic",
            _labels(("q01", 601, 3)),
            ideal_dcg=1.0,
        )
        self.assertEqual(grade3_before_null["strict_hit_at_5"], 1.0)
        self.assertAlmostEqual(grade3_before_null["strict_mrr_at_5"], 1.0)

        null_before_grade3 = compute_metrics._query_mode_metrics(
            candidates,
            "basic",
            _labels(("q01", 602, 3)),
            ideal_dcg=1.0,
        )
        self.assertIsNone(null_before_grade3["strict_mrr_at_5"])
        self.assertTrue(null_before_grade3["strict_mrr_excluded_null_at_5"])

    def test_ndcg_at_5_strict_null_exclusion(self):
        candidates = [
            _candidate("q01", 701, {"basic": {"rank": 0}}),
            _candidate("q01", 702, {"basic": {"rank": 1}}),
            _candidate("q01", 703, {"advanced": {"rank": 0}}),
        ]
        labels = _labels(("q01", 701, 2), ("q01", 703, 3))

        ideal = compute_metrics._ideal_dcg_for_query(candidates, labels, k=5)
        expected_ideal = 1.0 / math.log2(2) + 0.7 / math.log2(3)
        self.assertAlmostEqual(ideal, expected_ideal)

        metrics = compute_metrics._query_mode_metrics(
            candidates,
            "basic",
            labels,
            ideal_dcg={5: ideal, 10: ideal, 15: ideal},
        )
        self.assertIsNone(metrics["ndcg_at_5"])
        self.assertTrue(metrics["ndcg_excluded_null_at_5"])

    def test_dcg_with_exact_log2_denominators(self):
        rows = [
            {"rank": 1, "grade": 3},
            {"rank": 2, "grade": 2},
            {"rank": 3, "grade": 1},
            {"rank": 4, "grade": 0},
            {"rank": 5, "grade": 3},
        ]
        expected = (
            1.0 / math.log2(2)
            + 0.7 / math.log2(3)
            + 0.3 / math.log2(4)
            + 0.0 / math.log2(5)
            + 1.0 / math.log2(6)
        )
        self.assertAlmostEqual(compute_metrics._dcg_at_5(rows), expected)

    def test_at_10_and_at_15_present_in_by_mode(self):
        candidates, labels, queries = _e2e_fixture()
        with _temporary_run(candidates, labels, queries) as (run_id, _run_dir):
            _actual_run_id, _metrics_path, data = compute_metrics.run(
                run_id=run_id,
                bootstrap_b=10,
                seed=7,
            )

        basic = data["by_mode"]["basic"]
        for key in (
            "hit_at_10",
            "mrr_at_10",
            "ndcg_at_10",
            "hit_at_15",
            "mrr_at_15",
            "ndcg_at_15",
        ):
            self.assertIn(key, basic)
        for key in (
            "hit_at_5",
            "mrr_at_5",
            "ndcg_at_5",
            "hit_at_10",
            "mrr_at_10",
            "ndcg_at_10",
            "hit_at_15",
            "mrr_at_15",
            "ndcg_at_15",
        ):
            self.assertIn(key, basic["ci_half_widths"])

    def test_no_at_20(self):
        candidates, labels, queries = _e2e_fixture()
        data = compute_metrics.compute_metrics(
            run_id="synthetic-run",
            candidates=candidates,
            silver_labels=labels,
            query_records={query["qid"]: query for query in queries},
            bootstrap_b=10,
            seed=7,
        )
        for mode_data in data["by_mode"].values():
            for key in mode_data:
                self.assertFalse(key.endswith("_at_20"), key)
            for key in mode_data["ci_half_widths"]:
                self.assertFalse(key.endswith("_at_20"), key)

    def test_axis_has_hit_at_5_hit_at_10_hit_at_15(self):
        candidates, labels, queries = _e2e_fixture()
        with _temporary_run(candidates, labels, queries) as (run_id, _run_dir):
            _actual_run_id, _metrics_path, data = compute_metrics.run(
                run_id=run_id,
                bootstrap_b=10,
                seed=7,
            )

        entry = data["by_axis"]["vocab_distance"]["low"]["by_mode"]["basic"]
        self.assertIn("hit_at_5", entry)
        self.assertIn("hit_at_10", entry)
        self.assertIn("hit_at_15", entry)
        self.assertIn("n", entry)

    def test_bucket_qids_mood_null_goes_to_none(self):
        records = {"q01": {"tags": {"mood": None}}}

        buckets = compute_metrics._bucket_qids(["q01"], records, "mood_emotion")

        self.assertEqual(buckets, {"none": ["q01"]})

    def test_bucket_qids_mood_full_dict_correct_bucket(self):
        records = {
            "q01": {
                "tags": {
                    "mood": {
                        "current_emotion": "sad",
                        "desired_direction": "comfort_me",
                        "safety_sensitivity": "safe_hopeful",
                    }
                }
            }
        }

        self.assertEqual(
            compute_metrics._bucket_qids(["q01"], records, "mood_emotion"),
            {"sad": ["q01"]},
        )
        self.assertEqual(
            compute_metrics._bucket_qids(["q01"], records, "mood_direction"),
            {"comfort_me": ["q01"]},
        )
        self.assertEqual(
            compute_metrics._bucket_qids(["q01"], records, "mood_safety"),
            {"safe_hopeful": ["q01"]},
        )

    def test_bucket_qids_mood_missing_current_emotion(self):
        records = {
            "q01": {
                "tags": {
                    "mood": {
                        "desired_direction": "comfort_me",
                        "safety_sensitivity": "safe_hopeful",
                    }
                }
            }
        }

        buckets = compute_metrics._bucket_qids(["q01"], records, "mood_emotion")

        self.assertEqual(buckets, {"unknown": ["q01"]})

    def test_bucket_qids_mood_missing_desired_direction(self):
        records = {
            "q01": {
                "tags": {
                    "mood": {
                        "current_emotion": "sad",
                        "safety_sensitivity": "safe_hopeful",
                    }
                }
            }
        }

        buckets = compute_metrics._bucket_qids(["q01"], records, "mood_direction")

        self.assertEqual(buckets, {"unknown": ["q01"]})

    def test_bucket_qids_mood_missing_safety_sensitivity(self):
        records = {
            "q01": {
                "tags": {
                    "mood": {
                        "current_emotion": "sad",
                        "desired_direction": "comfort_me",
                    }
                }
            }
        }

        buckets = compute_metrics._bucket_qids(["q01"], records, "mood_safety")

        self.assertEqual(buckets, {"unknown": ["q01"]})

    def test_bucket_qids_mood_non_dict(self):
        records = {"q01": {"tags": {"mood": "sad"}}}

        buckets = compute_metrics._bucket_qids(["q01"], records, "mood_emotion")

        self.assertEqual(buckets, {"unknown": ["q01"]})

    def test_bucket_qids_mood_key_absent_from_tags(self):
        records = {"q01": {"tags": {}}}

        buckets = compute_metrics._bucket_qids(["q01"], records, "mood_emotion")

        self.assertEqual(buckets, {"none": ["q01"]})

    def test_bucket_qids_genre_multi_bucket_unchanged(self):
        records = {
            "q01": {"tags": {"genre": ["drama", "thriller"]}},
            "q02": {"tags": {"genre": ["drama"]}},
        }

        buckets = compute_metrics._bucket_qids(["q02", "q01"], records, "genre")

        self.assertEqual(
            buckets,
            {"drama": ["q01", "q02"], "thriller": ["q01"]},
        )

    def test_bucket_qids_non_mood_axes_unchanged(self):
        records = {
            "q01": {"tags": {"length": "short"}},
            "q02": {"tags": {"length": "long"}},
        }

        buckets = compute_metrics._bucket_qids(["q02", "q01"], records, "length")

        self.assertEqual(buckets, {"short": ["q01"], "long": ["q02"]})

    def test_provisional_flag_and_no_metrics_json(self):
        candidates, labels, queries = _e2e_fixture()
        with _temporary_run(candidates, labels, queries) as (run_id, run_dir):
            exit_code = compute_metrics.main(
                ["--run", run_id, "--bootstrap-b", "10", "--seed", "7"]
            )
            self.assertEqual(exit_code, 0)

            provisional_path = run_dir / "metrics_provisional.json"
            self.assertTrue(provisional_path.exists())
            self.assertFalse((run_dir / "metrics.json").exists())
            self.assertFalse((_run_io.RUNS_DIR / "current_run.txt").exists())

            with provisional_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertIs(data["provisional"], True)
            self.assertEqual(data["run_id"], run_id)

    def test_bootstrap_ci_shrinks_with_variance(self):
        zero_variance = compute_metrics._bootstrap_half_width(
            [1.0] * 20,
            b=200,
            rng=random.Random(11),
        )
        high_variance = compute_metrics._bootstrap_half_width(
            [0.0, 1.0] * 10,
            b=200,
            rng=random.Random(11),
        )
        self.assertLess(zero_variance, high_variance)


if __name__ == "__main__":
    unittest.main()
