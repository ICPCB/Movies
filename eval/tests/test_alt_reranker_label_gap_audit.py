"""Tests for alt_reranker_label_gap_audit.py."""
from __future__ import annotations

import json
import py_compile
from pathlib import Path

import pytest

from eval.scripts.alt_reranker_label_gap_audit import find_unlabeled


def _make_top15_data(per_qid: dict) -> dict:
    return {"per_qid_top15": per_qid}


def _make_candidates(tmdb_ids: list[int]) -> list[dict]:
    return [
        {"tmdb_id": tid, "title": f"Movie {tid}", "movie_key": f"m{tid}", "rank": i}
        for i, tid in enumerate(tmdb_ids)
    ]


class TestCompile:
    def test_py_compile(self):
        py_compile.compile(
            "eval/scripts/alt_reranker_label_gap_audit.py", doraise=True
        )


class TestFindUnlabeled:
    def test_basic_gap_detection(self):
        top15 = _make_top15_data({
            "q01": {
                "alt": {
                    "advanced": _make_candidates([100, 200, 300]),
                    "hybrid": _make_candidates([100, 200, 400]),
                },
                "baseline": {
                    "advanced": _make_candidates([100, 500]),
                    "hybrid": _make_candidates([100, 600]),
                },
            },
        })
        labeled = {("q01", 100), ("q01", 200)}
        report = find_unlabeled(top15, labeled)

        assert report["total_unlabeled_alt"] == 2  # 300, 400
        assert report["total_unlabeled_baseline"] == 2  # 500, 600
        gaps = report["per_query_gaps"]["q01"]
        assert gaps["alt_unlabeled"] == 2
        assert gaps["baseline_unlabeled"] == 2

    def test_dedup_across_modes(self):
        top15 = _make_top15_data({
            "q01": {
                "alt": {
                    "advanced": _make_candidates([100, 200]),
                    "hybrid": _make_candidates([100, 200]),
                },
                "baseline": {
                    "advanced": _make_candidates([100]),
                    "hybrid": _make_candidates([100]),
                },
            },
        })
        labeled = {("q01", 100)}
        report = find_unlabeled(top15, labeled)

        unlabeled_tmdb_ids = [c["tmdb_id"] for c in report["unlabeled_candidates"]]
        assert unlabeled_tmdb_ids == [200]
        assert "advanced" in report["unlabeled_candidates"][0]["modes"]
        assert "hybrid" in report["unlabeled_candidates"][0]["modes"]

    def test_fully_labeled_zero_gaps(self):
        top15 = _make_top15_data({
            "q01": {
                "alt": {
                    "advanced": _make_candidates([100, 200]),
                },
                "baseline": {
                    "advanced": _make_candidates([100, 200]),
                },
            },
        })
        labeled = {("q01", 100), ("q01", 200)}
        report = find_unlabeled(top15, labeled)

        assert report["total_unlabeled_alt"] == 0
        assert report["total_unlabeled_baseline"] == 0
        assert report["total_unlabeled_union"] == 0
        assert report["per_query_gaps"]["q01"]["union_unlabeled"] == 0
        assert report["unlabeled_candidates"] == []

    def test_deterministic_ordering(self):
        top15 = _make_top15_data({
            "q02": {
                "alt": {"advanced": _make_candidates([300])},
                "baseline": {"advanced": _make_candidates([300])},
            },
            "q01": {
                "alt": {"advanced": _make_candidates([200, 100])},
                "baseline": {"advanced": _make_candidates([100])},
            },
        })
        labeled = set()
        report = find_unlabeled(top15, labeled)

        qids = [c["qid"] for c in report["unlabeled_candidates"]]
        tmdb_ids = [c["tmdb_id"] for c in report["unlabeled_candidates"]]
        assert qids == sorted(qids)
        for i in range(len(qids) - 1):
            if qids[i] == qids[i + 1]:
                assert tmdb_ids[i] <= tmdb_ids[i + 1]

    def test_multi_query(self):
        top15 = _make_top15_data({
            "q01": {
                "alt": {"advanced": _make_candidates([100, 200])},
                "baseline": {"advanced": _make_candidates([100])},
            },
            "q02": {
                "alt": {"advanced": _make_candidates([300, 400])},
                "baseline": {"advanced": _make_candidates([300])},
            },
        })
        labeled = {("q01", 100), ("q02", 300)}
        report = find_unlabeled(top15, labeled)

        assert report["per_query_gaps"]["q01"]["alt_unlabeled"] == 1
        assert report["per_query_gaps"]["q02"]["alt_unlabeled"] == 1
        assert report["total_unlabeled_union"] == 2

    def test_alt_modes_with_gaps(self):
        top15 = _make_top15_data({
            "q01": {
                "alt": {
                    "advanced": _make_candidates([100, 200]),
                    "basic": _make_candidates([100]),
                    "hybrid": _make_candidates([100, 300]),
                },
                "baseline": {
                    "advanced": _make_candidates([100]),
                    "basic": _make_candidates([100]),
                    "hybrid": _make_candidates([100]),
                },
            },
        })
        labeled = {("q01", 100)}
        report = find_unlabeled(top15, labeled)

        gaps = report["per_query_gaps"]["q01"]
        assert "advanced" in gaps["alt_modes_with_gaps"]
        assert "hybrid" in gaps["alt_modes_with_gaps"]
        assert "basic" not in gaps["alt_modes_with_gaps"]

    def test_source_tracking(self):
        top15 = _make_top15_data({
            "q01": {
                "alt": {"advanced": _make_candidates([100])},
                "baseline": {"advanced": _make_candidates([100])},
            },
        })
        labeled = set()
        report = find_unlabeled(top15, labeled)

        cand = report["unlabeled_candidates"][0]
        assert "alt" in cand["sources"]
        assert "baseline" in cand["sources"]

    def test_schema_version(self):
        top15 = _make_top15_data({"q01": {"alt": {}, "baseline": {}}})
        report = find_unlabeled(top15, set())
        assert report["schema_version"] == 1
        assert "generated_at" in report


class TestEndToEnd:
    def test_main_with_files(self, tmp_path):
        analysis_dir = tmp_path / "analysis" / "rerank_regression"
        analysis_dir.mkdir(parents=True)

        top15 = _make_top15_data({
            "q01": {
                "alt": {"advanced": _make_candidates([100, 200])},
                "baseline": {"advanced": _make_candidates([100])},
            },
        })
        with open(analysis_dir / "score_stage_top15.json", "w") as f:
            json.dump(top15, f)

        labels = [
            {"qid": "q01", "tmdb_id": 100, "grade": 3, "label_source": "gold",
             "silver_grade": None, "gold_grade": 3, "gold_notes": None},
        ]
        with open(tmp_path / "gold_labels.jsonl", "w") as f:
            for lb in labels:
                f.write(json.dumps(lb) + "\n")

        from eval.scripts.alt_reranker_label_gap_audit import main
        main([str(tmp_path)])

        out_path = analysis_dir / "alt_label_gap_audit.json"
        assert out_path.exists()
        with open(out_path) as f:
            report = json.load(f)
        assert report["total_unlabeled_alt"] == 1
        assert report["unlabeled_candidates"][0]["tmdb_id"] == 200
