"""Unit tests for eval/scripts/rerank_regression_eval.py.

All tests are hermetic: no model load, no GPU, no LLM, no src/* edit.
"""
from __future__ import annotations

import inspect
import json
import math
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.scripts import rerank_regression_eval as rre


def _pool(*movies: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [dict(m) for m in movies]


class BlendReproductionTests(unittest.TestCase):
    """blend_final_scores must match src/retrieval/reranker.py:rerank exactly."""

    def test_blend_matches_src_reranker_formula(self) -> None:
        from src.retrieval.reranker import (
            RERANK_VOTE_COUNT_WEIGHT,
            RERANK_UPSTREAM_WEIGHT,
            RERANK_SOURCE_AGREEMENT_BONUS,
        )
        pool = _pool(
            {
                "tmdb_id": 1,
                "vote_count": 100,
                "upstream_raw": 0.5,
                "semantic_rank": 0,
                "bm25_rank": 0,
            },
            {
                "tmdb_id": 2,
                "vote_count": 50,
                "upstream_raw": 0.25,
                "semantic_rank": None,
                "bm25_rank": 1,
            },
            {
                "tmdb_id": 3,
                "vote_count": 0,
                "upstream_raw": 0.0,
                "semantic_rank": None,
                "bm25_rank": None,
            },
        )
        rerank_scores = [2.0, 1.0, 0.5]
        out = rre.blend_final_scores(rerank_scores, pool)

        max_vote_log = math.log1p(100)
        max_upstream = 0.5
        # member 1
        v1 = math.log1p(100) / max_vote_log
        u1 = 0.5 / max_upstream
        s1 = 1.0
        expected1 = 2.0 + RERANK_VOTE_COUNT_WEIGHT * v1 + RERANK_UPSTREAM_WEIGHT * u1 + RERANK_SOURCE_AGREEMENT_BONUS * s1
        # member 2 (no source agreement: semantic_rank None)
        v2 = math.log1p(50) / max_vote_log
        u2 = 0.25 / max_upstream
        s2 = 0.0
        expected2 = 1.0 + RERANK_VOTE_COUNT_WEIGHT * v2 + RERANK_UPSTREAM_WEIGHT * u2 + RERANK_SOURCE_AGREEMENT_BONUS * s2
        # member 3 (zero votes, zero upstream): vote_prior=0, upstream_prior=0
        expected3 = 0.5
        self.assertAlmostEqual(out[0], expected1, places=10)
        self.assertAlmostEqual(out[1], expected2, places=10)
        self.assertAlmostEqual(out[2], expected3, places=10)

    def test_blend_empty_pool(self) -> None:
        self.assertEqual(rre.blend_final_scores([], []), [])

    def test_blend_length_mismatch_raises(self) -> None:
        with self.assertRaises(ValueError):
            rre.blend_final_scores([1.0, 2.0], [{"vote_count": 0, "upstream_raw": 0.0}])


class RankConstructionTests(unittest.TestCase):

    def test_build_ranked_top15_sorts_by_final_score(self) -> None:
        pool = _pool(
            {"tmdb_id": 1, "movie_key": "k1", "title": "A", "vote_count": 0,
             "upstream_raw": 0.0, "semantic_rank": None, "bm25_rank": None},
            {"tmdb_id": 2, "movie_key": "k2", "title": "B", "vote_count": 0,
             "upstream_raw": 0.0, "semantic_rank": None, "bm25_rank": None},
            {"tmdb_id": 3, "movie_key": "k3", "title": "C", "vote_count": 0,
             "upstream_raw": 0.0, "semantic_rank": None, "bm25_rank": None},
        )
        # ascending raw scores; after blend with all-zero priors final == raw
        scores = [0.1, 0.9, 0.5]
        top = rre._build_ranked_top15(pool, scores)
        self.assertEqual([t["tmdb_id"] for t in top], [2, 3, 1])
        for rank, t in enumerate(top):
            self.assertEqual(t["rank"], rank)


class PerQueryStrictHitTests(unittest.TestCase):

    def test_strict_hit_at_5_per_mode(self) -> None:
        # Two queries, two modes, with simple per_mode rank assignments.
        candidates = [
            {"qid": "q01", "tmdb_id": 10, "per_mode": {"hybrid": {"rank": 0}}},
            {"qid": "q01", "tmdb_id": 11, "per_mode": {"hybrid": {"rank": 1}}},
            {"qid": "q02", "tmdb_id": 20, "per_mode": {"hybrid": {"rank": 3}}},
        ]
        labels = {("q01", 10): 3, ("q01", 11): 1, ("q02", 20): 2}
        out = rre._per_query_strict_hit_at_5(candidates, labels)
        # q01 hybrid has grade 3 in top-5 -> 1.0
        self.assertEqual(out["q01"]["hybrid"], 1.0)
        # q02 hybrid has only grade 2 in top-5 -> 0.0 (strict = grade==3)
        self.assertEqual(out["q02"]["hybrid"], 0.0)
        # basic/advanced not present -> 0.0 (no rows, no null)
        self.assertEqual(out["q01"]["basic"], 0.0)


class GateVerdictTests(unittest.TestCase):

    def _by_mode(self, sh5: float, sh10: float, mrr5: float, excluded: int = 0) -> Dict[str, Any]:
        return {
            "strict_hit_at_5": sh5,
            "strict_hit_at_10": sh10,
            "mrr_at_5": mrr5,
            "queries_excluded_null": excluded,
            "queries_with_ideal_dcg_zero": 0,
            # other metric_family keys are not consulted by the gate beyond headline:
            "hit_at_5": 0.0, "hit_at_10": 0.0, "hit_at_15": 0.0,
            "strict_mrr_at_5": 0.0, "strict_mrr_at_10": 0.0, "strict_mrr_at_15": 0.0,
            "ndcg_at_5": 0.0, "ndcg_at_10": 0.0, "ndcg_at_15": 0.0,
            "mrr_at_10": 0.0, "mrr_at_15": 0.0,
            "strict_hit_at_15": 0.0,
        }

    def _identical_by_mode(self) -> Dict[str, Dict[str, Any]]:
        return {
            "basic": self._by_mode(0.5, 0.6, 0.4),
            "advanced": self._by_mode(0.6, 0.7, 0.5),
            "hybrid": self._by_mode(0.6, 0.7, 0.5),
        }

    def test_gate_pass(self) -> None:
        baseline = self._identical_by_mode()
        alt = self._identical_by_mode()
        # alt improves advanced/hybrid:
        alt["advanced"] = self._by_mode(0.7, 0.75, 0.55)
        alt["hybrid"] = self._by_mode(0.7, 0.75, 0.55)
        per_q_b = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 0.0}}
        per_q_a = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0}}
        verdict = rre._gate_verdict(
            baseline, alt, per_q_b, per_q_a, [],
            {"passed": True, "details": [], "comparisons": {}},
        )
        self.assertEqual(verdict["value"], "gate_pass")
        self.assertTrue(verdict["q10_fixed"])
        # phase5_unblocked must ALWAYS be False:
        self.assertFalse(verdict["phase5_unblocked"])

    def test_gate_fail_on_aggregate_regression(self) -> None:
        baseline = self._identical_by_mode()
        alt = self._identical_by_mode()
        alt["hybrid"] = self._by_mode(0.5, 0.7, 0.5)  # strict_hit_at_5 regresses
        per_q_b = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 0.0}}
        per_q_a = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0}}
        verdict = rre._gate_verdict(
            baseline, alt, per_q_b, per_q_a, [],
            {"passed": True, "details": [], "comparisons": {}},
        )
        self.assertEqual(verdict["value"], "gate_fail")
        self.assertFalse(verdict["phase5_unblocked"])

    def test_gate_fail_on_q10_not_fixed(self) -> None:
        baseline = self._identical_by_mode()
        alt = self._identical_by_mode()
        per_q_b = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 0.0}}
        per_q_a = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 0.0}}
        verdict = rre._gate_verdict(
            baseline, alt, per_q_b, per_q_a, [],
            {"passed": True, "details": [], "comparisons": {}},
        )
        self.assertEqual(verdict["value"], "gate_fail")
        self.assertFalse(verdict["q10_fixed"])

    def test_gate_fail_on_per_query_flip(self) -> None:
        baseline = self._identical_by_mode()
        alt = self._identical_by_mode()
        per_q_b = {
            "q01": {"basic": 1.0, "advanced": 1.0, "hybrid": 1.0},
            "q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 0.0},
        }
        per_q_a = {
            "q01": {"basic": 1.0, "advanced": 0.0, "hybrid": 1.0},  # flip in advanced
            "q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0},
        }
        verdict = rre._gate_verdict(
            baseline, alt, per_q_b, per_q_a, [],
            {"passed": True, "details": [], "comparisons": {}},
        )
        self.assertEqual(verdict["value"], "gate_fail")

    def test_gate_inconclusive_on_null_metric(self) -> None:
        baseline = self._identical_by_mode()
        alt = self._identical_by_mode()
        alt["hybrid"]["strict_hit_at_5"] = None  # null metric
        per_q_b = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 0.0}}
        per_q_a = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0}}
        verdict = rre._gate_verdict(
            baseline, alt, per_q_b, per_q_a, [],
            {"passed": True, "details": [], "comparisons": {}},
        )
        self.assertEqual(verdict["value"], "gate_inconclusive")

    def test_gate_inconclusive_on_basic_invariant_violation(self) -> None:
        baseline = self._identical_by_mode()
        alt = self._identical_by_mode()
        verdict = rre._gate_verdict(
            baseline, alt,
            {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0}},
            {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0}},
            ["basic.strict_hit_at_5: 0.5 != 0.6"],
            {"passed": True, "details": [], "comparisons": {}},
        )
        self.assertEqual(verdict["value"], "gate_inconclusive")

    def test_gate_inconclusive_on_self_check_fail(self) -> None:
        baseline = self._identical_by_mode()
        alt = self._identical_by_mode()
        verdict = rre._gate_verdict(
            baseline, alt,
            {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0}},
            {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0}},
            [],
            {"passed": False, "details": ["mismatch"], "comparisons": {}},
        )
        self.assertEqual(verdict["value"], "gate_inconclusive")

    def test_gate_inconclusive_on_excluded_null_differs(self) -> None:
        baseline = self._identical_by_mode()
        alt = self._identical_by_mode()
        alt["advanced"] = self._by_mode(0.6, 0.7, 0.5, excluded=2)
        per_q_b = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 0.0}}
        per_q_a = {"q10": {"basic": 0.0, "advanced": 0.0, "hybrid": 1.0}}
        verdict = rre._gate_verdict(
            baseline, alt, per_q_b, per_q_a, [],
            {"passed": True, "details": [], "comparisons": {}},
        )
        self.assertEqual(verdict["value"], "gate_inconclusive")


class NoSrcEditNoLLMInScoringPathTests(unittest.TestCase):
    """Sanity: the scoring-path functions must not import LLM modules at call time."""

    def test_blend_final_scores_does_not_use_llm(self) -> None:
        src = inspect.getsource(rre.blend_final_scores)
        self.assertNotIn("langchain_ollama", src)
        self.assertNotIn("expand_query", src)
        self.assertNotIn("hyde_generate", src)

    def test_build_ranked_top15_does_not_use_llm(self) -> None:
        src = inspect.getsource(rre._build_ranked_top15)
        self.assertNotIn("langchain_ollama", src)
        self.assertNotIn("expand_query", src)

    def test_gate_verdict_pure(self) -> None:
        src = inspect.getsource(rre._gate_verdict)
        self.assertNotIn("langchain_ollama", src)
        # No model/CrossEncoder/AutoModel in gate logic:
        for forbidden in ("CrossEncoder", "AutoModel", "torch", "expand_query"):
            self.assertNotIn(forbidden, src, f"gate verdict references {forbidden}")


class PoolStructureTests(unittest.TestCase):
    """Mechanical invariants on the harness's pool-record schema."""

    def test_required_pool_record_keys(self) -> None:
        # The wrapper builds pool records with these keys; verify they exist
        # by reading the source.
        src = inspect.getsource(rre._install_capture_wrappers)
        for key in (
            "tmdb_id", "movie_key", "vote_count", "upstream_raw",
            "semantic_rank", "bm25_rank", "document_text", "rerank_query",
        ):
            self.assertIn(f'"{key}"', src)


if __name__ == "__main__":
    unittest.main()
