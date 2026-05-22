import inspect
import unittest
from pathlib import Path

from eval.scripts import rerank_failure_q05_q10


class RerankFailureQ05Q10Tests(unittest.TestCase):
    def test_document_field_analysis_records_presence_and_truncation(self):
        movie = {
            "title": "Target",
            "genres": "Horror",
            "tagline": "",
            "overview": "a" * 601,
            "keywords": "b" * 201,
        }
        fields = rerank_failure_q05_q10.analyze_document_fields(
            movie,
            "document text " * 20,
        )

        self.assertTrue(fields["field_presence"]["title"])
        self.assertTrue(fields["field_presence"]["genres"])
        self.assertFalse(fields["field_presence"]["tagline"])
        self.assertEqual(fields["overview_chars"], 601)
        self.assertTrue(fields["overview_truncated"])
        self.assertEqual(fields["keywords_chars"], 201)
        self.assertTrue(fields["keywords_truncated"])
        self.assertFalse(fields["document_degenerate"])

    def test_score_gap_is_false_positive_minus_target(self):
        self.assertAlmostEqual(
            rerank_failure_q05_q10.compute_score_gap(0.75, 0.25),
            0.5,
        )
        self.assertIsNone(rerank_failure_q05_q10.compute_score_gap(None, 0.25))

    def test_stage_disagreement_attributes_clean_reranker_loss(self):
        stage = rerank_failure_q05_q10.attribute_stage_disagreement(
            {"rrf_rank": 1, "rerank_rank": 5, "final_rank": 10},
            standard_cutoff=50,
        )

        self.assertEqual(stage["attribution"], "reranker")
        self.assertTrue(stage["reranker_demoted_well_retrieved_target"])

    def test_stage_disagreement_keeps_pinned_recall_loss_out_of_reranker(self):
        stage = rerank_failure_q05_q10.attribute_stage_disagreement(
            {"rrf_rank": 66, "rerank_rank": 4, "final_rank": 54},
            standard_cutoff=50,
        )

        self.assertEqual(stage["attribution"], "rrf_recall")
        self.assertFalse(stage["reranker_demoted_well_retrieved_target"])
        self.assertEqual(stage["secondary_attributions"], ["final_blend"])

    def test_failure_mode_inconclusive_when_required_text_is_unresolved(self):
        mode = rerank_failure_q05_q10.classify_failure_mode(
            [_qid_fixture()],
            [
                {
                    "qid": "q05",
                    "role": "false_positive",
                    "tmdb_id": 123,
                    "title": "Missing",
                    "rerank_rank": 0,
                    "reason": "missing_from_candidates_and_movies_clean",
                }
            ],
        )

        self.assertEqual(mode["classification"], "inconclusive")
        self.assertIn("unresolved required document text", mode["evidence"][0])

    def test_failure_mode_model_hypothesis_for_clean_well_formed_reranker_loss(self):
        mode = rerank_failure_q05_q10.classify_failure_mode([_qid_fixture()], [])

        self.assertEqual(mode["classification"], "model_capability_limit_hypothesis")
        self.assertTrue(
            any("q05 no_llm" in item for item in mode["evidence"]),
            mode["evidence"],
        )

    def test_script_does_not_instantiate_reranker_model(self):
        import src.models as models

        self.assertIsNone(models._reranker)
        source = Path(inspect.getfile(rerank_failure_q05_q10)).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("get_reranker", source)
        self.assertNotIn(".predict(", source)


def _candidate(role, *, doc_len=250, overview_chars=100):
    return {
        "role": role,
        "tmdb_id": 144204,
        "title": "Thanatomorphose",
        "rerank_rank": 5,
        "rerank_score": 0.01,
        "document_fields": {
            "document_degenerate": False,
            "document_text_len": doc_len,
            "overview_chars": overview_chars,
            "fields_present": ["title", "genres", "overview"],
        },
    }


def _qid_fixture():
    return {
        "qid": "q05",
        "tmdb_id": 144204,
        "title": "Thanatomorphose",
        "arms": {
            "pinned": {
                "target": _candidate("target"),
                "false_positive_count": 1,
                "stage_disagreement": {
                    "attribution": "rrf_recall",
                    "secondary_attributions": ["final_blend"],
                    "reranker_demoted_well_retrieved_target": False,
                    "target_rrf_rank": 66,
                    "target_rerank_rank": 4,
                    "target_final_rank": 54,
                },
            },
            "no_llm": {
                "target": _candidate("target"),
                "false_positive_count": 5,
                "stage_disagreement": {
                    "attribution": "reranker",
                    "secondary_attributions": [],
                    "reranker_demoted_well_retrieved_target": True,
                    "target_rrf_rank": 1,
                    "target_rerank_rank": 5,
                    "target_final_rank": 10,
                },
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
