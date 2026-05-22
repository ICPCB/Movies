import unittest

from eval.scripts import decomp_pool_q05_q10
from eval.scripts.hybrid_live_trace import StageRun, Target


TARGET_KEY = "title:target|year:2020"


def _target():
    return Target(
        qid="q05",
        tmdb_id=100,
        title="Target",
        year=2020,
        release_date="2020-01-01",
        movie_key=TARGET_KEY,
    )


def _movie(
    key,
    *,
    title,
    tmdb_id,
    semantic_score=None,
    bm25_score=None,
    rrf_score=None,
    rerank_score=None,
    quality_prior=None,
    upstream_prior=None,
    source_agreement=None,
    final_score=None,
):
    movie = {
        "movie_key": key,
        "id": tmdb_id,
        "title": title,
        "year": 2020,
    }
    for field, value in {
        "semantic_score": semantic_score,
        "bm25_score": bm25_score,
        "rrf_score": rrf_score,
        "rerank_score": rerank_score,
        "quality_prior": quality_prior,
        "upstream_prior": upstream_prior,
        "source_agreement": source_agreement,
        "final_score": final_score,
    }.items():
        if value is not None:
            movie[field] = value
    return movie


def _scored(key, title, tmdb_id, rerank, quality, upstream, agreement):
    weights = {"quality_prior": 0.1, "upstream_prior": 0.2, "source_agreement": 0.3}
    return _movie(
        key,
        title=title,
        tmdb_id=tmdb_id,
        rerank_score=rerank,
        quality_prior=quality,
        upstream_prior=upstream,
        source_agreement=agreement,
        final_score=(
            rerank
            + weights["quality_prior"] * quality
            + weights["upstream_prior"] * upstream
            + weights["source_agreement"] * agreement
        ),
    )


class DecompPoolQ05Q10Tests(unittest.TestCase):
    def test_build_pool_rows_aggregates_all_stage_scores_and_formula(self):
        target = _target()
        other_key = "title:other|year:2020"
        stage_run = StageRun(
            retrieval_query="retrieval",
            rerank_query="rerank",
            filters=None,
            semantic=(
                _movie(
                    TARGET_KEY,
                    title="Target",
                    tmdb_id=100,
                    semantic_score=0.7,
                ),
                _movie(
                    other_key,
                    title="Other",
                    tmdb_id=101,
                    semantic_score=0.6,
                ),
            ),
            bm25=(
                _movie(
                    other_key,
                    title="Other",
                    tmdb_id=101,
                    bm25_score=11.0,
                ),
            ),
            rrf=(
                _movie(
                    other_key,
                    title="Other",
                    tmdb_id=101,
                    rrf_score=0.9,
                ),
                _movie(
                    TARGET_KEY,
                    title="Target",
                    tmdb_id=100,
                    rrf_score=0.8,
                ),
            ),
            scored_pool=(
                _scored(TARGET_KEY, "Target", 100, 0.5, 1.0, 0.0, 0.0),
                _scored(other_key, "Other", 101, 0.4, 0.0, 1.0, 1.0),
            ),
        )

        rows = decomp_pool_q05_q10.build_pool_rows(
            stage_run=stage_run,
            target=target,
            pool_depth=2,
            formula_weights={
                "quality_prior": 0.1,
                "upstream_prior": 0.2,
                "source_agreement": 0.3,
            },
        )

        self.assertEqual([row["movie_key"] for row in rows], [other_key, TARGET_KEY])
        target_row = rows[1]
        self.assertTrue(target_row["is_target"])
        self.assertEqual(target_row["semantic_score"], 0.7)
        self.assertIsNone(target_row["bm25_score"])
        self.assertEqual(target_row["rrf_score"], 0.8)
        self.assertEqual(target_row["rerank_rank"], 0)
        self.assertEqual(target_row["final_rank"], 1)
        self.assertAlmostEqual(
            sum(target_row["final_blend"]["contributions"].values()),
            target_row["final_score"],
        )

    def test_target_rescued_uses_zero_based_top5(self):
        rows = [
            {"movie_key": "a", "policy_final_rank": 0},
            {"movie_key": TARGET_KEY, "policy_final_rank": 4},
            {"movie_key": "b", "policy_final_rank": 5},
        ]

        self.assertTrue(decomp_pool_q05_q10.target_rescued(rows, TARGET_KEY))
        self.assertFalse(decomp_pool_q05_q10.target_rescued(rows, "b"))

    def test_collateral_impact_counts_non_target_rank_changes_and_magnitude(self):
        baseline = [
            {"movie_key": "a", "policy_final_rank": 0},
            {"movie_key": "b", "policy_final_rank": 1},
            {"movie_key": TARGET_KEY, "policy_final_rank": 6},
            {"movie_key": "c", "policy_final_rank": 7},
        ]
        policy = [
            {"movie_key": "b", "policy_final_rank": 0},
            {"movie_key": "a", "policy_final_rank": 1},
            {"movie_key": TARGET_KEY, "policy_final_rank": 4},
            {"movie_key": "c", "policy_final_rank": 7},
            {"movie_key": "new", "policy_final_rank": 8},
        ]

        impact = decomp_pool_q05_q10.collateral_impact(
            baseline,
            policy,
            target_key=TARGET_KEY,
        )

        self.assertEqual(impact["common_non_target_count"], 3)
        self.assertEqual(impact["non_target_rank_changes_count"], 2)
        self.assertEqual(impact["non_target_rank_change_magnitude"], 2)
        self.assertEqual(impact["policy_only_non_target_count"], 1)

    def test_reweight_rows_can_rescue_target(self):
        rows = [
            {
                "movie_key": TARGET_KEY,
                "title": "Target",
                "is_target": True,
                "final_blend": {
                    "inputs": {
                        "rerank_score": 0.9,
                        "quality_prior": 0.0,
                        "upstream_prior": 0.0,
                        "source_agreement": 0.0,
                    }
                },
            },
            {
                "movie_key": "boosted",
                "title": "Boosted",
                "is_target": False,
                "final_blend": {
                    "inputs": {
                        "rerank_score": 0.8,
                        "quality_prior": 1.0,
                        "upstream_prior": 1.0,
                        "source_agreement": 1.0,
                    }
                },
            },
        ]

        ranked = decomp_pool_q05_q10.reweight_rows(
            rows,
            {
                "quality_prior": 0.0,
                "upstream_prior": 0.0,
                "source_agreement": 0.0,
            },
        )

        self.assertEqual(ranked[0]["movie_key"], TARGET_KEY)
        self.assertTrue(decomp_pool_q05_q10.target_rescued(ranked, TARGET_KEY))


if __name__ == "__main__":
    unittest.main()
