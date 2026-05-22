import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from eval.scripts import _run_io
from eval.scripts import build_regrade_sheet, check_regrade_sheet


REVIEW_KEYS = [
    "qid",
    "tmdb_id",
    "query",
    "title",
    "year",
    "overview",
    "genres",
    "silver_grade",
    "silver_confidence",
    "silver_reason",
    "in_top_5_of",
    "flag_reasons",
    "gold_grade",
    "gold_notes",
]
ROW_KEYS = set(REVIEW_KEYS + ["batch", "batch_purpose"])


class BuildRegradeSheetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_id = "2026-05-20-1200-nogit"
        self.eval_dir = self.root / "eval"
        self.run_dir = self.eval_dir / "runs" / self.run_id

        self._old_project_root = _run_io.PROJECT_ROOT
        self._old_eval_dir = _run_io.EVAL_DIR
        self._old_runs_dir = _run_io.RUNS_DIR
        self.addCleanup(self._restore_run_io)
        _run_io.PROJECT_ROOT = self.root
        _run_io.EVAL_DIR = self.eval_dir
        _run_io.RUNS_DIR = self.eval_dir / "runs"

        self.review_rows = [
            self._review_row("q12", 1201, "Source A", 1),
            self._review_row("q13", 1301, "Source B", 0),
        ]
        self._write_fixtures()

    def _restore_run_io(self):
        _run_io.PROJECT_ROOT = self._old_project_root
        _run_io.EVAL_DIR = self._old_eval_dir
        _run_io.RUNS_DIR = self._old_runs_dir

    def _review_row(self, qid, tmdb_id, title, grade):
        return {
            "qid": qid,
            "tmdb_id": tmdb_id,
            "query": f"{qid} query",
            "title": title,
            "year": 2000 + grade,
            "overview": f"{title} overview",
            "genres": "Drama",
            "silver_grade": grade,
            "silver_confidence": "low",
            "silver_reason": f"{title} reason",
            "in_top_5_of": ["advanced"],
            "flag_reasons": ["qid_in_audit_list"],
            "gold_grade": None,
            "gold_notes": None,
        }

    def _write_jsonl(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def _top_row(self, tmdb_id, rank):
        return {
            "rank": rank,
            "tmdb_id": tmdb_id,
            "title": f"Movie {tmdb_id}",
            "year": 2000 + rank,
            "grade": rank % 4,
            "confidence": "high" if rank % 2 == 0 else "low",
        }

    def _per_query_row(self, qid, mode, ids):
        return {
            "qid": qid,
            "mode": mode,
            "k": 5,
            "top": [self._top_row(tmdb_id, index + 1) for index, tmdb_id in enumerate(ids)],
            "hit_at_k": 0,
            "strict_hit_at_k": 0,
            "first_relevant_rank": None,
            "first_perfect_rank": None,
            "null_grades_in_top_k": 0,
        }

    def _candidate_row(self, qid, tmdb_id):
        return {
            "qid": qid,
            "tmdb_id": tmdb_id,
            "movie_key": f"title:movie {tmdb_id}|year:2001",
            "title": f"Movie {tmdb_id}",
            "year": 2001,
            "overview": f"Overview {qid} {tmdb_id}",
            "genres": "Comedy, Science Fiction",
            "keywords": "keyword",
            "tagline": "tagline",
            "per_mode": {"basic": {"rank": 0, "final_score": 1.0}},
            "in_top_k_of": ["basic"],
            "source": "union",
        }

    def _write_fixtures(self):
        self._write_jsonl(
            self.run_dir / "analysis" / "audit_silver_labels" / "review_sheet.jsonl",
            self.review_rows,
        )

        self.per_query_rows = [
            self._per_query_row("q03", "basic", [301, 302, 303, 304, 305, 399]),
            self._per_query_row("q03", "advanced", [302, 306, 307, 308, 309]),
            self._per_query_row("q03", "hybrid", [301, 309, 310, 311, 312]),
            self._per_query_row("q08", "basic", [801, 802, 803, 804, 805]),
            self._per_query_row("q08", "advanced", [805, 806, 807, 808, 809]),
            self._per_query_row("q08", "hybrid", [809, 810, 811, 812, 813]),
            self._per_query_row("q01", "basic", [1, 2, 3, 4, 5]),
        ]
        self._write_jsonl(
            self.run_dir / "analysis" / "error_report" / "per_query_mode.jsonl",
            self.per_query_rows,
        )

        union_ids = {
            ("q03", tmdb_id)
            for tmdb_id in [301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312]
        } | {
            ("q08", tmdb_id)
            for tmdb_id in [801, 802, 803, 804, 805, 806, 807, 808, 809, 810, 811, 812, 813]
        }
        self._write_jsonl(
            self.run_dir / "candidates.jsonl",
            [self._candidate_row(qid, tmdb_id) for qid, tmdb_id in sorted(union_ids)],
        )

        silver_rows = [
            {
                "qid": qid,
                "tmdb_id": tmdb_id,
                "grade": 1,
                "confidence": "low",
                "reason": f"Reason {qid} {tmdb_id}",
                "model": "fixture",
                "ts": "2026-05-20T00:00:00Z",
            }
            for qid, tmdb_id in sorted(union_ids)
            if tmdb_id != 813
        ]
        self._write_jsonl(self.run_dir / "silver_labels.jsonl", silver_rows)

        self._write_jsonl(
            self.eval_dir / "queries" / "v1.jsonl",
            [
                {"qid": "q03", "query": "q03 query", "tags": {}, "notes": ""},
                {"qid": "q08", "query": "q08 query", "tags": {}, "notes": ""},
                {"qid": "q12", "query": "q12 query", "tags": {}, "notes": ""},
                {"qid": "q13", "query": "q13 query", "tags": {}, "notes": ""},
            ],
        )

    def _run_tool(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = build_regrade_sheet.main(["--run", self.run_id])
        return code, stdout.getvalue(), stderr.getvalue()

    def _read_output_rows(self):
        path = self.run_dir / "analysis" / "regrade" / "regrade_sheet.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_batch1_rows_carried_verbatim(self):
        code, _, _ = self._run_tool()
        self.assertEqual(code, 0)

        rows = self._read_output_rows()
        batch1_rows = [row for row in rows if row["batch"] == 1]
        source_by_key = {(row["qid"], row["tmdb_id"]): row for row in self.review_rows}

        self.assertEqual(len(batch1_rows), len(self.review_rows))
        for row in batch1_rows:
            stripped = {key: row[key] for key in REVIEW_KEYS}
            self.assertEqual(stripped, source_by_key[(row["qid"], row["tmdb_id"])])
            self.assertEqual(row["batch_purpose"], "label_artifact_audit")

    def test_batch2_is_top5_union(self):
        code, _, _ = self._run_tool()
        self.assertEqual(code, 0)

        expected = set()
        for row in self.per_query_rows:
            if row["qid"] in {"q03", "q08"}:
                expected.update((row["qid"], top["tmdb_id"]) for top in row["top"][:5])

        rows = self._read_output_rows()
        actual = {
            (row["qid"], row["tmdb_id"])
            for row in rows
            if row["batch"] == 2
        }
        self.assertEqual(actual, expected)
        self.assertNotIn(("q03", 399), actual)

    def test_row_keysets_match_across_batches(self):
        code, _, _ = self._run_tool()
        self.assertEqual(code, 0)

        rows = self._read_output_rows()
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(set(row), ROW_KEYS)

    def test_refuses_to_overwrite_existing_sheet(self):
        code, _, _ = self._run_tool()
        self.assertEqual(code, 0)
        sheet_path = self.run_dir / "analysis" / "regrade" / "regrade_sheet.jsonl"
        before = sheet_path.read_bytes()

        code, _, stderr = self._run_tool()

        self.assertNotEqual(code, 0)
        self.assertIn(build_regrade_sheet.OVERWRITE_MESSAGE, stderr)
        self.assertEqual(sheet_path.read_bytes(), before)

    def test_manifest_counts_and_snapshot(self):
        code, _, _ = self._run_tool()
        self.assertEqual(code, 0)

        rows = self._read_output_rows()
        manifest_path = self.run_dir / "analysis" / "regrade" / "regrade_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["rows_total"], len(rows))
        self.assertEqual(manifest["rows_by_batch"]["1"], 2)
        self.assertEqual(
            manifest["rows_by_batch"]["2"],
            sum(1 for row in rows if row["batch"] == 2),
        )
        for qid in ["q12", "q13", "q03", "q08"]:
            self.assertEqual(
                manifest["rows_by_qid"][qid],
                sum(1 for row in rows if row["qid"] == qid),
            )
        self.assertEqual(len(manifest["silver_grade_snapshot"]), len(rows))
        for row in rows:
            key = f"{row['qid']}:{row['tmdb_id']}"
            self.assertEqual(manifest["silver_grade_snapshot"][key], row["silver_grade"])


class AddQ07BatchTests(unittest.TestCase):
    """RG-03 A1 — additive, non-destructive q07 batch 3."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_id = "2026-05-22-0700-nogit"
        self.eval_dir = self.root / "eval"
        self.run_dir = self.eval_dir / "runs" / self.run_id

        self._old_project_root = _run_io.PROJECT_ROOT
        self._old_eval_dir = _run_io.EVAL_DIR
        self._old_runs_dir = _run_io.RUNS_DIR
        self.addCleanup(self._restore_run_io)
        _run_io.PROJECT_ROOT = self.root
        _run_io.EVAL_DIR = self.eval_dir
        _run_io.RUNS_DIR = self.eval_dir / "runs"

        self._write_fixtures()
        build_regrade_sheet.build_regrade_sheet(self.run_id)

    def _restore_run_io(self):
        _run_io.PROJECT_ROOT = self._old_project_root
        _run_io.EVAL_DIR = self._old_eval_dir
        _run_io.RUNS_DIR = self._old_runs_dir

    def _write_jsonl(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def _review_row(self, qid, tmdb_id, grade):
        return {
            "qid": qid,
            "tmdb_id": tmdb_id,
            "query": f"{qid} query",
            "title": f"Movie {tmdb_id}",
            "year": 2000 + grade,
            "overview": f"Movie {tmdb_id} overview",
            "genres": "Drama",
            "silver_grade": grade,
            "silver_confidence": "low",
            "silver_reason": f"Movie {tmdb_id} reason",
            "in_top_5_of": ["advanced"],
            "flag_reasons": ["qid_in_audit_list"],
            "gold_grade": None,
            "gold_notes": None,
        }

    def _top_row(self, tmdb_id, rank):
        return {
            "rank": rank,
            "tmdb_id": tmdb_id,
            "title": f"Movie {tmdb_id}",
            "year": 2000 + rank,
            "grade": rank % 4,
            "confidence": "high" if rank % 2 == 0 else "low",
        }

    def _per_query_row(self, qid, mode, ids):
        return {
            "qid": qid,
            "mode": mode,
            "k": 5,
            "top": [self._top_row(t, i + 1) for i, t in enumerate(ids)],
            "hit_at_k": 0,
            "strict_hit_at_k": 0,
            "first_relevant_rank": None,
            "first_perfect_rank": None,
            "null_grades_in_top_k": 0,
        }

    def _candidate_row(self, qid, tmdb_id):
        return {
            "qid": qid,
            "tmdb_id": tmdb_id,
            "movie_key": f"title:movie {tmdb_id}|year:2001",
            "title": f"Movie {tmdb_id}",
            "year": 2001,
            "overview": f"Overview {qid} {tmdb_id}",
            "genres": "Comedy, Science Fiction",
            "keywords": "keyword",
            "tagline": "tagline",
            "per_mode": {"basic": {"rank": 0, "final_score": 1.0}},
            "in_top_k_of": ["basic"],
            "source": "union",
        }

    def _write_fixtures(self):
        self._write_jsonl(
            self.run_dir / "analysis" / "audit_silver_labels" / "review_sheet.jsonl",
            [self._review_row("q12", 1201, 1), self._review_row("q13", 1301, 0)],
        )
        self.per_query_rows = [
            self._per_query_row("q03", "basic", [301, 302, 303]),
            self._per_query_row("q03", "hybrid", [301, 304]),
            self._per_query_row("q08", "basic", [801, 802]),
            self._per_query_row("q07", "basic", [701, 702, 703]),
            self._per_query_row("q07", "advanced", [701, 704, 705]),
            self._per_query_row("q07", "hybrid", [702, 706]),
        ]
        self._write_jsonl(
            self.run_dir / "analysis" / "error_report" / "per_query_mode.jsonl",
            self.per_query_rows,
        )
        union = {
            ("q03", 301), ("q03", 302), ("q03", 303), ("q03", 304),
            ("q08", 801), ("q08", 802),
            ("q07", 701), ("q07", 702), ("q07", 703),
            ("q07", 704), ("q07", 705), ("q07", 706),
        }
        self._write_jsonl(
            self.run_dir / "candidates.jsonl",
            [self._candidate_row(qid, tmdb_id) for qid, tmdb_id in sorted(union)],
        )
        self._write_jsonl(
            self.run_dir / "silver_labels.jsonl",
            [
                {
                    "qid": qid,
                    "tmdb_id": tmdb_id,
                    "grade": 1,
                    "confidence": "low",
                    "reason": f"Reason {qid} {tmdb_id}",
                    "model": "fixture",
                    "ts": "2026-05-20T00:00:00Z",
                }
                for qid, tmdb_id in sorted(union)
            ],
        )
        self._write_jsonl(
            self.eval_dir / "queries" / "v1.jsonl",
            [
                {"qid": qid, "query": f"{qid} query", "tags": {}, "notes": ""}
                for qid in ("q03", "q07", "q08", "q12", "q13")
            ],
        )

    @property
    def sheet_path(self):
        return self.run_dir / "analysis" / "regrade" / "regrade_sheet.jsonl"

    @property
    def manifest_path(self):
        return self.run_dir / "analysis" / "regrade" / "regrade_manifest.json"

    def _read_rows(self):
        return [
            json.loads(line)
            for line in self.sheet_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_add_q07_batch_preserves_existing_rows_byte_identical(self):
        rows = self._read_rows()
        rows[0]["gold_grade"] = 2
        rows[0]["gold_notes"] = "human graded"
        self._write_jsonl(self.sheet_path, rows)
        before_lines = self.sheet_path.read_text(encoding="utf-8").splitlines()

        build_regrade_sheet.add_q07_batch(self.run_id)

        after_lines = self.sheet_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(after_lines[: len(before_lines)], before_lines)
        after_rows = self._read_rows()
        self.assertEqual(after_rows[0]["gold_grade"], 2)
        self.assertEqual(after_rows[0]["gold_notes"], "human graded")

    def test_add_q07_batch_appends_q07_batch_3(self):
        build_regrade_sheet.add_q07_batch(self.run_id)
        batch3 = [row for row in self._read_rows() if row["batch"] == 3]
        self.assertEqual(
            {row["tmdb_id"] for row in batch3},
            {701, 702, 703, 704, 705, 706},
        )
        for row in batch3:
            self.assertEqual(row["qid"], "q07")
            self.assertEqual(row["batch_purpose"], "ql_01_label_followup")
            self.assertIsNone(row["gold_grade"])
            self.assertIsNone(row["gold_notes"])
            self.assertEqual(set(row), set(build_regrade_sheet.ROW_KEYS))

    def test_add_q07_batch_updates_manifest(self):
        build_regrade_sheet.add_q07_batch(self.run_id)
        rows = self._read_rows()
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["rows_total"], len(rows))
        self.assertEqual(manifest["rows_by_batch"]["3"], 6)
        self.assertEqual(manifest["rows_by_qid"]["q07"], 6)
        self.assertEqual(len(manifest["silver_grade_snapshot"]), len(rows))

    def test_add_q07_batch_is_idempotent_guard(self):
        build_regrade_sheet.add_q07_batch(self.run_id)
        before = self.sheet_path.read_bytes()
        with self.assertRaises(FileExistsError):
            build_regrade_sheet.add_q07_batch(self.run_id)
        self.assertEqual(self.sheet_path.read_bytes(), before)

    def test_add_q07_batch_requires_existing_sheet(self):
        self.sheet_path.unlink()
        self.manifest_path.unlink()
        with self.assertRaises(FileNotFoundError):
            build_regrade_sheet.add_q07_batch(self.run_id)

    def test_check_accepts_extended_sheet_incomplete(self):
        build_regrade_sheet.add_q07_batch(self.run_id)
        check_path, report = check_regrade_sheet.check_regrade_sheet(self.run_id)
        self.assertTrue(check_path.exists())
        self.assertFalse(report["complete"])
        self.assertEqual(report["pending_by_batch"]["3"], 6)

    def test_cli_add_q07_batch_flag(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = build_regrade_sheet.main(["--run", self.run_id, "--add-q07-batch"])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertTrue(any(row["batch"] == 3 for row in self._read_rows()))


if __name__ == "__main__":
    unittest.main()
