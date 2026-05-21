import ast
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from eval.scripts import _run_io, hy_fix_rrf_pool_validate


RUN_ID = "2026-05-22-0200-nogit"


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


def _localization():
    return {
        "schema_version": "hy-fix-01.v1",
        "run_id": RUN_ID,
        "per_target": [
            {"qid": "q05", "consolidated_fix_category": "mixed"},
            {"qid": "q07", "consolidated_fix_category": "reranker_scoring"},
            {"qid": "q08", "consolidated_fix_category": "recall_depth_fusion_pool"},
            {"qid": "q10", "consolidated_fix_category": "mixed"},
        ],
    }


def _trace(*, boundary_tie=False):
    return {
        "schema_version": "hy-fix-02a-rrf-pool.v1",
        "run_id": RUN_ID,
        "config": {
            "CANDIDATE_POOL": 1500,
            "RERANK_POOL": 800,
            "RRF_K": 15,
            "RERANK_TOP_K": 50,
            "FINAL_TOP_K": 5,
        },
        "per_qid": [
            {
                "qid": "q08",
                "tmdb_id": 545611,
                "title": "Everything Everywhere All at Once",
                "arms": {
                    "pinned": _arm(rank=183, boundary_tie=boundary_tie),
                    "no_llm": _arm(rank=79, boundary_tie=False),
                },
            }
        ],
    }


def _arm(*, rank, boundary_tie):
    first_out_score = 0.025 if boundary_tie else 0.024
    return {
        "target": {
            "rrf": {"present": True, "rank": rank, "score": 0.01},
            "source_count": 1,
            "in_rerank_pool": False,
        },
        "cutoff": {
            "rerank_top_k": 50,
            "last_in_pool": {"rrf_rank": 49, "rrf_score": 0.025},
            "first_out_of_pool": {"rrf_rank": 50, "rrf_score": first_out_score},
        },
        "in_pool_source_mix": {
            "dual_source": 16,
            "semantic_only": 15,
            "bm25_only": 19,
        },
    }


def _write_inputs(run_dir, *, trace=None, localization=None):
    _write_json(
        run_dir / "analysis" / "hy_fix_rrf_pool" / "rrf_pool_trace.json",
        trace if trace is not None else _trace(),
    )
    _write_json(
        run_dir / "analysis" / "hy_fix_localize" / "localization.json",
        localization if localization is not None else _localization(),
    )


def _policies(data):
    return {policy["policy_id"]: policy for policy in data["policies"]}


class HyFixRrfPoolValidateTests(unittest.TestCase):
    def test_run_writes_validation_without_src_implementation_recommendation(self):
        with _temporary_project() as (run_id, run_dir):
            _write_inputs(run_dir)
            actual_run_id, output_path, data = hy_fix_rrf_pool_validate.run(run_id)
            self.assertTrue(output_path.exists())

        self.assertEqual(actual_run_id, RUN_ID)
        self.assertEqual(data["schema_version"], "hy-fix-02b-validate.v1")
        self.assertFalse(data["implementation_recommended"])
        self.assertIsNone(data["recommended_policy"])
        self.assertEqual(data["implementation_allowed_files"], [])
        self.assertEqual(
            data["decision"]["next_action"],
            "continue_to_hy_fix_03_reranker_scoring_q07",
        )

    def test_cutoff_policies_report_q08_rescue_and_memory_risk(self):
        data = hy_fix_rrf_pool_validate.build_validation(
            RUN_ID,
            _trace(),
            _localization(),
        )
        policies = _policies(data)

        self.assertTrue(policies["cutoff_only_top_80"]["q08_no_llm_rescued_before_rerank_pool"])
        self.assertFalse(policies["cutoff_only_top_80"]["q08_pinned_rescued_before_rerank_pool"])
        self.assertEqual(
            policies["cutoff_only_top_80"]["minimum_cutoff_needed"],
            {"no_llm": 80, "pinned": 184},
        )
        self.assertTrue(policies["cutoff_only_top_200"]["q08_no_llm_rescued_before_rerank_pool"])
        self.assertTrue(policies["cutoff_only_top_200"]["q08_pinned_rescued_before_rerank_pool"])
        self.assertEqual(
            policies["cutoff_only_top_200"]["estimated_candidate_count_memory_risk"]["level"],
            "high",
        )
        self.assertFalse(policies["cutoff_only_top_200"]["safe_enough_for_hy_fix_02b"])
        self.assertEqual(
            policies["cutoff_only_top_200"]["stop_reason"],
            "pinned_q08_requires_cutoff_at_or_above_200_medium_high_risk",
        )

    def test_quota_and_fusion_policies_remain_analysis_only_blockers(self):
        policies = _policies(
            hy_fix_rrf_pool_validate.build_validation(
                RUN_ID,
                _trace(),
                _localization(),
            )
        )

        quota = policies["quota_preserve_semantic_bm25_small"]
        fusion = policies["fusion_depth_increase_small"]
        self.assertFalse(quota["safe_enough_for_hy_fix_02b"])
        self.assertFalse(fusion["safe_enough_for_hy_fix_02b"])
        self.assertEqual(quota["exact_allowed_src_config_files"], [])
        self.assertEqual(fusion["exact_allowed_src_config_files"], [])
        self.assertIn("trace_lacks_full_source_rank_lists", quota["stop_reason"])
        self.assertIn("depth_increase_does_not_change_pool_cutoff", fusion["stop_reason"])

    def test_affected_fixed_defect_qids_are_reported(self):
        data = hy_fix_rrf_pool_validate.build_validation(
            RUN_ID,
            _trace(),
            _localization(),
        )

        self.assertEqual(
            set(data["affected_fixed_defect_qids"].keys()),
            {"q05", "q07", "q08", "q10"},
        )
        self.assertTrue(data["affected_fixed_defect_qids"]["q08"]["has_rrf_pool_trace_data"])
        self.assertFalse(data["affected_fixed_defect_qids"]["q07"]["has_rrf_pool_trace_data"])
        self.assertEqual(
            data["affected_fixed_defect_qids"]["q07"]["localization_category"],
            "reranker_scoring",
        )

    def test_boundary_policy_is_emitted_only_when_trace_shows_boundary_tie(self):
        without_tie = _policies(
            hy_fix_rrf_pool_validate.build_validation(
                RUN_ID,
                _trace(boundary_tie=False),
                _localization(),
            )
        )
        with_tie = _policies(
            hy_fix_rrf_pool_validate.build_validation(
                RUN_ID,
                _trace(boundary_tie=True),
                _localization(),
            )
        )

        self.assertNotIn("tie_or_boundary_fix_only", without_tie)
        self.assertIn("tie_or_boundary_fix_only", with_tie)
        self.assertFalse(with_tie["tie_or_boundary_fix_only"]["safe_enough_for_hy_fix_02b"])

    def test_cli_writes_artifact_and_reports_next_action(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            _write_inputs(run_dir)
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = hy_fix_rrf_pool_validate.main(["--run", run_id])
            output_path = (
                run_dir
                / "analysis"
                / "hy_fix_rrf_pool"
                / "rrf_pool_policy_validation.json"
            )
            self.assertTrue(output_path.exists())

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn("implementation_recommended=False", stdout.getvalue())
        self.assertIn("recommended_policy=None", stdout.getvalue())
        self.assertIn("next_action=continue_to_hy_fix_03_reranker_scoring_q07", stdout.getvalue())

    def test_missing_inputs_fail_without_writing_output(self):
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            with redirect_stderr(stderr):
                code = hy_fix_rrf_pool_validate.main(["--run", run_id])
            output_path = (
                run_dir
                / "analysis"
                / "hy_fix_rrf_pool"
                / "rrf_pool_policy_validation.json"
            )

        self.assertEqual(code, 1)
        self.assertIn("required input file missing", stderr.getvalue())
        self.assertFalse(output_path.exists())

    def test_script_stays_analysis_only(self):
        source = Path(hy_fix_rrf_pool_validate.__file__).read_text(encoding="utf-8")
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
                if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_import_prefixes)
            ]
        )
        for forbidden_text in ("ollama", "requests.", "urllib.", "socket.", "subprocess."):
            self.assertNotIn(forbidden_text, source.lower())


if __name__ == "__main__":
    unittest.main()
