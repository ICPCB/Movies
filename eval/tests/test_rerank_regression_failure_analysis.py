"""Tests for eval.scripts.rerank_regression_failure_analysis."""

from __future__ import annotations

import unittest

from eval.scripts.rerank_regression_failure_analysis import (
    analyze_baseline_top,
    classify_failure,
    get_gold_targets,
    find_in_pool,
    summarize_patterns,
    recommend_direction,
)


class TestGetGoldTargets(unittest.TestCase):
    def test_filters_by_grade(self):
        gold = {
            ("q01", 1): {"qid": "q01", "tmdb_id": 1, "gold_grade": 3, "grade": 3, "label_source": "gold"},
            ("q01", 2): {"qid": "q01", "tmdb_id": 2, "gold_grade": 1, "grade": 1, "label_source": "silver"},
            ("q01", 3): {"qid": "q01", "tmdb_id": 3, "gold_grade": 2, "grade": 2, "label_source": "silver"},
            ("q02", 4): {"qid": "q02", "tmdb_id": 4, "gold_grade": 3, "grade": 3, "label_source": "gold"},
        }
        targets = get_gold_targets(gold, "q01", min_grade=2)
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0]["tmdb_id"], 1)
        self.assertEqual(targets[1]["tmdb_id"], 3)

    def test_empty_for_no_matches(self):
        gold = {("q01", 1): {"qid": "q01", "tmdb_id": 1, "gold_grade": 1, "grade": 1, "label_source": "s"}}
        self.assertEqual(get_gold_targets(gold, "q01"), [])

    def test_falls_back_to_grade_field(self):
        gold = {("q01", 1): {"qid": "q01", "tmdb_id": 1, "gold_grade": None, "grade": 3, "label_source": "s"}}
        targets = get_gold_targets(gold, "q01")
        self.assertEqual(len(targets), 1)


class TestFindInPool(unittest.TestCase):
    def test_finds_matching_tmdb_id(self):
        pool = [{"tmdb_id": 1, "title": "A"}, {"tmdb_id": 2, "title": "B"}]
        self.assertEqual(find_in_pool(pool, 2)["title"], "B")

    def test_returns_none_if_missing(self):
        pool = [{"tmdb_id": 1, "title": "A"}]
        self.assertIsNone(find_in_pool(pool, 99))


class TestAnalyzeBaselineTop(unittest.TestCase):
    def test_counts_targets_in_top5(self):
        baseline_top = [
            {"tmdb_id": 1, "rank": 0, "title": "A", "rerank_score": 0.9, "final_score": 0.8},
            {"tmdb_id": 2, "rank": 1, "title": "B", "rerank_score": 0.8, "final_score": 0.7},
            {"tmdb_id": 3, "rank": 2, "title": "C", "rerank_score": 0.7, "final_score": 0.6},
            {"tmdb_id": 4, "rank": 5, "title": "D", "rerank_score": 0.5, "final_score": 0.4},
        ]
        targets = [{"tmdb_id": 1, "grade": 3}, {"tmdb_id": 4, "grade": 2}]
        result = analyze_baseline_top(baseline_top, targets, [], "test query")
        self.assertEqual(result["targets_in_top5_count"], 1)
        self.assertEqual(len(result["non_targets_in_top5"]), 2)

    def test_targets_not_in_top(self):
        baseline_top = [{"tmdb_id": 1, "rank": 0, "title": "A", "rerank_score": 0.9}]
        targets = [{"tmdb_id": 99, "grade": 3}]
        pool = [{"tmdb_id": 99, "movie_key": "title:test|year:2020", "title": "Test", "rrf_score": 0.1}]
        result = analyze_baseline_top(baseline_top, targets, pool, "test")
        self.assertEqual(len(result["targets_not_in_baseline_top"]), 1)
        self.assertTrue(result["targets_not_in_baseline_top"][0]["in_pool"])


class TestClassifyFailure(unittest.TestCase):
    def test_miss_to_hit_is_semantic_target_demoted(self):
        ba = {"targets_in_top5_count": 0, "non_targets_in_top5": []}
        self.assertEqual(classify_failure(ba, "miss_to_hit", "test", 3), "semantic_target_demoted")

    def test_hit_to_miss_with_targets_in_top5(self):
        ba = {"targets_in_top5_count": 2, "non_targets_in_top5": []}
        self.assertEqual(classify_failure(ba, "hit_to_miss", "test query", 3), "semantic_target_demoted")

    def test_surface_match_detection(self):
        ba = {
            "targets_in_top5_count": 1,
            "non_targets_in_top5": [{"title": "robot space adventure"}],
        }
        self.assertEqual(
            classify_failure(ba, "hit_to_miss", "a trash robot falls in love in space", 3),
            "over_promotes_surface_match",
        )

    def test_genre_drift_for_many_targets(self):
        ba = {"targets_in_top5_count": 2, "non_targets_in_top5": []}
        self.assertEqual(classify_failure(ba, "hit_to_miss", "test", 8), "genre_or_intent_drift")

    def test_inconclusive_for_unchanged(self):
        ba = {"targets_in_top5_count": 0, "non_targets_in_top5": []}
        self.assertEqual(classify_failure(ba, "unchanged", "test", 3), "artifact_inconclusive")


class TestSummarizePatterns(unittest.TestCase):
    def test_counts_regressions_and_fixes(self):
        analyses = [
            {
                "qid": "q01",
                "mode_analyses": {
                    "advanced": {"change": "hit_to_miss", "baseline_top_analysis": {"targets_in_top5_count": 2}},
                    "hybrid": {"change": "hit_to_miss", "baseline_top_analysis": {"targets_in_top5_count": 2}},
                },
                "failure_mode": "semantic_target_demoted",
            },
            {
                "qid": "q10",
                "mode_analyses": {
                    "advanced": {"change": "miss_to_hit", "baseline_top_analysis": {"targets_in_top5_count": 0}},
                    "hybrid": {"change": "miss_to_hit", "baseline_top_analysis": {"targets_in_top5_count": 0}},
                },
                "failure_mode": "semantic_target_demoted",
            },
        ]
        s = summarize_patterns(analyses)
        self.assertEqual(s["total_regressions"], 1)
        self.assertEqual(s["total_fixes"], 1)
        self.assertTrue(s["all_regressions_in_both_modes"])


class TestRecommendDirection(unittest.TestCase):
    def test_direction_b_for_many_regressions(self):
        summary = {
            "total_regressions": 7,
            "total_fixes": 1,
            "all_regressions_in_both_modes": True,
            "failure_mode_distribution": {"semantic_target_demoted": ["q01", "q03", "q04", "q11", "q12", "q15", "q18"]},
        }
        r = recommend_direction(summary, [])
        self.assertEqual(r["recommended_direction"], "B")
        self.assertTrue(r["alibaba_assessment"]["viable_diagnostic_tool_only"])

    def test_direction_a_for_no_regressions(self):
        summary = {
            "total_regressions": 0,
            "total_fixes": 1,
            "all_regressions_in_both_modes": True,
            "failure_mode_distribution": {},
        }
        r = recommend_direction(summary, [])
        self.assertEqual(r["recommended_direction"], "A")
        self.assertTrue(r["alibaba_assessment"]["viable_global_replacement"])


if __name__ == "__main__":
    unittest.main()
