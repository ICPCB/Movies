"""Tests for eval.scripts.rerank_blend_weight_simulation."""

from __future__ import annotations

import unittest

from eval.scripts.rerank_blend_weight_simulation import (
    build_pool_lookup,
    check_strict_hit_at_k,
    generate_weight_sets,
    recompute_final_scores,
    source_agreement,
    upstream_score,
)


class TestSourceAgreement(unittest.TestCase):
    def test_both_ranks_present(self):
        self.assertEqual(source_agreement({"semantic_rank": 1, "bm25_rank": 3}), 1.0)

    def test_missing_bm25(self):
        self.assertEqual(source_agreement({"semantic_rank": 1}), 0.0)

    def test_missing_both(self):
        self.assertEqual(source_agreement({}), 0.0)


class TestUpstreamScore(unittest.TestCase):
    def test_rrf_score(self):
        self.assertAlmostEqual(upstream_score({"rrf_score": 0.5}), 0.5)

    def test_fallback_to_semantic(self):
        self.assertAlmostEqual(upstream_score({"semantic_score": 0.3}), 0.3)

    def test_zero_default(self):
        self.assertEqual(upstream_score({}), 0.0)


class TestBuildPoolLookup(unittest.TestCase):
    def test_lookup_by_tmdb_id(self):
        pool = [{"tmdb_id": 1, "title": "A"}, {"tmdb_id": 2, "title": "B"}]
        lookup = build_pool_lookup(pool)
        self.assertEqual(lookup[1]["title"], "A")
        self.assertEqual(lookup[2]["title"], "B")


class TestRecomputeFinalScores(unittest.TestCase):
    def test_reorders_by_new_weights(self):
        baseline_top = [
            {"tmdb_id": 1, "rerank_score": 0.5, "final_score": 0.8, "rank": 0, "title": "A"},
            {"tmdb_id": 2, "rerank_score": 0.9, "final_score": 0.7, "rank": 1, "title": "B"},
        ]
        pool = [
            {"tmdb_id": 1, "vote_count": 10000, "rrf_score": 0.3, "semantic_rank": 1, "bm25_rank": 2},
            {"tmdb_id": 2, "vote_count": 100, "rrf_score": 0.1, "semantic_rank": 5, "bm25_rank": None},
        ]
        pool_lookup = build_pool_lookup(pool)
        # With high upstream weight, entry 1 (high votes, high rrf) stays first
        high_upstream = {"rerank_upstream_weight": 0.50, "rerank_vote_count_weight": 0.30, "rerank_source_agreement_bonus": 0.10}
        result = recompute_final_scores(baseline_top, pool_lookup, pool, high_upstream)
        self.assertEqual(result[0]["tmdb_id"], 1)

        # With zero upstream weight, entry 2 (higher rerank_score) should be first
        zero_upstream = {"rerank_upstream_weight": 0.0, "rerank_vote_count_weight": 0.0, "rerank_source_agreement_bonus": 0.0}
        result = recompute_final_scores(baseline_top, pool_lookup, pool, zero_upstream)
        self.assertEqual(result[0]["tmdb_id"], 2)

    def test_empty_baseline_top(self):
        result = recompute_final_scores([], {}, [], {"rerank_upstream_weight": 0.2, "rerank_vote_count_weight": 0.08, "rerank_source_agreement_bonus": 0.1})
        self.assertEqual(result, [])


class TestCheckStrictHitAtK(unittest.TestCase):
    def test_hit_when_grade3_in_top_k(self):
        entries = [{"tmdb_id": 1}, {"tmdb_id": 2}, {"tmdb_id": 3}]
        gold = {("q01", 2): {"qid": "q01", "tmdb_id": 2, "gold_grade": 3, "grade": 3}}
        self.assertTrue(check_strict_hit_at_k(entries, gold, "q01", k=3))

    def test_miss_when_grade3_outside_k(self):
        entries = [{"tmdb_id": 1}, {"tmdb_id": 2}, {"tmdb_id": 3}]
        gold = {("q01", 3): {"qid": "q01", "tmdb_id": 3, "gold_grade": 3, "grade": 3}}
        self.assertFalse(check_strict_hit_at_k(entries, gold, "q01", k=2))

    def test_miss_when_grade2_only(self):
        entries = [{"tmdb_id": 1}]
        gold = {("q01", 1): {"qid": "q01", "tmdb_id": 1, "gold_grade": 2, "grade": 2}}
        self.assertFalse(check_strict_hit_at_k(entries, gold, "q01", k=5))

    def test_miss_when_grade1(self):
        entries = [{"tmdb_id": 1}]
        gold = {("q01", 1): {"qid": "q01", "tmdb_id": 1, "gold_grade": 1, "grade": 1}}
        self.assertFalse(check_strict_hit_at_k(entries, gold, "q01", k=5))


class TestGenerateWeightSets(unittest.TestCase):
    def test_generates_combinations(self):
        sets = generate_weight_sets()
        self.assertGreater(len(sets), 10)
        self.assertIn("rerank_upstream_weight", sets[0])
        self.assertIn("rerank_vote_count_weight", sets[0])
        self.assertIn("rerank_source_agreement_bonus", sets[0])

    def test_includes_current_weights(self):
        sets = generate_weight_sets()
        current = {"rerank_upstream_weight": 0.20, "rerank_vote_count_weight": 0.08, "rerank_source_agreement_bonus": 0.10}
        found = any(
            abs(s["rerank_upstream_weight"] - current["rerank_upstream_weight"]) < 1e-9
            and abs(s["rerank_vote_count_weight"] - current["rerank_vote_count_weight"]) < 1e-9
            and abs(s["rerank_source_agreement_bonus"] - current["rerank_source_agreement_bonus"]) < 1e-9
            for s in sets
        )
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
