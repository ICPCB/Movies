import unittest

from eval.scripts.run_pipelines import build_candidate_union


def _movie(tmdb_id, movie_key=None, title=None, **scores):
    record = {
        "tmdb_id": tmdb_id,
        "movie_key": movie_key or f"title:movie-{tmdb_id}|year:2000",
        "title": title or f"Movie {tmdb_id}",
        "year": 2000,
        "overview": f"Overview {tmdb_id}",
        "genres": "Drama",
        "keywords": "test",
        "tagline": "",
    }
    record.update(scores)
    return record


def _ids(records):
    return [record["tmdb_id"] for record in records]


class RunPipelinesUnionTests(unittest.TestCase):
    def test_top5_of_each_mode_preserved_even_past_soft_cap(self):
        per_mode = {
            "basic": [_movie(i) for i in range(100, 105)],
            "advanced": [_movie(i) for i in range(200, 205)],
            "hybrid": [_movie(i) for i in range(300, 305)],
        }

        records, warnings = build_candidate_union("q01", per_mode)

        self.assertEqual([], warnings)
        self.assertEqual(15, len(records))
        selected = set(_ids(records))
        for expected in list(range(100, 105)) + list(range(200, 205)) + list(
            range(300, 305)
        ):
            self.assertIn(expected, selected)

    def test_soft_cap_exceeded_only_for_missing_top5s(self):
        per_mode = {
            "basic": [_movie(i) for i in [1, 2, 3, 4, 5, 21, 22]],
            "advanced": [_movie(i) for i in [4, 5, 6, 7, 8, 23, 24]],
            "hybrid": [_movie(i) for i in [8, 9, 10, 11, 12, 25, 26]],
        }

        records, warnings = build_candidate_union("q02", per_mode)

        self.assertEqual([], warnings)
        self.assertEqual(12, len(records))
        self.assertLessEqual(len(records), 15)
        self.assertEqual(set(range(1, 13)), set(_ids(records)))

    def test_soft_cap_not_exceeded_when_top5s_fit_inside_it(self):
        per_mode = {
            "basic": [_movie(i) for i in range(1, 12)],
            "advanced": [_movie(i) for i in range(1, 12)],
            "hybrid": [_movie(i) for i in range(1, 12)],
        }

        records, warnings = build_candidate_union("q03", per_mode)

        self.assertEqual([], warnings)
        self.assertEqual(8, len(records))
        self.assertEqual(list(range(1, 9)), _ids(records))

    def test_ties_use_mode_order_basic_advanced_hybrid(self):
        per_mode = {
            "basic": [_movie(30)],
            "advanced": [_movie(20)],
            "hybrid": [_movie(10)],
        }

        records, warnings = build_candidate_union("q04", per_mode)

        self.assertEqual([], warnings)
        self.assertEqual([30, 20, 10], _ids(records))

    def test_dedup_bug_warns_for_same_tmdb_id_different_movie_key(self):
        per_mode = {
            "basic": [_movie(501, movie_key="title:first|year:2000")],
            "advanced": [_movie(501, movie_key="title:second|year:2000")],
            "hybrid": [],
        }

        records, warnings = build_candidate_union("q05", per_mode)

        self.assertEqual(1, len(records))
        self.assertEqual(
            [
                "dedup_bug: qid=q05 tmdb_id=501 "
                "movie_keys=title:first|year:2000,title:second|year:2000"
            ],
            warnings,
        )
        self.assertEqual(["basic", "advanced"], records[0]["in_top_k_of"])
        self.assertIn("basic", records[0]["per_mode"])
        self.assertIn("advanced", records[0]["per_mode"])
        self.assertNotIn("hybrid", records[0]["per_mode"])

    def test_per_mode_omits_absent_modes_and_absent_scores(self):
        per_mode = {
            "basic": [_movie(701, semantic_score=0.7)],
            "advanced": [_movie(701, bm25_score=None, final_score=3.5)],
            "hybrid": [],
        }

        records, warnings = build_candidate_union("q06", per_mode)

        self.assertEqual([], warnings)
        per_mode_record = records[0]["per_mode"]
        self.assertEqual({"rank": 0, "semantic_score": 0.7}, per_mode_record["basic"])
        self.assertEqual(
            {"rank": 0, "bm25_score": 0.0, "final_score": 3.5},
            per_mode_record["advanced"],
        )
        self.assertNotIn("hybrid", per_mode_record)


if __name__ == "__main__":
    unittest.main()
