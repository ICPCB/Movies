import io
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from eval.scripts import _run_io, hybrid_expansion_stability, hybrid_live_trace


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


def _target(qid="q03", tmdb_id=10681, title="WALL E", year=2008):
    movie = {"title": title, "year": year, "release_date": f"{year}-01-01"}
    return hybrid_live_trace.Target(
        qid=qid,
        tmdb_id=tmdb_id,
        title=movie["title"],
        year=movie["year"],
        release_date=movie["release_date"],
        movie_key=hybrid_live_trace.get_movie_key(movie),
    )


def _inputs(target=None):
    target = target or _target()
    return hybrid_live_trace.TraceInputs(
        run_id="run",
        run_path=Path("."),
        queries_path=Path("queries.jsonl"),
        movies_csv_path=Path("movies.csv"),
        qids=(target.qid,),
        queries={target.qid: "synthetic query"},
        targets=(target,),
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
    quality_prior=None,
    upstream_prior=None,
    source_agreement=None,
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
        "quality_prior": quality_prior,
        "upstream_prior": upstream_prior,
        "source_agreement": source_agreement,
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


def _trace_row(arm, target, classification, *, repeat=0, final_rank=None):
    return {
        "arm": arm,
        "qid": target.qid,
        "tmdb_id": target.tmdb_id,
        "title": target.title,
        "repeat": repeat,
        "loss_classification": classification,
        "final": {"final_rank": final_rank},
    }


def _stage_run(*, retrieval_query="retrieval query", rerank_query="rerank query"):
    return hybrid_live_trace.StageRun(
        retrieval_query=retrieval_query,
        rerank_query=rerank_query,
        filters=None,
        semantic=(),
        bm25=(),
        rrf=(),
        scored_pool=(),
    )


@contextmanager
def _patched_live_globals(**overrides):
    fake_config = SimpleNamespace(
        EMBEDDING_MODEL="embed-test",
        RERANKER_MODEL="reranker-test",
        LLM_MODEL="llm-test",
        HYBRID_USE_LLM_EXPANSION=True,
        LLM_RETRIEVAL_ENABLED=True,
    )

    def score(movie, key, fallback="final_score"):
        try:
            return float(movie.get(key, movie.get(fallback, 0.0)) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    values = {
        "runtime_config": fake_config,
        "normalize_query": lambda query: "processed:" + query.strip(),
        "expand_retrieval_query": lambda query: "expanded:" + query,
        "expand_query": lambda query: "llm:" + query,
        "parse_filters": lambda query: None,
        "semantic_search": lambda query, top_k, filters=None: [],
        "bm25_search": lambda query, top_k, filters=None: [],
        "rrf_fusion": lambda sem, bm, top_k: [],
        "rerank": lambda query, movies, top_k, rerank_pool: [],
        "_score": score,
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
    values.update(overrides)

    with ExitStack() as stack:
        stack.enter_context(patch.object(hybrid_live_trace, "_ensure_live_imports", lambda: None))
        for name, value in values.items():
            stack.enter_context(patch.object(hybrid_live_trace, name, value))
        yield


class HybridExpansionStabilityTest(unittest.TestCase):
    def test_live_arm_matches_hybrid_live_trace(self):
        def fake_parse_filters(query):
            self.assertEqual(query, "synthetic query")
            return {"year": {"$gte": 2000}}

        def fake_semantic_search(query, top_k, filters=None):
            self.assertEqual(query, "expanded:llm:processed:synthetic query")
            self.assertEqual(top_k, 10)
            self.assertEqual(filters, {"year": {"$gte": 2000}})
            return [_movie("Semantic", tmdb_id=1, semantic_score=0.9)]

        def fake_bm25_search(query, top_k, filters=None):
            self.assertEqual(query, "expanded:llm:processed:synthetic query")
            self.assertEqual(top_k, 10)
            self.assertEqual(filters, {"year": {"$gte": 2000}})
            return [_movie("BM25", tmdb_id=2, bm25_score=7.0)]

        def fake_rrf_fusion(sem, bm, top_k):
            self.assertEqual(len(sem), 1)
            self.assertEqual(len(bm), 1)
            self.assertEqual(top_k, 8)
            return [
                _movie("Fused A", tmdb_id=3, rrf_score=2.0, final_score=2.0),
                _movie("Fused B", tmdb_id=4, rrf_score=1.0, final_score=1.0),
            ]

        def fake_rerank(query, movies, top_k, rerank_pool):
            self.assertEqual(query, "expanded:processed:synthetic query")
            self.assertEqual(top_k, 5)
            self.assertEqual(rerank_pool, 5)
            return [
                dict(
                    movie,
                    rerank_score=10.0 - index,
                    final_score=10.0 - index,
                )
                for index, movie in enumerate(movies)
            ]

        with _patched_live_globals(
            parse_filters=fake_parse_filters,
            semantic_search=fake_semantic_search,
            bm25_search=fake_bm25_search,
            rrf_fusion=fake_rrf_fusion,
            rerank=fake_rerank,
        ):
            expected = hybrid_live_trace._run_hybrid_stages("synthetic query")
            rows, stage_runs = hybrid_expansion_stability._trace_all(
                inputs=_inputs(),
                repeat=1,
                arms=("live",),
            )

        self.assertEqual(stage_runs[("live", "q03", 0)], expected)
        self.assertEqual(len(rows), 1)

    def test_pinned_arm_calls_expand_query_once_per_qid(self):
        calls = []

        def fake_expand_query(query):
            calls.append(query)
            return f"llm:{query}:{len(calls)}"

        with _patched_live_globals(expand_query=fake_expand_query):
            rows, _stage_runs = hybrid_expansion_stability._trace_all(
                inputs=_inputs(),
                repeat=3,
                arms=("pinned",),
            )

        self.assertEqual(len(calls), 1)
        retrieval_queries = {row["resolved"]["retrieval_query"] for row in rows}
        self.assertEqual(
            retrieval_queries,
            {"expanded:llm:processed:synthetic query:1"},
        )

    def test_no_llm_arm_never_calls_expand_query(self):
        def raising_expand_query(query):
            raise AssertionError(f"unexpected expand_query call: {query}")

        with _patched_live_globals(expand_query=raising_expand_query):
            rows, _stage_runs = hybrid_expansion_stability._trace_all(
                inputs=_inputs(),
                repeat=1,
                arms=("no_llm",),
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["resolved"]["retrieval_query"],
            "expanded:processed:synthetic query",
        )

    def test_attribution_fixed_defect(self):
        target = _target()
        rows = [
            _trace_row("live", target, "rerank_recovered_final_demoted"),
            _trace_row("pinned", target, "rerank_recovered_final_demoted"),
            _trace_row("no_llm", target, "unretrieved"),
        ]

        with _patched_live_globals():
            diagnosis = hybrid_expansion_stability.build_diagnosis(
                inputs=_inputs(target),
                repeat=1,
                arms=("live", "pinned", "no_llm"),
                trace_rows=rows,
            )

        self.assertEqual(
            diagnosis["instability_attribution"][0]["attribution"],
            "fixed_defect",
        )
        self.assertEqual(diagnosis["attribution_summary"]["fixed_defect"], 1)

    def test_attribution_expansion_dependent(self):
        target = _target()
        rows = [
            _trace_row("live", target, "unretrieved"),
            _trace_row("pinned", target, "hybrid_top5_hit", final_rank=2),
            _trace_row("no_llm", target, "unretrieved"),
        ]

        with _patched_live_globals():
            diagnosis = hybrid_expansion_stability.build_diagnosis(
                inputs=_inputs(target),
                repeat=1,
                arms=("live", "pinned", "no_llm"),
                trace_rows=rows,
            )

        self.assertEqual(
            diagnosis["instability_attribution"][0]["attribution"],
            "expansion_dependent",
        )
        self.assertEqual(diagnosis["attribution_summary"]["fixed_defect"], 0)
        self.assertEqual(diagnosis["attribution_summary"]["expansion_dependent"], 1)

    def test_attribution_expansion_variance_only(self):
        target = _target()
        rows = [
            _trace_row("live", target, "unretrieved", repeat=0),
            _trace_row("live", target, "hybrid_top5_hit", repeat=1, final_rank=1),
            _trace_row("pinned", target, "hybrid_top5_hit", repeat=0, final_rank=1),
            _trace_row("pinned", target, "hybrid_top5_hit", repeat=1, final_rank=1),
            _trace_row("no_llm", target, "hybrid_top5_hit", repeat=0, final_rank=1),
            _trace_row("no_llm", target, "hybrid_top5_hit", repeat=1, final_rank=1),
        ]

        with _patched_live_globals():
            diagnosis = hybrid_expansion_stability.build_diagnosis(
                inputs=_inputs(target),
                repeat=2,
                arms=("live", "pinned", "no_llm"),
                trace_rows=rows,
            )

        self.assertEqual(
            diagnosis["instability_attribution"][0]["attribution"],
            "expansion_variance_only",
        )

    def test_attribution_stable_hit(self):
        target = _target()
        rows = [
            _trace_row("live", target, "hybrid_top5_hit", final_rank=0),
            _trace_row("pinned", target, "unretrieved"),
            _trace_row("no_llm", target, "unretrieved"),
        ]

        with _patched_live_globals():
            diagnosis = hybrid_expansion_stability.build_diagnosis(
                inputs=_inputs(target),
                repeat=1,
                arms=("live", "pinned", "no_llm"),
                trace_rows=rows,
            )

        self.assertEqual(
            diagnosis["instability_attribution"][0]["attribution"],
            "stable_hit",
        )

    def test_subset_missing_control_arm_is_inconclusive(self):
        target = _target()
        rows = [_trace_row("live", target, "hybrid_top5_hit", final_rank=0)]

        with _patched_live_globals():
            diagnosis = hybrid_expansion_stability.build_diagnosis(
                inputs=_inputs(target),
                repeat=1,
                arms=("live",),
                trace_rows=rows,
            )

        attribution = diagnosis["instability_attribution"][0]
        self.assertIsNone(attribution["pinned_stable"])
        self.assertIsNone(attribution["no_llm_stable"])
        self.assertEqual(attribution["attribution"], "inconclusive")

    def test_attribution_inconclusive_when_control_arm_unstable(self):
        target = _target()
        rows = [
            _trace_row("live", target, "unretrieved", repeat=0),
            _trace_row("live", target, "unretrieved", repeat=1),
            _trace_row("pinned", target, "unretrieved", repeat=0),
            _trace_row("pinned", target, "hybrid_top5_hit", repeat=1, final_rank=1),
            _trace_row("no_llm", target, "unretrieved", repeat=0),
            _trace_row("no_llm", target, "unretrieved", repeat=1),
        ]

        with _patched_live_globals():
            diagnosis = hybrid_expansion_stability.build_diagnosis(
                inputs=_inputs(target),
                repeat=2,
                arms=("live", "pinned", "no_llm"),
                trace_rows=rows,
            )

        self.assertEqual(
            diagnosis["instability_attribution"][0]["attribution"],
            "inconclusive",
        )

    def test_q03_contributions_sum(self):
        target = _target()
        pool = [
            _target_movie(
                target,
                rerank_score=0.50,
                quality_prior=0.25,
                upstream_prior=0.50,
                source_agreement=1.0,
                final_score=0.50 + 0.08 * 0.25 + 0.20 * 0.50 + 0.10,
            ),
            _movie(
                "Competitor",
                tmdb_id=2,
                rerank_score=0.40,
                quality_prior=1.0,
                upstream_prior=1.0,
                source_agreement=0.0,
                final_score=0.40 + 0.08 + 0.20,
            ),
        ]

        with _patched_live_globals():
            result = hybrid_expansion_stability._decompose_pool(
                scored_pool=pool,
                target=target,
            )

        rows = [result["target"]] + result["leapfrog_competitors"]
        for row in rows:
            contributions = row["contributions"]
            total = (
                contributions["rerank_score"]
                + contributions["vote"]
                + contributions["upstream"]
                + contributions["agreement"]
            )
            self.assertAlmostEqual(total, row["final_score"], places=6)

    def test_q03_leapfrog_competitors(self):
        target = _target()
        pool = [
            _target_movie(
                target,
                rerank_score=0.50,
                quality_prior=0.0,
                upstream_prior=0.0,
                source_agreement=0.0,
                final_score=0.50,
            ),
            _movie(
                "Leapfrog",
                tmdb_id=2,
                rerank_score=0.40,
                quality_prior=1.0,
                upstream_prior=1.0,
                source_agreement=1.0,
                final_score=0.40 + 0.08 + 0.20 + 0.10,
            ),
            _movie(
                "Behind",
                tmdb_id=3,
                rerank_score=0.30,
                quality_prior=0.0,
                upstream_prior=0.0,
                source_agreement=0.0,
                final_score=0.30,
            ),
        ]

        with _patched_live_globals():
            result = hybrid_expansion_stability._decompose_pool(
                scored_pool=pool,
                target=target,
            )

        self.assertEqual(result["leapfrog_count"], 1)
        self.assertEqual(result["leapfrog_competitors"][0]["title"], "Leapfrog")

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
                exit_code = hybrid_expansion_stability.main(
                    ["--run", run_id, "--dry-run"]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("arms=live,pinned,no_llm", stdout.getvalue())
            self.assertIn("q03:", stdout.getvalue())
            self.assertIn("tmdb_id=1000", stdout.getvalue())
            self.assertFalse(
                (run_dir / "analysis" / "hybrid_expansion_stability").exists()
            )

        self.assertNotIn("src.models", sys.modules)
        self.assertNotIn("src.retrieval.semantic", sys.modules)
        self.assertNotIn("src.retrieval.bm25", sys.modules)
        self.assertNotIn("src.retrieval.reranker", sys.modules)
        self.assertFalse(any(name.startswith("src.llm") for name in sys.modules))

    def test_missing_diagnosis_exits_nonzero(self):
        stderr = io.StringIO()
        with _temporary_project(include_diagnosis=False) as (run_id, run_dir):
            with redirect_stderr(stderr):
                exit_code = hybrid_expansion_stability.main(["--run", run_id])

            self.assertNotEqual(exit_code, 0)
            self.assertIn("diagnosis.json", stderr.getvalue())
            self.assertFalse(
                (run_dir / "analysis" / "hybrid_expansion_stability").exists()
            )

    def test_diagnosis_counts_sum_to_targets_total(self):
        target = _target()
        rows = [
            _trace_row("live", target, "unretrieved"),
            _trace_row("pinned", target, "unretrieved"),
            _trace_row("no_llm", target, "unretrieved"),
        ]

        with _patched_live_globals():
            diagnosis = hybrid_expansion_stability.build_diagnosis(
                inputs=_inputs(target),
                repeat=1,
                arms=("live", "pinned", "no_llm"),
                trace_rows=rows,
            )

        targets_total = diagnosis["trace_meta"]["targets_total"]
        for arm_data in diagnosis["per_arm"].values():
            self.assertEqual(
                sum(arm_data["loss_classification_counts"].values()),
                targets_total,
            )
            self.assertEqual(
                sum(arm_data["mechanism_summary"].values()),
                targets_total,
            )
        self.assertEqual(sum(diagnosis["attribution_summary"].values()), targets_total)


if __name__ == "__main__":
    unittest.main()
