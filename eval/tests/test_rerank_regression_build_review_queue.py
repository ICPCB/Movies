"""Tests for the rerank-regression missing-label review queue builder."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import pytest

from eval.scripts import rerank_regression_build_review_queue as queue


def _manifest_row(
    *,
    qid: str,
    tmdb_id: int,
    mode: str,
    model: str,
    rank: int,
    title: str,
    source_artifact_path: str,
    source_top_field: str,
) -> Dict[str, Any]:
    return {
        "affects": ["@5"],
        "mode": mode,
        "model": model,
        "movie_key": f"title:{title.lower()}|year:2001",
        "qid": qid,
        "rank": rank,
        "source_artifact_path": source_artifact_path,
        "source_top_field": source_top_field,
        "title": title,
        "tmdb_id": tmdb_id,
    }


def _fixtures() -> Dict[str, Any]:
    run_prefix = "eval/runs/fixture-run/analysis/rerank_regression"
    score_path = f"{run_prefix}/score_stage_top15.json"
    snapshot_path = f"{run_prefix}/full_set_pool_snapshot.json"
    manifest = {
        "schema_version": "rerank-regression-missing-label-manifest.v1",
        "run_id": "fixture-run",
        "missing_labels": [
            _manifest_row(
                qid="q02",
                tmdb_id=200,
                mode="basic",
                model="baseline",
                rank=4,
                title="Silver Only",
                source_artifact_path=snapshot_path,
                source_top_field="modes.basic.baseline_top",
            ),
            _manifest_row(
                qid="q01",
                tmdb_id=101,
                mode="hybrid",
                model="baseline",
                rank=7,
                title="Shared Candidate",
                source_artifact_path=snapshot_path,
                source_top_field="modes.hybrid.baseline_top",
            ),
            _manifest_row(
                qid="q01",
                tmdb_id=101,
                mode="advanced",
                model="alt",
                rank=3,
                title="Shared Candidate",
                source_artifact_path=score_path,
                source_top_field="per_qid_top15.q01.alt.advanced",
            ),
            _manifest_row(
                qid="q01",
                tmdb_id=102,
                mode="basic",
                model="alt",
                rank=0,
                title="Gold Candidate",
                source_artifact_path=snapshot_path,
                source_top_field="modes.basic.baseline_top",
            ),
            _manifest_row(
                qid="q03",
                tmdb_id=303,
                mode="advanced",
                model="baseline",
                rank=1,
                title="Missing Pool Candidate",
                source_artifact_path=score_path,
                source_top_field="per_qid_top15.q03.baseline.advanced",
            ),
        ],
    }
    long_text = "Line one\nLine two " + ("x" * 600)
    snapshot = {
        "schema_version": "rerank-regression-pool.v1",
        "queries": [
            {
                "qid": "q01",
                "query": "first query",
                "modes": {
                    "advanced": {
                        "pool": [
                            {"tmdb_id": 101, "document_text": long_text},
                            {"tmdb_id": 102, "document_text": "gold text"},
                        ]
                    },
                    "hybrid": {
                        "pool": [
                            {
                                "tmdb_id": 101,
                                "document_text": "second match should not win",
                            }
                        ]
                    },
                },
            },
            {
                "qid": "q02",
                "query": "second query",
                "modes": {
                    "advanced": {
                        "pool": [{"tmdb_id": 200, "document_text": "silver text"}]
                    },
                    "hybrid": {"pool": []},
                },
            },
            {
                "qid": "q03",
                "query": "third query",
                "modes": {"advanced": {"pool": []}, "hybrid": {"pool": []}},
            },
        ],
    }
    gold_rows = [
        {
            "qid": "q01",
            "tmdb_id": 102,
            "grade": 1,
            "silver_grade": 1,
            "gold_grade": 2,
            "gold_notes": "human",
        },
        {
            "qid": "q02",
            "tmdb_id": 200,
            "grade": 1,
            "silver_grade": 1,
            "gold_grade": None,
            "gold_notes": None,
        },
    ]
    return {
        "manifest": manifest,
        "score_top15": {"schema_version": "rerank-regression-score-stage-top15.v1"},
        "snapshot": snapshot,
        "gold_rows": gold_rows,
    }


def _build_rows(tmp_path: Path) -> List[Dict[str, Any]]:
    data = _fixtures()
    return queue.build_review_queue(
        manifest=data["manifest"],
        score_top15=data["score_top15"],
        snapshot=data["snapshot"],
        gold_rows=data["gold_rows"],
        manifest_path=tmp_path / "missing_label_manifest.json",
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _artifact_paths(tmp_path: Path) -> Dict[str, Path]:
    return {
        "jsonl_path": tmp_path / "missing_label_review_queue.jsonl",
        "csv_path": tmp_path / "missing_label_review_queue.csv",
        "summary_path": tmp_path / "missing_label_review_queue_summary.txt",
    }


def test_schema_conformance_and_null_grade_fields(tmp_path: Path) -> None:
    rows = _build_rows(tmp_path)

    assert rows
    for row in rows:
        assert set(row) == set(queue.QUEUE_FIELDS)
        assert isinstance(row["document_text_excerpt"], str)
        assert row["grade"] is None
        assert row["grader_notes"] is None
        assert isinstance(row["models_affected"], list) and row["models_affected"]
        assert isinstance(row["modes_affected"], list) and row["modes_affected"]
        assert isinstance(row["movie_key"], str) and row["movie_key"]
        assert isinstance(row["qid"], str) and row["qid"]
        assert isinstance(row["query_text"], str) and row["query_text"]
        assert isinstance(row["queue_position"], int)
        assert isinstance(row["ranks_observed"], list) and row["ranks_observed"]
        assert isinstance(row["source_artifact_paths"], list)
        assert 2 <= len(row["source_artifact_paths"]) <= 3
        assert isinstance(row["source_top_fields"], list) and row["source_top_fields"]
        assert isinstance(row["title"], str) and row["title"]
        assert isinstance(row["tmdb_id"], int)

    first = rows[0]
    assert first["document_text_excerpt"].startswith("Line one Line two")
    assert "\n" not in first["document_text_excerpt"]
    assert len(first["document_text_excerpt"]) == 500
    assert first["modes_affected"] == ["advanced", "hybrid"]
    assert first["models_affected"] == ["alt", "baseline"]
    assert first["ranks_observed"] == [
        {"mode": "advanced", "model": "alt", "rank": 3},
        {"mode": "hybrid", "model": "baseline", "rank": 7},
    ]


def test_deterministic_ordering_queue_position_and_gold_exclusion(
    tmp_path: Path,
) -> None:
    rows = _build_rows(tmp_path)

    assert [(row["qid"], row["tmdb_id"]) for row in rows] == [
        ("q01", 101),
        ("q02", 200),
        ("q03", 303),
    ]
    assert [row["queue_position"] for row in rows] == [0, 1, 2]
    assert ("q01", 102) not in {(row["qid"], row["tmdb_id"]) for row in rows}
    assert ("q02", 200) in {(row["qid"], row["tmdb_id"]) for row in rows}


def test_byte_identical_rerun_for_jsonl_csv_and_summary(tmp_path: Path) -> None:
    rows = _build_rows(tmp_path)
    paths = _artifact_paths(tmp_path)

    queue.write_review_queue_artifacts(rows=rows, **paths)
    first = {name: path.read_bytes() for name, path in paths.items()}
    queue.write_review_queue_artifacts(rows=rows, **paths)
    second = {name: path.read_bytes() for name, path in paths.items()}

    assert first == second
    assert first["jsonl_path"].endswith(b"\n")
    assert first["summary_path"].endswith(b"\n")
    assert first["csv_path"].splitlines()[0].decode("utf-8").split(",") == queue.QUEUE_FIELDS


def test_build_review_queue_from_paths_uses_tiny_fixtures(tmp_path: Path) -> None:
    data = _fixtures()
    manifest_path = tmp_path / "missing_label_manifest.json"
    score_path = tmp_path / "score_stage_top15.json"
    snapshot_path = tmp_path / "full_set_pool_snapshot.json"
    gold_path = tmp_path / "gold_labels.jsonl"
    _write_json(manifest_path, data["manifest"])
    _write_json(score_path, data["score_top15"])
    _write_json(snapshot_path, data["snapshot"])
    _write_jsonl(gold_path, data["gold_rows"])

    rows = queue.build_review_queue_from_paths(
        manifest_path=manifest_path,
        score_top15_path=score_path,
        snapshot_path=snapshot_path,
        gold_labels_path=gold_path,
    )

    assert [row["queue_position"] for row in rows] == [0, 1, 2]


def test_atomic_write_rollback_preserves_existing_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = _build_rows(tmp_path)
    paths = _artifact_paths(tmp_path)
    paths["jsonl_path"].write_text("existing\n", encoding="utf-8")

    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        queue.write_review_queue_artifacts(rows=rows, **paths)

    assert paths["jsonl_path"].read_text(encoding="utf-8") == "existing\n"


def test_empty_pool_fallback_produces_empty_string_excerpt(tmp_path: Path) -> None:
    rows = _build_rows(tmp_path)

    missing_pool = next(row for row in rows if row["tmdb_id"] == 303)
    assert missing_pool["document_text_excerpt"] == ""
