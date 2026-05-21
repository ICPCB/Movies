import ast
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from eval.scripts import _run_io, hy_fix_mixed_q05_q10


RUN_ID = "2026-05-22-0400-nogit"


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
            yield RUN_ID, _run_io.ensure_run_dir(RUN_ID)
        finally:
            _run_io.PROJECT_ROOT = old_project_root
            _run_io.EVAL_DIR = old_eval_dir
            _run_io.RUNS_DIR = old_runs_dir


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


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
                    "pinned": _arm(
                        loss_stage="retrieved_dropped_before_rerank_pool",
                        fix_category="recall_depth_fusion_pool",
                        semantic_rank=32,
                        bm25_rank=None,
                        rrf_rank=66,
                        in_pool=False,
                        rerank_rank=None,
                        final_rank=None,
                    ),
                    "no_llm": _arm(
                        loss_stage="rerank_recovered_final_demoted",
                        fix_category="final_blend",
                        semantic_rank=0,
                        bm25_rank=None,
                        rrf_rank=1,
                        in_pool=True,
                        rerank_rank=4,
                        final_rank=9,
                    ),
                },
            },
            {
                "qid": "q10",
                "tmdb_id": 8329,
                "title": "[REC]",
                "consolidated_fix_category": "mixed",
                "arms_agree": False,
                "arms": {
                    "pinned": _arm(
                        loss_stage="retrieved_dropped_before_rerank_pool",
                        fix_category="recall_depth_fusion_pool",
                        semantic_rank=30,
                        bm25_rank=916,
                        rrf_rank=53,
                        in_pool=False,
                        rerank_rank=None,
                        final_rank=None,
                    ),
                    "no_llm": _arm(
                        loss_stage="rerank_demoted",
                        fix_category="reranker_scoring",
                        semantic_rank=7,
                        bm25_rank=54,
                        rrf_rank=10,
                        in_pool=True,
                        rerank_rank=6,
                        final_rank=7,
                    ),
                },
            },
        ],
    }


def _arm(
    *,
    loss_stage,
    fix_category,
    semantic_rank,
    bm25_rank,
    rrf_rank,
    in_pool,
    rerank_rank,
    final_rank,
):
    return {
        "loss_stage": loss_stage,
        "fix_category": fix_category,
        "stage_table": {
            "semantic": {"present": True, "rank": semantic_rank},
            "bm25": {"present": bm25_rank is not None, "rank": bm25_rank},
            "rrf": {"present": True, "rank": rrf_rank},
            "rerank": {
                "in_pool": in_pool,
                "rerank_score": 0.02 if rerank_rank is not None else None,
                "rerank_rank": rerank_rank,
            },
            "final": {
                "final_score": 0.25 if final_rank is not None else None,
                "final_rank": final_rank,
                "in_top5": False,
            },
        },
    }


def _stability_rows():
    rows = []
    for qid, arms in (
        ("q05", {"pinned": "retrieved_dropped_before_rerank_pool", "no_llm": "rerank_recovered_final_demoted"}),
        ("q10", {"pinned": "retrieved_dropped_before_rerank_pool", "no_llm": "rerank_demoted"}),
    ):
        for arm, loss in arms.items():
            rows.append(
                {
                    "schema_version": "hy-stab-01.v1",
                    "run_id": RUN_ID,
                    "arm": arm,
                    "qid": qid,
                    "repeat": 0,
                    "loss_classification": loss,
                }
            )
    return rows


def _error_rows():
    return [
        {
            "qid": "q05",
            "mode": "basic",
            "strict_hit_at_k": 1,
            "first_relevant_rank": 1,
            "first_perfect_rank": 1,
            "top": [{"title": "Thanatomorphose"}],
        },
        {
            "qid": "q05",
            "mode": "hybrid",
            "strict_hit_at_k": 0,
            "first_relevant_rank": 1,
            "first_perfect_rank": None,
            "top": [{"title": "The Beast Within"}],
        },
        {
            "qid": "q10",
            "mode": "basic",
            "strict_hit_at_k": 1,
            "first_relevant_rank": 1,
            "first_perfect_rank": 5,
            "top": [{"title": "[REC]"}],
        },
        {
            "qid": "q10",
            "mode": "advanced",
            "strict_hit_at_k": 1,
            "first_relevant_rank": 1,
            "first_perfect_rank": 4,
            "top": [{"title": "[REC]"}],
        },
        {
            "qid": "q10",
            "mode": "hybrid",
            "strict_hit_at_k": 0,
            "first_relevant_rank": 1,
            "first_perfect_rank": None,
            "top": [{"title": "Ghost Team One"}],
        },
    ]


def _prior_rrf_policy():
    return {
        "schema_version": "hy-fix-02b-validate.v1",
        "decision": {
            "status": "implementation_not_justified",
            "reason": "No safe global cutoff policy.",
        },
    }


def _prior_q07_analysis():
    return {
        "schema_version": "hy-fix-03-reranker-q07.v1",
        "decision": {
            "status": "implementation_not_justified",
            "reason": "No safe q07 scorer policy.",
        },
    }


def _inputs():
    return {
        "localization": _localization(),
        "stability_rows": _stability_rows(),
        "error_rows": _error_rows(),
        "rrf_policy": _prior_rrf_policy(),
        "q07_analysis": _prior_q07_analysis(),
    }


def _write_inputs(run_dir):
    _write_json(
        run_dir / "analysis" / "hy_fix_localize" / "localization.json",
        _localization(),
    )
    _write_jsonl(
        run_dir
        / "analysis"
        / "hybrid_expansion_stability"
        / "stability_trace.jsonl",
        _stability_rows(),
    )
    _write_jsonl(
        run_dir / "analysis" / "error_report" / "per_query_mode.gold.jsonl",
        _error_rows(),
    )
    _write_json(
        run_dir / "analysis" / "hy_fix_rrf_pool" / "rrf_pool_policy_validation.json",
        _prior_rrf_policy(),
    )
    _write_json(
        run_dir
        / "analysis"
        / "hy_fix_reranker_scoring"
        / "q07_reranker_scoring_analysis.json",
        _prior_q07_analysis(),
    )


def _policies(data):
    return {policy["policy_id"]: policy for policy in data["policies"]}


class HyFixMixedQ05Q10Tests(unittest.TestCase):
    def test_run_writes_analysis_without_src_implementation_recommendation(self):
        with _temporary_project() as (run_id, run_dir):
            _write_inputs(run_dir)
            actual_run_id, output_path, data = hy_fix_mixed_q05_q10.run(run_id)
            self.assertTrue(output_path.exists())

        self.assertEqual(actual_run_id, RUN_ID)
        self.assertEqual(data["schema_version"], "hy-fix-04-mixed-q05-q10.v1")
        self.assertFalse(data["implementation_recommended"])
        self.assertIsNone(data["recommended_policy"])
        self.assertEqual(data["implementation_allowed_files"], [])
        self.assertEqual(
            data["decision"]["next_action"],
            "final_closeout_no_safe_localized_fixes_remaining",
        )

    def test_records_mixed_arm_requirements(self):
        data = hy_fix_mixed_q05_q10.build_analysis(RUN_ID, _inputs())
        per_qid = data["evidence"]["per_qid"]

        self.assertEqual(
            per_qid["q05"]["deterministic_arms"]["pinned"][
                "minimum_rerank_top_k_needed_if_rrf_rank_zero_based"
            ],
            67,
        )
        self.assertEqual(
            per_qid["q10"]["deterministic_arms"]["pinned"][
                "minimum_rerank_top_k_needed_if_rrf_rank_zero_based"
            ],
            54,
        )
        self.assertEqual(per_qid["q05"]["deterministic_arms"]["no_llm"]["final_rank"], 9)
        self.assertEqual(per_qid["q10"]["deterministic_arms"]["no_llm"]["rerank_rank"], 6)

    def test_records_mode_comparison(self):
        data = hy_fix_mixed_q05_q10.build_analysis(RUN_ID, _inputs())
        per_qid = data["evidence"]["per_qid"]

        self.assertEqual(
            per_qid["q05"]["mode_comparison"]["basic"]["first_perfect_rank"],
            1,
        )
        self.assertIsNone(
            per_qid["q05"]["mode_comparison"]["hybrid"]["first_perfect_rank"]
        )
        self.assertEqual(
            per_qid["q10"]["mode_comparison"]["advanced"]["first_perfect_rank"],
            4,
        )
        self.assertIsNone(
            per_qid["q10"]["mode_comparison"]["hybrid"]["first_perfect_rank"]
        )

    def test_policy_blockers_are_explicit(self):
        policies = _policies(hy_fix_mixed_q05_q10.build_analysis(RUN_ID, _inputs()))

        self.assertEqual(
            set(policies),
            {
                "global_cutoff_small",
                "final_blend_reweight_for_mixed",
                "reranker_scoring_adjustment",
                "query_or_label_review",
            },
        )
        self.assertEqual(policies["global_cutoff_small"]["q05_pinned_minimum_rerank_top_k"], 67)
        self.assertEqual(policies["global_cutoff_small"]["q10_pinned_minimum_rerank_top_k"], 54)
        self.assertIn(
            "hy_fix_02b_no_safe_global_cutoff",
            policies["global_cutoff_small"]["stop_reason"],
        )
        self.assertIn(
            "needs_full_pool_decomposition",
            policies["final_blend_reweight_for_mixed"]["stop_reason"],
        )
        self.assertFalse(
            any(policy["safe_enough_for_hy_fix_04"] for policy in policies.values())
        )

    def test_cli_writes_artifact_and_reports_next_action(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            _write_inputs(run_dir)
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = hy_fix_mixed_q05_q10.main(["--run", run_id])
            output_path = (
                run_dir
                / "analysis"
                / "hy_fix_mixed"
                / "q05_q10_mixed_analysis.json"
            )
            self.assertTrue(output_path.exists())

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn("implementation_recommended=False", stdout.getvalue())
        self.assertIn("recommended_policy=None", stdout.getvalue())
        self.assertIn(
            "next_action=final_closeout_no_safe_localized_fixes_remaining",
            stdout.getvalue(),
        )

    def test_missing_inputs_fail_without_writing_output(self):
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            with redirect_stderr(stderr):
                code = hy_fix_mixed_q05_q10.main(["--run", run_id])
            output_path = (
                run_dir
                / "analysis"
                / "hy_fix_mixed"
                / "q05_q10_mixed_analysis.json"
            )

        self.assertEqual(code, 1)
        self.assertIn("required input file missing", stderr.getvalue())
        self.assertFalse(output_path.exists())

    def test_script_stays_analysis_only(self):
        source = Path(hy_fix_mixed_q05_q10.__file__).read_text(encoding="utf-8")
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
