import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from eval.scripts import _run_io, compute_metrics, merge_labels


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _candidate_row(qid, tmdb_id, rank=0, modes=("basic", "advanced", "hybrid")):
    per_mode = {
        mode: {"rank": rank, "final_score": float(1000 - tmdb_id)}
        for mode in modes
    }
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "movie_key": f"title:movie {tmdb_id}|year:2001",
        "title": f"Movie {tmdb_id}",
        "year": 2001,
        "overview": f"Overview {qid} {tmdb_id}",
        "genres": "Drama",
        "keywords": "keyword",
        "tagline": "tagline",
        "per_mode": per_mode,
        "in_top_k_of": list(modes),
        "source": "union",
    }


def _silver_row(qid, tmdb_id, grade):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "confidence": "low" if grade is None else "high",
        "reason": f"Silver reason {qid} {tmdb_id}",
        "model": "fixture",
        "ts": "2026-05-20T00:00:00Z",
    }


def _regrade_row(qid, tmdb_id, silver_grade, gold_grade, notes="gold note"):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "query": f"{qid} query",
        "title": f"Movie {tmdb_id}",
        "year": 2001,
        "overview": f"Overview {qid} {tmdb_id}",
        "genres": "Drama",
        "silver_grade": silver_grade,
        "silver_confidence": "low" if silver_grade is None else "high",
        "silver_reason": f"Silver reason {qid} {tmdb_id}",
        "in_top_5_of": ["basic"],
        "flag_reasons": ["fixture"],
        "gold_grade": gold_grade,
        "gold_notes": notes,
        "label_provenance": "ai_draft",
        "batch": 1,
        "batch_purpose": "fixture",
    }


def _query_row(qid):
    return {
        "qid": qid,
        "query": f"{qid} query",
        "tags": {
            "era": "2015+",
            "genre": ["drama"],
            "vocab_distance": "low",
            "length": "short",
            "specificity": "low",
            "ambiguity": "low",
        },
        "notes": "fixture",
    }


class MergeLabelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_id = "2026-05-20-1400-nogit"
        self.eval_dir = self.root / "eval"
        self.run_dir = self.eval_dir / "runs" / self.run_id

        self._old_project_root = _run_io.PROJECT_ROOT
        self._old_eval_dir = _run_io.EVAL_DIR
        self._old_runs_dir = _run_io.RUNS_DIR
        self.addCleanup(self._restore_run_io)
        _run_io.PROJECT_ROOT = self.root
        _run_io.EVAL_DIR = self.eval_dir
        _run_io.RUNS_DIR = self.eval_dir / "runs"

    def _restore_run_io(self):
        _run_io.PROJECT_ROOT = self._old_project_root
        _run_io.EVAL_DIR = self._old_eval_dir
        _run_io.RUNS_DIR = self._old_runs_dir

    @property
    def regrade_dir(self):
        return self.run_dir / "analysis" / "regrade"

    @property
    def sheet_path(self):
        return self.regrade_dir / "regrade_sheet.jsonl"

    @property
    def check_path(self):
        return self.regrade_dir / "regrade_check.json"

    @property
    def manifest_path(self):
        return self.regrade_dir / "regrade_manifest.json"

    @property
    def gold_path(self):
        return self.run_dir / "gold_labels.jsonl"

    @property
    def metrics_path(self):
        return self.run_dir / "metrics.json"

    def _write_fixture(
        self,
        *,
        silver_rows=None,
        candidates=None,
        regrade_rows=None,
        query_rows=None,
        v1_query_rows=None,
        complete=True,
        stale_check=False,
    ):
        if silver_rows is None:
            silver_rows = [
                _silver_row("q01", 101, 1),
                _silver_row("q01", 102, 0),
                _silver_row("q02", 201, 2),
            ]
        if candidates is None:
            candidates = [
                _candidate_row("q01", 101, rank=0),
                _candidate_row("q01", 102, rank=1),
                _candidate_row("q02", 201, rank=0),
            ]
        if regrade_rows is None:
            regrade_rows = [_regrade_row("q01", 101, 1, 3)]
        if query_rows is None:
            query_rows = [_query_row("q01"), _query_row("q02"), _query_row("q03")]
        if v1_query_rows is None:
            v1_query_rows = query_rows

        _write_jsonl(self.run_dir / "silver_labels.jsonl", silver_rows)
        _write_jsonl(self.run_dir / "candidates.jsonl", candidates)
        _write_jsonl(self.eval_dir / "queries" / "v1.jsonl", v1_query_rows)
        _write_jsonl(self.eval_dir / "queries" / "all.jsonl", query_rows)
        _write_jsonl(self.sheet_path, regrade_rows)
        _write_json(
            self.manifest_path,
            {
                "run_id": self.run_id,
                "rows_total": len(regrade_rows),
            },
        )
        _write_json(
            self.check_path,
            {
                "run_id": self.run_id,
                "complete": complete,
                "rows_total": len(regrade_rows),
                "rows_filled": len(regrade_rows) if complete else 0,
            },
        )
        if stale_check:
            sheet_mtime = self.sheet_path.stat().st_mtime
            os.utime(self.check_path, (sheet_mtime - 10, sheet_mtime - 10))

    def _run_merge(self):
        return merge_labels.merge_labels(
            run_id=self.run_id,
            bootstrap_b=0,
            seed=7,
        )

    def _run_main(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = merge_labels.main(["--run", self.run_id])
        return code, stdout.getvalue(), stderr.getvalue()

    def _gold_rows(self):
        return [
            json.loads(line)
            for line in self.gold_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_gold_overrides_silver_for_regraded_pairs(self):
        self._write_fixture()

        self._run_merge()

        row = next(row for row in self._gold_rows() if row["tmdb_id"] == 101)
        self.assertEqual(row["grade"], 3)
        self.assertEqual(row["gold_grade"], 3)
        self.assertEqual(row["silver_grade"], 1)
        self.assertEqual(row["label_source"], "gold")
        self.assertEqual(row["label_provenance"], "ai_draft")

    def test_silver_passthrough_for_unregraded_pairs(self):
        self._write_fixture()

        self._run_merge()

        row = next(row for row in self._gold_rows() if row["tmdb_id"] == 102)
        self.assertEqual(row["grade"], 0)
        self.assertEqual(row["silver_grade"], 0)
        self.assertIsNone(row["gold_grade"])
        self.assertEqual(row["label_source"], "silver")
        self.assertEqual(row["label_provenance"], "silver_llm_pregrade")

    def test_gold_only_pair_absent_from_silver_is_added(self):
        self._write_fixture(
            regrade_rows=[
                _regrade_row("q01", 101, 1, 3),
                _regrade_row("q02", 999, None, 2, "gold only"),
            ]
        )

        self._run_merge()

        row = self._gold_rows()[-1]
        self.assertEqual((row["qid"], row["tmdb_id"]), ("q02", 999))
        self.assertEqual(row["grade"], 2)
        self.assertIsNone(row["silver_grade"])
        self.assertEqual(row["label_source"], "gold")
        self.assertEqual(row["label_provenance"], "ai_draft")

    def test_metrics_json_envelope(self):
        self._write_fixture()

        self._run_merge()

        metrics = json.loads(self.metrics_path.read_text(encoding="utf-8"))
        self.assertIs(metrics["provisional"], False)
        self.assertEqual(metrics["label_source"], "merged_gold_over_silver")
        self.assertEqual(
            metrics["label_provenance"],
            {
                "gold": 1,
                "silver": 2,
                "total": 3,
                "regraded_queries": ["q01"],
                "counts": {
                    "ai_draft": 1,
                    "silver_llm_pregrade": 2,
                },
            },
        )
        self.assertEqual(
            metrics["built_from"],
            {
                "silver_labels": "silver_labels.jsonl",
                "gold_labels": "gold_labels.jsonl",
                "regrade_sheet": "analysis/regrade/regrade_sheet.jsonl",
            },
        )

    def test_gold_grades_change_metrics(self):
        self._write_fixture()
        silver_rows = compute_metrics._load_silver_labels(self.run_dir / "silver_labels.jsonl")
        candidates = compute_metrics._load_candidates(self.run_dir / "candidates.jsonl")
        queries = compute_metrics._load_queries(self.eval_dir / "queries" / "all.jsonl")
        silver_only = compute_metrics.compute_metrics(
            run_id=self.run_id,
            candidates=candidates,
            silver_labels=silver_rows,
            query_records=queries,
            bootstrap_b=0,
            seed=7,
        )

        self._run_merge()

        merged = json.loads(self.metrics_path.read_text(encoding="utf-8"))
        self.assertEqual(silver_only["by_mode"]["basic"]["hit_at_5"], 0.5)
        self.assertEqual(merged["by_mode"]["basic"]["hit_at_5"], 1.0)
        self.assertNotEqual(
            silver_only["by_mode"]["basic"]["hit_at_5"],
            merged["by_mode"]["basic"]["hit_at_5"],
        )

    def test_default_queries_supports_60_query_merge(self):
        qids = [f"q{index:02d}" for index in range(1, 61)]
        tmdb_by_qid = {qid: 1000 + index for index, qid in enumerate(qids, start=1)}
        self._write_fixture(
            silver_rows=[
                _silver_row(qid, tmdb_id, 1)
                for qid, tmdb_id in tmdb_by_qid.items()
            ],
            candidates=[
                _candidate_row(qid, tmdb_id, rank=0)
                for qid, tmdb_id in tmdb_by_qid.items()
            ],
            regrade_rows=[
                _regrade_row("q60", tmdb_by_qid["q60"], 1, 3, "sixty query gold")
            ],
            query_rows=[_query_row(qid) for qid in qids],
            v1_query_rows=[_query_row(qid) for qid in qids[:20]],
        )

        self._run_merge()

        metrics = json.loads(self.metrics_path.read_text(encoding="utf-8"))
        self.assertEqual(metrics["queries_total"], 60)
        self.assertEqual(metrics["label_provenance"]["regraded_queries"], ["q60"])
        self.assertEqual(
            sum(metrics["label_provenance"]["counts"].values()),
            len(self._gold_rows()),
        )

    def test_missing_regrade_provenance_rejected(self):
        row = _regrade_row("q01", 101, 1, 3)
        row.pop("label_provenance")
        self._write_fixture(regrade_rows=[row])

        code, _stdout, stderr = self._run_main()

        self.assertNotEqual(code, 0)
        self.assertIn("label_provenance is required", stderr)
        self.assertFalse(self.gold_path.exists())
        self.assertFalse(self.metrics_path.exists())

    def test_unsupported_regrade_provenance_rejected(self):
        row = _regrade_row("q01", 101, 1, 3)
        row["label_provenance"] = "robot_guess"
        self._write_fixture(regrade_rows=[row])

        code, _stdout, stderr = self._run_main()

        self.assertNotEqual(code, 0)
        self.assertIn("label_provenance must be one of", stderr)
        self.assertFalse(self.gold_path.exists())
        self.assertFalse(self.metrics_path.exists())

    def test_human_gold_provenance_rejected(self):
        row = _regrade_row("q01", 101, 1, 3)
        row["label_provenance"] = "human_gold"
        self._write_fixture(regrade_rows=[row])

        code, _stdout, stderr = self._run_main()

        self.assertNotEqual(code, 0)
        self.assertIn("label_provenance must be one of", stderr)
        self.assertFalse(self.gold_path.exists())
        self.assertFalse(self.metrics_path.exists())

    def test_metrics_provenance_counts_sum_to_total_labels(self):
        self._write_fixture(
            regrade_rows=[
                _regrade_row("q01", 101, 1, 3),
                {
                    **_regrade_row("q02", 201, 2, 2),
                    "label_provenance": "null_parse_error_fixed",
                },
            ]
        )

        self._run_merge()

        metrics = json.loads(self.metrics_path.read_text(encoding="utf-8"))
        counts = metrics["label_provenance"]["counts"]
        self.assertEqual(sum(counts.values()), len(self._gold_rows()))
        self.assertEqual(counts["ai_draft"], 1)
        self.assertEqual(counts["null_parse_error_fixed"], 1)
        self.assertEqual(counts["silver_llm_pregrade"], 1)

    def test_refuses_when_regrade_incomplete(self):
        self._write_fixture(complete=False)

        code, _stdout, stderr = self._run_main()

        self.assertNotEqual(code, 0)
        self.assertIn("regrade_check.json missing or complete:false", stderr)
        self.assertFalse(self.gold_path.exists())
        self.assertFalse(self.metrics_path.exists())

    def test_refuses_when_regrade_check_stale(self):
        self._write_fixture(stale_check=True)

        code, _stdout, stderr = self._run_main()

        self.assertNotEqual(code, 0)
        self.assertIn("regrade_check.json is stale", stderr)
        self.assertFalse(self.gold_path.exists())
        self.assertFalse(self.metrics_path.exists())

    def test_idempotent_rerun_byte_identical(self):
        self._write_fixture()

        self._run_merge()
        first_gold = self.gold_path.read_bytes()
        first_metrics = self.metrics_path.read_bytes()
        self._run_merge()

        self.assertEqual(self.gold_path.read_bytes(), first_gold)
        self.assertEqual(self.metrics_path.read_bytes(), first_metrics)

    def test_does_not_modify_silver_or_sheet(self):
        self._write_fixture()
        silver_before = (self.run_dir / "silver_labels.jsonl").read_bytes()
        sheet_before = self.sheet_path.read_bytes()

        self._run_merge()

        self.assertEqual((self.run_dir / "silver_labels.jsonl").read_bytes(), silver_before)
        self.assertEqual(self.sheet_path.read_bytes(), sheet_before)

    def test_null_in_top5_exits_nonzero(self):
        self._write_fixture(
            silver_rows=[
                _silver_row("q01", 101, None),
                _silver_row("q01", 102, 0),
            ],
            candidates=[
                _candidate_row("q01", 101, rank=0),
                _candidate_row("q01", 102, rank=1),
            ],
            regrade_rows=[_regrade_row("q01", 102, 0, 0, None)],
        )

        code, _stdout, stderr = self._run_main()

        self.assertNotEqual(code, 0)
        self.assertIn("(q01, basic, 101)", stderr)
        self.assertFalse(self.gold_path.exists())
        self.assertFalse(self.metrics_path.exists())


if __name__ == "__main__":
    unittest.main()
