import json
import tempfile
import unittest
from pathlib import Path

from eval.scripts import _run_io, phase8_regression_attribution as attribution


def _candidate(qid, tmdb_id, rank, *, mode="basic", score=None):
    mode_data = {"rank": rank}
    if score is not None:
        mode_data["final_score"] = score
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
        "per_mode": {mode: mode_data},
        "in_top_k_of": [mode],
        "source": "union",
    }


def _silver(qid, tmdb_id, grade):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "confidence": "low" if grade is None else "high",
        "reason": "Synthetic.",
        "model": "test-model",
        "ts": "2026-05-19T12:00:00Z",
    }


def _gold(qid, tmdb_id, grade):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "label_source": "gold" if grade is not None else "silver",
        "silver_grade": grade,
        "gold_grade": grade,
        "gold_notes": None,
    }


def _full_modes(qid, tmdb_id, rank, *, score=1.0):
    row = _candidate(qid, tmdb_id, rank, mode="basic", score=score)
    row["per_mode"]["advanced"] = {"rank": rank, "final_score": score}
    row["per_mode"]["hybrid"] = {"rank": rank, "final_score": score}
    row["in_top_k_of"] = ["basic", "advanced", "hybrid"]
    return row


class Phase8RegressionAttributionTest(unittest.TestCase):
    def test_label_only_classification(self):
        baseline = [_full_modes("q01", 101, 0)]
        candidate = [_full_modes("q01", 101, 0)]
        data, _queue = attribution.build_attribution(
            baseline_run="base",
            candidate_run="cand",
            qids=["q01"],
            baseline_candidates=baseline,
            candidate_candidates=candidate,
            baseline_silver_rows=[_silver("q01", 101, 2)],
            candidate_silver_rows=[_silver("q01", 101, 1)],
            baseline_gold_rows=[_gold("q01", 101, 2)],
        )

        self.assertEqual(
            data["by_qid"]["q01"]["by_mode"]["basic"]["classification"],
            "label_only",
        )

    def test_candidate_only_classification_and_rank_changes(self):
        baseline = [_full_modes("q02", 101, 0), _full_modes("q02", 102, 1)]
        candidate = [_full_modes("q02", 102, 0), _full_modes("q02", 101, 1)]
        labels = [_silver("q02", 101, 0), _silver("q02", 102, 2)]
        gold = [_gold("q02", 101, 0), _gold("q02", 102, 2)]

        data, _queue = attribution.build_attribution(
            baseline_run="base",
            candidate_run="cand",
            qids=["q02"],
            baseline_candidates=baseline,
            candidate_candidates=candidate,
            baseline_silver_rows=labels,
            candidate_silver_rows=labels,
            baseline_gold_rows=gold,
        )
        record = data["by_qid"]["q02"]["by_mode"]["basic"]

        self.assertEqual(record["classification"], "candidate_only")
        self.assertEqual(
            record["rank_changes"],
            [
                {"tmdb_id": 101, "baseline_rank": 1, "candidate_rank": 2, "delta": 1},
                {"tmdb_id": 102, "baseline_rank": 2, "candidate_rank": 1, "delta": -1},
            ],
        )

    def test_mixed_classification_for_candidate_and_relevant_label_drift(self):
        baseline = [_full_modes("q03", 101, 0), _full_modes("q03", 102, 1)]
        candidate = [_full_modes("q03", 101, 1), _full_modes("q03", 103, 0)]

        data, _queue = attribution.build_attribution(
            baseline_run="base",
            candidate_run="cand",
            qids=["q03"],
            baseline_candidates=baseline,
            candidate_candidates=candidate,
            baseline_silver_rows=[
                _silver("q03", 101, 2),
                _silver("q03", 102, 0),
                _silver("q03", 103, 1),
            ],
            candidate_silver_rows=[
                _silver("q03", 101, 1),
                _silver("q03", 102, 0),
                _silver("q03", 103, 1),
            ],
            baseline_gold_rows=[
                _gold("q03", 101, 2),
                _gold("q03", 102, 0),
                _gold("q03", 103, 1),
            ],
        )

        self.assertEqual(
            data["by_qid"]["q03"]["by_mode"]["basic"]["classification"],
            "mixed",
        )

    def test_insufficient_labels_for_missing_frozen_label(self):
        baseline = [_full_modes("q04", 101, 0)]
        candidate = [_full_modes("q04", 102, 0)]

        data, queue = attribution.build_attribution(
            baseline_run="base",
            candidate_run="cand",
            qids=["q04"],
            baseline_candidates=baseline,
            candidate_candidates=candidate,
            baseline_silver_rows=[_silver("q04", 101, 0)],
            candidate_silver_rows=[_silver("q04", 102, 2)],
            baseline_gold_rows=[_gold("q04", 101, 0)],
        )
        record = data["by_qid"]["q04"]["by_mode"]["basic"]

        self.assertEqual(record["classification"], "insufficient_labels")
        self.assertEqual(record["hit_status"]["frozen_baseline_labels"]["missing"], [{"qid": "q04", "tmdb_id": 102}])
        self.assertEqual(queue[0]["label_provenance"], "ai_draft")
        self.assertEqual(queue[0]["review_status"], "pending_human")

    def test_score_order_reconstruction_reports_rank_difference(self):
        rows = [
            _candidate("q05", 101, 0, mode="advanced", score=0.10),
            _candidate("q05", 102, 1, mode="advanced", score=0.30),
        ]

        result = attribution._score_order(rows, "advanced")

        self.assertTrue(result["stored_rank_differs_from_score_rank"])
        self.assertEqual([row["tmdb_id"] for row in result["top_five"]], [102, 101])

    def test_run_writes_stable_outputs(self):
        old_runs_dir = _run_io.RUNS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _run_io.RUNS_DIR = root / "eval" / "runs"
            baseline_dir = _run_io.ensure_run_dir("base")
            candidate_dir = _run_io.ensure_run_dir("cand")
            query_path = root / "queries.jsonl"
            query_path.write_text('{"qid":"q01","query":"x"}\n', encoding="utf-8")
            candidate = _full_modes("q01", 101, 0)
            for path in (baseline_dir, candidate_dir):
                (path / "candidates.jsonl").write_text(
                    json.dumps(candidate) + "\n",
                    encoding="utf-8",
                )
            (baseline_dir / "silver_labels.jsonl").write_text(
                json.dumps(_silver("q01", 101, 2)) + "\n",
                encoding="utf-8",
            )
            (candidate_dir / "silver_labels.jsonl").write_text(
                json.dumps(_silver("q01", 101, 1)) + "\n",
                encoding="utf-8",
            )
            (baseline_dir / "gold_labels.jsonl").write_text(
                json.dumps(_gold("q01", 101, 2)) + "\n",
                encoding="utf-8",
            )
            try:
                json_path, markdown_path, queue_path, data = attribution.run(
                    baseline_run="base",
                    candidate_run="cand",
                    queries_path=query_path,
                    qids=["q01"],
                    output_dir=root / "out",
                )
            finally:
                _run_io.RUNS_DIR = old_runs_dir

            self.assertEqual(
                list(data["by_qid"]["q01"]["by_mode"]),
                ["basic", "advanced", "hybrid"],
            )
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertTrue(queue_path.exists())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["by_qid"]["q01"]["by_mode"]["basic"]["classification"], "label_only")


if __name__ == "__main__":
    unittest.main()
