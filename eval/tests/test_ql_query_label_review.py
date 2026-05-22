import ast
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from eval.scripts import _run_io, ql_query_label_review


RUN_ID = "2026-05-22-0600-nogit"


@contextmanager
def _temporary_project():
    old_root = _run_io.PROJECT_ROOT
    old_eval = _run_io.EVAL_DIR
    old_runs = _run_io.RUNS_DIR

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _run_io.PROJECT_ROOT = root
        _run_io.EVAL_DIR = root / "eval"
        _run_io.RUNS_DIR = _run_io.EVAL_DIR / "runs"
        try:
            yield RUN_ID, _run_io.ensure_run_dir(RUN_ID)
        finally:
            _run_io.PROJECT_ROOT = old_root
            _run_io.EVAL_DIR = old_eval
            _run_io.RUNS_DIR = old_runs


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _queries():
    return [
        {
            "qid": "q05",
            "query": "a body horror story where ambition mutates into something intimate and disgusting",
            "tags": {"genre": ["horror", "drama"], "vocab_distance": "medium"},
            "notes": "",
        },
        {
            "qid": "q07",
            "query": "a mockumentary about vampires sharing chores, rent, and eternal grudges",
            "tags": {"genre": ["comedy", "horror"], "vocab_distance": "medium"},
            "notes": "",
        },
        {
            "qid": "q10",
            "query": "found footage friends chased through a haunted apartment maze",
            "tags": {"genre": ["horror", "thriller"], "vocab_distance": "medium"},
            "notes": "",
        },
    ]


def _gold():
    return [
        {"qid": "q05", "tmdb_id": 144204, "grade": 3, "label_source": "silver", "silver_grade": 3, "gold_grade": None, "gold_notes": None},
        {"qid": "q05", "tmdb_id": 40219, "grade": 2, "label_source": "silver", "silver_grade": 2, "gold_grade": None, "gold_notes": None},
        {"qid": "q07", "tmdb_id": 63700, "grade": 3, "label_source": "silver", "silver_grade": 3, "gold_grade": None, "gold_notes": None},
        {"qid": "q07", "tmdb_id": 246741, "grade": 2, "label_source": "silver", "silver_grade": 2, "gold_grade": None, "gold_notes": None},
        {"qid": "q07", "tmdb_id": 411354, "grade": 1, "label_source": "silver", "silver_grade": 1, "gold_grade": None, "gold_notes": None},
        {"qid": "q10", "tmdb_id": 8329, "grade": 3, "label_source": "silver", "silver_grade": 3, "gold_grade": None, "gold_notes": None},
        {"qid": "q10", "tmdb_id": 159638, "grade": 2, "label_source": "silver", "silver_grade": 2, "gold_grade": None, "gold_notes": None},
    ]


def _silver():
    return [
        {"qid": "q05", "tmdb_id": 144204, "grade": 3, "confidence": "high", "reason": "Body horror; tagline rotting from the inside out.", "model": "llama3.2", "ts": "2026-05-19T19:32:18Z"},
        {"qid": "q07", "tmdb_id": 63700, "grade": 3, "confidence": "high", "reason": "Genres Fantasy and Horror common in mockumentary vampire films.", "model": "llama3.2", "ts": "2026-05-19T19:32:46Z"},
        {"qid": "q10", "tmdb_id": 8329, "grade": 3, "confidence": "high", "reason": "Keywords found footage, haunted apartment, chased present.", "model": "llama3.2", "ts": "2026-05-19T19:33:21Z"},
    ]


def _cand(qid, tmdb_id, title, ranks):
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "title": title,
        "per_mode": {mode: {"rank": rank} for mode, rank in ranks.items()},
        "in_top_k_of": list(ranks),
    }


def _candidates():
    return [
        _cand("q05", 144204, "Thanatomorphose", {"basic": 0}),
        _cand("q07", 63700, "My Babysitter's a Vampire", {"basic": 4}),
        _cand("q10", 8329, "[REC]", {"basic": 4, "advanced": 3, "hybrid": 8}),
    ]


def _loc_arm(loss_stage, fix_category, *, semantic_rank, rrf_rank, in_pool, rerank_rank, final_rank):
    return {
        "loss_stage": loss_stage,
        "fix_category": fix_category,
        "stage_table": {
            "semantic": {"present": True, "rank": semantic_rank},
            "bm25": {"present": False, "rank": None},
            "rrf": {"present": True, "rank": rrf_rank},
            "rerank": {"in_pool": in_pool, "rerank_score": None, "rerank_rank": rerank_rank},
            "final": {"final_score": None, "final_rank": final_rank, "in_top5": False},
        },
    }


def _localization():
    return {
        "schema_version": "hy-fix-01.v1",
        "run_id": RUN_ID,
        "per_target": [
            {
                "qid": "q05",
                "tmdb_id": 144204,
                "title": "Thanatomorphose",
                "consolidated_fix_category": "mixed",
                "arms_agree": False,
                "arms": {
                    "pinned": _loc_arm("retrieved_dropped_before_rerank_pool", "recall_depth_fusion_pool", semantic_rank=32, rrf_rank=66, in_pool=False, rerank_rank=None, final_rank=None),
                    "no_llm": _loc_arm("rerank_recovered_final_demoted", "final_blend", semantic_rank=0, rrf_rank=1, in_pool=True, rerank_rank=4, final_rank=9),
                },
            },
            {
                "qid": "q07",
                "tmdb_id": 63700,
                "title": "My Babysitter's a Vampire",
                "consolidated_fix_category": "reranker_scoring",
                "arms_agree": True,
                "arms": {
                    "pinned": _loc_arm("rerank_demoted", "reranker_scoring", semantic_rank=3, rrf_rank=11, in_pool=True, rerank_rank=20, final_rank=25),
                    "no_llm": _loc_arm("rerank_demoted", "reranker_scoring", semantic_rank=4, rrf_rank=13, in_pool=True, rerank_rank=17, final_rank=29),
                },
            },
            {
                "qid": "q10",
                "tmdb_id": 8329,
                "title": "[REC]",
                "consolidated_fix_category": "mixed",
                "arms_agree": False,
                "arms": {
                    "pinned": _loc_arm("retrieved_dropped_before_rerank_pool", "recall_depth_fusion_pool", semantic_rank=30, rrf_rank=53, in_pool=False, rerank_rank=None, final_rank=None),
                    "no_llm": _loc_arm("rerank_demoted", "reranker_scoring", semantic_rank=7, rrf_rank=10, in_pool=True, rerank_rank=6, final_rank=7),
                },
            },
        ],
    }


def _error_rows():
    rows = []

    def add(qid, mode, strict, first_perfect, top):
        rows.append(
            {
                "qid": qid,
                "mode": mode,
                "strict_hit_at_k": strict,
                "first_relevant_rank": 1,
                "first_perfect_rank": first_perfect,
                "top": top,
            }
        )

    add("q05", "basic", 1, 1, [{"rank": 1, "tmdb_id": 144204, "title": "Thanatomorphose", "grade": 3}])
    add("q05", "advanced", 0, None, [{"rank": 1, "tmdb_id": 40219, "title": "The Beast Within", "grade": 2}])
    add("q05", "hybrid", 0, None, [{"rank": 1, "tmdb_id": 40219, "title": "The Beast Within", "grade": 2}])
    add("q07", "basic", 1, 5, [{"rank": 5, "tmdb_id": 63700, "title": "My Babysitter's a Vampire", "grade": 3}])
    add("q07", "advanced", 0, None, [{"rank": 1, "tmdb_id": 411354, "title": "WWDITS Interviews", "grade": 1}])
    add("q07", "hybrid", 0, None, [{"rank": 1, "tmdb_id": 411354, "title": "WWDITS Interviews", "grade": 1}])
    add("q10", "basic", 1, 5, [{"rank": 5, "tmdb_id": 8329, "title": "[REC]", "grade": 3}])
    add("q10", "advanced", 1, 4, [{"rank": 4, "tmdb_id": 8329, "title": "[REC]", "grade": 3}])
    add("q10", "hybrid", 0, None, [{"rank": 1, "tmdb_id": 159638, "title": "Ghost Team One", "grade": 2}])
    return rows


def _stability_rows():
    rows = []
    for qid in ("q05", "q07", "q10"):
        rows.append(
            {
                "schema_version": "hy-stab-01.v1",
                "qid": qid,
                "arm": "live",
                "repeat": 0,
                "resolved": {
                    "expansion_source": "live",
                    "retrieval_query": f"expanded retrieval query for {qid}",
                    "rerank_query": "original query",
                    "filters": None,
                },
            }
        )
    return rows


def _inputs():
    return {
        "queries": _queries(),
        "gold": _gold(),
        "silver": _silver(),
        "candidates": _candidates(),
        "localization": _localization(),
        "error_rows": _error_rows(),
        "stability_rows": _stability_rows(),
    }


def _write_inputs(run_dir):
    _write_jsonl(_run_io.EVAL_DIR / "queries" / "v1.jsonl", _queries())
    _write_jsonl(run_dir / "gold_labels.jsonl", _gold())
    _write_jsonl(run_dir / "silver_labels.jsonl", _silver())
    _write_jsonl(run_dir / "candidates.jsonl", _candidates())
    _write_json(run_dir / "analysis" / "hy_fix_localize" / "localization.json", _localization())
    _write_jsonl(run_dir / "analysis" / "error_report" / "per_query_mode.gold.jsonl", _error_rows())
    _write_jsonl(
        run_dir / "analysis" / "hybrid_expansion_stability" / "stability_trace.jsonl",
        _stability_rows(),
    )


class QlQueryLabelReviewTests(unittest.TestCase):
    def test_target_extraction_selects_grade_3_row(self):
        row = ql_query_label_review._target_gold_row(_gold(), "q07")
        self.assertEqual(row["tmdb_id"], 63700)
        self.assertEqual(row["grade"], 3)

    def test_provenance_fields_are_silver_for_cluster(self):
        data = ql_query_label_review.build_review(RUN_ID, _inputs())
        for query in data["queries"]:
            target = query["target"]
            self.assertEqual(target["label_source"], "silver")
            self.assertIsNone(target["gold_grade"])
            self.assertEqual(target["silver_grade"], target["grade_used_for_eval"])

    def test_silver_pregrade_populated_and_absent(self):
        present = ql_query_label_review._silver_pregrade(_silver(), "q07", 63700)
        self.assertEqual(present["model"], "llama3.2")
        self.assertEqual(present["confidence"], "high")
        self.assertTrue(present["reason"])
        absent = ql_query_label_review._silver_pregrade(_silver(), "q07", 99999)
        self.assertIsNone(absent["model"])
        self.assertIsNone(absent["reason"])

    def test_rule_based_lean_reranker_blend_when_both_arms_demoted(self):
        arms = {
            "pinned": {"loss_stage": "rerank_demoted"},
            "no_llm": {"loss_stage": "rerank_demoted"},
        }
        lean, trace = ql_query_label_review._rule_based_lean(arms)
        self.assertEqual(lean, "reranker_blend_issue_later_eval")
        self.assertTrue(any("R1" in line for line in trace))

    def test_rule_based_lean_needs_review_when_arms_mixed(self):
        arms = {
            "pinned": {"loss_stage": "retrieved_dropped_before_rerank_pool"},
            "no_llm": {"loss_stage": "rerank_demoted"},
        }
        lean, trace = ql_query_label_review._rule_based_lean(arms)
        self.assertEqual(lean, "needs_analyst_review")
        self.assertTrue(any("R2" in line for line in trace))

    def test_rule_based_lean_inconclusive_when_arms_missing(self):
        arms = {"pinned": {"loss_stage": "rerank_demoted"}, "no_llm": {}}
        lean, trace = ql_query_label_review._rule_based_lean(arms)
        self.assertEqual(lean, "inconclusive")
        self.assertTrue(any("R3" in line for line in trace))

    def test_build_review_shape_and_leans(self):
        data = ql_query_label_review.build_review(RUN_ID, _inputs())
        self.assertEqual(data["schema_version"], "ql-01-query-label-review.v1")
        self.assertEqual([query["qid"] for query in data["queries"]], ["q05", "q07", "q10"])
        self.assertTrue(data["label_provenance_note"])
        self.assertEqual(data["decision"]["status"], "analyst_classification_required")
        leans = {query["qid"]: query["rule_based_lean"] for query in data["queries"]}
        self.assertEqual(leans["q07"], "reranker_blend_issue_later_eval")
        self.assertEqual(leans["q05"], "needs_analyst_review")
        self.assertEqual(leans["q10"], "needs_analyst_review")

    def test_evidence_carries_silver_pregrade_and_retrieval_flags(self):
        data = ql_query_label_review.build_review(RUN_ID, _inputs())
        q07 = next(query for query in data["queries"] if query["qid"] == "q07")
        self.assertEqual(q07["target"]["silver_pregrade"]["model"], "llama3.2")
        self.assertEqual(q07["evidence"]["hybrid_expansion_text"], "expanded retrieval query for q07")
        self.assertTrue(q07["evidence"]["target_retrieved_by_mode"]["basic"])
        self.assertFalse(q07["evidence"]["target_retrieved_by_mode"]["hybrid"])

    def test_run_writes_artifact(self):
        with _temporary_project() as (run_id, run_dir):
            _write_inputs(run_dir)
            actual_run_id, output_path, data = ql_query_label_review.run(run_id)
            self.assertTrue(output_path.exists())
            written = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(actual_run_id, RUN_ID)
        self.assertEqual(written["schema_version"], "ql-01-query-label-review.v1")
        self.assertEqual(len(written["queries"]), 3)
        self.assertEqual(data["queries"][1]["qid"], "q07")

    def test_cli_writes_artifact_and_reports_leans(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            _write_inputs(run_dir)
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = ql_query_label_review.main(["--run", run_id])
            output_path = (
                run_dir / "analysis" / "query_label_review" / "q05_q07_q10_review.json"
            )
            self.assertTrue(output_path.exists())

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn("q07_lean=reranker_blend_issue_later_eval", stdout.getvalue())

    def test_missing_inputs_fail_without_writing_output(self):
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            with redirect_stderr(stderr):
                code = ql_query_label_review.main(["--run", run_id])
            output_path = (
                run_dir / "analysis" / "query_label_review" / "q05_q07_q10_review.json"
            )

        self.assertEqual(code, 1)
        self.assertIn("required input file missing", stderr.getvalue())
        self.assertFalse(output_path.exists())

    def test_script_stays_analysis_only(self):
        source = Path(ql_query_label_review.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden_import_prefixes = (
            "src",
            "ollama",
            "requests",
            "urllib",
            "http",
            "socket",
            "subprocess",
            "chromadb",
            "sentence_transformers",
        )
        self.assertFalse(
            [
                name
                for name in imports
                if any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in forbidden_import_prefixes
                )
            ]
        )
        for forbidden_text in ("ollama", "requests.", "urllib.", "socket.", "subprocess."):
            self.assertNotIn(forbidden_text, source.lower())


if __name__ == "__main__":
    unittest.main()
