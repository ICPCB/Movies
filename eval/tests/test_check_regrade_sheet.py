import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from eval.scripts import _run_io, build_regrade_sheet, check_regrade_sheet


class CheckRegradeSheetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_id = "2026-05-20-1300-nogit"
        self.eval_dir = self.root / "eval"
        self.run_dir = self.eval_dir / "runs" / self.run_id

        self._old_project_root = _run_io.PROJECT_ROOT
        self._old_eval_dir = _run_io.EVAL_DIR
        self._old_runs_dir = _run_io.RUNS_DIR
        self.addCleanup(self._restore_run_io)
        _run_io.PROJECT_ROOT = self.root
        _run_io.EVAL_DIR = self.eval_dir
        _run_io.RUNS_DIR = self.eval_dir / "runs"

        self._write_source_fixtures()
        build_regrade_sheet.build_regrade_sheet(self.run_id)

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
            "silver_confidence": "high",
            "silver_reason": f"{title} reason",
            "in_top_5_of": ["advanced"],
            "flag_reasons": ["qid_in_audit_list"],
            "gold_grade": None,
            "gold_notes": None,
        }

    def _top_row(self, tmdb_id, grade):
        return {
            "rank": 1,
            "tmdb_id": tmdb_id,
            "title": f"Movie {tmdb_id}",
            "year": 2000 + grade,
            "grade": grade,
            "confidence": "high",
        }

    def _per_query_row(self, qid, mode, tmdb_id, grade):
        return {
            "qid": qid,
            "mode": mode,
            "k": 5,
            "top": [self._top_row(tmdb_id, grade)],
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

    def _write_jsonl(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _write_source_fixtures(self):
        self._write_jsonl(
            self.run_dir / "analysis" / "audit_silver_labels" / "review_sheet.jsonl",
            [
                self._review_row("q12", 1201, "Source A", 1),
                self._review_row("q13", 1301, "Source B", 2),
            ],
        )
        self._write_jsonl(
            self.run_dir / "analysis" / "error_report" / "per_query_mode.jsonl",
            [
                self._per_query_row("q03", "basic", 301, 1),
                self._per_query_row("q08", "hybrid", 801, 3),
            ],
        )
        self._write_jsonl(
            self.run_dir / "candidates.jsonl",
            [
                self._candidate_row("q03", 301),
                self._candidate_row("q08", 801),
            ],
        )
        self._write_jsonl(
            self.run_dir / "silver_labels.jsonl",
            [
                {
                    "qid": "q03",
                    "tmdb_id": 301,
                    "grade": 1,
                    "confidence": "high",
                    "reason": "Reason q03 301",
                    "model": "fixture",
                    "ts": "2026-05-20T00:00:00Z",
                },
                {
                    "qid": "q08",
                    "tmdb_id": 801,
                    "grade": 3,
                    "confidence": "high",
                    "reason": "Reason q08 801",
                    "model": "fixture",
                    "ts": "2026-05-20T00:00:00Z",
                },
            ],
        )
        self._write_jsonl(
            self.eval_dir / "queries" / "v1.jsonl",
            [
                {"qid": "q03", "query": "q03 query", "tags": {}, "notes": ""},
                {"qid": "q08", "query": "q08 query", "tags": {}, "notes": ""},
                {"qid": "q12", "query": "q12 query", "tags": {}, "notes": ""},
                {"qid": "q13", "query": "q13 query", "tags": {}, "notes": ""},
            ],
        )

    @property
    def sheet_path(self):
        return self.run_dir / "analysis" / "regrade" / "regrade_sheet.jsonl"

    @property
    def check_path(self):
        return self.run_dir / "analysis" / "regrade" / "regrade_check.json"

    def _read_rows(self):
        return [
            json.loads(line)
            for line in self.sheet_path.read_text(encoding="utf-8").splitlines()
        ]

    def _write_rows(self, rows):
        self._write_jsonl(self.sheet_path, rows)

    def _run_tool(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = check_regrade_sheet.main(["--run", self.run_id])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_detects_tampered_silver_field(self):
        rows = self._read_rows()
        rows[0]["silver_grade"] = 2
        self._write_rows(rows)

        code, _stdout, stderr = self._run_tool()

        self.assertNotEqual(code, 0)
        self.assertIn("row 1", stderr)
        self.assertIn("silver_grade", stderr)

    def test_detects_added_or_removed_row(self):
        rows = self._read_rows()
        self._write_rows(rows[:-1])

        code, _stdout, stderr = self._run_tool()

        self.assertNotEqual(code, 0)
        self.assertIn("row count differs from manifest", stderr)

    def test_missing_note_on_changed_grade_fails(self):
        rows = self._read_rows()
        rows[0]["gold_grade"] = 3
        rows[0]["gold_notes"] = ""
        self._write_rows(rows)

        code, _stdout, stderr = self._run_tool()

        self.assertNotEqual(code, 0)
        self.assertIn("row 1", stderr)
        self.assertIn("gold_notes", stderr)

    def test_incomplete_sheet_exits_zero_status_false(self):
        before = self.sheet_path.read_bytes()

        code, stdout, stderr = self._run_tool()

        self.assertEqual(code, 0, stderr)
        self.assertIn("complete=false", stdout)
        self.assertEqual(self.sheet_path.read_bytes(), before)
        report = json.loads(self.check_path.read_text(encoding="utf-8"))
        self.assertFalse(report["complete"])
        self.assertEqual(report["rows_filled"], 0)
        self.assertEqual(report["agreement"]["exact"], None)
        self.assertEqual(report["agreement"]["within_1"], None)
        self.assertEqual(report["pending_by_batch"], {"1": 2, "2": 2})

    def test_agreement_and_threshold_crossings_on_complete_fixture(self):
        rows = self._read_rows()
        gold_by_key = {
            ("q12", 1201): (3, "upward crossing"),
            ("q13", 1301): (2, None),
            ("q03", 301): (0, "changed below threshold"),
            ("q08", 801): (1, "downward crossing"),
        }
        for row in rows:
            row["gold_grade"], row["gold_notes"] = gold_by_key[
                (row["qid"], row["tmdb_id"])
            ]
        self._write_rows(rows)

        code, _stdout, stderr = self._run_tool()

        self.assertEqual(code, 0, stderr)
        report = json.loads(self.check_path.read_text(encoding="utf-8"))
        self.assertTrue(report["complete"])
        self.assertEqual(report["rows_total"], 4)
        self.assertEqual(report["rows_filled"], 4)
        self.assertEqual(report["agreement"]["exact"], 0.25)
        self.assertEqual(report["agreement"]["within_1"], 0.5)
        self.assertEqual(report["agreement"]["disagree_ge1_count"], 3)
        self.assertEqual(report["agreement"]["disagree_ge2_count"], 2)
        self.assertEqual(report["by_qid"]["q12"], {"filled": 1, "changed": 1})
        self.assertEqual(report["by_qid"]["q13"], {"filled": 1, "changed": 0})
        self.assertEqual(report["by_qid"]["q03"], {"filled": 1, "changed": 1})
        self.assertEqual(report["by_qid"]["q08"], {"filled": 1, "changed": 1})
        self.assertEqual(
            report["threshold_crossings"],
            [
                {
                    "qid": "q12",
                    "tmdb_id": 1201,
                    "silver_grade": 1,
                    "gold_grade": 3,
                    "crossing": "silver<2->gold>=2; silver<3->gold==3",
                },
                {
                    "qid": "q08",
                    "tmdb_id": 801,
                    "silver_grade": 3,
                    "gold_grade": 1,
                    "crossing": "silver>=2->gold<2; silver==3->gold<3",
                },
            ],
        )

    def _write_phase7_sheet(self, *, provenance="human_reviewed_ai_assisted"):
        rows = [
            {
                "qid": "q21",
                "tmdb_id": 101,
                "query": "phase 7 query",
                "title": "Phase 7 Movie",
                "year": 2023,
                "overview": "overview",
                "genres": "Comedy",
                "silver_grade": 2,
                "silver_confidence": "high",
                "silver_reason": "reason",
                "in_top_5_of": [],
                "flag_reasons": [],
                "gold_grade": 3,
                "gold_notes": "human reviewed rationale",
                "batch": 4,
                "batch_purpose": "phase7_mood_strict_calibration",
                "label_provenance": provenance,
            },
            {
                "qid": "q55",
                "tmdb_id": 202,
                "query": "phase 7 query 2",
                "title": "Phase 7 Movie 2",
                "year": 2024,
                "overview": "overview",
                "genres": "War",
                "silver_grade": 1,
                "silver_confidence": "high",
                "silver_reason": "reason",
                "in_top_5_of": [],
                "flag_reasons": [],
                "gold_grade": 1,
                "gold_notes": None,
                "batch": 4,
                "batch_purpose": "phase7_mood_strict_calibration",
                "label_provenance": "null_parse_error_fixed",
            }
        ]
        manifest = {
            "run_id": self.run_id,
            "built_from": {
                "phase7_mood_triage": "docs/superpowers/reports/phase7-mood-triage.md",
                "error_report": "analysis/error_report/per_query_mode.jsonl",
            },
            "rows_total": 2,
            "rows_by_batch": {"4": 2},
            "rows_by_qid": {"q21": 1, "q55": 1},
            "silver_grade_snapshot": {"q55:202": 1, "q21:101": 2},
        }
        regrade_dir = self.run_dir / "analysis" / "regrade"
        self._write_jsonl(regrade_dir / "regrade_sheet.jsonl", rows)
        self._write_json(regrade_dir / "regrade_manifest.json", manifest)

    def test_phase7_custom_manifest_validates_without_legacy_sources(self):
        self._write_phase7_sheet()

        code, stdout, stderr = self._run_tool()

        self.assertEqual(code, 0, stderr)
        self.assertIn("complete=true", stdout)
        report = json.loads(self.check_path.read_text(encoding="utf-8"))
        self.assertTrue(report["complete"])
        self.assertEqual(report["pending_by_batch"], {"4": 0})

    def test_phase7_custom_manifest_rejects_human_gold_provenance(self):
        self._write_phase7_sheet(provenance="human_gold")

        code, _stdout, stderr = self._run_tool()

        self.assertNotEqual(code, 0)
        self.assertIn("label_provenance", stderr)


if __name__ == "__main__":
    unittest.main()
