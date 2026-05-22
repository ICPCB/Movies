import inspect
from types import SimpleNamespace
import unittest
from pathlib import Path

from eval.scripts import rerank_model_comparison


class RerankModelComparisonTests(unittest.TestCase):
    def test_overlap_metrics_use_lowercase_word_token_sets(self):
        metrics = rerank_model_comparison.overlap_metrics(
            "Haunted apartment found footage",
            "Found-footage haunted ghost",
        )

        self.assertEqual(metrics["overlap_count"], 3)
        self.assertEqual(metrics["overlap_tokens"], ["footage", "found", "haunted"])
        self.assertAlmostEqual(metrics["jaccard"], 0.6)

    def test_candidate_overlap_includes_full_document_text(self):
        row = rerank_model_comparison.candidate_overlap_record(
            rerank_query="haunted apartment footage",
            candidate={
                "role": "target",
                "movie_key": "movie",
                "title": "Movie",
                "rerank_rank": 7,
                "rerank_score": 0.1,
            },
            member={
                "movie_key": "movie",
                "title": "Movie",
                "genres": "Horror",
                "keywords": "found footage",
                "overview": "A reporter enters an infected building.",
                "document_text": "Title: Movie. Overview: haunted apartment footage",
            },
        )

        self.assertEqual(row["overlap"]["combined"]["overlap_count"], 1)
        self.assertEqual(row["overlap"]["document_text"]["overlap_count"], 3)

    def test_content_gap_requires_every_false_positive_strictly_higher(self):
        target = _overlap_row("target", combined_count=1, combined_jaccard=0.1)
        false_positives = [
            _overlap_row("false_positive", combined_count=2, combined_jaccard=0.2),
            _overlap_row("false_positive", combined_count=3, combined_jaccard=0.3),
        ]

        gap = rerank_model_comparison.evaluate_content_gap(target, false_positives)

        self.assertTrue(gap["signal"])
        self.assertEqual(gap["finding"], "content_gap_present")
        self.assertEqual(gap["min_overlap_count_margin"], 1)

        tied = rerank_model_comparison.evaluate_content_gap(
            target,
            [_overlap_row("false_positive", combined_count=1, combined_jaccard=0.2)],
        )
        self.assertFalse(tied["signal"])
        self.assertEqual(tied["finding"], "content_gap_absent")
        self.assertEqual(tied["min_overlap_count_margin"], 0)

    def test_rank_computation_is_descending_and_zero_based(self):
        rows = [
            {"movie_key": "target", "pool_index": 2, "score": 0.5},
            {"movie_key": "winner", "pool_index": 0, "score": 0.8},
            {"movie_key": "tie_before", "pool_index": 1, "score": 0.5},
        ]

        ranked = rerank_model_comparison.ranked_records(rows, score_key="score")
        target = rerank_model_comparison.target_rank(
            rows,
            target_movie_key="target",
            score_key="score",
        )

        self.assertEqual([row["movie_key"] for row in ranked], ["winner", "tie_before", "target"])
        self.assertEqual(target["rank_zero_based"], 2)
        self.assertEqual(target["rank_one_based"], 3)

    def test_position_id_repair_resets_corrupt_nonpersistent_buffer(self):
        import torch

        class Embeddings(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.register_buffer(
                    "position_ids",
                    torch.tensor([999, 0, 0, 0], dtype=torch.long),
                    persistent=False,
                )

        model = SimpleNamespace(
            config=SimpleNamespace(max_position_embeddings=4),
            new=SimpleNamespace(embeddings=Embeddings()),
        )

        details = rerank_model_comparison.repair_position_ids_if_needed(model, torch)

        self.assertTrue(details["checked"])
        self.assertTrue(details["repaired"])
        self.assertEqual(details["before_prefix"], [999, 0, 0, 0])
        self.assertEqual(details["after_prefix"], [0, 1, 2, 3])
        self.assertEqual(model.new.embeddings.position_ids.tolist(), [0, 1, 2, 3])

    def test_decision_confirms_model_capability_on_any_top5_rescue(self):
        phase_a = _phase_a(headline_signals=(False, False))
        phase_b = _phase_b(
            models=[
                _model_result(
                    "Alibaba-NLP/gte-multilingual-reranker-base",
                    q05_rank=2,
                    q10_rank=9,
                )
            ]
        )

        decision = rerank_model_comparison.decide_outcome(phase_a, phase_b)

        self.assertEqual(decision["value"], "model_capability_confirmed")
        self.assertEqual(decision["model"], "Alibaba-NLP/gte-multilingual-reranker-base")
        self.assertEqual(decision["qid"], "q05")
        self.assertFalse(decision["phase5_unblocked"])

    def test_decision_content_gap_dominant_when_no_model_rescues(self):
        phase_a = _phase_a(headline_signals=(True, True))
        phase_b = _phase_b(
            models=[
                _model_result(
                    "cross-encoder/ms-marco-MiniLM-L6-v2",
                    q05_rank=8,
                    q10_rank=9,
                )
            ]
        )

        decision = rerank_model_comparison.decide_outcome(phase_a, phase_b)

        self.assertEqual(decision["value"], "content_gap_dominant")

    def test_decision_rules_out_model_when_no_gap_and_no_rescue(self):
        phase_a = _phase_a(headline_signals=(False, False))
        phase_b = _phase_b(
            models=[
                _model_result(
                    "cross-encoder/ms-marco-MiniLM-L6-v2",
                    q05_rank=8,
                    q10_rank=9,
                )
            ]
        )

        decision = rerank_model_comparison.decide_outcome(phase_a, phase_b)

        self.assertEqual(decision["value"], "model_capability_ruled_out")

    def test_decision_inconclusive_without_successful_model_evidence(self):
        phase_a = _phase_a(headline_signals=(True, True))
        phase_b = {
            "status": "failed",
            "models": [
                {
                    "model_id": "Alibaba-NLP/gte-multilingual-reranker-base",
                    "status": "failed",
                    "error": "download failed",
                }
            ],
        }

        decision = rerank_model_comparison.decide_outcome(phase_a, phase_b)

        self.assertEqual(decision["value"], "inconclusive")

    def test_phase_a_source_imports_no_model_library(self):
        phase_a_source = "\n".join(
            inspect.getsource(item)
            for item in (
                rerank_model_comparison.build_phase_a,
                rerank_model_comparison.candidate_overlap_record,
                rerank_model_comparison.field_overlap_metrics,
                rerank_model_comparison.overlap_metrics,
                rerank_model_comparison.evaluate_content_gap,
            )
        )
        module_import_block = Path(
            inspect.getfile(rerank_model_comparison)
        ).read_text(encoding="utf-8").split("SCHEMA_VERSION", 1)[0]

        for needle in (
            "import torch",
            "from transformers",
            "sentence_transformers",
            "huggingface_hub",
        ):
            self.assertNotIn(needle, module_import_block)
            self.assertNotIn(needle, phase_a_source)

    def test_script_makes_no_src_import_or_llm_call(self):
        source = Path(inspect.getfile(rerank_model_comparison)).read_text(
            encoding="utf-8"
        )

        self.assertNotIn("from src", source)
        self.assertNotIn("import src", source)
        self.assertNotIn("expand_query", source)
        self.assertNotIn("ollama", source.lower())

    def test_model_specs_match_approved_bounded_set(self):
        self.assertEqual(
            [spec.model_id for spec in rerank_model_comparison.MODEL_SPECS],
            [
                "Alibaba-NLP/gte-multilingual-reranker-base",
                "cross-encoder/ms-marco-MiniLM-L6-v2",
            ],
        )


def _overlap_row(role, *, combined_count, combined_jaccard):
    return {
        "role": role,
        "overlap": {
            "combined": {
                "overlap_count": combined_count,
                "jaccard": combined_jaccard,
            }
        },
    }


def _phase_a(*, headline_signals):
    per_qid = []
    for qid, signal in zip(rerank_model_comparison.QIDS, headline_signals):
        per_qid.append(
            {
                "qid": qid,
                "arms": {
                    "pinned": {
                        "content_gap": {
                            "signal": False,
                            "target_combined_overlap_count": 0,
                            "min_overlap_count_margin": None,
                            "false_positive_count": 0,
                        }
                    },
                    "no_llm": {
                        "content_gap": {
                            "signal": signal,
                            "target_combined_overlap_count": 1,
                            "min_overlap_count_margin": 2 if signal else 0,
                            "false_positive_count": 2,
                        }
                    },
                },
            }
        )
    return {"per_qid": per_qid}


def _phase_b(*, models):
    return {"status": "complete", "models": models}


def _model_result(model_id, *, q05_rank, q10_rank):
    return {
        "model_id": model_id,
        "status": "success",
        "per_qid": [
            _qid_rank_result("q05", q05_rank),
            _qid_rank_result("q10", q10_rank),
        ],
    }


def _qid_rank_result(qid, rank):
    return {
        "qid": qid,
        "arms": {
            "no_llm": {
                "baseline": {"target_rank_zero_based": 7},
                "alternative": {
                    "target_rank_zero_based": rank,
                    "target_rank_one_based": rank + 1,
                },
                "rescued_to_top5": rank < 5,
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
