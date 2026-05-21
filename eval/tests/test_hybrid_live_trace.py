import io
import importlib
import json
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from eval.scripts import _run_io, hybrid_live_trace


def _gold(qid, tmdb_id, grade):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "grade": grade,
        "label_source": "silver",
        "silver_grade": grade,
        "gold_grade": None,
        "gold_notes": None,
    }


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _write_movies_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["id,title,year,release_date"]
    for row in rows:
        lines.append(
            f"{row['id']},{row['title']},{row['year']},{row['release_date']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _diagnosis(qids=None):
    return {
        "run_id": "2026-05-19-1200-nogit",
        "labels_file": "gold_labels.jsonl",
        "hybrid_strict_miss_total": 8,
        "partition": {
            "hybrid_attributable": list(
                qids or hybrid_live_trace.HYBRID_ATTRIBUTABLE_QIDS
            ),
            "shared_miss": [],
            "no_perfect_candidate": [],
        },
        "demoting_stage_counts": {},
    }


def _query_rows(qids=None):
    return [
        {"qid": qid, "query": f"query for {qid}", "tags": {}, "notes": ""}
        for qid in (qids or hybrid_live_trace.HYBRID_ATTRIBUTABLE_QIDS)
    ]


@contextmanager
def _temporary_project(*, include_diagnosis=True):
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
            tmdb_ids = {
                qid: 1000 + index
                for index, qid in enumerate(
                    hybrid_live_trace.HYBRID_ATTRIBUTABLE_QIDS
                )
            }
            _write_jsonl(
                run_dir / "gold_labels.jsonl",
                [_gold(qid, tmdb_id, 3) for qid, tmdb_id in tmdb_ids.items()],
            )
            if include_diagnosis:
                _write_json(
                    run_dir / "analysis" / "hybrid_gap" / "diagnosis.json",
                    _diagnosis(),
                )
            _write_jsonl(_run_io.EVAL_DIR / "queries" / "v1.jsonl", _query_rows())
            _write_movies_csv(
                project_root / "data" / "movies_clean.csv",
                [
                    {
                        "id": tmdb_id,
                        "title": f"Movie {tmdb_id}",
                        "year": 2000 + index,
                        "release_date": f"{2000 + index}-01-01",
                    }
                    for index, tmdb_id in enumerate(tmdb_ids.values())
                ],
            )
            yield run_id, run_dir
        finally:
            _run_io.PROJECT_ROOT = old_project_root
            _run_io.EVAL_DIR = old_eval_dir
            _run_io.RUNS_DIR = old_runs_dir


def _target(qid="q01", tmdb_id=101):
    movie = {"title": "Target Movie", "year": 2001, "release_date": "2001-01-01"}
    return hybrid_live_trace.Target(
        qid=qid,
        tmdb_id=tmdb_id,
        title=movie["title"],
        year=movie["year"],
        release_date=movie["release_date"],
        movie_key=hybrid_live_trace.get_movie_key(movie),
    )


def _movie(
    title,
    *,
    tmdb_id,
    year=2001,
    semantic_score=None,
    bm25_score=None,
    rrf_score=None,
    rerank_score=None,
    final_score=None,
):
    movie = {
        "id": tmdb_id,
        "title": title,
        "year": year,
        "release_date": f"{year}-01-01",
    }
    movie["movie_key"] = hybrid_live_trace.get_movie_key(movie)
    for key, value in {
        "semantic_score": semantic_score,
        "bm25_score": bm25_score,
        "rrf_score": rrf_score,
        "rerank_score": rerank_score,
        "final_score": final_score,
    }.items():
        if value is not None:
            movie[key] = value
    return movie


def _target_movie(target, **scores):
    movie = {
        "id": target.tmdb_id,
        "title": target.title,
        "year": target.year,
        "release_date": target.release_date,
        "movie_key": target.movie_key,
    }
    movie.update({key: value for key, value in scores.items() if value is not None})
    return movie


def _stage_run(*, semantic=(), bm25=(), rrf=(), scored_pool=()):
    return hybrid_live_trace.StageRun(
        retrieval_query="retrieval query",
        rerank_query="rerank query",
        filters=None,
        semantic=tuple(semantic),
        bm25=tuple(bm25),
        rrf=tuple(rrf),
        scored_pool=tuple(scored_pool),
    )


def _record_for(stage_run, target=None, repeat=0):
    target = target or _target()
    return hybrid_live_trace._trace_record(
        run_id="run",
        qid=target.qid,
        target=target,
        repeat=repeat,
        stage_run=stage_run,
    )


@contextmanager
def _patched_trace_config():
    fake_config = SimpleNamespace(
        EMBEDDING_MODEL="embed-test",
        RERANKER_MODEL="reranker-test",
        LLM_MODEL="llm-test",
        HYBRID_USE_LLM_EXPANSION=True,
        LLM_RETRIEVAL_ENABLED=True,
    )
    values = {
        "runtime_config": fake_config,
        "CANDIDATE_POOL": 10,
        "RERANK_POOL": 8,
        "RERANK_TOP_K": 5,
        "FINAL_TOP_K": 5,
        "RRF_K": 15,
        "SEMANTIC_WEIGHT": 1.0,
        "BM25_WEIGHT": 1.0,
        "RERANK_VOTE_COUNT_WEIGHT": 0.08,
        "RERANK_UPSTREAM_WEIGHT": 0.20,
        "RERANK_SOURCE_AGREEMENT_BONUS": 0.10,
    }
    with ExitStack() as stack:
        stack.enter_context(patch.object(hybrid_live_trace, "_ensure_live_imports", lambda: None))
        for name, value in values.items():
            stack.enter_context(patch.object(hybrid_live_trace, name, value))
        yield


class HybridLiveTraceTest(unittest.TestCase):
    def test_composition_matches_hybrid_run(self):
        from src.utils import dedup as dedup_module

        semantic_module = types.ModuleType("src.retrieval.semantic")
        semantic_module.semantic_search = lambda *args, **kwargs: []
        bm25_module = types.ModuleType("src.retrieval.bm25")
        bm25_module.bm25_search = lambda *args, **kwargs: []
        reranker_module = types.ModuleType("src.retrieval.reranker")
        reranker_module.rerank = lambda *args, **kwargs: []
        llm_package = types.ModuleType("src.llm")
        llm_package.__path__ = []
        llm_module = types.ModuleType("src.llm.langchain_ollama")
        llm_module.expand_query = lambda query: query
        llm_module.explain_movies_batch = lambda query, movies: []
        llm_module._fallback_explanation = lambda query, movie: ""

        sys.modules.pop("src.pipelines.hybrid", None)
        with patch.dict(
            sys.modules,
            {
                "src.retrieval.semantic": semantic_module,
                "src.retrieval.bm25": bm25_module,
                "src.retrieval.reranker": reranker_module,
                "src.llm": llm_package,
                "src.llm.langchain_ollama": llm_module,
            },
        ):
            hybrid = importlib.import_module("src.pipelines.hybrid")

        fake_config = SimpleNamespace(
            HYBRID_USE_LLM_EXPANSION=True,
            LLM_RETRIEVAL_ENABLED=True,
        )

        def fake_normalize(query):
            return "processed:" + query.strip()

        def fake_expand_retrieval_query(query):
            return "expanded:" + query

        def fake_expand_query(query):
            return "llm:" + query

        def fake_parse_filters(query):
            self.assertEqual(query, "synthetic query")
            return {"year": {"$gte": 2000}}

        def fake_semantic_search(query, top_k, filters=None):
            self.assertEqual(query, "expanded:llm:processed:synthetic query")
            self.assertEqual(top_k, 30)
            self.assertEqual(filters, {"year": {"$gte": 2000}})
            return [
                _movie("Semantic A", tmdb_id=1, semantic_score=0.9, final_score=0.9),
                _movie("Semantic B", tmdb_id=2, semantic_score=0.8, final_score=0.8),
            ]

        def fake_bm25_search(query, top_k, filters=None):
            self.assertEqual(query, "expanded:llm:processed:synthetic query")
            self.assertEqual(top_k, 30)
            self.assertEqual(filters, {"year": {"$gte": 2000}})
            return [
                _movie("BM A", tmdb_id=3, bm25_score=9.0, final_score=9.0),
                _movie("BM B", tmdb_id=4, bm25_score=8.0, final_score=8.0),
            ]

        def fake_rrf_fusion(sem, bm, top_k):
            self.assertEqual(top_k, 20)
            del sem, bm
            return [
                _movie(
                    f"Fused {index:02d}",
                    tmdb_id=100 + index,
                    rrf_score=50.0 - index,
                    final_score=50.0 - index,
                )
                for index in range(20)
            ]

        def fake_rerank(query, movies, top_k, rerank_pool):
            self.assertEqual(query, "expanded:processed:synthetic query")
            self.assertEqual(rerank_pool, 20)
            pool = [dict(movie) for movie in movies[:rerank_pool]]
            for index, movie in enumerate(pool):
                movie["rerank_score"] = float(200 - index)
                movie["final_score"] = float(200 - index)
            pool.sort(key=lambda movie: movie["final_score"], reverse=True)
            return pool[:top_k]

        def fake_deduplicate(movies, prefer_score="final_score"):
            return dedup_module.deduplicate_movies(movies, prefer_score=prefer_score)

        patches = {
            "runtime_config": fake_config,
            "normalize_query": fake_normalize,
            "expand_retrieval_query": fake_expand_retrieval_query,
            "expand_query": fake_expand_query,
            "parse_filters": fake_parse_filters,
            "semantic_search": fake_semantic_search,
            "bm25_search": fake_bm25_search,
            "rrf_fusion": fake_rrf_fusion,
            "rerank": fake_rerank,
            "deduplicate_movies": fake_deduplicate,
            "_score": hybrid._score,
            "CANDIDATE_POOL": 30,
            "RERANK_POOL": 20,
            "RERANK_TOP_K": 20,
        }

        with ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(patch.object(hybrid_live_trace, name, value))
            for name, value in patches.items():
                if hasattr(hybrid, name):
                    stack.enter_context(patch.object(hybrid, name, value))

            stage_run = hybrid_live_trace._run_hybrid_stages("synthetic query")
            trace_final = hybrid_live_trace.deduplicate_movies(
                list(stage_run.scored_pool),
                prefer_score="final_score",
            )
            trace_final.sort(
                key=lambda movie: hybrid_live_trace._score(
                    movie,
                    "final_score",
                    "rerank_score",
                ),
                reverse=True,
            )
            trace_final = trace_final[:15]
            for movie in trace_final:
                movie["explanation"] = ""

            hybrid_final = hybrid.run(
                "synthetic query",
                top_k=15,
                with_explanation=False,
            )

        self.assertEqual(trace_final, hybrid_final)

    def test_target_resolution_from_gold_labels(self):
        targets = hybrid_live_trace._resolve_targets(
            qids=("q03",),
            gold_labels=[
                _gold("q03", 25199, 3),
                _gold("q03", 123, 2),
                _gold("q04", 999, 3),
            ],
            movie_rows_by_tmdb_id={
                25199: {
                    "id": "25199",
                    "title": "Teen Witch",
                    "year": "1989.0",
                    "release_date": "1989-04-28",
                }
            },
        )

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].tmdb_id, 25199)
        self.assertEqual(targets[0].title, "Teen Witch")
        self.assertEqual(targets[0].movie_key, "title:teen witch|year:1989")

    def test_loss_unretrieved(self):
        record = _record_for(_stage_run())
        self.assertEqual(record["loss_classification"], "unretrieved")

    def test_loss_dropped_at_fusion(self):
        target = _target()
        record = _record_for(
            _stage_run(
                semantic=[
                    _target_movie(
                        target,
                        semantic_score=0.9,
                        final_score=0.9,
                    )
                ],
            ),
            target=target,
        )
        self.assertEqual(
            record["loss_classification"],
            "retrieved_dropped_at_fusion",
        )

    def test_loss_dropped_before_rerank_pool(self):
        target = _target()
        record = _record_for(
            _stage_run(
                semantic=[
                    _target_movie(
                        target,
                        semantic_score=0.9,
                        final_score=0.9,
                    )
                ],
                rrf=[
                    _target_movie(
                        target,
                        rrf_score=0.1,
                        final_score=0.1,
                    )
                ],
            ),
            target=target,
        )
        self.assertEqual(
            record["loss_classification"],
            "retrieved_dropped_before_rerank_pool",
        )

    def test_loss_rerank_recovered_final_demoted(self):
        target = _target()
        competitors = [
            _movie(
                f"Competitor {index}",
                tmdb_id=200 + index,
                rerank_score=float(index),
                final_score=float(10 - index),
            )
            for index in range(5)
        ]
        record = _record_for(
            _stage_run(
                semantic=[_target_movie(target, semantic_score=0.9)],
                rrf=[_target_movie(target, rrf_score=0.9, final_score=0.9)],
                scored_pool=competitors
                + [_target_movie(target, rerank_score=99.0, final_score=1.0)],
            ),
            target=target,
        )
        self.assertEqual(
            record["loss_classification"],
            "rerank_recovered_final_demoted",
        )
        self.assertEqual(record["rerank"]["rerank_rank"], 0)
        self.assertEqual(record["final"]["final_rank"], 5)

    def test_loss_rerank_demoted(self):
        target = _target()
        competitors = [
            _movie(
                f"Competitor {index}",
                tmdb_id=300 + index,
                rerank_score=float(10 - index),
                final_score=float(10 - index),
            )
            for index in range(5)
        ]
        record = _record_for(
            _stage_run(
                semantic=[_target_movie(target, semantic_score=0.9)],
                rrf=[_target_movie(target, rrf_score=0.9, final_score=0.9)],
                scored_pool=competitors
                + [_target_movie(target, rerank_score=1.0, final_score=1.0)],
            ),
            target=target,
        )
        self.assertEqual(record["loss_classification"], "rerank_demoted")
        self.assertEqual(record["rerank"]["rerank_rank"], 5)

    def test_loss_hybrid_top5_hit(self):
        target = _target()
        record = _record_for(
            _stage_run(
                semantic=[_target_movie(target, semantic_score=0.9)],
                rrf=[_target_movie(target, rrf_score=0.9, final_score=0.9)],
                scored_pool=[
                    _target_movie(target, rerank_score=5.0, final_score=10.0),
                    _movie(
                        "Competitor",
                        tmdb_id=400,
                        rerank_score=4.0,
                        final_score=9.0,
                    ),
                ],
            ),
            target=target,
        )
        self.assertEqual(record["loss_classification"], "hybrid_top5_hit")
        self.assertTrue(record["final"]["in_top5"])

    def test_repeat_stability_aggregation(self):
        target = _target(qid="q01", tmdb_id=501)
        row_a = _record_for(_stage_run(), target=target, repeat=0)
        row_b = dict(row_a)
        row_b["repeat"] = 1
        row_b["loss_classification"] = "hybrid_top5_hit"
        inputs = hybrid_live_trace.TraceInputs(
            run_id="run",
            run_path=Path("."),
            queries_path=Path("queries.jsonl"),
            movies_csv_path=Path("movies.csv"),
            qids=("q01",),
            queries={"q01": "query"},
            targets=(target,),
        )

        with _patched_trace_config():
            diagnosis = hybrid_live_trace.build_diagnosis(
                inputs=inputs,
                repeat=2,
                trace_rows=[row_a, row_b],
            )

        per_target = diagnosis["per_target"][0]
        self.assertFalse(per_target["stable"])
        self.assertEqual(per_target["classification"], "unstable")
        self.assertEqual(
            per_target["classifications"],
            ["unretrieved", "hybrid_top5_hit"],
        )
        self.assertEqual(diagnosis["loss_classification_counts"]["unstable"], 1)
        self.assertEqual(diagnosis["mechanism_summary"]["resolved_or_unstable"], 1)

    def test_dry_run_no_model_import(self):
        for module_name in list(sys.modules):
            if (
                module_name == "src.models"
                or module_name in {
                    "src.retrieval.semantic",
                    "src.retrieval.bm25",
                    "src.retrieval.reranker",
                }
                or module_name.startswith("src.llm")
            ):
                sys.modules.pop(module_name, None)

        stdout = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            with redirect_stdout(stdout):
                exit_code = hybrid_live_trace.main(["--run", run_id, "--dry-run"])

            self.assertEqual(exit_code, 0)
            self.assertIn("q03:", stdout.getvalue())
            self.assertIn("tmdb_id=1000", stdout.getvalue())
            self.assertFalse((run_dir / "analysis" / "hybrid_live_trace").exists())

        self.assertNotIn("src.models", sys.modules)
        self.assertNotIn("src.retrieval.semantic", sys.modules)
        self.assertNotIn("src.retrieval.bm25", sys.modules)
        self.assertNotIn("src.retrieval.reranker", sys.modules)
        self.assertFalse(any(name.startswith("src.llm") for name in sys.modules))

    def test_missing_diagnosis_exits_nonzero(self):
        stderr = io.StringIO()
        with _temporary_project(include_diagnosis=False) as (run_id, run_dir):
            with redirect_stderr(stderr):
                exit_code = hybrid_live_trace.main(["--run", run_id])

            self.assertNotEqual(exit_code, 0)
            self.assertIn("diagnosis.json", stderr.getvalue())
            self.assertFalse((run_dir / "analysis" / "hybrid_live_trace").exists())

    def test_mechanism_summary_sums_to_targets_total(self):
        per_target = [
            {"classification": "unretrieved"},
            {"classification": "retrieved_dropped_at_fusion"},
            {"classification": "retrieved_dropped_before_rerank_pool"},
            {"classification": "rerank_recovered_final_demoted"},
            {"classification": "rerank_demoted"},
            {"classification": "hybrid_top5_hit"},
            {"classification": "other"},
            {"classification": "unstable"},
        ]

        counts = hybrid_live_trace._loss_counts(per_target)
        summary = hybrid_live_trace._mechanism_summary(counts)

        self.assertEqual(sum(counts.values()), len(per_target))
        self.assertEqual(sum(summary.values()), len(per_target))
        self.assertEqual(summary["recall_depth"], 3)
        self.assertEqual(summary["final_score_blend"], 1)
        self.assertEqual(summary["reranker"], 1)
        self.assertEqual(summary["resolved_or_unstable"], 3)


if __name__ == "__main__":
    unittest.main()
