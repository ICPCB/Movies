import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from eval.scripts import _run_io, hy_fix_localize


RUN_ID = "2026-05-19-1200-nogit"
TARGETS = {
    "q05": (144204, "Thanatomorphose"),
    "q07": (63700, "My Babysitter's a Vampire"),
    "q08": (545611, "Everything Everywhere All at Once"),
    "q10": (8329, "[REC]"),
}
DEFAULT_LOSSES = {
    "q05": {
        "pinned": "retrieved_dropped_before_rerank_pool",
        "no_llm": "rerank_recovered_final_demoted",
    },
    "q07": {"pinned": "rerank_demoted", "no_llm": "rerank_demoted"},
    "q08": {
        "pinned": "retrieved_dropped_before_rerank_pool",
        "no_llm": "retrieved_dropped_before_rerank_pool",
    },
    "q10": {
        "pinned": "retrieved_dropped_before_rerank_pool",
        "no_llm": "rerank_demoted",
    },
}


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


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _diagnosis(*, fixed_qids=None):
    if fixed_qids is None:
        fixed_qids = hy_fix_localize.FIXED_DEFECT_QIDS
    entries = []
    for qid in fixed_qids:
        tmdb_id, title = TARGETS.get(qid, (9000, "Other"))
        entries.append(
            {
                "qid": qid,
                "tmdb_id": tmdb_id,
                "title": title,
                "attribution": "fixed_defect",
            }
        )
    return {
        "schema_version": "hy-stab-01.v1",
        "run_id": RUN_ID,
        "trace_meta": {
            "config": {
                "CANDIDATE_POOL": 1500,
                "RERANK_POOL": 800,
                "RERANK_TOP_K": 50,
                "FINAL_TOP_K": 5,
                "RRF_K": 15,
            }
        },
        "instability_attribution": entries,
    }


def _stage_blocks(loss_stage, *, final_rank=None):
    if loss_stage == "unretrieved":
        return {
            "semantic": {"present": False, "rank": None, "score": None, "list_len": 10},
            "bm25": {"present": False, "rank": None, "score": None, "list_len": 10},
            "rrf": {"present": False, "rank": None, "score": None, "list_len": 8},
            "rerank": {"in_pool": False, "rerank_score": None, "rerank_rank": None},
            "final": {
                "final_score": None,
                "final_rank": None,
                "in_top5": False,
                "in_top15": False,
            },
        }
    if loss_stage == "retrieved_dropped_at_fusion":
        return {
            "semantic": {"present": True, "rank": 7, "score": 0.7, "list_len": 10},
            "bm25": {"present": False, "rank": None, "score": None, "list_len": 10},
            "rrf": {"present": False, "rank": None, "score": None, "list_len": 8},
            "rerank": {"in_pool": False, "rerank_score": None, "rerank_rank": None},
            "final": {
                "final_score": None,
                "final_rank": None,
                "in_top5": False,
                "in_top15": False,
            },
        }
    if loss_stage == "retrieved_dropped_before_rerank_pool":
        return {
            "semantic": {"present": True, "rank": 6, "score": 0.6, "list_len": 10},
            "bm25": {"present": False, "rank": None, "score": None, "list_len": 10},
            "rrf": {"present": True, "rank": 55, "score": 0.01, "list_len": 80},
            "rerank": {"in_pool": False, "rerank_score": None, "rerank_rank": None},
            "final": {
                "final_score": None,
                "final_rank": None,
                "in_top5": False,
                "in_top15": False,
            },
        }
    if loss_stage == "rerank_demoted":
        rank = 9 if final_rank is None else final_rank
        return {
            "semantic": {"present": True, "rank": 3, "score": 0.8, "list_len": 10},
            "bm25": {"present": True, "rank": 4, "score": 4.0, "list_len": 10},
            "rrf": {"present": True, "rank": 8, "score": 0.04, "list_len": 80},
            "rerank": {"in_pool": True, "rerank_score": 0.2, "rerank_rank": 7},
            "final": {
                "final_score": 0.3,
                "final_rank": rank,
                "in_top5": False,
                "in_top15": True,
            },
        }
    if loss_stage == "rerank_recovered_final_demoted":
        rank = 8 if final_rank is None else final_rank
        return {
            "semantic": {"present": True, "rank": 2, "score": 0.9, "list_len": 10},
            "bm25": {"present": True, "rank": 3, "score": 5.0, "list_len": 10},
            "rrf": {"present": True, "rank": 5, "score": 0.05, "list_len": 80},
            "rerank": {"in_pool": True, "rerank_score": 0.9, "rerank_rank": 2},
            "final": {
                "final_score": 0.4,
                "final_rank": rank,
                "in_top5": False,
                "in_top15": True,
            },
        }
    if loss_stage == "hybrid_top5_hit":
        rank = 2 if final_rank is None else final_rank
        return {
            "semantic": {"present": True, "rank": 1, "score": 1.0, "list_len": 10},
            "bm25": {"present": True, "rank": 1, "score": 10.0, "list_len": 10},
            "rrf": {"present": True, "rank": 1, "score": 0.1, "list_len": 80},
            "rerank": {"in_pool": True, "rerank_score": 1.0, "rerank_rank": 1},
            "final": {
                "final_score": 1.0,
                "final_rank": rank,
                "in_top5": True,
                "in_top15": True,
            },
        }
    return {
        "semantic": {"present": False, "rank": None, "score": None, "list_len": 10},
        "bm25": {"present": False, "rank": None, "score": None, "list_len": 10},
        "rrf": {"present": False, "rank": None, "score": None, "list_len": 8},
        "rerank": {"in_pool": False, "rerank_score": None, "rerank_rank": None},
        "final": {
            "final_score": None,
            "final_rank": None,
            "in_top5": False,
            "in_top15": False,
        },
    }


def _trace_row(arm, qid, repeat, loss_stage, *, final_rank=None):
    tmdb_id, title = TARGETS[qid]
    row = {
        "schema_version": "hy-stab-01.v1",
        "run_id": RUN_ID,
        "arm": arm,
        "qid": qid,
        "tmdb_id": tmdb_id,
        "title": title,
        "repeat": repeat,
        "loss_classification": loss_stage,
    }
    row.update(_stage_blocks(loss_stage, final_rank=final_rank))
    return row


def _trace_rows():
    rows = []
    live_plan = {
        "q05": [
            ("retrieved_dropped_before_rerank_pool", None),
            ("rerank_recovered_final_demoted", 8),
            ("rerank_demoted", 10),
        ],
        "q07": [("rerank_demoted", 20), ("rerank_demoted", 22)],
        "q08": [
            ("retrieved_dropped_before_rerank_pool", None),
            ("retrieved_dropped_at_fusion", None),
        ],
        "q10": [("rerank_demoted", 8), ("retrieved_dropped_before_rerank_pool", None)],
    }
    for qid in hy_fix_localize.FIXED_DEFECT_QIDS:
        for arm in ("pinned", "no_llm"):
            for repeat in range(2):
                rows.append(_trace_row(arm, qid, repeat, DEFAULT_LOSSES[qid][arm]))
        for repeat, (loss_stage, final_rank) in enumerate(live_plan[qid]):
            rows.append(_trace_row("live", qid, repeat, loss_stage, final_rank=final_rank))
    return rows


def _write_project(run_dir, *, diagnosis=None, rows=None, include_trace=True):
    analysis_dir = run_dir / "analysis" / "hybrid_expansion_stability"
    _write_json(
        analysis_dir / "stability_diagnosis.json",
        diagnosis if diagnosis is not None else _diagnosis(),
    )
    if include_trace:
        _write_jsonl(
            analysis_dir / "stability_trace.jsonl",
            rows if rows is not None else _trace_rows(),
        )


class HyFixLocalizeTest(unittest.TestCase):
    def test_fix_category_recall_depth(self):
        for loss_stage in (
            "unretrieved",
            "retrieved_dropped_at_fusion",
            "retrieved_dropped_before_rerank_pool",
        ):
            self.assertEqual(
                hy_fix_localize.fix_category_for_loss(loss_stage),
                "recall_depth_fusion_pool",
            )

    def test_fix_category_reranker(self):
        self.assertEqual(
            hy_fix_localize.fix_category_for_loss("rerank_demoted"),
            "reranker_scoring",
        )

    def test_fix_category_final_blend(self):
        self.assertEqual(
            hy_fix_localize.fix_category_for_loss(
                "rerank_recovered_final_demoted"
            ),
            "final_blend",
        )

    def test_consolidated_agree(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            data = hy_fix_localize.build_localization(run_id)

        q08 = _target(data, "q08")
        self.assertTrue(q08["arms_agree"])
        self.assertEqual(
            q08["consolidated_fix_category"], "recall_depth_fusion_pool"
        )

    def test_consolidated_mixed(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            data = hy_fix_localize.build_localization(run_id)

        q05 = _target(data, "q05")
        self.assertFalse(q05["arms_agree"])
        self.assertEqual(q05["consolidated_fix_category"], "mixed")

    def test_deterministic_arm_assertion(self):
        rows = _trace_rows()
        for row in rows:
            if row["qid"] == "q08" and row["arm"] == "pinned" and row["repeat"] == 1:
                row["final"]["final_rank"] = 99

        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir, rows=rows)
            with self.assertRaises(hy_fix_localize.HyFixLocalizeError):
                hy_fix_localize.build_localization(run_id)

    def test_fixed_defect_qids_mismatch(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir, diagnosis=_diagnosis(fixed_qids=("q05",)))
            with self.assertRaises(hy_fix_localize.HyFixLocalizeError):
                hy_fix_localize.build_localization(run_id)

    def test_live_arm_summary(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            data = hy_fix_localize.build_localization(run_id)

        live = _target(data, "q05")["arms"]["live"]
        self.assertFalse(live["deterministic"])
        self.assertEqual(live["repeats"], 3)
        self.assertEqual(
            live["loss_stage_per_repeat"],
            [
                "retrieved_dropped_before_rerank_pool",
                "rerank_recovered_final_demoted",
                "rerank_demoted",
            ],
        )
        self.assertEqual(
            live["final_rank_summary"],
            {"min": 8, "median": 9.0, "max": 10, "n_present": 2},
        )

    def test_missing_input_exits_nonzero(self):
        stderr = io.StringIO()
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir, include_trace=False)
            with redirect_stderr(stderr):
                exit_code = hy_fix_localize.main(["--run", run_id])

            self.assertNotEqual(exit_code, 0)
            self.assertIn("stability_trace.jsonl", stderr.getvalue())
            self.assertFalse(
                (run_dir / "analysis" / "hy_fix_localize").exists()
            )

    def test_localization_schema_and_recommended_sequence(self):
        with _temporary_project() as (run_id, run_dir):
            _write_project(run_dir)
            output_path, data = hy_fix_localize.write_localization(run_id)

            self.assertTrue(output_path.exists())
            loaded = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(loaded, data)
        self.assertEqual(data["schema_version"], "hy-fix-01.v1")
        self.assertEqual(data["run_id"], RUN_ID)
        self.assertEqual(
            data["source_artifacts"],
            {
                "stability_trace": (
                    "analysis/hybrid_expansion_stability/stability_trace.jsonl"
                ),
                "stability_diagnosis": (
                    "analysis/hybrid_expansion_stability/stability_diagnosis.json"
                ),
            },
        )
        self.assertEqual(
            data["fixed_defect_qids"],
            list(hy_fix_localize.FIXED_DEFECT_QIDS),
        )
        self.assertEqual(
            data["priority_order"], list(hy_fix_localize.PRIORITY_ORDER)
        )
        self.assertEqual(
            data["stage_pipeline"], ["semantic", "bm25", "rrf", "rerank", "final"]
        )
        self.assertEqual(
            data["config"],
            {
                "CANDIDATE_POOL": 1500,
                "RERANK_POOL": 800,
                "RERANK_TOP_K": 50,
                "FINAL_TOP_K": 5,
            },
        )
        self.assertEqual([target["qid"] for target in data["per_target"]], ["q05", "q07", "q08", "q10"])
        self.assertEqual(sum(data["fix_category_summary"].values()), 4)
        self.assertEqual(
            data["recommended_sequence"],
            list(hy_fix_localize.PRIORITY_ORDER),
        )
        self.assertEqual(
            data["recommended_first_fix"], "recall_depth_fusion_pool"
        )


def _target(data, qid):
    for target in data["per_target"]:
        if target["qid"] == qid:
            return target
    raise AssertionError(f"target not found: {qid}")


if __name__ == "__main__":
    unittest.main()
