import inspect
import unittest
from pathlib import Path

import pandas as pd

from eval.scripts import rerank_text_snapshot


class RerankTextSnapshotTests(unittest.TestCase):
    def test_stage_classification_preserves_dual_id_semantics(self):
        self.assertEqual(
            rerank_text_snapshot.classify_source_stage(
                {"semantic_rank": 0, "bm25_rank": 3}
            ),
            {
                "source_stage": "semantic+bm25",
                "id_semantics": "tmdb_id",
                "resolved_from": "chroma:movies",
            },
        )
        self.assertEqual(
            rerank_text_snapshot.classify_source_stage(
                {"semantic_rank": None, "bm25_rank": 4}
            ),
            {
                "source_stage": "bm25_only",
                "id_semantics": "movies_clean_row_index",
                "resolved_from": "movies_clean.csv:iloc",
            },
        )
        self.assertIsNone(
            rerank_text_snapshot.classify_source_stage(
                {"semantic_rank": None, "bm25_rank": None}
            )["source_stage"]
        )

    def test_semantic_recipe_mirrors_chroma_metadata_fields(self):
        movie = rerank_text_snapshot.semantic_movie_from_metadata(
            8353,
            {
                "title": "Limite",
                "release_date": "1931-05-17",
                "year": "",
                "genres": "Drama",
                "overview": "At sea.",
                "keywords": "boat, silence",
                "tagline": "A landmark.",
            },
        )

        self.assertEqual(movie["id"], 8353)
        self.assertEqual(movie["title"], "Limite")
        self.assertEqual(movie["release_date"], "1931-05-17")
        self.assertEqual(movie["year"], 1931)
        self.assertEqual(movie["genres"], "Drama")
        self.assertEqual(movie["overview"], "At sea.")
        self.assertEqual(movie["keywords"], "boat, silence")
        self.assertEqual(movie["tagline"], "A landmark.")

    def test_bm25_recipe_uses_row_index_and_csv_text_fields(self):
        row = pd.Series(
            {
                "id": 10384,
                "title": "Supernova",
                "release_date": "2000-01-14",
                "year": float("nan"),
                "genres": "ignored",
                "genres_clean": "Science Fiction Drama",
                "overview": "x" * 650,
                "keywords_clean": "space crew",
                "tagline": "In space.",
            }
        )

        movie = rerank_text_snapshot.bm25_movie_from_row(8353, row)

        self.assertEqual(movie["id"], 8353)
        self.assertEqual(movie["title"], "Supernova")
        self.assertEqual(movie["year"], 2000)
        self.assertEqual(movie["genres"], "Science Fiction Drama")
        self.assertEqual(len(movie["overview"]), 500)
        self.assertEqual(movie["keywords"], "space crew")
        self.assertEqual(movie["tagline"], "In space.")

    def test_movie_key_mismatch_is_unresolved_without_member(self):
        movies_df = pd.DataFrame(
            [
                {
                    "id": 10384,
                    "title": "Supernova",
                    "release_date": "2000-01-14",
                    "year": 2000,
                    "genres_clean": "Science Fiction",
                    "overview": "x" * 300,
                    "keywords_clean": "space",
                    "tagline": "A crew in danger.",
                }
            ]
        )
        row = {
            "tmdb_id": 0,
            "title": "Supernova",
            "movie_key": "title:not supernova|year:2000",
            "semantic_rank": None,
            "bm25_rank": 0,
        }

        member, issue = rerank_text_snapshot.resolve_member(
            qid="q05",
            arm="pinned",
            pool_index=0,
            row=row,
            movies_df=movies_df,
            collection=FakeCollection({}),
        )

        self.assertIsNone(member)
        self.assertEqual(issue["reason"], "movie_key_mismatch")
        self.assertEqual(issue["expected_movie_key"], "title:not supernova|year:2000")
        self.assertEqual(issue["resolved_movie_key"], "title:supernova|year:2000")

    def test_coverage_reports_analysis_complete_only_at_full_resolution(self):
        per_qid = [
            {
                "qid": "q05",
                "arms": {
                    "pinned": {
                        "member_count": 1,
                        "resolved_count": 1,
                        "unresolved_count": 0,
                        "members": [
                            {
                                "source_stage": "bm25_only",
                                "resolved_from": "movies_clean.csv:iloc",
                            }
                        ],
                    },
                    "no_llm": {
                        "member_count": 1,
                        "resolved_count": 1,
                        "unresolved_count": 0,
                        "members": [
                            {
                                "source_stage": "semantic",
                                "resolved_from": "chroma:movies",
                            }
                        ],
                    },
                },
            }
        ]

        complete = rerank_text_snapshot.compute_coverage(per_qid, [])
        self.assertTrue(complete["analysis_complete"])
        self.assertEqual(complete["total_members"], 2)
        self.assertEqual(complete["resolved_members"], 2)

        incomplete = rerank_text_snapshot.compute_coverage(
            per_qid,
            [{"reason": "movie_key_mismatch"}],
        )
        self.assertFalse(incomplete["analysis_complete"])
        self.assertEqual(incomplete["unresolved_members"], 1)

    def test_script_uses_no_embedder_or_chroma_query(self):
        source = Path(inspect.getfile(rerank_text_snapshot)).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("get_embedder", source)
        self.assertNotIn("get_reranker", source)
        self.assertNotIn(".query(", source)

        metadata = {
            "tmdb_99": {
                "title": "Fixture",
                "release_date": "1999-01-01",
                "year": 1999,
                "genres": "Drama",
                "overview": "A long enough overview " * 20,
                "keywords": "fixture",
                "tagline": "",
            }
        }
        collection = FakeCollection(metadata)
        movie_key = rerank_text_snapshot.get_movie_key(
            rerank_text_snapshot.semantic_movie_from_metadata(99, metadata["tmdb_99"])
        )

        member, issue = rerank_text_snapshot.resolve_member(
            qid="q10",
            arm="no_llm",
            pool_index=0,
            row={
                "tmdb_id": 99,
                "title": "Fixture",
                "movie_key": movie_key,
                "semantic_rank": 0,
                "bm25_rank": None,
            },
            movies_df=pd.DataFrame(),
            collection=collection,
        )

        self.assertIsNone(issue)
        self.assertEqual(member["source_stage"], "semantic")
        self.assertEqual(collection.get_calls, [(["tmdb_99"], ["metadatas"])])


class FakeCollection:
    def __init__(self, metadata_by_id):
        self.metadata_by_id = metadata_by_id
        self.get_calls = []

    def get(self, *, ids, include):
        self.get_calls.append((list(ids), list(include)))
        found_ids = []
        metadatas = []
        for item in ids:
            if item in self.metadata_by_id:
                found_ids.append(item)
                metadatas.append(self.metadata_by_id[item])
        return {"ids": found_ids, "metadatas": metadatas}

    def query(self, *args, **kwargs):
        raise AssertionError("snapshot runner must not call Chroma query")


if __name__ == "__main__":
    unittest.main()
