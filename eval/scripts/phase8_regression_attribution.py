"""Attribute Phase 8 regression rows to candidate drift or label drift.

This script is intentionally artifact-only. It reads existing eval run files
and writes an attribution report plus a human review queue.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io
from eval.scripts.compute_metrics import MODE_ORDER


TOP_K = 5
RELEVANT_GRADE = 2
CLASSIFICATIONS = {
    "label_only",
    "candidate_only",
    "mixed",
    "insufficient_labels",
}


class AttributionError(ValueError):
    """Raised when attribution inputs are missing or malformed."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AttributionError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise AttributionError(f"{path}:{line_number}: row must be an object")
            rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    text = "\n".join(json.dumps(dict(row), ensure_ascii=False) for row in rows)
    if text:
        text += "\n"
    _run_io._atomic_write_text(path, text)


def _label_map(rows: Iterable[Mapping[str, Any]], *, field: str = "grade") -> dict[tuple[str, int], Optional[int]]:
    labels: dict[tuple[str, int], Optional[int]] = {}
    for row in rows:
        key = (str(row["qid"]), int(row["tmdb_id"]))
        grade = row.get(field)
        if grade is not None and (not isinstance(grade, int) or isinstance(grade, bool)):
            raise AttributionError(f"{key[0]}:{key[1]} has invalid {field}")
        labels[key] = grade
    return labels


def _candidate_map(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, int], Mapping[str, Any]]:
    candidates: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row in rows:
        candidates[(str(row["qid"]), int(row["tmdb_id"]))] = row
    return candidates


def _group_candidates(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["qid"]), []).append(row)
    return grouped


def _is_relevant(grade: Optional[int]) -> bool:
    return grade is not None and grade >= RELEVANT_GRADE


def _hit(ids: Sequence[int], labels: Mapping[tuple[str, int], Optional[int]], qid: str) -> Optional[bool]:
    grades = [labels.get((qid, tmdb_id)) for tmdb_id in ids]
    if any(_is_relevant(grade) for grade in grades):
        return True
    if any(grade is None for grade in grades):
        return None
    return False


def _top_for_mode(
    rows: Sequence[Mapping[str, Any]],
    mode: str,
    *,
    k: int = TOP_K,
) -> list[dict[str, Any]]:
    top: list[dict[str, Any]] = []
    for row in rows:
        mode_data = row.get("per_mode", {}).get(mode)
        if mode_data is None:
            continue
        rank0 = int(mode_data["rank"])
        if rank0 >= k:
            continue
        top.append(
            {
                "tmdb_id": int(row["tmdb_id"]),
                "rank": rank0 + 1,
                "stored_rank0": rank0,
                "final_score": mode_data.get("final_score"),
            }
        )
    top.sort(key=lambda item: (item["rank"], item["tmdb_id"]))
    return top[:k]


def _score_order(
    rows: Sequence[Mapping[str, Any]],
    mode: str,
    *,
    k: int = TOP_K,
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    for row in rows:
        mode_data = row.get("per_mode", {}).get(mode)
        if mode_data is None or "final_score" not in mode_data:
            continue
        scored.append(
            {
                "tmdb_id": int(row["tmdb_id"]),
                "stored_rank": int(mode_data["rank"]) + 1,
                "final_score": float(mode_data["final_score"]),
            }
        )
    scored.sort(key=lambda item: (-item["final_score"], item["stored_rank"], item["tmdb_id"]))
    inferred = [
        {
            "tmdb_id": item["tmdb_id"],
            "score_rank": index,
            "stored_rank": item["stored_rank"],
            "final_score": item["final_score"],
        }
        for index, item in enumerate(scored[:k], start=1)
    ]
    stored_ids = [item["tmdb_id"] for item in sorted(scored, key=lambda item: (item["stored_rank"], item["tmdb_id"]))[:k]]
    score_ids = [item["tmdb_id"] for item in inferred]
    return {
        "basis": "inference_from_descending_final_score",
        "stored_rank_differs_from_score_rank": stored_ids != score_ids
        or any(item["stored_rank"] != item["score_rank"] for item in inferred),
        "top_five": inferred,
    }


def _grade_rows(
    qid: str,
    ids: Sequence[int],
    baseline_silver: Mapping[tuple[str, int], Optional[int]],
    candidate_silver: Mapping[tuple[str, int], Optional[int]],
    baseline_gold: Mapping[tuple[str, int], Optional[int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tmdb_id in ids:
        key = (qid, tmdb_id)
        rows.append(
            {
                "tmdb_id": tmdb_id,
                "baseline_silver_grade": baseline_silver.get(key),
                "candidate_silver_grade": candidate_silver.get(key),
                "baseline_gold_grade": baseline_gold.get(key),
            }
        )
    return rows


def _grade_conflicts(
    qid: str,
    ids: Sequence[int],
    baseline_silver: Mapping[tuple[str, int], Optional[int]],
    candidate_silver: Mapping[tuple[str, int], Optional[int]],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for tmdb_id in ids:
        key = (qid, tmdb_id)
        if key not in baseline_silver or key not in candidate_silver:
            continue
        baseline_grade = baseline_silver.get(key)
        candidate_grade = candidate_silver.get(key)
        if baseline_grade != candidate_grade:
            conflicts.append(
                {
                    "tmdb_id": tmdb_id,
                    "baseline_silver_grade": baseline_grade,
                    "candidate_silver_grade": candidate_grade,
                    "relevance_changed": _is_relevant(baseline_grade) != _is_relevant(candidate_grade),
                }
            )
    return conflicts


def _frozen_label_source(
    qid: str,
    ids: Sequence[int],
    baseline_gold: Mapping[tuple[str, int], Optional[int]],
    baseline_silver: Mapping[tuple[str, int], Optional[int]],
) -> tuple[dict[tuple[str, int], Optional[int]], list[dict[str, Any]]]:
    labels: dict[tuple[str, int], Optional[int]] = {}
    missing: list[dict[str, Any]] = []
    for tmdb_id in ids:
        key = (qid, tmdb_id)
        if key in baseline_gold and baseline_gold[key] is not None:
            labels[key] = baseline_gold[key]
        elif key in baseline_silver and baseline_silver[key] is not None:
            labels[key] = baseline_silver[key]
        else:
            labels[key] = None
            missing.append({"qid": qid, "tmdb_id": tmdb_id})
    return labels, missing


def _rank_changes(
    baseline_top: Sequence[Mapping[str, Any]],
    candidate_top: Sequence[Mapping[str, Any]],
) -> list[dict[str, int]]:
    baseline_ranks = {int(row["tmdb_id"]): int(row["rank"]) for row in baseline_top}
    candidate_ranks = {int(row["tmdb_id"]): int(row["rank"]) for row in candidate_top}
    changes: list[dict[str, int]] = []
    for tmdb_id in sorted(set(baseline_ranks) & set(candidate_ranks)):
        old_rank = baseline_ranks[tmdb_id]
        new_rank = candidate_ranks[tmdb_id]
        if old_rank != new_rank:
            changes.append(
                {
                    "tmdb_id": tmdb_id,
                    "baseline_rank": old_rank,
                    "candidate_rank": new_rank,
                    "delta": new_rank - old_rank,
                }
            )
    return changes


def _classification(
    *,
    ordered_equal: bool,
    set_equal: bool,
    rank_changes: Sequence[Mapping[str, int]],
    own_baseline_hit: Optional[bool],
    own_candidate_hit: Optional[bool],
    missing_frozen: Sequence[Mapping[str, Any]],
    conflicts: Sequence[Mapping[str, Any]],
) -> str:
    if missing_frozen:
        return "insufficient_labels"
    own_hit_changes = own_baseline_hit != own_candidate_hit
    candidate_drift = not set_equal or bool(rank_changes) or not ordered_equal
    relevant_conflict = any(bool(row["relevance_changed"]) for row in conflicts)
    if ordered_equal and own_hit_changes:
        return "label_only"
    if candidate_drift and relevant_conflict:
        return "mixed"
    return "candidate_only"


def _candidate_summary(
    qid: str,
    tmdb_id: int,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    for candidate in candidates:
        if str(candidate["qid"]) == qid and int(candidate["tmdb_id"]) == tmdb_id:
            return {
                "qid": qid,
                "tmdb_id": tmdb_id,
                "title": candidate.get("title"),
                "metadata": {
                    "year": candidate.get("year"),
                    "genres": candidate.get("genres"),
                    "keywords": candidate.get("keywords"),
                    "tagline": candidate.get("tagline"),
                    "overview": candidate.get("overview"),
                },
            }
    return {
        "qid": qid,
        "tmdb_id": tmdb_id,
        "title": None,
        "metadata": {},
    }


def build_attribution(
    *,
    baseline_run: str,
    candidate_run: str,
    qids: Sequence[str],
    baseline_candidates: Sequence[Mapping[str, Any]],
    candidate_candidates: Sequence[Mapping[str, Any]],
    baseline_silver_rows: Sequence[Mapping[str, Any]],
    candidate_silver_rows: Sequence[Mapping[str, Any]],
    baseline_gold_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    baseline_by_qid = _group_candidates(baseline_candidates)
    candidate_by_qid = _group_candidates(candidate_candidates)
    all_candidates_by_key = _candidate_map(list(baseline_candidates) + list(candidate_candidates))
    baseline_silver = _label_map(baseline_silver_rows)
    candidate_silver = _label_map(candidate_silver_rows)
    baseline_gold = _label_map(baseline_gold_rows)
    by_qid: dict[str, Any] = {}
    review_queue_by_key: dict[tuple[str, int], dict[str, Any]] = {}

    for qid in qids:
        by_mode: dict[str, Any] = {}
        for mode in MODE_ORDER:
            baseline_top = _top_for_mode(baseline_by_qid.get(qid, []), mode)
            candidate_top = _top_for_mode(candidate_by_qid.get(qid, []), mode)
            baseline_ids = [row["tmdb_id"] for row in baseline_top]
            candidate_ids = [row["tmdb_id"] for row in candidate_top]
            union_ids = sorted(set(baseline_ids) | set(candidate_ids))
            common_ids = sorted(set(baseline_ids) & set(candidate_ids))
            frozen_labels, missing_frozen = _frozen_label_source(
                qid,
                union_ids,
                baseline_gold,
                baseline_silver,
            )
            rank_changes = _rank_changes(baseline_top, candidate_top)
            conflicts = _grade_conflicts(
                qid,
                common_ids,
                baseline_silver,
                candidate_silver,
            )
            own_baseline_hit = _hit(baseline_ids, baseline_silver, qid)
            own_candidate_hit = _hit(candidate_ids, candidate_silver, qid)
            frozen_baseline_hit = _hit(baseline_ids, frozen_labels, qid)
            frozen_candidate_hit = _hit(candidate_ids, frozen_labels, qid)
            classification = _classification(
                ordered_equal=baseline_ids == candidate_ids,
                set_equal=set(baseline_ids) == set(candidate_ids),
                rank_changes=rank_changes,
                own_baseline_hit=own_baseline_hit,
                own_candidate_hit=own_candidate_hit,
                missing_frozen=missing_frozen,
                conflicts=conflicts,
            )
            if classification not in CLASSIFICATIONS:
                raise AttributionError(f"invalid classification: {classification}")

            record: dict[str, Any] = {
                "classification": classification,
                "baseline_top_five_ids": baseline_ids,
                "candidate_top_five_ids": candidate_ids,
                "exact_order_equal": baseline_ids == candidate_ids,
                "set_equal": set(baseline_ids) == set(candidate_ids),
                "lost_ids": sorted(set(baseline_ids) - set(candidate_ids)),
                "gained_ids": sorted(set(candidate_ids) - set(baseline_ids)),
                "rank_changes": rank_changes,
                "baseline_top_five_grades": _grade_rows(
                    qid,
                    baseline_ids,
                    baseline_silver,
                    candidate_silver,
                    baseline_gold,
                ),
                "candidate_top_five_grades": _grade_rows(
                    qid,
                    candidate_ids,
                    baseline_silver,
                    candidate_silver,
                    baseline_gold,
                ),
                "grade_conflicts": conflicts,
                "hit_status": {
                    "own_labels": {
                        "baseline": own_baseline_hit,
                        "candidate": own_candidate_hit,
                    },
                    "frozen_baseline_labels": {
                        "baseline": frozen_baseline_hit,
                        "candidate": frozen_candidate_hit,
                        "missing": missing_frozen,
                    },
                },
            }
            if mode in {"advanced", "hybrid"}:
                record["pre_safety_order_reconstruction"] = {
                    "baseline": _score_order(baseline_by_qid.get(qid, []), mode),
                    "candidate": _score_order(candidate_by_qid.get(qid, []), mode),
                    "note": "Inference only: reconstructed from descending final_score.",
                }
            by_mode[mode] = record

            needs_review = qid in {"q49", "q59"} or classification == "insufficient_labels"
            if needs_review:
                for tmdb_id in union_ids:
                    key = (qid, tmdb_id)
                    summary = _candidate_summary(qid, tmdb_id, [all_candidates_by_key.get(key, {})])
                    review_queue_by_key[key] = {
                        **summary,
                        "baseline_grade": baseline_silver.get(key),
                        "candidate_run_grade": candidate_silver.get(key),
                        "baseline_gold_grade": baseline_gold.get(key),
                        "modes": sorted(
                            mode_name
                            for mode_name in MODE_ORDER
                            if tmdb_id
                            in {
                                int(row["tmdb_id"])
                                for row in _top_for_mode(baseline_by_qid.get(qid, []), mode_name)
                                + _top_for_mode(candidate_by_qid.get(qid, []), mode_name)
                            }
                        ),
                        "label_provenance": "ai_draft",
                        "review_status": "pending_human",
                    }
        by_qid[qid] = {"by_mode": by_mode}

    review_queue = [
        review_queue_by_key[key]
        for key in sorted(review_queue_by_key, key=lambda item: (item[0], item[1]))
    ]
    output = {
        "schema_version": 1,
        "baseline_run": baseline_run,
        "candidate_run": candidate_run,
        "k": TOP_K,
        "classification_values": sorted(CLASSIFICATIONS),
        "label_sources": {
            "baseline_silver": "baseline run silver_labels.jsonl",
            "candidate_silver": "candidate run silver_labels.jsonl",
            "frozen_baseline": "baseline gold_labels.jsonl when non-null, else baseline silver_labels.jsonl",
        },
        "by_qid": by_qid,
        "review_queue_count": len(review_queue),
    }
    return output, review_queue


def _markdown_report(data: Mapping[str, Any], review_queue: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Phase 8 Regression Attribution",
        "",
        f"- Baseline run: `{data['baseline_run']}`",
        f"- Candidate run: `{data['candidate_run']}`",
        f"- Review queue rows: {len(review_queue)}",
        "",
        "## Classification Summary",
        "",
        "| QID | Basic | Advanced | Hybrid |",
        "|---|---|---|---|",
    ]
    for qid in sorted(data["by_qid"]):
        by_mode = data["by_qid"][qid]["by_mode"]
        lines.append(
            f"| {qid} | {by_mode['basic']['classification']} | "
            f"{by_mode['advanced']['classification']} | "
            f"{by_mode['hybrid']['classification']} |"
        )
    lines.extend(["", "## Label Conflicts", ""])
    for qid in sorted(data["by_qid"]):
        for mode in MODE_ORDER:
            conflicts = data["by_qid"][qid]["by_mode"][mode]["grade_conflicts"]
            if not conflicts:
                continue
            conflict_text = ", ".join(
                f"{row['tmdb_id']} {row['baseline_silver_grade']}->{row['candidate_silver_grade']}"
                for row in conflicts
            )
            lines.append(f"- {qid}/{mode}: {conflict_text}")
    if lines[-1] == "":
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Accuracy Decisions",
            "",
            "Deferred. Classifications identify evidence type only; human review is required before any production fix.",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    *,
    baseline_run: str,
    candidate_run: str,
    queries_path: Path,
    qids: Sequence[str],
    output_dir: Path,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    if not queries_path.exists():
        raise AttributionError(f"queries file not found: {queries_path}")
    baseline_dir = _run_io.run_dir(baseline_run)
    candidate_dir = _run_io.run_dir(candidate_run)
    baseline_candidates = _read_jsonl(baseline_dir / "candidates.jsonl")
    candidate_candidates = _read_jsonl(candidate_dir / "candidates.jsonl")
    baseline_silver = _read_jsonl(baseline_dir / "silver_labels.jsonl")
    candidate_silver = _read_jsonl(candidate_dir / "silver_labels.jsonl")
    baseline_gold_path = baseline_dir / "gold_labels.jsonl"
    if not baseline_gold_path.exists():
        raise AttributionError(f"baseline gold labels missing: {baseline_gold_path}")
    baseline_gold = _read_jsonl(baseline_gold_path)

    data, review_queue = build_attribution(
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        qids=qids,
        baseline_candidates=baseline_candidates,
        candidate_candidates=candidate_candidates,
        baseline_silver_rows=baseline_silver,
        candidate_silver_rows=candidate_silver,
        baseline_gold_rows=baseline_gold,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "attribution.json"
    markdown_path = output_dir / "attribution.md"
    review_queue_path = output_dir / "review_queue.jsonl"
    _run_io._atomic_write_json(json_path, data)
    _run_io._atomic_write_text(markdown_path, _markdown_report(data, review_queue))
    _write_jsonl(review_queue_path, review_queue)
    return json_path, markdown_path, review_queue_path, data


def _parse_qids(value: str) -> list[str]:
    qids = [item.strip() for item in value.split(",") if item.strip()]
    if not qids:
        raise argparse.ArgumentTypeError("--qids must contain at least one qid")
    return qids


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attribute Phase 8 regression evidence from existing artifacts."
    )
    parser.add_argument("--baseline-run", required=True)
    parser.add_argument("--candidate-run", required=True)
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--qids", required=True, type=_parse_qids)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        json_path, markdown_path, review_queue_path, data = run(
            baseline_run=args.baseline_run,
            candidate_run=args.candidate_run,
            queries_path=args.queries,
            qids=args.qids,
            output_dir=args.output_dir,
        )
    except AttributionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    q02_basic = data["by_qid"].get("q02", {}).get("by_mode", {}).get("basic", {})
    print(f"attribution={json_path}")
    print(f"markdown={markdown_path}")
    print(f"review_queue={review_queue_path}")
    if q02_basic:
        print(f"q02/basic classification: {q02_basic['classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
