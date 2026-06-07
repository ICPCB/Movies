"""Audit alt-reranker top-15 candidates for missing gold labels.

Reads score_stage_top15.json and gold_labels.jsonl to identify candidates
in the alt (and baseline) reranker top-15 that lack labels. Produces a
structured JSON report used to prioritize label gap closure for fixing
gate_inconclusive / queries_excluded_null.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


ANALYSIS_SUBDIR = Path("analysis") / "rerank_regression"
SCORE_TOP15_FILE = "score_stage_top15.json"
GOLD_LABELS_FILE = "gold_labels.jsonl"
OUTPUT_FILE = "alt_label_gap_audit.json"

MODES = ("basic", "advanced", "hybrid")
SOURCES = ("alt", "baseline")


def load_score_top15(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / ANALYSIS_SUBDIR / SCORE_TOP15_FILE
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_gold_labels(run_dir: Path) -> Set[Tuple[str, int]]:
    path = run_dir / GOLD_LABELS_FILE
    labeled: Set[Tuple[str, int]] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            labeled.add((rec["qid"], rec["tmdb_id"]))
    return labeled


def find_unlabeled(
    top15_data: Dict[str, Any],
    labeled: Set[Tuple[str, int]],
) -> Dict[str, Any]:
    per_qid = top15_data.get("per_qid_top15", {})
    per_query_gaps: Dict[str, Dict[str, Any]] = {}
    unlabeled_map: Dict[Tuple[str, int], Dict[str, Any]] = {}

    for qid in sorted(per_qid.keys()):
        qid_data = per_qid[qid]
        alt_unlabeled_ids: Set[int] = set()
        baseline_unlabeled_ids: Set[int] = set()
        alt_modes_with_gaps: List[str] = []

        for source in SOURCES:
            source_data = qid_data.get(source, {})
            for mode in MODES:
                candidates = source_data.get(mode, [])
                for cand in candidates:
                    tmdb_id = cand["tmdb_id"]
                    key = (qid, tmdb_id)
                    if key not in labeled:
                        if source == "alt":
                            alt_unlabeled_ids.add(tmdb_id)
                        else:
                            baseline_unlabeled_ids.add(tmdb_id)

                        if key not in unlabeled_map:
                            unlabeled_map[key] = {
                                "qid": qid,
                                "tmdb_id": tmdb_id,
                                "title": cand.get("title", ""),
                                "movie_key": cand.get("movie_key", ""),
                                "sources": set(),
                                "modes": set(),
                                "ranks": {},
                            }
                        entry = unlabeled_map[key]
                        entry["sources"].add(source)
                        entry["modes"].add(mode)
                        rank_key = f"{source}.{mode}"
                        entry["ranks"][rank_key] = cand.get("rank", -1)

        for mode in MODES:
            alt_cands = qid_data.get("alt", {}).get(mode, [])
            for cand in alt_cands:
                if (qid, cand["tmdb_id"]) not in labeled:
                    if mode not in alt_modes_with_gaps:
                        alt_modes_with_gaps.append(mode)
                    break

        union_ids = alt_unlabeled_ids | baseline_unlabeled_ids
        per_query_gaps[qid] = {
            "alt_unlabeled": len(alt_unlabeled_ids),
            "baseline_unlabeled": len(baseline_unlabeled_ids),
            "union_unlabeled": len(union_ids),
            "alt_modes_with_gaps": sorted(alt_modes_with_gaps),
        }

    unlabeled_list = []
    for key in sorted(unlabeled_map.keys()):
        entry = unlabeled_map[key]
        unlabeled_list.append({
            "qid": entry["qid"],
            "tmdb_id": entry["tmdb_id"],
            "title": entry["title"],
            "movie_key": entry["movie_key"],
            "sources": sorted(entry["sources"]),
            "modes": sorted(entry["modes"]),
            "ranks": dict(sorted(entry["ranks"].items())),
        })

    total_alt = sum(g["alt_unlabeled"] for g in per_query_gaps.values())
    total_baseline = sum(g["baseline_unlabeled"] for g in per_query_gaps.values())
    total_union = sum(g["union_unlabeled"] for g in per_query_gaps.values())

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_labeled": len(labeled),
        "total_unlabeled_alt": total_alt,
        "total_unlabeled_baseline": total_baseline,
        "total_unlabeled_union": total_union,
        "queries_with_alt_gaps": sum(
            1 for g in per_query_gaps.values() if g["alt_unlabeled"] > 0
        ),
        "queries_with_baseline_gaps": sum(
            1 for g in per_query_gaps.values() if g["baseline_unlabeled"] > 0
        ),
        "per_query_gaps": per_query_gaps,
        "unlabeled_candidates": unlabeled_list,
    }


def write_report(report: Dict[str, Any], run_dir: Path) -> Path:
    out_path = run_dir / ANALYSIS_SUBDIR / OUTPUT_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    return out_path


def print_summary(report: Dict[str, Any]) -> None:
    print(f"Total labeled pairs: {report['total_labeled']}")
    print(f"Unlabeled in alt top-15: {report['total_unlabeled_alt']}")
    print(f"Unlabeled in baseline top-15: {report['total_unlabeled_baseline']}")
    print(f"Unlabeled union: {report['total_unlabeled_union']}")
    print(f"Queries with alt gaps: {report['queries_with_alt_gaps']}")
    print(f"Queries with baseline gaps: {report['queries_with_baseline_gaps']}")
    print()
    print("Per-query gaps:")
    for qid, gaps in sorted(report["per_query_gaps"].items()):
        if gaps["union_unlabeled"] > 0:
            print(
                f"  {qid}: alt={gaps['alt_unlabeled']} "
                f"baseline={gaps['baseline_unlabeled']} "
                f"union={gaps['union_unlabeled']} "
                f"alt_modes={gaps['alt_modes_with_gaps']}"
            )


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Audit alt-reranker top-15 for missing gold labels."
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Path to the eval run directory.",
    )
    args = parser.parse_args(argv)
    run_dir: Path = args.run_dir

    top15_path = run_dir / ANALYSIS_SUBDIR / SCORE_TOP15_FILE
    if not top15_path.exists():
        print(f"ERROR: {top15_path} not found", file=sys.stderr)
        sys.exit(1)

    gold_path = run_dir / GOLD_LABELS_FILE
    if not gold_path.exists():
        print(f"ERROR: {gold_path} not found", file=sys.stderr)
        sys.exit(1)

    top15_data = load_score_top15(run_dir)
    labeled = load_gold_labels(run_dir)
    report = find_unlabeled(top15_data, labeled)
    report["run_dir"] = str(run_dir)

    out_path = write_report(report, run_dir)
    print_summary(report)
    print(f"\nReport written to: {out_path}")


if __name__ == "__main__":
    main()
