"""Tests for the Dep #9 agreement-bonus simulation."""

from math import log1p

import pytest

from eval.scripts.rerank_agreement_simulation import (
    check_strict_hit_at_k,
    classify_change,
    compute_final_score,
    parse_decomp_pool_row,
    recompute_final_scores,
    simulate_decomp_pool,
    source_agreement,
    upstream_score,
)


def test_source_agreement_requires_both_ranks():
    assert source_agreement({"semantic_rank": 0, "bm25_rank": 3}) == 1.0
    assert source_agreement({"semantic_rank": 0, "bm25_rank": None}) == 0.0
    assert source_agreement({"semantic_rank": None, "bm25_rank": 3}) == 0.0


def test_upstream_score_extracts_rrf_score():
    assert upstream_score({"rrf_score": "0.125", "semantic_score": 0.9}) == 0.125


def test_compute_final_score_with_known_inputs():
    score = compute_final_score(0.4, 0.5, 0.25, 0.02)
    assert score == pytest.approx(0.4 + 0.08 * 0.5 + 0.12 * 0.25 + 0.02)


def test_normalization_uses_full_pool():
    baseline = [{"tmdb_id": 1, "rerank_score": 0.1}]
    pool = [
        {"tmdb_id": 1, "vote_count": 9, "rrf_score": 0.5},
        {"tmdb_id": 2, "vote_count": 99, "rrf_score": 1.0},
    ]
    result = recompute_final_scores(baseline, pool, agreement=0.0)[0]
    assert result["quality_prior"] == pytest.approx(log1p(9) / log1p(99))
    assert result["upstream_prior"] == pytest.approx(0.5)


def test_strict_hit_requires_grade_three_or_higher():
    entries = [{"tmdb_id": 1}, {"tmdb_id": 2}]
    gold = {
        ("q01", 1): {"grade": 2},
        ("q01", 2): {"grade": 3},
    }
    assert check_strict_hit_at_k(entries, gold, "q01", k=2)
    assert not check_strict_hit_at_k(entries[:1], gold, "q01", k=1)


def test_classify_change_detects_regression():
    assert classify_change(True, False) == "hit_to_miss"


def test_classify_change_detects_improvement():
    assert classify_change(False, True) == "miss_to_hit"


@pytest.mark.parametrize("original,new", [(True, True), (False, False)])
def test_classify_change_detects_unchanged(original, new):
    assert classify_change(original, new) == "unchanged"


def test_empty_pool_handling():
    assert recompute_final_scores([{"tmdb_id": 1, "rerank_score": 0.1}], [], 0.02) == []
    assert simulate_decomp_pool([], 0.02) == {
        "agreement": 0.02,
        "target_rank": None,
        "hit": False,
    }


def test_decomp_row_uses_precomputed_quality_prior():
    row = {
        "tmdb_id": 144204,
        "rerank_score": 0.2,
        "vote_count": 999999,
        "is_target": True,
        "final_blend": {
            "inputs": {
                "quality_prior": 0.25,
                "upstream_prior": 0.5,
                "source_agreement": 1.0,
            }
        },
    }
    parsed = parse_decomp_pool_row(row, 0.02)
    assert parsed["quality_prior"] == 0.25
    assert parsed["final_score"] == pytest.approx(0.2 + 0.08 * 0.25 + 0.12 * 0.5 + 0.02)


def test_decomp_target_rank_is_zero_based_top_five():
    def row(tmdb_id, score, is_target=False):
        return {
            "tmdb_id": tmdb_id,
            "rerank_score": score,
            "is_target": is_target,
            "final_blend": {
                "inputs": {
                    "quality_prior": 0.0,
                    "upstream_prior": 0.0,
                    "source_agreement": 0.0,
                }
            },
        }

    rows = [row(index, 1.0 - index / 10) for index in range(4)]
    rows.append(row(144204, 0.5, is_target=True))
    result = simulate_decomp_pool(rows, 0.02)
    assert result["target_rank"] == 4
    assert result["hit"] is True
