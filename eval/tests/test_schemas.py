import unittest

from eval.tests import conftest as _conftest
from eval.scripts import _schemas


def valid_query_record():
    return {
        "qid": "q01",
        "query": "a mind-bending movie about dreams",
        "tags": {
            "era": "2000-2015",
            "genre": ["sf", "thriller"],
            "vocab_distance": "high",
            "length": "short",
            "specificity": "medium",
            "ambiguity": "low",
        },
        "notes": "vocab mismatch",
    }


def valid_candidate_record():
    return {
        "qid": "q01",
        "tmdb_id": 27205,
        "movie_key": "title:inception|year:2010",
        "title": "Inception",
        "year": 2010,
        "overview": "A thief enters dreams.",
        "genres": "Action, Science Fiction",
        "keywords": "dream, subconscious",
        "tagline": "Your mind is the scene of the crime.",
        "per_mode": {
            "basic": {"rank": 0, "semantic_score": 0.83, "final_score": 0.83},
            "hybrid": {"rank": 2, "semantic_score": 0.81, "final_score": 4.42},
        },
        "in_top_k_of": ["basic", "hybrid"],
        "source": "union",
    }


def valid_silver_record():
    return {
        "qid": "q01",
        "tmdb_id": 27205,
        "grade": 3,
        "confidence": "high",
        "reason": "Overview explicitly matches dreams and reality.",
        "model": "llama3.2",
        "ts": "2026-05-19T15:30:42Z",
    }


class SchemaTest(unittest.TestCase):
    def test_validate_query_record_accepts_valid_record(self):
        record = valid_query_record()
        self.assertIs(_schemas.validate_query_record(record), record)

    def test_validate_query_record_rejects_bad_qid(self):
        record = valid_query_record()
        record["qid"] = "q21"
        with self.assertRaisesRegex(ValueError, "qid must be one of"):
            _schemas.validate_query_record(record)

    def test_validate_query_record_rejects_empty_genre(self):
        record = valid_query_record()
        record["tags"]["genre"] = []
        with self.assertRaisesRegex(ValueError, "tags.genre must be a non-empty list"):
            _schemas.validate_query_record(record)

    def test_validate_query_record_rejects_long_notes(self):
        record = valid_query_record()
        record["notes"] = "x" * 201
        with self.assertRaisesRegex(ValueError, "notes must be <= 200 characters"):
            _schemas.validate_query_record(record)

    def test_validate_candidate_record_accepts_valid_record(self):
        record = valid_candidate_record()
        self.assertIs(_schemas.validate_candidate_record(record), record)

    def test_validate_candidate_record_rejects_none_per_mode(self):
        record = valid_candidate_record()
        record["per_mode"]["advanced"] = None
        with self.assertRaisesRegex(ValueError, "per_mode.advanced must be an object, not None"):
            _schemas.validate_candidate_record(record)

    def test_validate_candidate_record_rejects_negative_rank(self):
        record = valid_candidate_record()
        record["per_mode"]["basic"]["rank"] = -1
        with self.assertRaisesRegex(ValueError, "per_mode.basic.rank must be >= 0"):
            _schemas.validate_candidate_record(record)

    def test_validate_candidate_record_rejects_unknown_mode(self):
        record = valid_candidate_record()
        record["per_mode"]["experimental"] = {"rank": 1}
        with self.assertRaisesRegex(ValueError, "per_mode has unexpected mode"):
            _schemas.validate_candidate_record(record)

    def test_validate_silver_record_accepts_valid_record(self):
        record = valid_silver_record()
        self.assertIs(_schemas.validate_silver_record(record), record)

    def test_validate_silver_record_accepts_null_grade_with_low_confidence(self):
        record = valid_silver_record()
        record["grade"] = None
        record["confidence"] = "low"
        self.assertIs(_schemas.validate_silver_record(record), record)

    def test_validate_silver_record_rejects_bad_grade(self):
        record = valid_silver_record()
        record["grade"] = 4
        with self.assertRaisesRegex(ValueError, "grade must be one of"):
            _schemas.validate_silver_record(record)

    def test_validate_silver_record_rejects_non_low_null_confidence(self):
        record = valid_silver_record()
        record["grade"] = None
        with self.assertRaisesRegex(ValueError, 'confidence must be "low"'):
            _schemas.validate_silver_record(record)

    def test_validate_silver_record_rejects_bad_timestamp(self):
        record = valid_silver_record()
        record["ts"] = "2026-05-19 15:30:42"
        with self.assertRaisesRegex(ValueError, "ts must be ISO-8601 UTC"):
            _schemas.validate_silver_record(record)


if __name__ == "__main__":
    unittest.main()
