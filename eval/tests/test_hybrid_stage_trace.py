import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from eval.scripts import _run_io, hybrid_stage_trace


TRACE_RECORD_KEYS = {
    "qid",
    "tmdb_id",
    "title",
    "year",
    "silver_grade",
    "silver_confidence",
    "advanced",
    "hybrid",
    "rank_delta_hybrid_minus_advanced",
    "in_top_5_advanced",
    "in_top_5_hybrid",
}

MODE_TRACE_KEYS = {
    "rank",
    "semantic_score",
    "bm25_score",
    "rrf_score",
    "rerank_score",
    "final_score",
}


def _mode(rank, *, score=1.0):
    return {
        "rank": rank,
        "semantic_score": score,
        "bm25_score": score + 1.0,
        "rrf_score": score + 2.0,
        "rerank_score": score + 3.0,
        "final_score": score + 4.0,
    }


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


def _silver(qid, tmdb_id, grade=2, confidence="medium"):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "confidence": confidence,
        "reason": "Synthetic label.",
        "model": "test-model",
        "ts": "2026-05-19T12:00:00Z",
    }


def _write_jsonl(path, rows):
    text = "\n".join(json.dumps(row, ensure_ascii=True) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


@contextmanager
def _temporary_run(candidates, labels):
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
            yield run_id, run_dir
        finally:
            _run_io.PROJECT_ROOT = old_project_root
            _run_io.EVAL_DIR = old_eval_dir
            _run_io.RUNS_DIR = old_runs_dir


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class HybridStageTraceTest(unittest.TestCase):
    def test_trace_record_shape(self):
        candidates = [
            _full_candidate("q03", 101, {"advanced": _mode(0), "hybrid": _mode(1)}),
            _full_candidate("q03", 102, {"advanced": _mode(1)}),
            _full_candidate("q03", 103, {"hybrid": _mode(0)}),
            _full_candidate("q03", 104, {"advanced": _mode(4), "hybrid": _mode(5)}),
            _full_candidate("q03", 105, {"advanced": _mode(5), "hybrid": _mode(4)}),
            _full_candidate("q03", 106, {"advanced": _mode(6), "hybrid": _mode(6)}),
        ]
        labels = [_silver("q03", candidate["tmdb_id"]) for candidate in candidates]

        with _temporary_run(candidates, labels) as (run_id, _run_dir):
            _actual, trace_path, _summary_path, _summary = hybrid_stage_trace.run(
                run_id=run_id,
                qid="q03",
            )
            records = _read_jsonl(trace_path)

        self.assertEqual(len(records), 6)
        for record in records:
            self.assertEqual(set(record), TRACE_RECORD_KEYS)
            if record["advanced"] is not None:
                self.assertEqual(set(record["advanced"]), MODE_TRACE_KEYS)
            if record["hybrid"] is not None:
                self.assertEqual(set(record["hybrid"]), MODE_TRACE_KEYS)

    def test_rank_delta_when_hybrid_only(self):
        candidates = [_full_candidate("q03", 103, {"hybrid": _mode(0)})]
        labels = [_silver("q03", 103)]

        with _temporary_run(candidates, labels) as (run_id, _run_dir):
            _actual, trace_path, _summary_path, _summary = hybrid_stage_trace.run(
                run_id=run_id,
                qid="q03",
            )
            record = _read_jsonl(trace_path)[0]

        self.assertIsNone(record["advanced"])
        self.assertIsNone(record["rank_delta_hybrid_minus_advanced"])

    def test_summary_advanced_only_top_5(self):
        candidates = [
            _full_candidate("q03", 201, {"advanced": _mode(0), "hybrid": _mode(0)}),
            _full_candidate("q03", 202, {"advanced": _mode(1), "hybrid": _mode(6)}),
            _full_candidate("q03", 203, {"advanced": _mode(5), "hybrid": _mode(1)}),
        ]
        labels = [_silver("q03", candidate["tmdb_id"]) for candidate in candidates]

        with _temporary_run(candidates, labels) as (run_id, _run_dir):
            _actual, _trace_path, _summary_path, summary = hybrid_stage_trace.run(
                run_id=run_id,
                qid="q03",
            )

        self.assertEqual(summary["advanced_only_top_5_tmdb_ids"], [202])

    def test_unknown_qid_exits_nonzero(self):
        candidates = [_full_candidate("q03", 301, {"advanced": _mode(0)})]
        labels = [_silver("q03", 301)]
        stderr = io.StringIO()

        with _temporary_run(candidates, labels) as (run_id, _run_dir):
            with redirect_stderr(stderr):
                code = hybrid_stage_trace.main(["--run", run_id, "--qid", "q99"])

        self.assertNotEqual(code, 0)
        self.assertEqual(
            stderr.getvalue().strip(),
            "qid q99 not in run 2026-05-19-1200-nogit",
        )


if __name__ == "__main__":
    unittest.main()
