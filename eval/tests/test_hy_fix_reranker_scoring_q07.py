import ast
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from eval.scripts import _run_io, hy_fix_reranker_scoring_q07


RUN_ID = "2026-05-22-0300-nogit"


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
                "qid": "q07",
                "tmdb_id": 63700,
                "title": "My Babysitter's a Vampire",
                "consolidated_fix_category": "reranker_scoring",
                "arms": {
                    "pinned": _localization_arm(rerank_rank=20, final_rank=25),
                    "no_llm": _localization_arm(rerank_rank=17, final_rank=29),
                },
            }
        ],
    }


def _localization_arm(*, rerank_rank, final_rank):
    return {
        "loss_stage": "rerank_demoted",
        "fix_category": "reranker_scoring",
        "stage_table": {
            "semantic": {"present": True, "rank": 3, "score": 0.57},
            "rrf": {"present": True, "rank": 11, "score": 0.05},
            "rerank": {
                "in_pool": True,
                "rerank_score": 0.0124671,
                "rerank_rank": rerank_rank,
            },
            "final": {
                "final_score": 0.18,
                "final_rank": final_rank,
                "in_top5": False,
            },
        },
    }


def _stability_rows():
    rows = []
    for arm, rerank_rank, final_rank in (
        ("pinned", 20, 25),
        ("no_llm", 17, 29),
        ("live", 16, 20),
    ):
        for repeat in range(2):
            rows.append(
                {
                    "schema_version": "hy-stab-01.v1",
                    "run_id": RUN_ID,
                    "arm": arm,
                    "qid": "q07",
                    "tmdb_id": 63700,
                    "rerank": {"in_pool": True, "rerank_rank": rerank_rank},
                    "final": {"final_rank": final_rank, "in_top5": False},
                    "loss_classification": "rerank_demoted",
                    "repeat": repeat,
                }
            )
    return rows


def _error_rows():
    return [
        {
            "qid": "q07",
            "mode": "basic",
            "k": 5,
            "strict_hit_at_k": 1,
            "first_relevant_rank": 2,
            "first_perfect_rank": 5,
            "top": [{"rank": 5, "title": "My Babysitter's a Vampire"}],
        },
        {
            "qid": "q07",
            "mode": "hybrid",
            "k": 5,
            "strict_hit_at_k": 0,
            "first_relevant_rank": 5,
            "first_perfect_rank": None,
            "top": [{"rank": 1, "title": "What We Do in the Shadows"}],
        },
    ]


def _candidate_rows():
    return [
        {
            "qid": "q07",
            "tmdb_id": 411354,
            "title": "What We Do in the Shadows: Interviews with Some Vampires",
            "per_mode": {
                "hybrid": {
                    "rank": 0,
                    "rerank_score": 0.734,
                    "rrf_score": 0.08,
                    "final_score": 1.05,
                }
            },
        },
        {
            "qid": "q07",
            "tmdb_id": 63700,
            "title": "My Babysitter's a Vampire",
            "per_mode": {
                "basic": {
                    "rank": 4,
                    "semantic_score": 0.563,
                    "final_score": 0.563,
                }
            },
        },
    ]


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
    _write_jsonl(run_dir / "candidates.jsonl", _candidate_rows())
    _write_jsonl(
        run_dir / "analysis" / "error_report" / "per_query_mode.gold.jsonl",
        _error_rows(),
    )


def _policies(data):
    return {policy["policy_id"]: policy for policy in data["policies"]}


class HyFixRerankerScoringQ07Tests(unittest.TestCase):
    def test_run_writes_analysis_without_src_implementation_recommendation(self):
        with _temporary_project() as (run_id, run_dir):
            _write_inputs(run_dir)
            actual_run_id, output_path, data = hy_fix_reranker_scoring_q07.run(run_id)
            self.assertTrue(output_path.exists())

        self.assertEqual(actual_run_id, RUN_ID)
        self.assertEqual(data["schema_version"], "hy-fix-03-reranker-q07.v1")
        self.assertFalse(data["implementation_recommended"])
        self.assertIsNone(data["recommended_policy"])
        self.assertEqual(data["implementation_allowed_files"], [])
        self.assertEqual(
            data["decision"]["next_action"],
            "continue_to_mixed_q05_q10_analysis",
        )

    def test_records_q07_deterministic_rerank_and_final_ranks(self):
        data = hy_fix_reranker_scoring_q07.build_analysis(
            RUN_ID,
            {
                "localization": _localization(),
                "stability_rows": _stability_rows(),
                "candidate_rows": _candidate_rows(),
                "error_rows": _error_rows(),
            },
        )
        arms = data["evidence"]["deterministic_arms"]

        self.assertEqual(arms["pinned"]["rerank_rank"], 20)
        self.assertEqual(arms["no_llm"]["rerank_rank"], 17)
        self.assertEqual(arms["pinned"]["final_rank"], 25)
        self.assertEqual(arms["no_llm"]["final_rank"], 29)
        self.assertFalse(arms["pinned"]["in_top5"])

    def test_records_basic_hit_and_hybrid_perfect_miss(self):
        data = hy_fix_reranker_scoring_q07.build_analysis(
            RUN_ID,
            {
                "localization": _localization(),
                "stability_rows": _stability_rows(),
                "candidate_rows": _candidate_rows(),
                "error_rows": _error_rows(),
            },
        )
        modes = data["evidence"]["mode_comparison"]

        self.assertEqual(modes["basic"]["first_perfect_rank"], 5)
        self.assertIsNone(modes["hybrid"]["first_perfect_rank"])
        self.assertEqual(modes["hybrid"]["strict_hit_at_k"], 0)

    def test_policy_blockers_are_explicit(self):
        policies = _policies(
            hy_fix_reranker_scoring_q07.build_analysis(
                RUN_ID,
                {
                    "localization": _localization(),
                    "stability_rows": _stability_rows(),
                    "candidate_rows": _candidate_rows(),
                    "error_rows": _error_rows(),
                },
            )
        )

        self.assertEqual(
            set(policies),
            {
                "final_blend_reweight_only",
                "reranker_document_text_change",
                "rerank_query_change",
                "final_top_k_expand_only",
            },
        )
        self.assertIn(
            "full_q07_pool_score_decomposition_is_missing",
            policies["final_blend_reweight_only"]["stop_reason"],
        )
        self.assertEqual(
            policies["final_top_k_expand_only"][
                "minimum_final_top_k_needed_if_rank_is_zero_based"
            ],
            30,
        )
        self.assertFalse(
            any(policy["safe_enough_for_hy_fix_03"] for policy in policies.values())
        )

    def test_cli_writes_artifact_and_reports_next_action(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            _write_inputs(run_dir)
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = hy_fix_reranker_scoring_q07.main(["--run", run_id])
            output_path = (
                run_dir
                / "analysis"
                / "hy_fix_reranker_scoring"
                / "q07_reranker_scoring_analysis.json"
            )
            self.assertTrue(output_path.exists())

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn("implementation_recommended=False", stdout.getvalue())
        self.assertIn("recommended_policy=None", stdout.getvalue())
        self.assertIn("next_action=continue_to_mixed_q05_q10_analysis", stdout.getvalue())

    def test_missing_inputs_fail_without_writing_output(self):
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            with redirect_stderr(stderr):
                code = hy_fix_reranker_scoring_q07.main(["--run", run_id])
            output_path = (
                run_dir
                / "analysis"
                / "hy_fix_reranker_scoring"
                / "q07_reranker_scoring_analysis.json"
            )

        self.assertEqual(code, 1)
        self.assertIn("required input file missing", stderr.getvalue())
        self.assertFalse(output_path.exists())

    def test_script_stays_analysis_only(self):
        source = Path(hy_fix_reranker_scoring_q07.__file__).read_text(encoding="utf-8")
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
