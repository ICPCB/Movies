"""Tests for generate_queries_v2.py and _schemas.validate_query_record_v2."""
from __future__ import annotations

import json
import py_compile
from pathlib import Path

import pytest

from eval.scripts._diversity import length_bucket
from eval.scripts._schemas import (
    QUERY_IDS_V2,
    validate_query_record_v2,
)
from eval.scripts.generate_queries_v2 import (
    REQUIRED_MOOD_COUNT,
    REQUIRED_MOOD_EMOTIONS,
    SMOKE_TEST_SUBSTR,
    build_records,
    write_jsonl,
)


class TestCompile:
    def test_py_compile(self):
        py_compile.compile(
            "eval/scripts/generate_queries_v2.py", doraise=True
        )


class TestBuildRecords:
    @pytest.fixture(scope="class")
    def records(self):
        return build_records(seed=42)

    def test_count(self, records):
        assert len(records) == 40

    def test_qid_range(self, records):
        qids = [r["qid"] for r in records]
        assert qids == [f"q{i:02d}" for i in range(21, 61)]

    def test_all_valid_v2(self, records):
        for rec in records:
            validate_query_record_v2(rec)

    def test_length_tags_match(self, records):
        for rec in records:
            assert rec["tags"]["length"] == length_bucket(rec["query"]), (
                f"{rec['qid']} length mismatch"
            )

    def test_no_duplicate_queries(self, records):
        queries = [r["query"] for r in records]
        assert len(queries) == len(set(queries))

    def test_mood_count(self, records):
        mood_recs = [r for r in records if r["tags"].get("mood") is not None]
        assert len(mood_recs) >= REQUIRED_MOOD_COUNT

    def test_mood_emotion_coverage(self, records):
        mood_recs = [r for r in records if r["tags"].get("mood") is not None]
        emotions = {r["tags"]["mood"]["current_emotion"] for r in mood_recs}
        missing = REQUIRED_MOOD_EMOTIONS - emotions
        assert not missing, f"missing emotions: {missing}"

    def test_smoke_test_present(self, records):
        matches = [r for r in records if SMOKE_TEST_SUBSTR in r["query"]]
        assert len(matches) == 1

    def test_deterministic(self):
        a = build_records(seed=42)
        b = build_records(seed=42)
        assert a == b

    def test_different_seed(self):
        a = build_records(seed=42)
        b = build_records(seed=99)
        qids_a = [r["qid"] for r in a]
        qids_b = [r["qid"] for r in b]
        assert qids_a == qids_b
        queries_a = [r["query"] for r in a]
        queries_b = [r["query"] for r in b]
        assert queries_a != queries_b

    def test_non_mood_has_null_mood(self, records):
        non_mood = [r for r in records if r["tags"].get("mood") is None]
        assert len(non_mood) > 0
        for r in non_mood:
            assert r["tags"]["mood"] is None

    def test_mood_has_all_five_keys(self, records):
        mood_recs = [r for r in records if r["tags"].get("mood") is not None]
        expected_keys = {
            "current_emotion",
            "desired_direction",
            "energy_level",
            "intensity",
            "safety_sensitivity",
        }
        for r in mood_recs:
            assert set(r["tags"]["mood"].keys()) == expected_keys, (
                f"{r['qid']} mood keys mismatch"
            )

    def test_era_null_only_for_mood(self, records):
        for r in records:
            if r["tags"]["era"] is None:
                assert r["tags"]["mood"] is not None, (
                    f"{r['qid']} has era=null but no mood"
                )


class TestWriteJsonl:
    def test_roundtrip(self, tmp_path):
        records = build_records()
        out = tmp_path / "test.jsonl"
        write_jsonl(records, out)
        loaded = []
        with open(out, encoding="utf-8") as f:
            for line in f:
                loaded.append(json.loads(line))
        assert loaded == records

    def test_reserved_path_rejected(self):
        from eval.scripts.generate_queries_v2 import main
        with pytest.raises(SystemExit):
            main(["--out", "eval/queries/v2.jsonl"])


class TestSchemaV2:
    def _base_record(self, **overrides):
        rec = {
            "qid": "q21",
            "query": "test query text",
            "tags": {
                "era": "2015+",
                "genre": ["comedy"],
                "vocab_distance": "low",
                "length": "short",
                "specificity": "low",
                "ambiguity": "low",
                "mood": None,
            },
            "notes": "test note",
        }
        rec.update(overrides)
        return rec

    def test_valid_without_mood(self):
        validate_query_record_v2(self._base_record())

    def test_valid_with_mood(self):
        rec = self._base_record()
        rec["tags"]["mood"] = {
            "current_emotion": "sad",
            "desired_direction": "cheer_me_up",
            "energy_level": "light_cozy",
            "intensity": "very_light",
            "safety_sensitivity": "safe_hopeful",
        }
        validate_query_record_v2(rec)

    def test_era_null_allowed(self):
        rec = self._base_record()
        rec["tags"]["era"] = None
        validate_query_record_v2(rec)

    def test_qid_up_to_q60(self):
        rec = self._base_record(qid="q60")
        validate_query_record_v2(rec)

    def test_qid_q66_rejected(self):
        rec = self._base_record(qid="q66")
        with pytest.raises(ValueError):
            validate_query_record_v2(rec)

    def test_invalid_mood_emotion(self):
        rec = self._base_record()
        rec["tags"]["mood"] = {
            "current_emotion": "angry",
            "desired_direction": "cheer_me_up",
            "energy_level": "light_cozy",
            "intensity": "very_light",
            "safety_sensitivity": "safe_hopeful",
        }
        with pytest.raises(ValueError, match="current_emotion"):
            validate_query_record_v2(rec)

    def test_invalid_mood_missing_key(self):
        rec = self._base_record()
        rec["tags"]["mood"] = {
            "current_emotion": "sad",
            "desired_direction": "cheer_me_up",
        }
        with pytest.raises(ValueError, match="energy_level"):
            validate_query_record_v2(rec)

    def test_mood_unknown_key_rejected(self):
        rec = self._base_record()
        rec["tags"]["mood"] = {
            "current_emotion": "sad",
            "desired_direction": "cheer_me_up",
            "energy_level": "light_cozy",
            "intensity": "very_light",
            "safety_sensitivity": "safe_hopeful",
            "extra_field": "bad",
        }
        with pytest.raises(ValueError, match="unexpected"):
            validate_query_record_v2(rec)
