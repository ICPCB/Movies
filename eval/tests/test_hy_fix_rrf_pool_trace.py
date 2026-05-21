import io
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from eval.scripts import _run_io, hy_fix_rrf_pool_trace, hybrid_expansion_stability
from eval.scripts.hybrid_live_trace import StageRun


RUN_ID = "2026-05-19-1200-nogit"
TARGET_KEY = "title:everything everywhere all at once|year:2022"


@contextmanager
def _temporary_project():
    old_project_root = _run_io.PROJECT_ROOT
    old_eval_dir = _run_io.EVAL_DIR
    old_runs_dir = _run_io.RUNS_DIR

    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp)
        _run_io.PROJECT_ROOT = project_root
        _run_io.EVAL_DIR = project_root / "eval"
        _run_io.RUNS_DIR = _run_io.EVAL_DIR / "runs"
        try:
            run_dir = _run_io.ensure_run_dir(RUN_ID)
            yield RUN_ID, run_dir
        finally:
            _run_io.PROJECT_ROOT = old_project_root
            _run_io.EVAL_DIR = old_eval_dir
            _run_io.RUNS_DIR = old_runs_dir


@contextmanager
def _patched_run_stages(fake):
    old = hybrid_expansion_stability.run_stages
    hybrid_expansion_stability.run_stages = fake
    try:
        yield
    finally:
        hybrid_expansion_stability.run_stages = old


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _diagnosis(*, rerank_top_k=3):
    return {
        "schema_version": "hy-stab-01.v1",
        "run_id": RUN_ID,
        "trace_meta": {
            "config": {
                "CANDIDATE_POOL": 1500,
                "RERANK_POOL": 800,
                "RRF_K": 15,
                "RERANK_TOP_K": rerank_top_k,
                "FINAL_TOP_K": 5,
                "SEMANTIC_WEIGHT": 1.0,
                "BM25_WEIGHT": 1.0,
            }
        },
    }


def _localization(*, q08_category="recall_depth_fusion_pool"):
    return {
        "schema_version": "hy-fix-01.v1",
        "run_id": RUN_ID,
        "per_target": [
            {
                "qid": "q08",
                "tmdb_id": 545611,
                "title": "Everything Everywhere All at Once",
                "arms": {
                    "pinned": {"fix_category": q08_category},
                    "no_llm": {"fix_category": q08_category},
                },
            },
            {
                "qid": "q07",
                "tmdb_id": 63700,
                "title": "My Babysitter's a Vampire",
                "arms": {
                    "pinned": {"fix_category": "reranker_scoring"},
                    "no_llm": {"fix_category": "reranker_scoring"},
                },
            },
        ],
    }


def _trace_row(arm, repeat, *, rrf_rank=4):
    return {
        "schema_version": "hy-stab-01.v1",
        "run_id": RUN_ID,
        "arm": arm,
        "qid": "q08",
        "tmdb_id": 545611,
        "movie_key": TARGET_KEY,
        "title": "Everything Everywhere All at Once",
        "repeat": repeat,
        "resolved": {
            "retrieval_query": f"{arm} retrieval",
            "rerank_query": f"{arm} rerank",
        },
        "rrf": {"present": True, "rank": rrf_rank, "score": 0.1},
    }


def _write_project(run_dir, *, localization=None, include_trace=True):
    analysis = run_dir / "analysis"
    _write_json(
        analysis / "hybrid_expansion_stability" / "stability_diagnosis.json",
        _diagnosis(),
    )
    if include_trace:
        rows = []
        for arm in ("pinned", "no_llm"):
            for repeat in range(2):
                rows.append(_trace_row(arm, repeat, rrf_rank=4 if arm == "pinned" else 2))
        _write_jsonl(
            analysis / "hybrid_expansion_stability" / "stability_trace.jsonl",
            rows,
        )
    _write_json(
        analysis / "hy_fix_localize" / "localization.json",
        localization if localization is not None else _localization(),
    )
    _write_jsonl(
        _run_io.EVAL_DIR / "queries" / "v1.jsonl",
        [{"qid": "q08", "query": "raw q08"}, {"qid": "q07", "query": "raw q07"}],
    )


def _movie(index, *, key=None, semantic_rank=None, bm25_rank=None, score=None):
    return {
        "movie_key": key or f"title:movie {index}|year:2020",
        "title": f"Movie {index}",
        "rrf_score": 1.0 - (index * 0.1) if score is None else score,
        "semantic_rank": semantic_rank,
        "bm25_rank": bm25_rank,
    }


def _stage_run(*, include_target=True, target_index=4):
    rrf = [
        _movie(0, semantic_rank=0, bm25_rank=10, score=0.9),
        _movie(1, semantic_rank=1, bm25_rank=None, score=0.8),
        _movie(2, semantic_rank=None, bm25_rank=2, score=0.7),
        _movie(3, semantic_rank=3, bm25_rank=30, score=0.6),
        _movie(4, key=TARGET_KEY, semantic_rank=37, bm25_rank=None, score=0.4),
    ]
    if include_target:
        target = rrf.pop()
        rrf.insert(target_index, target)
    else:
        rrf = rrf[:-1]

    semantic = [
        {"movie_key": TARGET_KEY, "semantic_score": 0.55},
    ]
    bm25 = []
    return StageRun(
        retrieval_query="unused",
        rerank_query="unused",
        filters=None,
        semantic=tuple(semantic),
        bm25=tuple(bm25),
        rrf=tuple(rrf),
        scored_pool=(),
    )


class HyFixRrfPoolTraceTests(unittest.TestCase):
    def test_recorded_queries_used(self):
        calls = []

        def fake_run_stages(*, raw_query, retrieval_query, rerank_query):
            calls.append((raw_query, retrieval_query, rerank_query))
            self.assertEqual(raw_query, "raw q08")
            self.assertIn(retrieval_query, {"pinned retrieval", "no_llm retrieval"})
            self.assertIn(rerank_query, {"pinned rerank", "no_llm rerank"})
            return _stage_run()

        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            with _patched_run_stages(fake_run_stages):
                hy_fix_rrf_pool_trace.run(run_id=run_id, margin=1)

        self.assertEqual(len(calls), 2)

    def test_expand_query_never_called(self):
        old_expand = hybrid_expansion_stability.hybrid_live_trace.expand_query

        def boom(*_args, **_kwargs):
            raise AssertionError("expand_query must not be called")

        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            hybrid_expansion_stability.hybrid_live_trace.expand_query = boom
            try:
                with _patched_run_stages(lambda **_kwargs: _stage_run()):
                    hy_fix_rrf_pool_trace.run(run_id=run_id, margin=1)
            finally:
                hybrid_expansion_stability.hybrid_live_trace.expand_query = old_expand

    def test_target_located_in_rrf(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            with _patched_run_stages(lambda **_kwargs: _stage_run()):
                _run_id, _path, data = hy_fix_rrf_pool_trace.run(
                    run_id=run_id,
                    margin=1,
                )

        target = data["per_qid"][0]["arms"]["pinned"]["target"]
        self.assertTrue(target["rrf"]["present"])
        self.assertEqual(target["rrf"]["rank"], 4)
        self.assertEqual(target["source_count"], 1)
        self.assertFalse(target["in_rerank_pool"])

    def test_target_absent_from_rrf(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            with _patched_run_stages(lambda **_kwargs: _stage_run(include_target=False)):
                _run_id, _path, data = hy_fix_rrf_pool_trace.run(
                    run_id=run_id,
                    margin=1,
                )

        arm = data["per_qid"][0]["arms"]["pinned"]
        self.assertFalse(arm["target"]["rrf"]["present"])
        self.assertIsNone(arm["target"]["rrf"]["rank"])
        self.assertFalse(arm["target"]["in_rerank_pool"])
        self.assertIsNone(arm["cutoff"]["target_rrf_rank"])

    def test_cutoff_boundary(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            with _patched_run_stages(lambda **_kwargs: _stage_run()):
                _run_id, _path, data = hy_fix_rrf_pool_trace.run(
                    run_id=run_id,
                    margin=1,
                )

        cutoff = data["per_qid"][0]["arms"]["pinned"]["cutoff"]
        self.assertEqual(cutoff["last_in_pool"]["rrf_rank"], 2)
        self.assertEqual(cutoff["first_out_of_pool"]["rrf_rank"], 3)
        self.assertEqual(cutoff["ranks_below_cutoff"], 2)
        self.assertAlmostEqual(cutoff["rrf_score_gap_to_last_in_pool"], 0.3)

    def test_source_mix_counts(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            with _patched_run_stages(lambda **_kwargs: _stage_run()):
                _run_id, _path, data = hy_fix_rrf_pool_trace.run(
                    run_id=run_id,
                    margin=1,
                )

        arm = data["per_qid"][0]["arms"]["pinned"]
        self.assertEqual(
            arm["in_pool_source_mix"],
            {"dual_source": 1, "semantic_only": 1, "bm25_only": 1},
        )
        self.assertEqual(
            arm["neighborhood_source_mix"],
            {"dual_source": 2, "semantic_only": 1, "bm25_only": 1},
        )

    def test_reproduced_matches_recorded(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            with _patched_run_stages(lambda **_kwargs: _stage_run()):
                _run_id, _path, data = hy_fix_rrf_pool_trace.run(
                    run_id=run_id,
                    margin=1,
                )

        arms = data["per_qid"][0]["arms"]
        self.assertTrue(arms["pinned"]["reproduced_matches_recorded"])
        self.assertFalse(arms["no_llm"]["reproduced_matches_recorded"])

    def test_qid_not_recall_pool_rejected(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            with self.assertRaises(hy_fix_rrf_pool_trace.HyFixRrfPoolError):
                hy_fix_rrf_pool_trace.run(run_id=run_id, qids="q07", dry_run=True)

    def test_dry_run_no_model_import(self):
        for module_name in (
            "src.models",
            "src.retrieval.semantic",
            "src.retrieval.bm25",
            "src.retrieval.reranker",
            "src.llm.langchain_ollama",
        ):
            sys.modules.pop(module_name, None)

        stdout = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            with redirect_stdout(stdout):
                exit_code = hy_fix_rrf_pool_trace.main(["--run", run_id, "--dry-run"])

            self.assertEqual(exit_code, 0)
            self.assertFalse((run_dir / "analysis" / "hy_fix_rrf_pool").exists())

        self.assertIn("q08 pinned retrieval_query=pinned retrieval", stdout.getvalue())
        self.assertNotIn("src.models", sys.modules)
        self.assertNotIn("src.retrieval.semantic", sys.modules)
        self.assertNotIn("src.retrieval.bm25", sys.modules)
        self.assertNotIn("src.retrieval.reranker", sys.modules)
        self.assertNotIn("src.llm.langchain_ollama", sys.modules)

    def test_missing_input_exits_nonzero(self):
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir, include_trace=False)
            with redirect_stderr(stderr):
                exit_code = hy_fix_rrf_pool_trace.main(["--run", run_id])

            self.assertNotEqual(exit_code, 0)
            self.assertIn("stability_trace.jsonl", stderr.getvalue())
            self.assertFalse((run_dir / "analysis" / "hy_fix_rrf_pool").exists())


if __name__ == "__main__":
    unittest.main()
