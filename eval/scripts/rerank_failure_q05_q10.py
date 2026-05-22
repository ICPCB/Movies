"""Hermetic RERANK-01 characterization for q05 and q10."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io  # noqa: E402


SCHEMA_VERSION = "rerank-01-q05-q10.v1"
TEXT_SNAPSHOT_SCHEMA_VERSION = "rerank-01a-text-snapshot.v1"
QIDS = ("q05", "q10")
CONTROL_ARMS = ("pinned", "no_llm")
FAILURE_MODE_VALUES = {
    "document_text_degenerate",
    "metadata_genre_mismatch",
    "query_document_semantic_gap",
    "model_capability_limit_hypothesis",
    "stage_disagreement_only",
    "mixed",
    "inconclusive",
}
DECOMP_RELATIVE_PATH = (
    Path("analysis") / "decomp" / "q05_q10_pool_decomposition.json"
)
LOCALIZATION_RELATIVE_PATH = (
    Path("analysis") / "hy_fix_localize" / "localization.json"
)
TEXT_SNAPSHOT_RELATIVE_PATH = (
    Path("analysis") / "rerank_failure" / "q05_q10_text_snapshot.json"
)
OUTPUT_RELATIVE_PATH = (
    Path("analysis") / "rerank_failure" / "q05_q10_reranker_characterization.json"
)
REPORT_PATH = (
    _run_io.PROJECT_ROOT
    / "docs"
    / "superpowers"
    / "reports"
    / "rerank-01-q05-q10.md"
)


class RerankFailureError(ValueError):
    """Raised when RERANK-01 cannot safely characterize the evidence."""


def run(run_id: Optional[str] = None) -> tuple[str, Path, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    inputs = load_inputs(actual_run_id)
    data = build_characterization(actual_run_id, inputs)
    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_io._atomic_write_json(output_path, data)
    write_report(REPORT_PATH, data)
    return actual_run_id, output_path, REPORT_PATH, data


def load_inputs(run_id: str) -> Dict[str, Any]:
    run_path = _run_io.run_dir(run_id)
    paths = {
        "decomp": run_path / DECOMP_RELATIVE_PATH,
        "localization": run_path / LOCALIZATION_RELATIVE_PATH,
        "text_snapshot": run_path / TEXT_SNAPSHOT_RELATIVE_PATH,
    }
    missing = [path for path in paths.values() if not path.exists()]
    if missing:
        raise RerankFailureError(
            "required input file missing: " + ", ".join(str(path) for path in missing)
        )

    decomp = _read_json_object(paths["decomp"])
    localization = _read_json_object(paths["localization"])
    text_snapshot = _read_json_object(paths["text_snapshot"])
    _assert_text_snapshot_complete(text_snapshot)
    return {
        "decomp": decomp,
        "localization": localization,
        "snapshot_by_member_key": _index_text_snapshot(text_snapshot),
    }


def build_characterization(run_id: str, inputs: Mapping[str, Any]) -> Dict[str, Any]:
    decomp = inputs["decomp"]
    if decomp.get("schema_version") != "decomp-01-q05-q10.v1":
        raise RerankFailureError(
            "unexpected DECOMP schema_version: "
            f"{decomp.get('schema_version')!r}"
        )

    decomp_by_qid = _decomp_by_qid(decomp)
    localization_by_qid = _localization_by_qid(inputs["localization"])
    standard_cutoff = int(
        decomp.get("trace_meta", {}).get("standard_rerank_top_k", 50)
    )
    per_qid: list[Dict[str, Any]] = []
    unresolved: list[Dict[str, Any]] = []

    for qid in QIDS:
        qid_row = decomp_by_qid[qid]
        localized = localization_by_qid[qid]
        arms: Dict[str, Any] = {}
        for arm in CONTROL_ARMS:
            decomp_arm = qid_row["arms"][arm]
            _assert_localization_matches(
                qid=qid,
                arm=arm,
                decomp_arm=decomp_arm,
                localization_arm=localized["arms"][arm],
            )
            arm_result, arm_unresolved = characterize_arm(
                qid=qid,
                arm=arm,
                target_tmdb_id=int(qid_row["tmdb_id"]),
                decomp_arm=decomp_arm,
                inputs=inputs,
                standard_cutoff=standard_cutoff,
            )
            arms[arm] = arm_result
            unresolved.extend(arm_unresolved)
        per_qid.append(
            {
                "qid": qid,
                "tmdb_id": int(qid_row["tmdb_id"]),
                "title": str(qid_row["title"]),
                "arms": arms,
            }
        )

    failure_mode = classify_failure_mode(per_qid, unresolved)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "hermeticity": {
            "model_calls": False,
            "reranker_scores_recomputed": False,
            "gpu_required": False,
            "network_required": False,
            "src_import": False,
            "src_edit": False,
        },
        "source_artifacts": {
            "decomp_pool_q05_q10": str(DECOMP_RELATIVE_PATH).replace("\\", "/"),
            "decomp_schema_version": decomp.get("schema_version"),
            "text_snapshot": str(TEXT_SNAPSHOT_RELATIVE_PATH).replace("\\", "/"),
            "text_snapshot_schema_version": TEXT_SNAPSHOT_SCHEMA_VERSION,
            "localization": str(LOCALIZATION_RELATIVE_PATH).replace("\\", "/"),
        },
        "qids": list(QIDS),
        "arms": list(CONTROL_ARMS),
        "standard_rerank_top_k": standard_cutoff,
        "analysis_complete": not unresolved,
        "unresolved_text_members": unresolved,
        "per_qid": per_qid,
        "phase5_gate": "blocked",
        "failure_mode": failure_mode,
    }


def characterize_arm(
    *,
    qid: str,
    arm: str,
    target_tmdb_id: int,
    decomp_arm: Mapping[str, Any],
    inputs: Mapping[str, Any],
    standard_cutoff: int,
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    rows = list(decomp_arm.get("extended_pool_rows", []))
    target_row = _target_row(rows, target_tmdb_id)
    target_rank = int(target_row["rerank_rank"])
    false_positive_rows = sorted(
        [
            row
            for row in rows
            if not bool(row.get("is_target"))
            and _coerce_int(row.get("rerank_rank")) is not None
            and int(row["rerank_rank"]) < target_rank
        ],
        key=lambda row: int(row["rerank_rank"]),
    )

    target_record, target_unresolved = characterize_candidate(
        qid=qid,
        arm=arm,
        role="target",
        row=target_row,
        target_score=float(target_row["rerank_score"]),
        rerank_query=str(decomp_arm["rerank_query"]),
        inputs=inputs,
    )
    false_positives = []
    unresolved = list(target_unresolved)
    for row in false_positive_rows:
        record, record_unresolved = characterize_candidate(
            qid=qid,
            arm=arm,
            role="false_positive",
            row=row,
            target_score=float(target_row["rerank_score"]),
            rerank_query=str(decomp_arm["rerank_query"]),
            inputs=inputs,
        )
        false_positives.append(record)
        unresolved.extend(record_unresolved)

    stage = attribute_stage_disagreement(
        target_row,
        standard_cutoff=standard_cutoff,
    )
    return (
        {
            "rerank_query": str(decomp_arm["rerank_query"]),
            "recorded_loss_stage": decomp_arm.get("recorded_loss_stage"),
            "target": target_record,
            "false_positives_above_target": false_positives,
            "false_positive_count": len(false_positives),
            "stage_disagreement": stage,
        },
        unresolved,
    )


def characterize_candidate(
    *,
    qid: str,
    arm: str,
    role: str,
    row: Mapping[str, Any],
    target_score: float,
    rerank_query: str,
    inputs: Mapping[str, Any],
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    tmdb_id = int(row["tmdb_id"])
    movie_key = _required_movie_key(row)
    source = resolve_snapshot_member(
        qid=qid,
        arm=arm,
        movie_key=movie_key,
        inputs=inputs,
    )
    document_text = _required_document_text(source, qid=qid, arm=arm, movie_key=movie_key)
    document_fields = _required_document_fields(
        source,
        qid=qid,
        arm=arm,
        movie_key=movie_key,
    )
    source_stage = _required_source_stage(
        source,
        qid=qid,
        arm=arm,
        movie_key=movie_key,
    )

    return (
        {
            "role": role,
            "tmdb_id": tmdb_id,
            "movie_key": movie_key,
            "title": str(row.get("title", "")),
            "year": row.get("year"),
            "rerank_query": rerank_query,
            "document_text": document_text,
            "document_source": str(TEXT_SNAPSHOT_RELATIVE_PATH).replace("\\", "/"),
            "document_source_status": "resolved",
            "document_source_note": "resolved_by_movie_key",
            "document_fields": document_fields,
            "source_stage": source_stage,
            "id_semantics": source.get("id_semantics"),
            "resolved_from": source.get("resolved_from"),
            "stage_ranks": {
                "semantic_rank": row.get("semantic_rank"),
                "bm25_rank": row.get("bm25_rank"),
                "rrf_rank": row.get("rrf_rank"),
                "rerank_rank": row.get("rerank_rank"),
                "final_rank": row.get("final_rank"),
            },
            "stage_scores": {
                "semantic_score": row.get("semantic_score"),
                "bm25_score": row.get("bm25_score"),
                "rrf_score": row.get("rrf_score"),
                "rerank_score": row.get("rerank_score"),
                "final_score": row.get("final_score"),
            },
            "rerank_score": row.get("rerank_score"),
            "rerank_rank": row.get("rerank_rank"),
            "rerank_score_gap_vs_target": compute_score_gap(
                row.get("rerank_score"),
                target_score,
            ),
        },
        [],
    )


def resolve_snapshot_member(
    *,
    qid: str,
    arm: str,
    movie_key: str,
    inputs: Mapping[str, Any],
) -> Dict[str, Any]:
    key = (qid, arm, movie_key)
    member = inputs["snapshot_by_member_key"].get(key)
    if member is None:
        raise RerankFailureError(
            "text snapshot missing characterized candidate: "
            f"qid={qid} arm={arm} movie_key={movie_key!r}"
        )
    return dict(member)


def analyze_document_fields(
    movie: Mapping[str, Any],
    document_text: str,
) -> Dict[str, Any]:
    fields = {
        "title": _clean_text(movie.get("title")),
        "genres": _clean_text(movie.get("genres")),
        "tagline": _clean_text(movie.get("tagline")),
        "overview": _clean_text(movie.get("overview")),
        "keywords": _clean_text(movie.get("keywords")),
    }
    field_presence = {name: bool(value) for name, value in fields.items()}
    overview_chars = len(fields["overview"])
    keywords_chars = len(fields["keywords"])
    return {
        "field_presence": field_presence,
        "fields_present": [
            name for name in ("title", "genres", "tagline", "overview", "keywords")
            if field_presence[name]
        ],
        "fields_empty": [
            name for name in ("title", "genres", "tagline", "overview", "keywords")
            if not field_presence[name]
        ],
        "overview_chars": overview_chars,
        "overview_truncated": overview_chars > 600,
        "keywords_chars": keywords_chars,
        "keywords_truncated": keywords_chars > 200,
        "document_text_len": len(document_text),
        "document_degenerate": (not field_presence["overview"])
        or len(document_text) < 120,
    }


def unresolved_document_fields() -> Dict[str, Any]:
    return {
        "field_presence": {
            "title": None,
            "genres": None,
            "tagline": None,
            "overview": None,
            "keywords": None,
        },
        "fields_present": [],
        "fields_empty": [],
        "overview_chars": None,
        "overview_truncated": None,
        "keywords_chars": None,
        "keywords_truncated": None,
        "document_text_len": None,
        "document_degenerate": None,
    }


def compute_score_gap(score: Any, target_score: Any) -> Optional[float]:
    if score is None or target_score is None:
        return None
    return float(score) - float(target_score)


def attribute_stage_disagreement(
    target_row: Mapping[str, Any],
    *,
    standard_cutoff: int,
    final_top_k: int = 5,
) -> Dict[str, Any]:
    rrf_rank = _coerce_int(target_row.get("rrf_rank"))
    rerank_rank = _coerce_int(target_row.get("rerank_rank"))
    final_rank = _coerce_int(target_row.get("final_rank"))
    if rrf_rank is None or rrf_rank >= standard_cutoff:
        attribution = "rrf_recall"
        reranker_demoted = False
    elif rerank_rank is not None and rerank_rank >= final_top_k:
        attribution = "reranker"
        reranker_demoted = True
    elif final_rank is not None and final_rank >= final_top_k:
        attribution = "final_blend"
        reranker_demoted = False
    else:
        attribution = "final_blend"
        reranker_demoted = False

    secondary: list[str] = []
    if (
        final_rank is not None
        and rerank_rank is not None
        and final_rank >= final_top_k
        and final_rank > rerank_rank
        and "final_blend" != attribution
    ):
        secondary.append("final_blend")
    return {
        "attribution": attribution,
        "secondary_attributions": secondary,
        "reranker_demoted_well_retrieved_target": reranker_demoted,
        "standard_cutoff": standard_cutoff,
        "target_rrf_rank": rrf_rank,
        "target_rerank_rank": rerank_rank,
        "target_final_rank": final_rank,
        "final_top_k": final_top_k,
    }


def classify_failure_mode(
    per_qid: Sequence[Mapping[str, Any]],
    unresolved: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    evidence: list[str] = []
    if unresolved:
        for item in unresolved[:8]:
            evidence.append(
                "unresolved required document text: "
                f"qid={item['qid']} role={item['role']} "
                f"tmdb_id={item['tmdb_id']} title={item['title']!r} "
                f"rerank_rank={item['rerank_rank']} reason={item['reason']}"
            )
        classification = "inconclusive"
        rejected = {
            "document_text_degenerate": (
                "Cannot distinguish true degenerate target text from missing "
                "allowed-source coverage for false positives."
            ),
            "metadata_genre_mismatch": (
                "Cannot compare metadata composition for every false positive "
                "above the target."
            ),
            "model_capability_limit_hypothesis": (
                "Cannot isolate model behavior until exact false-positive "
                "document text is reconstructed."
            ),
            "stage_disagreement_only": (
                "The no_llm arms still show reranker-stage demotion, but the "
                "text-pair evidence is incomplete."
            ),
        }
    else:
        clean_reranker = _clean_reranker_evidence(per_qid)
        degenerate_targets = _degenerate_targets(per_qid)
        domain_signals = _domain_signals(per_qid)
        if degenerate_targets and clean_reranker:
            classification = "mixed"
            evidence.extend(degenerate_targets)
            evidence.extend(clean_reranker)
            rejected = {}
        elif degenerate_targets:
            classification = "document_text_degenerate"
            evidence.extend(degenerate_targets)
            rejected = {}
        elif clean_reranker and domain_signals:
            classification = "model_capability_limit_hypothesis"
            evidence.extend(clean_reranker)
            evidence.extend(domain_signals)
            rejected = {
                "document_text_degenerate": "Target documents are overview-bearing.",
                "stage_disagreement_only": "The no_llm arms contain reranker demotion.",
            }
        elif clean_reranker:
            classification = "query_document_semantic_gap"
            evidence.extend(clean_reranker)
            rejected = {
                "document_text_degenerate": "Target documents are overview-bearing.",
                "stage_disagreement_only": "The no_llm arms contain reranker demotion.",
            }
        else:
            classification = "stage_disagreement_only"
            evidence.append("No clean no_llm reranker demotion remained after staging.")
            rejected = {}

    if classification not in FAILURE_MODE_VALUES:
        raise RerankFailureError(f"unsupported failure_mode: {classification}")

    evidence.extend(_stage_evidence(per_qid))
    return {
        "classification": classification,
        "evidence": evidence,
        "rejected_competing_classifications": rejected,
        "recommended_followup": recommended_followup(classification),
    }


def recommended_followup(classification: str) -> str:
    if classification == "inconclusive":
        return (
            "RERANK-02 should first repair or snapshot the missing allowed "
            "document sources for the unresolved false positives, then run a "
            "model-backed comparison on the same q05/q10 no_llm pairs against "
            "an alternative cross-encoder. Keep pinned arms as RRF/final-blend "
            "context, not as the primary reranker signal."
        )
    if classification == "document_text_degenerate":
        return (
            "RERANK-02 should re-score the affected pairs with repaired "
            "document text and compare target rank movement against the "
            "recorded DECOMP-01 scores."
        )
    if classification == "metadata_genre_mismatch":
        return (
            "RERANK-02 should model-score metadata ablations for Genres and "
            "Keywords on target and false-positive pairs."
        )
    if classification == "query_document_semantic_gap":
        return (
            "RERANK-02 should re-score the same documents with bounded "
            "alternative rerank_query formulations."
        )
    if classification == "model_capability_limit_hypothesis":
        return (
            "RERANK-02 should compare bge-reranker-v2-m3 with an alternative "
            "cross-encoder on the exact reconstructed q05/q10 no_llm pairs."
        )
    if classification == "stage_disagreement_only":
        return (
            "RERANK-02 may not be the next ticket; first re-open stage "
            "attribution because the decisive loss is not isolated to the "
            "cross-encoder."
        )
    return (
        "RERANK-02 should test the strongest model-backed what-if for each "
        "material sub-mode identified here, one bounded comparison at a time."
    )


def write_report(path: Path, data: Mapping[str, Any]) -> None:
    lines = [
        "# RERANK-01 q05/q10 Cross-Encoder Characterization",
        "",
        "Ticket: RERANK-01B",
        f"Timestamp: {data['generated_at']}",
        f"Run: `{data['run_id']}`",
        "Scope: eval/report only; no src/* edits; hermetic.",
        "",
        "## Method",
        "",
        (
            "The runner consumed the DECOMP-01 pool decomposition, "
            "the RERANK-01A text snapshot keyed by `(qid, arm, movie_key)`, "
            "and localization for consistency checks. It consumed snapshot "
            "`document_text` verbatim, kept reranker scores and ranks from "
            "DECOMP-01, imported no `src/*` code, and made no model, GPU, LLM, "
            "Ollama, network, or reranker scoring call."
        ),
        "",
        "## Completeness",
        "",
        f"- analysis_complete: `{data['analysis_complete']}`",
        f"- unresolved_text_members: `{len(data['unresolved_text_members'])}`",
        "",
    ]

    lines.append("## Per-arm characterization")
    for qid_row in data["per_qid"]:
        qid = qid_row["qid"]
        for arm in CONTROL_ARMS:
            arm_data = qid_row["arms"][arm]
            lines.extend(
                [
                    "",
                    f"### {qid} {arm}",
                    "",
                    "| role | tmdb_id | title | source_stage | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |",
                    "|---|---:|---|---|---:|---:|---:|---:|---:|---|",
                ]
            )
            records = [arm_data["target"]] + arm_data["false_positives_above_target"]
            for record in records:
                fields = record["document_fields"]
                fields_present = ", ".join(fields.get("fields_present") or [])
                lines.append(
                    "| "
                    f"{record['role']} | "
                    f"{record['tmdb_id']} | "
                    f"{_md(record['title'])} | "
                    f"{_md(record['source_stage'])} | "
                    f"{record['rerank_rank']} | "
                    f"{_fmt_float(record['rerank_score'])} | "
                    f"{_fmt_float(record['rerank_score_gap_vs_target'])} | "
                    f"{_fmt_int(fields.get('document_text_len'))} | "
                    f"{_fmt_int(fields.get('overview_chars'))} | "
                    f"{_md(fields_present or 'UNRESOLVED')} |"
                )

    lines.extend(
        [
            "",
            "## Stage-disagreement summary",
            "",
            "| qid | arm | attribution | reranker_demoted_well_retrieved_target | secondary |",
            "|---|---|---|---:|---|",
        ]
    )
    for qid_row in data["per_qid"]:
        for arm in CONTROL_ARMS:
            stage = qid_row["arms"][arm]["stage_disagreement"]
            lines.append(
                "| "
                f"{qid_row['qid']} | {arm} | {stage['attribution']} | "
                f"{stage['reranker_demoted_well_retrieved_target']} | "
                f"{', '.join(stage['secondary_attributions']) or 'none'} |"
            )

    failure = data["failure_mode"]
    lines.extend(
        [
            "",
            "## Failure mode",
            "",
            f"Classification: `{failure['classification']}`",
            "",
            "Evidence:",
        ]
    )
    for item in failure["evidence"]:
        lines.append(f"- {item}")
    lines.extend(["", "Rejected competing classifications:"])
    rejected = failure.get("rejected_competing_classifications") or {}
    if rejected:
        for key, reason in rejected.items():
            lines.append(f"- `{key}`: {reason}")
    else:
        lines.append("- None recorded.")

    lines.extend(
        [
            "",
            "## Recommended RERANK-02 scope",
            "",
            failure["recommended_followup"],
            "",
            "## Phase 5 gate",
            "",
            "Phase 5 remains BLOCKED.",
        ]
    )
    _run_io._atomic_write_text(path, "\n".join(lines) + "\n")


def _assert_localization_matches(
    *,
    qid: str,
    arm: str,
    decomp_arm: Mapping[str, Any],
    localization_arm: Mapping[str, Any],
) -> None:
    decomp_stage = decomp_arm.get("reproduced_standard_stage_table", {})
    localization_stage = localization_arm.get("stage_table", {})
    checks = (
        ("semantic", "rank"),
        ("bm25", "rank"),
        ("rrf", "rank"),
        ("rerank", "rerank_rank"),
        ("final", "final_rank"),
    )
    mismatches = []
    for section, field in checks:
        decomp_value = _nested(decomp_stage, section, field)
        loc_value = _nested(localization_stage, section, field)
        if decomp_value != loc_value:
            mismatches.append(
                f"{section}.{field}: decomp={decomp_value} localization={loc_value}"
            )
    if decomp_arm.get("recorded_loss_stage") != localization_arm.get("loss_stage"):
        mismatches.append(
            "loss_stage: "
            f"decomp={decomp_arm.get('recorded_loss_stage')} "
            f"localization={localization_arm.get('loss_stage')}"
        )
    if mismatches:
        raise RerankFailureError(
            f"{qid} {arm} DECOMP/localization divergence: "
            + "; ".join(mismatches)
        )


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RerankFailureError(f"{path}: JSON root must be an object")
    return data


def _assert_text_snapshot_complete(snapshot: Mapping[str, Any]) -> None:
    schema_version = snapshot.get("schema_version")
    if schema_version != TEXT_SNAPSHOT_SCHEMA_VERSION:
        raise RerankFailureError(
            "unexpected text snapshot schema_version: "
            f"{schema_version!r}"
        )
    if snapshot.get("analysis_complete") is not True:
        unresolved = snapshot.get("unresolved")
        unresolved_count = len(unresolved) if isinstance(unresolved, list) else "unknown"
        raise RerankFailureError(
            "text snapshot is incomplete: "
            f"analysis_complete={snapshot.get('analysis_complete')!r} "
            f"unresolved={unresolved_count}"
        )


def _index_text_snapshot(
    snapshot: Mapping[str, Any],
) -> Dict[tuple[str, str, str], Dict[str, Any]]:
    rows = snapshot.get("per_qid")
    if not isinstance(rows, list):
        raise RerankFailureError("text snapshot missing per_qid list")

    result: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    seen_qids: set[str] = set()
    for qid_row in rows:
        if not isinstance(qid_row, dict):
            raise RerankFailureError("text snapshot per_qid row must be object")
        qid = str(qid_row.get("qid"))
        seen_qids.add(qid)
        arms = qid_row.get("arms")
        if not isinstance(arms, dict):
            raise RerankFailureError(f"text snapshot {qid} missing arms object")
        for arm in CONTROL_ARMS:
            arm_data = arms.get(arm)
            if not isinstance(arm_data, dict):
                raise RerankFailureError(
                    f"text snapshot {qid} {arm} missing arm object"
                )
            members = arm_data.get("members")
            if not isinstance(members, list):
                raise RerankFailureError(
                    f"text snapshot {qid} {arm} missing members list"
                )
            for member in members:
                if not isinstance(member, dict):
                    raise RerankFailureError(
                        f"text snapshot {qid} {arm} member must be object"
                    )
                member_qid = str(member.get("qid", qid))
                member_arm = str(member.get("arm", arm))
                if member_qid != qid or member_arm != arm:
                    raise RerankFailureError(
                        "text snapshot member qid/arm mismatch: "
                        f"container={qid}/{arm} member={member_qid}/{member_arm}"
                    )
                movie_key = str(member.get("movie_key", "") or "").strip()
                if not movie_key:
                    raise RerankFailureError(
                        f"text snapshot {qid} {arm} member missing movie_key"
                    )
                key = (qid, arm, movie_key)
                if key in result:
                    raise RerankFailureError(
                        "text snapshot duplicate member key: "
                        f"qid={qid} arm={arm} movie_key={movie_key!r}"
                    )
                result[key] = dict(member)

    missing = [qid for qid in QIDS if qid not in seen_qids]
    if missing:
        raise RerankFailureError(
            "text snapshot missing qids: " + ", ".join(missing)
        )
    return result


def _required_movie_key(row: Mapping[str, Any]) -> str:
    movie_key = str(row.get("movie_key", "") or "").strip()
    if not movie_key:
        raise RerankFailureError(
            "DECOMP row missing movie_key for characterized candidate: "
            f"tmdb_id={row.get('tmdb_id')} title={row.get('title')!r}"
        )
    return movie_key


def _required_document_text(
    member: Mapping[str, Any],
    *,
    qid: str,
    arm: str,
    movie_key: str,
) -> str:
    document_text = member.get("document_text")
    if not isinstance(document_text, str) or not document_text:
        raise RerankFailureError(
            "text snapshot member missing document_text: "
            f"qid={qid} arm={arm} movie_key={movie_key!r}"
        )
    return document_text


def _required_document_fields(
    member: Mapping[str, Any],
    *,
    qid: str,
    arm: str,
    movie_key: str,
) -> Dict[str, Any]:
    document_fields = member.get("document_fields")
    if not isinstance(document_fields, dict):
        raise RerankFailureError(
            "text snapshot member missing document_fields: "
            f"qid={qid} arm={arm} movie_key={movie_key!r}"
        )
    return dict(document_fields)


def _required_source_stage(
    member: Mapping[str, Any],
    *,
    qid: str,
    arm: str,
    movie_key: str,
) -> str:
    source_stage = str(member.get("source_stage", "") or "").strip()
    if not source_stage:
        raise RerankFailureError(
            "text snapshot member missing source_stage: "
            f"qid={qid} arm={arm} movie_key={movie_key!r}"
        )
    return source_stage


def _decomp_by_qid(decomp: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    rows = decomp.get("per_qid")
    if not isinstance(rows, list):
        raise RerankFailureError("DECOMP artifact missing per_qid list")
    result = {str(row.get("qid")): row for row in rows if isinstance(row, dict)}
    missing = [qid for qid in QIDS if qid not in result]
    if missing:
        raise RerankFailureError("DECOMP artifact missing qids: " + ", ".join(missing))
    return result


def _localization_by_qid(
    localization: Mapping[str, Any],
) -> Dict[str, Mapping[str, Any]]:
    rows = localization.get("per_target")
    if not isinstance(rows, list):
        raise RerankFailureError("localization missing per_target list")
    result = {str(row.get("qid")): row for row in rows if isinstance(row, dict)}
    missing = [qid for qid in QIDS if qid not in result]
    if missing:
        raise RerankFailureError("localization missing qids: " + ", ".join(missing))
    return result


def _target_row(
    rows: Sequence[Mapping[str, Any]],
    target_tmdb_id: int,
) -> Mapping[str, Any]:
    matches = [
        row
        for row in rows
        if bool(row.get("is_target")) or int(row.get("tmdb_id")) == target_tmdb_id
    ]
    if len(matches) != 1:
        raise RerankFailureError(
            f"expected one target row for tmdb_id={target_tmdb_id}, got {len(matches)}"
        )
    return matches[0]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nested(data: Mapping[str, Any], section: str, field: str) -> Any:
    value = data.get(section)
    if isinstance(value, dict):
        return value.get(field)
    return None


def _clean_reranker_evidence(per_qid: Sequence[Mapping[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for qid_row in per_qid:
        arm = qid_row["arms"]["no_llm"]
        stage = arm["stage_disagreement"]
        target = arm["target"]
        if stage["reranker_demoted_well_retrieved_target"]:
            evidence.append(
                f"{qid_row['qid']} no_llm: target RRF rank "
                f"{stage['target_rrf_rank']} but rerank rank "
                f"{target['rerank_rank']} with rerank_score "
                f"{_fmt_float(target['rerank_score'])}; "
                f"{arm['false_positive_count']} false positives outrank it."
            )
    return evidence


def _degenerate_targets(per_qid: Sequence[Mapping[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for qid_row in per_qid:
        for arm in CONTROL_ARMS:
            target = qid_row["arms"][arm]["target"]
            fields = target["document_fields"]
            if fields.get("document_degenerate") is True:
                evidence.append(
                    f"{qid_row['qid']} {arm}: target document is degenerate "
                    f"(doc_len={fields.get('document_text_len')}, "
                    f"overview_chars={fields.get('overview_chars')})."
                )
    return evidence


def _domain_signals(per_qid: Sequence[Mapping[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for qid_row in per_qid:
        title = str(qid_row.get("title", ""))
        if "[" in title or "]" in title or title.lower() == "thanatomorphose":
            evidence.append(
                f"{qid_row['qid']}: target title/domain signal is atypical: {title!r}."
            )
    return evidence


def _stage_evidence(per_qid: Sequence[Mapping[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for qid_row in per_qid:
        for arm in CONTROL_ARMS:
            stage = qid_row["arms"][arm]["stage_disagreement"]
            evidence.append(
                f"{qid_row['qid']} {arm}: attribution={stage['attribution']}, "
                f"rrf_rank={stage['target_rrf_rank']}, "
                f"rerank_rank={stage['target_rerank_rank']}, "
                f"final_rank={stage['target_final_rank']}."
            )
    return evidence


def _fmt_float(value: Any) -> str:
    if value is None:
        return "null"
    return f"{float(value):.6f}"


def _fmt_int(value: Any) -> str:
    if value is None:
        return "null"
    return str(int(value))


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hermetically characterize q05/q10 cross-encoder failures."
    )
    parser.add_argument("--run", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, output_path, report_path, data = run(args.run)
    except (RerankFailureError, FileNotFoundError) as exc:
        print(f"rerank_failure_q05_q10: {exc}", file=sys.stderr)
        return 1

    print(f"run_id={run_id}")
    print(f"output={output_path}")
    print(f"report={report_path}")
    print(f"failure_mode={data['failure_mode']['classification']}")
    print(f"analysis_complete={data['analysis_complete']}")
    print(f"unresolved_text_members={len(data['unresolved_text_members'])}")
    print(f"phase5_gate={data['phase5_gate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
