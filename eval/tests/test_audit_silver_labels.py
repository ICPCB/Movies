import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from eval.scripts import _run_io, audit_silver_labels


def _full_candidate(qid, tmdb_id):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "movie_key": f"title:movie {tmdb_id}|year:2000",
        "title": f"Movie {tmdb_id}",
        "year": 2000,
        "overview": f"Synthetic overview for {tmdb_id}.",
        "genres": "Drama",
        "keywords": "synthetic",
        "tagline": "",
        "per_mode": {"basic": {"rank": 0}},
        "in_top_k_of": ["basic"],
        "source": "union",
    }


def _silver(qid, tmdb_id, grade, confidence=None):
    if confidence is None:
        confidence = "low" if grade is None else "high"
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "confidence": confidence,
        "reason": "Synthetic label.",
        "model": "test-model",
        "ts": "2026-05-19T12:00:00Z",
    }


def _query(qid):
    return {
        "qid": qid,
        "query": f"Synthetic query for {qid}",
        "tags": {
            "era": "2000-2015",
            "genre": ["drama"],
            "vocab_distance": "medium",
            "length": "medium",
            "specificity": "medium",
            "ambiguity": "medium",
        },
        "notes": "Synthetic.",
    }


def _per_query(qid, mode, tmdb_ids):
    return {
        "qid": qid,
        "mode": mode,
        "k": 5,
        "top": [
            {
                "rank": index,
                "tmdb_id": tmdb_id,
                "title": f"Movie {tmdb_id}",
                "year": 2000,
                "grade": 1,
                "confidence": "high",
            }
            for index, tmdb_id in enumerate(tmdb_ids, start=1)
        ],
        "hit_at_k": 0,
        "strict_hit_at_k": 0,
        "first_relevant_rank": None,
        "first_perfect_rank": None,
        "null_grades_in_top_k": 0,
    }


def _write_jsonl(path, rows):
    text = "\n".join(json.dumps(row, ensure_ascii=True) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


@contextmanager
def _temporary_run(candidates, labels, *, error_report=True, per_query_rows=None):
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
            query_dir = _run_io.EVAL_DIR / "queries"
            query_dir.mkdir(parents=True, exist_ok=True)
            query_qids = sorted({str(row["qid"]) for row in candidates})
            _write_jsonl(query_dir / "v1.jsonl", [_query(qid) for qid in query_qids])
            _write_jsonl(run_dir / "candidates.jsonl", candidates)
            _write_jsonl(run_dir / "silver_labels.jsonl", labels)

            if error_report:
                error_dir = run_dir / "analysis" / "error_report"
                error_dir.mkdir(parents=True, exist_ok=True)
                _write_jsonl(error_dir / "per_query_mode.jsonl", per_query_rows or [])
                (error_dir / "summary.json").write_text(
                    json.dumps({"run_id": run_id}) + "\n",
                    encoding="utf-8",
                )
            yield run_id, run_dir
        finally:
            _run_io.PROJECT_ROOT = old_project_root
            _run_io.EVAL_DIR = old_eval_dir
            _run_io.RUNS_DIR = old_runs_dir


def _review_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class AuditSilverLabelsTest(unittest.TestCase):
    def test_explicit_qids_only_with_no_rules(self):
        candidates = [
            _full_candidate("q12", 1201),
            _full_candidate("q12", 1202),
            _full_candidate("q13", 1301),
        ]
        labels = [
            _silver("q12", 1201, 1, confidence="low"),
            _silver("q12", 1202, 0),
            _silver("q13", 1301, None),
        ]

        with _temporary_run(candidates, labels) as (run_id, _run_dir):
            _actual, review_path, _summary_path, _summary = audit_silver_labels.run(
                run_id=run_id,
                qids=["q12"],
            )
            rows = _review_rows(review_path)

        self.assertEqual([row["tmdb_id"] for row in rows], [1201, 1202])
        self.assertTrue(all(row["qid"] == "q12" for row in rows))
        self.assertTrue(
            all(row["flag_reasons"] == ["qid_in_audit_list"] for row in rows)
        )

    def test_include_rules_adds_low_confidence_rows(self):
        candidates = [
            _full_candidate("q12", 1201),
            _full_candidate("q14", 1401),
        ]
        labels = [
            _silver("q12", 1201, 0),
            _silver("q14", 1401, 0, confidence="low"),
        ]

        with _temporary_run(candidates, labels) as (run_id, _run_dir):
            _actual, review_path, _summary_path, summary = audit_silver_labels.run(
                run_id=run_id,
                qids=["q12"],
                include_rules=True,
            )
            rows = _review_rows(review_path)

        by_key = {(row["qid"], row["tmdb_id"]): row for row in rows}
        self.assertIn(("q14", 1401), by_key)
        self.assertIn("silver_confidence_low", by_key[("q14", 1401)]["flag_reasons"])
        self.assertEqual(summary["rules_applied"], list(audit_silver_labels.RULES))

    def test_missing_error_report_exits_nonzero(self):
        candidates = [_full_candidate("q12", 1201)]
        labels = [_silver("q12", 1201, 0)]
        stderr = io.StringIO()

        with _temporary_run(candidates, labels, error_report=False) as (
            run_id,
            _run_dir,
        ):
            with redirect_stderr(stderr):
                code = audit_silver_labels.main(["--run", run_id])

        self.assertNotEqual(code, 0)
        self.assertIn("error_report not found", stderr.getvalue())

    def test_review_sheet_is_idempotent(self):
        candidates = [
            _full_candidate("q12", 1201),
            _full_candidate("q12", 1202),
        ]
        labels = [
            _silver("q12", 1201, 1),
            _silver("q12", 1202, 0),
        ]
        per_query_rows = [_per_query("q12", "basic", [1202, 1201])]

        with _temporary_run(
            candidates,
            labels,
            per_query_rows=per_query_rows,
        ) as (run_id, _run_dir):
            _actual, review_path, _summary_path, _summary = audit_silver_labels.run(
                run_id=run_id,
                qids=["q12"],
            )
            first = review_path.read_bytes()
            audit_silver_labels.run(run_id=run_id, qids=["q12"])
            second = review_path.read_bytes()

        self.assertEqual(first, second)

    def test_does_not_modify_silver_labels(self):
        candidates = [_full_candidate("q12", 1201)]
        labels = [_silver("q12", 1201, 1)]

        with _temporary_run(candidates, labels) as (run_id, run_dir):
            silver_path = run_dir / "silver_labels.jsonl"
            before = silver_path.read_bytes()
            audit_silver_labels.run(run_id=run_id, qids=["q12"])
            after = silver_path.read_bytes()

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
