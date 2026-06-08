import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from eval.scripts import _run_io, hybrid_gap_trace


def _mode(
    rank,
    *,
    semantic=None,
    bm25=None,
    rrf=None,
    rerank=None,
    final=None,
):
    block = {"rank": rank}
    scores = {
        "semantic_score": semantic,
        "bm25_score": bm25,
        "rrf_score": rrf,
        "rerank_score": rerank,
        "final_score": final,
    }
    for key, value in scores.items():
        if value is not None:
            block[key] = float(value)
    return block


def _candidate(qid, tmdb_id, per_mode):
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


def _gold(qid, tmdb_id, grade):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "label_source": "silver",
        "label_provenance": "silver_llm_pregrade",
        "silver_grade": grade,
        "gold_grade": None,
        "gold_notes": None,
    }


def _write_jsonl(path, rows):
    text = "\n".join(json.dumps(row, ensure_ascii=True) for row in rows)
    if text:
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _summary(hybrid_miss_qids, basic_miss_qids=None, advanced_miss_qids=None):
    return {
        "run_id": "2026-05-19-1200-nogit",
        "k": 5,
        "by_mode": {
            "basic": {"strict_miss_qids": list(basic_miss_qids or [])},
            "advanced": {"strict_miss_qids": list(advanced_miss_qids or [])},
            "hybrid": {"strict_miss_qids": list(hybrid_miss_qids)},
        },
        "labels_file": "gold_labels.jsonl",
    }


def _metrics(qids_total, hybrid_miss_count):
    return {
        "run_id": "2026-05-19-1200-nogit",
        "queries_total": qids_total,
        "by_mode": {
            "hybrid": {
                "strict_hit_at_5": 1.0 - (hybrid_miss_count / qids_total),
            },
        },
    }


@contextmanager
def _temporary_run(
    candidates,
    gold_labels,
    *,
    hybrid_miss_qids,
    include_summary=True,
):
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
            qids = {
                str(row["qid"])
                for row in list(candidates) + list(gold_labels)
            }
            _write_jsonl(run_dir / "candidates.jsonl", candidates)
            _write_jsonl(run_dir / "gold_labels.jsonl", gold_labels)
            _write_json(
                run_dir / "metrics.json",
                _metrics(len(qids), len(hybrid_miss_qids)),
            )
            error_dir = run_dir / "analysis" / "error_report"
            if include_summary:
                _write_json(
                    error_dir / "summary.gold.json",
                    _summary(hybrid_miss_qids),
                )
            _write_jsonl(error_dir / "per_query_mode.gold.jsonl", [])
            yield run_id, run_dir
        finally:
            _run_io.PROJECT_ROOT = old_project_root
            _run_io.EVAL_DIR = old_eval_dir
            _run_io.RUNS_DIR = old_runs_dir


def _simple_final_mode(rank):
    return _mode(rank, semantic=10 - rank, final=10 - rank)


def _hybrid_attributable_fixture(qid="q_attr"):
    candidates = [
        _candidate(
            qid,
            200,
            {
                "advanced": _mode(0, semantic=10, bm25=10, rrf=10, rerank=10, final=10),
                "hybrid": _mode(5, semantic=0, bm25=0, rrf=0, rerank=0, final=0),
            },
        )
    ]
    for offset in range(5):
        tmdb_id = 201 + offset
        candidates.append(
            _candidate(
                qid,
                tmdb_id,
                {
                    "advanced": _mode(
                        offset + 1,
                        semantic=5 - offset,
                        bm25=5 - offset,
                        rrf=5 - offset,
                        rerank=5 - offset,
                        final=5 - offset,
                    ),
                    "hybrid": _mode(
                        offset,
                        semantic=5 - offset,
                        bm25=5 - offset,
                        rrf=5 - offset,
                        rerank=5 - offset,
                        final=5 - offset,
                    ),
                },
            )
        )
    labels = [_gold(qid, 200, 3)] + [_gold(qid, 201 + offset, 0) for offset in range(5)]
    return candidates, labels


def _demoting_fixture(qid="q_demote"):
    candidates = [
        _candidate(
            qid,
            100,
            {
                "advanced": _mode(0, semantic=20, bm25=20, rrf=20, rerank=20, final=20),
                "hybrid": _mode(5, semantic=20, bm25=20, rrf=20, rerank=0, final=0),
            },
        )
    ]
    for offset in range(5):
        tmdb_id = 101 + offset
        score = 5 - offset
        candidates.append(
            _candidate(
                qid,
                tmdb_id,
                {
                    "advanced": _mode(
                        offset + 1,
                        semantic=score,
                        bm25=score,
                        rrf=score,
                        rerank=score,
                        final=score,
                    ),
                    "hybrid": _mode(
                        offset,
                        semantic=score,
                        bm25=score,
                        rrf=score,
                        rerank=score,
                        final=score,
                    ),
                },
            )
        )
    labels = [_gold(qid, 100, 3)] + [_gold(qid, 101 + offset, 0) for offset in range(5)]
    return candidates, labels


class HybridGapTraceTest(unittest.TestCase):
    def test_partition_no_perfect_candidate(self):
        qid = "q_no_perfect"
        candidates = [
            _candidate(
                qid,
                101,
                {
                    "basic": _simple_final_mode(0),
                    "advanced": _simple_final_mode(0),
                    "hybrid": _simple_final_mode(0),
                },
            )
        ]
        labels = [_gold(qid, 101, 2)]

        with _temporary_run(
            candidates,
            labels,
            hybrid_miss_qids=[qid],
        ) as (run_id, _run_dir):
            _actual, trace_path, _diagnosis_path, diagnosis = hybrid_gap_trace.run(
                run_id=run_id
            )
            trace_text = trace_path.read_text(encoding="utf-8")

        self.assertEqual(diagnosis["partition"]["no_perfect_candidate"], [qid])
        self.assertEqual(diagnosis["partition"]["hybrid_attributable"], [])
        self.assertEqual(trace_text, "")

    def test_partition_hybrid_attributable(self):
        candidates, labels = _hybrid_attributable_fixture("q_attr")

        with _temporary_run(
            candidates,
            labels,
            hybrid_miss_qids=["q_attr"],
        ) as (run_id, _run_dir):
            _actual, _trace_path, _diagnosis_path, diagnosis = hybrid_gap_trace.run(
                run_id=run_id
            )

        self.assertEqual(diagnosis["partition"]["hybrid_attributable"], ["q_attr"])
        self.assertEqual(diagnosis["partition"]["shared_miss"], [])
        self.assertEqual(diagnosis["partition"]["no_perfect_candidate"], [])

    def test_partition_shared_miss(self):
        qid = "q_shared"
        candidates = [
            _candidate(
                qid,
                301,
                {
                    "basic": _simple_final_mode(5),
                    "advanced": _simple_final_mode(5),
                    "hybrid": _simple_final_mode(5),
                },
            )
        ]
        labels = [_gold(qid, 301, 3)]

        with _temporary_run(
            candidates,
            labels,
            hybrid_miss_qids=[qid],
        ) as (run_id, _run_dir):
            _actual, trace_path, _diagnosis_path, diagnosis = hybrid_gap_trace.run(
                run_id=run_id
            )
            trace_text = trace_path.read_text(encoding="utf-8")

        self.assertEqual(diagnosis["partition"]["shared_miss"], [qid])
        self.assertEqual(diagnosis["partition"]["hybrid_attributable"], [])
        self.assertEqual(trace_text, "")

    def test_demoting_stage_localization(self):
        candidates, labels = _demoting_fixture()

        with _temporary_run(
            candidates,
            labels,
            hybrid_miss_qids=["q_demote"],
        ) as (run_id, _run_dir):
            _actual, trace_path, _diagnosis_path, diagnosis = hybrid_gap_trace.run(
                run_id=run_id
            )
            trace = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(trace[0]["demoting_stage"], "rerank_score")
        self.assertLess(trace[0]["stage_ranks"]["hybrid"]["semantic_score"], 5)
        self.assertLess(trace[0]["stage_ranks"]["hybrid"]["rrf_score"], 5)
        self.assertGreaterEqual(trace[0]["stage_ranks"]["hybrid"]["rerank_score"], 5)
        self.assertEqual(diagnosis["demoting_stage_counts"]["rerank_score"], 1)

    def test_not_retrieved_by_hybrid(self):
        qid = "q_not_retrieved"
        candidates = [
            _candidate(
                qid,
                401,
                {
                    "advanced": _mode(0, semantic=10, bm25=10, rrf=10, rerank=10, final=10),
                },
            )
        ]
        labels = [_gold(qid, 401, 3)]

        with _temporary_run(
            candidates,
            labels,
            hybrid_miss_qids=[qid],
        ) as (run_id, _run_dir):
            _actual, trace_path, _diagnosis_path, diagnosis = hybrid_gap_trace.run(
                run_id=run_id
            )
            trace = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(trace[0]["demoting_stage"], "not_retrieved_by_hybrid")
        self.assertEqual(
            diagnosis["demoting_stage_counts"]["not_retrieved_by_hybrid"],
            1,
        )

    def test_missing_summary_gold_exits_nonzero(self):
        candidates, labels = _hybrid_attributable_fixture("q_missing")
        stderr = io.StringIO()

        with _temporary_run(
            candidates,
            labels,
            hybrid_miss_qids=["q_missing"],
            include_summary=False,
        ) as (run_id, run_dir):
            with redirect_stderr(stderr):
                exit_code = hybrid_gap_trace.main(["--run", run_id])

            self.assertNotEqual(exit_code, 0)
            self.assertIn("summary.gold.json", stderr.getvalue())
            self.assertFalse((run_dir / "analysis" / "hybrid_gap").exists())

    def test_idempotent_rerun_byte_identical(self):
        candidates, labels = _demoting_fixture("q_idempotent")

        with _temporary_run(
            candidates,
            labels,
            hybrid_miss_qids=["q_idempotent"],
        ) as (run_id, _run_dir):
            _actual, trace_path, diagnosis_path, _diagnosis = hybrid_gap_trace.run(
                run_id=run_id
            )
            first_trace = trace_path.read_bytes()
            first_diagnosis = diagnosis_path.read_bytes()

            _actual, trace_path, diagnosis_path, _diagnosis = hybrid_gap_trace.run(
                run_id=run_id
            )
            second_trace = trace_path.read_bytes()
            second_diagnosis = diagnosis_path.read_bytes()

        self.assertEqual(first_trace, second_trace)
        self.assertEqual(first_diagnosis, second_diagnosis)


if __name__ == "__main__":
    unittest.main()
