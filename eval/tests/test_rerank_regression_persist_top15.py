"""Tests for the rerank-regression top-15 persistence sidecar."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

import pytest

from eval.scripts import rerank_regression_persist_top15 as persist


CORE_TOP15_FIELDS = {
    "rank",
    "tmdb_id",
    "movie_key",
    "title",
    "rerank_score",
    "final_score",
}


def _basic(qid: str) -> List[Dict[str, Any]]:
    return [
        {
            "rank": 0,
            "tmdb_id": 9000 + int(qid[1:]),
            "movie_key": f"{qid}:basic",
            "title": f"{qid} Basic",
            "final_score": 1.0,
        }
    ]


def _movie(qid: str, mode: str, suffix: str, tmdb_id: int) -> Dict[str, Any]:
    return {
        "tmdb_id": tmdb_id,
        "movie_key": f"{qid}:{mode}:{suffix}",
        "title": f"{qid} {mode} {suffix}",
        "vote_count": 0,
        "upstream_raw": 0.0,
        "semantic_rank": None,
        "bm25_rank": None,
        "document_text": f"{qid}-{mode}-{suffix}",
    }


def _top_record(movie: Mapping[str, Any], rank: int, score: float) -> Dict[str, Any]:
    return {
        "rank": rank,
        "tmdb_id": movie["tmdb_id"],
        "movie_key": movie["movie_key"],
        "title": movie["title"],
        "rerank_score": score,
        "final_score": score,
    }


def _mode_arm(qid: str, mode: str) -> Dict[str, Any]:
    high = _movie(qid, mode, "high", 1000 + len(mode) * 100 + int(qid[1:]) * 10)
    mid = _movie(qid, mode, "mid", high["tmdb_id"] + 1)
    low = _movie(qid, mode, "low", high["tmdb_id"] + 2)
    return {
        "rerank_query": f"{qid} query",
        "pool": [high, mid, low],
        "baseline_top": [
            _top_record(high, 0, 3.0),
            _top_record(mid, 1, 2.0),
            _top_record(low, 2, 1.0),
        ],
    }


def _snapshot() -> Dict[str, Any]:
    return {
        "schema_version": "rerank-regression-pool.v1",
        "ticket": "RERANK-REGRESSION-EVAL",
        "stage": "capture",
        "run_id": "fixture-run",
        "generated_at": "2026-05-19T18:46:00Z",
        "queries": [
            {
                "qid": qid,
                "query": f"{qid} query",
                "modes": {
                    "basic": {
                        "rerank_query": None,
                        "pool": None,
                        "baseline_top": _basic(qid),
                    },
                    "advanced": _mode_arm(qid, "advanced"),
                    "hybrid": _mode_arm(qid, "hybrid"),
                },
            }
            for qid in ("q05", "q10")
        ],
    }


def _score_map(snapshot: Mapping[str, Any], *, reverse: bool = False) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for q in snapshot["queries"]:
        for mode in ("advanced", "hybrid"):
            ordered = list(q["modes"][mode]["pool"])
            values = [1.0, 2.0, 3.0] if reverse else [3.0, 2.0, 1.0]
            for movie, score in zip(ordered, values):
                scores[movie["document_text"]] = score
    return scores


def _patch_scorers(monkeypatch: pytest.MonkeyPatch, snapshot: Mapping[str, Any]) -> None:
    baseline_scores = _score_map(snapshot)
    alt_scores = _score_map(snapshot, reverse=True)

    def baseline(pairs: List[tuple[str, str]]) -> List[float]:
        return [baseline_scores[doc] for _query, doc in pairs]

    def alt(pairs: List[tuple[str, str]]) -> tuple[List[float], Dict[str, Any]]:
        return [alt_scores[doc] for _query, doc in pairs], {"model_id": "fixture"}

    monkeypatch.setattr(persist, "_baseline_score_pairs", baseline)
    monkeypatch.setattr(persist, "_alt_score_pairs", alt)


def test_build_score_stage_top15_schema_and_invariants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot = _snapshot()
    _patch_scorers(monkeypatch, snapshot)

    artifact = persist.build_score_stage_top15(
        run_id="fixture-run",
        snapshot=snapshot,
        source_snapshot_path=tmp_path / "full_set_pool_snapshot.json",
    )

    assert artifact["schema_version"] == persist.SCORE_TOP15_SCHEMA
    assert artifact["ticket"] == "RERANK-REGRESSION-EVAL"
    assert artifact["stage"] == "score"
    assert artifact["generated_at"] == snapshot["generated_at"]
    assert artifact["scope"] == {
        "queries_total": 2,
        "modes": ["basic", "advanced", "hybrid"],
        "modes_with_rerank": ["advanced", "hybrid"],
    }

    q05 = artifact["per_qid_top15"]["q05"]
    expected_basic = [
        {
            **snapshot["queries"][0]["modes"]["basic"]["baseline_top"][0],
            "rerank_score": snapshot["queries"][0]["modes"]["basic"]["baseline_top"][0][
                "final_score"
            ],
        }
    ]
    assert q05["baseline"]["basic"] == expected_basic
    assert q05["alt"]["basic"] == expected_basic
    assert q05["baseline"]["basic"] == q05["alt"]["basic"]
    assert set(q05["baseline"]["basic"][0]) == CORE_TOP15_FIELDS
    assert q05["baseline"]["basic"][0]["rerank_score"] == 1.0
    assert q05["baseline"]["basic"][0]["final_score"] == 1.0
    assert [r["movie_key"] for r in q05["baseline"]["advanced"]] == [
        "q05:advanced:high",
        "q05:advanced:mid",
        "q05:advanced:low",
    ]
    assert [r["movie_key"] for r in q05["alt"]["advanced"]] == [
        "q05:advanced:low",
        "q05:advanced:mid",
        "q05:advanced:high",
    ]
    assert set(q05["alt"]["advanced"][0]) == CORE_TOP15_FIELDS


def test_persist_score_stage_top15_is_byte_identical_on_rerun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot = _snapshot()
    _patch_scorers(monkeypatch, snapshot)
    snapshot_path = tmp_path / "full_set_pool_snapshot.json"
    score_path = tmp_path / "score_stage_top15.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    persist.persist_score_stage_top15(
        run_id="fixture-run",
        snapshot_path=snapshot_path,
        output_path=score_path,
    )
    first = score_path.read_bytes()
    persist.persist_score_stage_top15(
        run_id="fixture-run",
        snapshot_path=snapshot_path,
        output_path=score_path,
    )
    second = score_path.read_bytes()

    assert first == second
    assert first.endswith(b"\n")


def test_missing_label_manifest_includes_alt_rerank_rows_and_sorted_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot = _snapshot()
    _patch_scorers(monkeypatch, snapshot)
    snapshot_path = tmp_path / "full_set_pool_snapshot.json"
    score_path = tmp_path / "score_stage_top15.json"
    comparison_path = tmp_path / "regression_comparison.json"
    gold_path = tmp_path / "gold_labels.jsonl"
    manifest_path = tmp_path / "missing_label_manifest.json"
    summary_path = tmp_path / "missing_label_manifest_summary.txt"

    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    comparison_path.write_text(
        json.dumps(
            {
                "gate_verdict": {"value": "gate_inconclusive"},
                "metrics_baseline_by_mode": {
                    mode: {"queries_excluded_null": 2}
                    for mode in ("basic", "advanced", "hybrid")
                },
                "metrics_alt_by_mode": {
                    mode: {"queries_excluded_null": 2}
                    for mode in ("basic", "advanced", "hybrid")
                },
            }
        ),
        encoding="utf-8",
    )
    first_basic = snapshot["queries"][0]["modes"]["basic"]["baseline_top"][0]
    gold_path.write_text(
        json.dumps({"qid": "q05", "tmdb_id": first_basic["tmdb_id"], "grade": 1})
        + "\n",
        encoding="utf-8",
    )

    persist.persist_score_stage_top15(
        run_id="fixture-run",
        snapshot_path=snapshot_path,
        output_path=score_path,
    )
    manifest, _, _ = persist.regenerate_missing_label_manifest(
        run_id="fixture-run",
        snapshot_path=snapshot_path,
        score_top15_path=score_path,
        comparison_path=comparison_path,
        gold_labels_path=gold_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
    )

    assert manifest["schema_version"] == persist.MANIFEST_SCHEMA
    assert str(score_path).replace("\\", "/") in manifest["generated_from"]
    sort_keys = [
        (r["qid"], r["mode"], r["model"], r["rank"], r["tmdb_id"])
        for r in manifest["missing_labels"]
    ]
    assert sort_keys == sorted(sort_keys)
    assert manifest["counts_by_model"]["alt"] > manifest["counts_by_model"]["baseline"] / 2
    assert manifest["records_total"] == len(manifest["missing_labels"])
    assert manifest["unique_label_keys_total"] == len(
        {(r["qid"], r["tmdb_id"]) for r in manifest["missing_labels"]}
    )
    assert any(
        row["source_top_field"] == "per_qid_top15.q05.alt.advanced"
        and row["source_artifact_path"] == str(score_path).replace("\\", "/")
        for row in manifest["missing_labels"]
    )
    assert "counts_by_qid=" in summary_path.read_text(encoding="utf-8")


def test_atomic_write_failure_does_not_clobber_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "artifact.json"
    target.write_text("old\n", encoding="utf-8")

    original_replace = Path.replace

    def fail_replace(self: Path, target_path: Path) -> Path:
        if self.name == ".artifact.json.tmp":
            raise RuntimeError("replace failed")
        return original_replace(self, target_path)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(RuntimeError, match="replace failed"):
        persist._atomic_write_json(target, {"new": True})

    assert target.read_text(encoding="utf-8") == "old\n"
