"""Dep #5 — Rerank regression failure analysis.

Analyzes why the alt reranker (Alibaba-NLP/gte-multilingual-reranker-base)
fixed q10 but regressed q01, q03, q04, q11, q12, q15, q18 in the Dep #4
regression eval.

Reads existing Dep #4 artifacts only. No model inference, no new labels,
no src/* changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

QUERIES_OF_INTEREST = ["q01", "q03", "q04", "q10", "q11", "q12", "q15", "q18"]

FAILURE_TAXONOMY = [
    "over_promotes_surface_match",
    "genre_or_intent_drift",
    "era_or_style_drift",
    "semantic_target_demoted",
    "hybrid_context_sensitive",
    "label_or_candidate_ceiling",
    "artifact_inconclusive",
    "other",
]


def load_artifacts(run_dir: str) -> tuple[dict, dict, dict]:
    base = Path(run_dir)
    reg_dir = base / "analysis" / "rerank_regression"

    snapshot_path = reg_dir / "full_set_pool_snapshot.json"
    comparison_path = reg_dir / "regression_comparison.json"
    gold_path = base / "gold_labels.jsonl"

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))

    gold: dict[tuple[str, int], dict] = {}
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            gold[(row["qid"], row["tmdb_id"])] = row

    return snapshot, comparison, gold


def get_query_data(snapshot: dict, qid: str) -> dict:
    return next(q for q in snapshot["queries"] if q["qid"] == qid)


def get_gold_targets(gold: dict, qid: str, min_grade: int = 2) -> list[dict]:
    """Return gold targets with grade >= min_grade for a query."""
    targets = []
    for (q, tid), v in gold.items():
        if q != qid:
            continue
        g = v.get("gold_grade") or v.get("grade", 0)
        if g is not None and g >= min_grade:
            targets.append({"tmdb_id": tid, "grade": g, "label_source": v.get("label_source", "?")})
    targets.sort(key=lambda x: (-x["grade"], x["tmdb_id"]))
    return targets


def find_in_pool(pool: list[dict], tmdb_id: int) -> dict | None:
    for p in pool:
        if p["tmdb_id"] == tmdb_id:
            return p
    return None


def analyze_baseline_top(
    baseline_top: list[dict],
    targets: list[dict],
    pool: list[dict],
    query_text: str,
) -> dict:
    """Analyze target positions in the baseline reranker's top-N output."""
    target_tmdb_ids = {t["tmdb_id"] for t in targets}
    grade_by_tmdb = {t["tmdb_id"]: t["grade"] for t in targets}

    targets_in_top5 = []
    targets_in_top15 = []
    non_targets_in_top5 = []

    for bt in baseline_top:
        rank = bt.get("rank", 999)
        tid = bt["tmdb_id"]
        entry = {
            "tmdb_id": tid,
            "movie_key": bt.get("movie_key", ""),
            "title": bt.get("title", ""),
            "rank": rank,
            "rerank_score": bt.get("rerank_score"),
            "final_score": bt.get("final_score"),
        }
        if tid in target_tmdb_ids:
            entry["grade"] = grade_by_tmdb[tid]
            if rank < 5:
                targets_in_top5.append(entry)
            targets_in_top15.append(entry)
        else:
            if rank < 5:
                non_targets_in_top5.append(entry)

    targets_not_in_top = []
    top_tmdb_ids = {bt["tmdb_id"] for bt in baseline_top}
    for t in targets:
        if t["tmdb_id"] not in top_tmdb_ids:
            member = find_in_pool(pool, t["tmdb_id"])
            entry = {"tmdb_id": t["tmdb_id"], "grade": t["grade"], "in_pool": member is not None}
            if member:
                entry["movie_key"] = member.get("movie_key", "")
                entry["title"] = member.get("title", "")
                entry["rrf_score"] = member.get("rrf_score")
            targets_not_in_top.append(entry)

    return {
        "targets_in_top5": targets_in_top5,
        "targets_in_top5_count": len(targets_in_top5),
        "targets_in_top15": targets_in_top15,
        "non_targets_in_top5": non_targets_in_top5,
        "targets_not_in_baseline_top": targets_not_in_top,
        "baseline_top5_titles": [bt.get("title", "") for bt in baseline_top if bt.get("rank", 999) < 5],
    }


def classify_failure(
    baseline_analysis: dict,
    change: str,
    query_text: str,
    target_count: int,
) -> str:
    """Classify the failure mode based on baseline top analysis and hit change."""
    if change == "miss_to_hit":
        return "semantic_target_demoted"

    if change != "hit_to_miss":
        return "artifact_inconclusive"

    targets_in_top5 = baseline_analysis.get("targets_in_top5_count", 0)
    non_targets_in_top5 = baseline_analysis.get("non_targets_in_top5", [])

    if targets_in_top5 == 0:
        return "artifact_inconclusive"

    if target_count > 5:
        return "genre_or_intent_drift"

    if non_targets_in_top5:
        titles_lower = [p.get("title", "").lower() for p in non_targets_in_top5]
        query_words = [w for w in query_text.lower().split() if len(w) > 3]
        if query_words:
            surface_matches = sum(
                1 for t in titles_lower
                if any(w in t for w in query_words)
            )
            if surface_matches > 0:
                return "over_promotes_surface_match"

    return "semantic_target_demoted"


def analyze_query(
    qid: str,
    snapshot: dict,
    comparison: dict,
    gold: dict,
) -> dict:
    """Full analysis for one query."""
    query_data = get_query_data(snapshot, qid)
    targets = get_gold_targets(gold, qid)

    baseline_pq = comparison.get("per_query_strict_hit_at_5_baseline", {}).get(qid, {})
    alt_pq = comparison.get("per_query_strict_hit_at_5_alt", {}).get(qid, {})

    mode_analyses = {}
    for mode in ["advanced", "hybrid"]:
        b_hit = baseline_pq.get(mode)
        a_hit = alt_pq.get(mode)

        mode_data = query_data["modes"].get(mode, {})
        pool = mode_data.get("pool", [])
        baseline_top = mode_data.get("baseline_top", [])

        change = (
            "miss_to_hit" if b_hit == 0.0 and a_hit == 1.0
            else "hit_to_miss" if b_hit == 1.0 and a_hit == 0.0
            else "unchanged" if b_hit == a_hit
            else "other"
        )

        baseline_top_analysis = analyze_baseline_top(
            baseline_top, targets, pool, query_data["query"]
        )

        failure_mode = classify_failure(
            baseline_top_analysis, change, query_data["query"], len(targets)
        )

        mode_analyses[mode] = {
            "baseline_strict_hit_at_5": b_hit,
            "alt_strict_hit_at_5": a_hit,
            "change": change,
            "failure_mode": failure_mode,
            "baseline_top_analysis": baseline_top_analysis,
        }

    adv_fm = mode_analyses.get("advanced", {}).get("failure_mode", "artifact_inconclusive")
    hyb_fm = mode_analyses.get("hybrid", {}).get("failure_mode", "artifact_inconclusive")
    query_failure_mode = adv_fm if adv_fm == hyb_fm else f"{adv_fm}+{hyb_fm}"

    return {
        "qid": qid,
        "query": query_data["query"],
        "gold_target_count": len(targets),
        "gold_targets": targets,
        "mode_analyses": mode_analyses,
        "failure_mode": query_failure_mode,
    }


def summarize_patterns(analyses: list[dict]) -> dict:
    """Summarize failure patterns across all analyzed queries."""
    regressions = [a for a in analyses if any(
        m["change"] == "hit_to_miss" for m in a["mode_analyses"].values()
    )]
    fixes = [a for a in analyses if any(
        m["change"] == "miss_to_hit" for m in a["mode_analyses"].values()
    )]

    failure_modes = defaultdict(list)
    for a in regressions:
        failure_modes[a["failure_mode"]].append(a["qid"])

    mode_concentration = {"advanced_only": 0, "hybrid_only": 0, "both": 0}
    for a in regressions:
        adv = a["mode_analyses"].get("advanced", {}).get("change") == "hit_to_miss"
        hyb = a["mode_analyses"].get("hybrid", {}).get("change") == "hit_to_miss"
        if adv and hyb:
            mode_concentration["both"] += 1
        elif adv:
            mode_concentration["advanced_only"] += 1
        elif hyb:
            mode_concentration["hybrid_only"] += 1

    baseline_top5_target_counts = []
    for a in regressions:
        for mode, md in a["mode_analyses"].items():
            c = md.get("baseline_top_analysis", {}).get("targets_in_top5_count", 0)
            baseline_top5_target_counts.append((a["qid"], mode, c))

    return {
        "total_regressions": len(regressions),
        "total_fixes": len(fixes),
        "regressed_qids": [a["qid"] for a in regressions],
        "fixed_qids": [a["qid"] for a in fixes],
        "failure_mode_distribution": dict(failure_modes),
        "mode_concentration": mode_concentration,
        "all_regressions_in_both_modes": mode_concentration["both"] == len(regressions),
        "baseline_top5_target_counts": baseline_top5_target_counts,
    }


def recommend_direction(summary: dict, analyses: list[dict]) -> dict:
    """Recommend next direction based on evidence."""
    regression_count = summary["total_regressions"]

    alibaba_viable_global = regression_count == 0
    alibaba_viable_conditional = regression_count <= 2 and summary["total_fixes"] > 0

    if alibaba_viable_global:
        direction = "A"
        rationale = "No regressions detected; alt reranker is viable as global replacement."
    elif alibaba_viable_conditional:
        direction = "B"
        rationale = (
            f"Alt reranker fixes {summary['total_fixes']} query(s) but regresses "
            f"{regression_count}. Conditional/localized strategy may work."
        )
    else:
        dominant_mode = max(
            summary["failure_mode_distribution"],
            key=lambda k: len(summary["failure_mode_distribution"][k]),
        )

        direction = "B"
        rationale = (
            f"{regression_count} regressions (dominant failure mode: {dominant_mode}). "
            f"All regressions in both advanced+hybrid modes: "
            f"{summary['all_regressions_in_both_modes']}. "
            f"The alt model systematically reranks differently from the baseline, "
            f"demoting gold targets that the baseline ranked correctly. "
            f"A global swap is unsafe. "
            f"Localized/conditional strategy recommended — the alt model could be "
            f"used selectively for queries where the baseline fails (e.g., q10-type "
            f"found-footage queries) without disturbing queries where the baseline "
            f"already succeeds."
        )

    return {
        "recommended_direction": direction,
        "direction_label": (
            "A: test another reranker" if direction == "A"
            else "B: localized/conditional strategy design"
        ),
        "rationale": rationale,
        "alibaba_assessment": {
            "viable_global_replacement": alibaba_viable_global,
            "viable_conditional_reranker": alibaba_viable_conditional,
            "viable_diagnostic_tool_only": not alibaba_viable_global and not alibaba_viable_conditional,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dep #5 rerank regression failure analysis")
    parser.add_argument("--run", required=True, help="Run directory name")
    args = parser.parse_args()

    run_dir = Path("eval/runs") / args.run
    if not run_dir.is_dir():
        print(f"ERROR: run directory not found: {run_dir}", file=sys.stderr)
        return 1

    print(f"[dep5] loading artifacts from {run_dir}")
    snapshot, comparison, gold = load_artifacts(str(run_dir))

    print(f"[dep5] analyzing {len(QUERIES_OF_INTEREST)} queries")
    analyses = []
    for qid in QUERIES_OF_INTEREST:
        analysis = analyze_query(qid, snapshot, comparison, gold)
        analyses.append(analysis)
        change_str = ", ".join(
            f"{m}={d['change']}" for m, d in analysis["mode_analyses"].items()
        )
        print(f"  {qid}: failure_mode={analysis['failure_mode']} ({change_str})")

    summary = summarize_patterns(analyses)
    recommendation = recommend_direction(summary, analyses)

    output = {
        "schema_version": "dep5-regression-failure-analysis.v1",
        "run_id": args.run,
        "queries_analyzed": QUERIES_OF_INTEREST,
        "analyses": analyses,
        "summary": summary,
        "recommendation": recommendation,
        "phase5_gate": "blocked",
        "phase5_note": "Dep #5 is analysis-only. Phase 5 remains BLOCKED.",
    }

    out_dir = run_dir / "analysis" / "rerank_regression"
    out_path = out_dir / "dep5_failure_analysis.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[dep5] wrote {out_path}")
    print(f"[dep5] recommendation: {recommendation['direction_label']}")
    print(f"[dep5] rationale: {recommendation['rationale']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
