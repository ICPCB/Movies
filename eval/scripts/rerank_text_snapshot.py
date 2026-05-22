"""Hermetic RERANK-01A text snapshot for q05 and q10.

This script reconstructs the exact reranker document source per DECOMP-01
pool member without model, embedder, GPU, Ollama, or network calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import chromadb
import pandas as pd


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from eval.scripts import _run_io  # noqa: E402
from src.config import CHROMA_DIR, COLLECTION_NAME, MOVIES_CSV  # noqa: E402
from src.retrieval.reranker import build_movie_document  # noqa: E402
from src.utils.dedup import get_movie_key  # noqa: E402


SCHEMA_VERSION = "rerank-01a-text-snapshot.v1"
QIDS = ("q05", "q10")
CONTROL_ARMS = ("pinned", "no_llm")
DECOMP_RELATIVE_PATH = (
    Path("analysis") / "decomp" / "q05_q10_pool_decomposition.json"
)
OUTPUT_RELATIVE_PATH = (
    Path("analysis") / "rerank_failure" / "q05_q10_text_snapshot.json"
)
REPORT_PATH = (
    _run_io.PROJECT_ROOT
    / "docs"
    / "superpowers"
    / "reports"
    / "rerank-01a-text-source-repair.md"
)


class RerankTextSnapshotError(ValueError):
    """Raised when RERANK-01A cannot safely reconstruct text."""


def run(run_id: Optional[str] = None) -> tuple[str, Path, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    decomp = load_decomp(actual_run_id)
    movies_df = pd.read_csv(MOVIES_CSV)
    collection = open_chroma_collection()
    data = build_snapshot(
        run_id=actual_run_id,
        decomp=decomp,
        movies_df=movies_df,
        collection=collection,
    )
    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    _run_io._atomic_write_json(output_path, data)
    write_report(REPORT_PATH, data)
    return actual_run_id, output_path, REPORT_PATH, data


def load_decomp(run_id: str) -> Dict[str, Any]:
    path = _run_io.run_dir(run_id) / DECOMP_RELATIVE_PATH
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RerankTextSnapshotError(f"{path}: JSON root must be an object")
    if data.get("schema_version") != "decomp-01-q05-q10.v1":
        raise RerankTextSnapshotError(
            "unexpected DECOMP schema_version: "
            f"{data.get('schema_version')!r}"
        )
    return data


def open_chroma_collection():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_collection(COLLECTION_NAME)


def build_snapshot(
    *,
    run_id: str,
    decomp: Mapping[str, Any],
    movies_df: pd.DataFrame,
    collection: Any,
) -> Dict[str, Any]:
    decomp_by_qid = _decomp_by_qid(decomp)
    per_qid: list[Dict[str, Any]] = []
    unresolved: list[Dict[str, Any]] = []

    for qid in QIDS:
        qid_row = decomp_by_qid[qid]
        qid_result: Dict[str, Any] = {
            "qid": qid,
            "tmdb_id": _optional_int(qid_row.get("tmdb_id")),
            "title": str(qid_row.get("title", "")),
            "arms": {},
        }
        for arm in CONTROL_ARMS:
            decomp_arm = qid_row["arms"][arm]
            rows = list(decomp_arm.get("extended_pool_rows", []))
            members: list[Dict[str, Any]] = []
            arm_unresolved: list[Dict[str, Any]] = []
            for pool_index, row in enumerate(rows):
                member, issue = resolve_member(
                    qid=qid,
                    arm=arm,
                    pool_index=pool_index,
                    row=row,
                    movies_df=movies_df,
                    collection=collection,
                )
                if issue is not None:
                    arm_unresolved.append(issue)
                    unresolved.append(issue)
                else:
                    members.append(member)

            qid_result["arms"][arm] = {
                "rerank_query": str(decomp_arm.get("rerank_query", "")),
                "recorded_loss_stage": decomp_arm.get("recorded_loss_stage"),
                "member_count": len(rows),
                "resolved_count": len(members),
                "unresolved_count": len(arm_unresolved),
                "members": members,
                "unresolved": arm_unresolved,
            }
        per_qid.append(qid_result)

    coverage = compute_coverage(per_qid, unresolved)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "hermeticity": {
            "model_calls": False,
            "embedder_calls": False,
            "gpu_required": False,
            "ollama_required": False,
            "network_required": False,
            "chroma_access": "PersistentClient.get_collection.get",
            "src_edit": False,
        },
        "source_artifacts": {
            "decomp_pool_q05_q10": str(DECOMP_RELATIVE_PATH).replace("\\", "/"),
            "movies_clean": "data/movies_clean.csv",
            "chroma_collection": f"{CHROMA_DIR}:{COLLECTION_NAME}",
        },
        "diagnosis": build_diagnosis(movies_df, collection),
        "qids": list(QIDS),
        "arms": list(CONTROL_ARMS),
        "analysis_complete": coverage["analysis_complete"],
        "coverage": coverage,
        "unresolved": unresolved,
        "per_qid": per_qid,
        "phase5_gate": "blocked",
    }


def resolve_member(
    *,
    qid: str,
    arm: str,
    pool_index: int,
    row: Mapping[str, Any],
    movies_df: pd.DataFrame,
    collection: Any,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    stage = classify_source_stage(row)
    decomp_id = _required_int(row.get("tmdb_id"), "tmdb_id")

    if stage["source_stage"] is None:
        return None, unresolved_member(
            qid=qid,
            arm=arm,
            pool_index=pool_index,
            row=row,
            decomp_id=decomp_id,
            reason="no_source_stage",
            stage=stage,
        )

    if stage["id_semantics"] == "tmdb_id":
        metadata = fetch_chroma_metadata(collection, decomp_id)
        if metadata is None:
            return None, unresolved_member(
                qid=qid,
                arm=arm,
                pool_index=pool_index,
                row=row,
                decomp_id=decomp_id,
                reason="missing_chroma_metadata",
                stage=stage,
            )
        movie = semantic_movie_from_metadata(decomp_id, metadata)
    else:
        if decomp_id < 0 or decomp_id >= len(movies_df):
            return None, unresolved_member(
                qid=qid,
                arm=arm,
                pool_index=pool_index,
                row=row,
                decomp_id=decomp_id,
                reason="row_index_out_of_range",
                stage=stage,
            )
        movie = bm25_movie_from_row(decomp_id, movies_df.iloc[decomp_id])

    actual_key = get_movie_key(movie)
    expected_key = str(row.get("movie_key", ""))
    if actual_key != expected_key:
        return None, unresolved_member(
            qid=qid,
            arm=arm,
            pool_index=pool_index,
            row=row,
            decomp_id=decomp_id,
            reason="movie_key_mismatch",
            stage=stage,
            expected_movie_key=expected_key,
            resolved_movie_key=actual_key,
        )

    document_text = build_movie_document(movie)
    text_fields = movie_text_fields(movie)
    member = {
        "qid": qid,
        "arm": arm,
        "pool_index": pool_index,
        "decomp_id": decomp_id,
        "decomp_tmdb_id_label": decomp_id,
        "movie_key": actual_key,
        "decomp_movie_key": expected_key,
        "movie_key_crosscheck_ok": True,
        "source_stage": stage["source_stage"],
        "id_semantics": stage["id_semantics"],
        "resolved_from": stage["resolved_from"],
        "is_target": bool(row.get("is_target")),
        "stage_ranks": stage_ranks(row),
        "stage_scores": stage_scores(row),
        "title": text_fields["title"],
        "release_date": text_fields["release_date"],
        "year": text_fields["year"],
        "genres": text_fields["genres"],
        "overview": text_fields["overview"],
        "keywords": text_fields["keywords"],
        "tagline": text_fields["tagline"],
        "text_fields": text_fields,
        "document_text": document_text,
        "document_fields": analyze_document_fields(movie, document_text),
    }
    if stage["id_semantics"] == "movies_clean_row_index":
        member["movies_clean_row_index"] = decomp_id
        member["movies_clean_tmdb_id"] = _optional_int(movies_df.iloc[decomp_id].get("id"))
    else:
        member["tmdb_id"] = decomp_id
    return member, None


def classify_source_stage(row: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    has_semantic = row.get("semantic_rank") is not None
    has_bm25 = row.get("bm25_rank") is not None
    if has_semantic:
        return {
            "source_stage": "semantic+bm25" if has_bm25 else "semantic",
            "id_semantics": "tmdb_id",
            "resolved_from": "chroma:movies",
        }
    if has_bm25:
        return {
            "source_stage": "bm25_only",
            "id_semantics": "movies_clean_row_index",
            "resolved_from": "movies_clean.csv:iloc",
        }
    return {
        "source_stage": None,
        "id_semantics": None,
        "resolved_from": None,
    }


def fetch_chroma_metadata(collection: Any, tmdb_id: int) -> Optional[Dict[str, Any]]:
    result = collection.get(ids=[f"tmdb_{tmdb_id}"], include=["metadatas"])
    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []
    if not ids or not metadatas or metadatas[0] is None:
        return None
    return dict(metadatas[0])


def semantic_movie_from_metadata(tmdb_id: int, meta: Mapping[str, Any]) -> Dict[str, Any]:
    # Mirrors src/retrieval/semantic.py:89-106 for fields used by reranker text.
    return {
        "id": int(tmdb_id),
        "title": meta.get("title", ""),
        "release_date": str(meta.get("release_date", "")),
        "year": derive_year_semantic(meta),
        "genres": meta.get("genres", ""),
        "overview": meta.get("overview", ""),
        "keywords": meta.get("keywords", ""),
        "tagline": meta.get("tagline", ""),
    }


def bm25_movie_from_row(row_index: int, row: Mapping[str, Any]) -> Dict[str, Any]:
    # Mirrors src/retrieval/bm25.py:169-185 for fields used by reranker text.
    return {
        "id": int(row_index),
        "title": str(row["title"]),
        "release_date": str(row.get("release_date", "")),
        "year": derive_year_bm25(row),
        "genres": str(row.get("genres_clean", row.get("genres", ""))),
        "overview": str(row.get("overview", ""))[:500],
        "keywords": str(row.get("keywords_clean", "") or ""),
        "tagline": str(row.get("tagline", "") or ""),
    }


def derive_year_semantic(meta: Mapping[str, Any]) -> int:
    y = meta.get("year")
    if y not in (None, "", 0, 0.0):
        try:
            return int(float(y))
        except (TypeError, ValueError):
            pass
    rd = str(meta.get("release_date", "") or "")
    if len(rd) >= 4 and rd[:4].isdigit():
        return int(rd[:4])
    return 0


def derive_year_bm25(row: Mapping[str, Any]) -> int:
    y = row.get("year")
    if pd.notna(y):
        try:
            return int(float(y))
        except (TypeError, ValueError):
            pass
    rd = row.get("release_date")
    if isinstance(rd, str) and len(rd) >= 4 and rd[:4].isdigit():
        return int(rd[:4])
    return 0


def movie_text_fields(movie: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": _optional_int(movie.get("id")),
        "title": str(movie.get("title", "") or ""),
        "release_date": str(movie.get("release_date", "") or ""),
        "year": _optional_int(movie.get("year")) or 0,
        "genres": str(movie.get("genres", "") or ""),
        "overview": str(movie.get("overview", "") or ""),
        "keywords": str(movie.get("keywords", "") or ""),
        "tagline": str(movie.get("tagline", "") or ""),
    }


def analyze_document_fields(
    movie: Mapping[str, Any],
    document_text: str,
) -> Dict[str, Any]:
    fields = {
        "title": _clean_text(movie.get("title")),
        "release_date": _clean_text(movie.get("release_date")),
        "year": str(_optional_int(movie.get("year")) or ""),
        "genres": _clean_text(movie.get("genres")),
        "tagline": _clean_text(movie.get("tagline")),
        "overview": _clean_text(movie.get("overview")),
        "keywords": _clean_text(movie.get("keywords")),
    }
    field_presence = {name: bool(value) for name, value in fields.items()}
    overview_chars = len(fields["overview"])
    keywords_chars = len(fields["keywords"])
    tagline_chars = len(fields["tagline"])
    ordered_names = (
        "title",
        "release_date",
        "year",
        "genres",
        "tagline",
        "overview",
        "keywords",
    )
    return {
        "field_presence": field_presence,
        "fields_present": [name for name in ordered_names if field_presence[name]],
        "fields_empty": [name for name in ordered_names if not field_presence[name]],
        "overview_chars": overview_chars,
        "overview_truncated": overview_chars > 600,
        "keywords_chars": keywords_chars,
        "keywords_truncated": keywords_chars > 200,
        "tagline_chars": tagline_chars,
        "tagline_truncated": tagline_chars > 200,
        "document_text_len": len(document_text),
        "document_degenerate": (not field_presence["overview"])
        or len(document_text) < 120,
    }


def unresolved_member(
    *,
    qid: str,
    arm: str,
    pool_index: int,
    row: Mapping[str, Any],
    decomp_id: int,
    reason: str,
    stage: Mapping[str, Optional[str]],
    expected_movie_key: Optional[str] = None,
    resolved_movie_key: Optional[str] = None,
) -> Dict[str, Any]:
    result = {
        "qid": qid,
        "arm": arm,
        "pool_index": pool_index,
        "decomp_id": decomp_id,
        "decomp_tmdb_id_label": decomp_id,
        "title": row.get("title"),
        "movie_key": row.get("movie_key"),
        "reason": reason,
        "source_stage": stage.get("source_stage"),
        "id_semantics": stage.get("id_semantics"),
        "resolved_from": stage.get("resolved_from"),
        "stage_ranks": stage_ranks(row),
    }
    if expected_movie_key is not None:
        result["expected_movie_key"] = expected_movie_key
    if resolved_movie_key is not None:
        result["resolved_movie_key"] = resolved_movie_key
    return result


def compute_coverage(
    per_qid: Sequence[Mapping[str, Any]],
    unresolved: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    per_arm: list[Dict[str, Any]] = []
    source_stage_counts: Counter[str] = Counter()
    resolved_from_counts: Counter[str] = Counter()
    total_members = 0
    resolved_members = 0

    for qid_row in per_qid:
        qid = str(qid_row["qid"])
        for arm in CONTROL_ARMS:
            arm_data = qid_row["arms"][arm]
            members = list(arm_data.get("members", []))
            member_count = int(arm_data["member_count"])
            unresolved_count = int(arm_data["unresolved_count"])
            total_members += member_count
            resolved_members += len(members)
            per_arm.append(
                {
                    "qid": qid,
                    "arm": arm,
                    "member_count": member_count,
                    "resolved_count": len(members),
                    "unresolved_count": unresolved_count,
                    "analysis_complete": unresolved_count == 0
                    and len(members) == member_count,
                }
            )
            for member in members:
                source_stage_counts[str(member["source_stage"])] += 1
                resolved_from_counts[str(member["resolved_from"])] += 1

    unresolved_count = len(unresolved)
    return {
        "total_members": total_members,
        "resolved_members": resolved_members,
        "unresolved_members": unresolved_count,
        "analysis_complete": unresolved_count == 0
        and resolved_members == total_members,
        "per_arm": per_arm,
        "source_stage_counts": dict(sorted(source_stage_counts.items())),
        "resolved_from_counts": dict(sorted(resolved_from_counts.items())),
    }


def build_diagnosis(movies_df: pd.DataFrame, collection: Any) -> Dict[str, Any]:
    row_8353_title = None
    row_8353_tmdb_id = None
    if len(movies_df) > 8353:
        row_8353 = movies_df.iloc[8353]
        row_8353_title = str(row_8353.get("title", ""))
        row_8353_tmdb_id = _optional_int(row_8353.get("id"))
    tmdb_8353_meta = fetch_chroma_metadata(collection, 8353)
    tmdb_8353_title = (
        str(tmdb_8353_meta.get("title", "")) if tmdb_8353_meta is not None else None
    )
    return {
        "summary": (
            "DECOMP-01 labelled each pool member id as tmdb_id, but the "
            "pipeline uses stage-dependent id semantics. Semantic-sourced "
            "members carry real TMDB ids from Chroma ids; BM25-only members "
            "carry movies_clean.csv positional row indexes."
        ),
        "dual_id_semantics": {
            "semantic": (
                "semantic.py uses Chroma doc ids tmdb_{id}; text fields come "
                "from Chroma metadata and the id is a real TMDB id."
            ),
            "bm25_only": (
                "bm25.py stamps id=int(idx), where idx is the pandas "
                "movies_clean.csv row position; text fields come from that "
                "CSV row with overview pre-truncated to 500 chars."
            ),
            "semantic_plus_bm25": (
                "fusion.py copies the semantic dict first and only fills "
                "empty metadata from BM25, so candidates found by both "
                "stages retain semantic id and text semantics."
            ),
        },
        "tmdb_8353_reconciliation": {
            "decomp_id": 8353,
            "bm25_interpretation": {
                "id_semantics": "movies_clean_row_index",
                "row_index": 8353,
                "title": row_8353_title,
                "csv_tmdb_id": row_8353_tmdb_id,
            },
            "tmdb_interpretation": {
                "id_semantics": "tmdb_id",
                "chroma_id": "tmdb_8353",
                "title": tmdb_8353_title,
            },
            "explanation": (
                "DECOMP 8353 is a BM25-only row index resolving to "
                "Supernova, while real TMDB id 8353 resolves to Limite."
            ),
        },
    }


def write_report(path: Path, data: Mapping[str, Any]) -> None:
    coverage = data["coverage"]
    diagnosis = data["diagnosis"]
    lines = [
        "# RERANK-01A Text Source Repair",
        "",
        "Ticket: RERANK-01A",
        f"Timestamp: {data['generated_at']}",
        f"Run: `{data['run_id']}`",
        "Scope: hermetic eval/report only; no src/* edits; no model, embedder, GPU, Ollama, or network.",
        "",
        "## Root cause",
        "",
        (
            "The pipeline uses two id semantics. Semantic candidates "
            "(`src/retrieval/semantic.py:74-108`, field recipe "
            "`semantic.py:89-106`) carry real TMDB ids from Chroma doc ids "
            "`tmdb_{id}` and Chroma metadata text. BM25-only candidates "
            "(`src/retrieval/bm25.py:163-187`, id stamp `bm25.py:168-169`, "
            "field recipe `bm25.py:169-185`) carry `int(idx)`, the "
            "0-based `movies_clean.csv` row index, and CSV-row text. "
            "RRF fusion (`src/retrieval/fusion.py:50,65-73`) gives the "
            "semantic dict precedence, so a candidate found by both stages "
            "keeps semantic id and text semantics."
        ),
        "",
        "## tmdb 8353 reconciliation",
        "",
    ]
    recon = diagnosis["tmdb_8353_reconciliation"]
    bm25 = recon["bm25_interpretation"]
    tmdb = recon["tmdb_interpretation"]
    lines.extend(
        [
            (
                f"DECOMP `8353` as a BM25-only id means "
                f"`movies_clean.csv` row {bm25['row_index']}, title "
                f"`{bm25['title']}`, CSV TMDB id `{bm25['csv_tmdb_id']}`."
            ),
            (
                f"Real TMDB id `8353` means Chroma id `{tmdb['chroma_id']}`, "
                f"title `{tmdb['title']}`. The earlier Supernova/Limite "
                "mismatch is therefore explained by the DECOMP label, not by "
                "a safe text source for BM25-only rows."
            ),
            "",
            "## Coverage",
            "",
            "| qid | arm | members | resolved | unresolved | complete |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in coverage["per_arm"]:
        lines.append(
            "| "
            f"{row['qid']} | {row['arm']} | {row['member_count']} | "
            f"{row['resolved_count']} | {row['unresolved_count']} | "
            f"{row['analysis_complete']} |"
        )

    lines.extend(
        [
            "",
            "## Source-stage breakdown",
            "",
            "| source_stage | members |",
            "|---|---:|",
        ]
    )
    for key, value in coverage["source_stage_counts"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "| resolved_from | members |", "|---|---:|"])
    for key, value in coverage["resolved_from_counts"].items():
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Snapshot",
            "",
            (
                "Snapshot: "
                "`eval/runs/"
                f"{data['run_id']}/analysis/rerank_failure/"
                "q05_q10_text_snapshot.json`"
            ),
            (
                "Schema: each resolved member carries `movie_key`, "
                "`decomp_id`, `source_stage`, `id_semantics`, "
                "`resolved_from`, the reconstructed text fields, "
                "`document_text`, and `document_fields` for the RERANK-01 "
                "re-run to consume directly."
            ),
            "",
            "## Phase 5 gate",
            "",
            "Phase 5 remains BLOCKED.",
        ]
    )
    _run_io._atomic_write_text(path, "\n".join(lines) + "\n")


def stage_ranks(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "semantic_rank": row.get("semantic_rank"),
        "bm25_rank": row.get("bm25_rank"),
        "rrf_rank": row.get("rrf_rank"),
        "rerank_rank": row.get("rerank_rank"),
        "final_rank": row.get("final_rank"),
    }


def stage_scores(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "semantic_score": row.get("semantic_score"),
        "bm25_score": row.get("bm25_score"),
        "rrf_score": row.get("rrf_score"),
        "rerank_score": row.get("rerank_score"),
        "final_score": row.get("final_score"),
    }


def _decomp_by_qid(decomp: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    rows = decomp.get("per_qid")
    if not isinstance(rows, list):
        raise RerankTextSnapshotError("DECOMP artifact missing per_qid list")
    result = {str(row.get("qid")): row for row in rows if isinstance(row, dict)}
    missing = [qid for qid in QIDS if qid not in result]
    if missing:
        raise RerankTextSnapshotError("DECOMP artifact missing qids: " + ", ".join(missing))
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _required_int(value: Any, field_name: str) -> int:
    result = _optional_int(value)
    if result is None:
        raise RerankTextSnapshotError(f"{field_name} must be an integer: {value!r}")
    return result


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build hermetic q05/q10 reranker text snapshot."
    )
    parser.add_argument("--run", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        run_id, output_path, report_path, data = run(args.run)
    except (RerankTextSnapshotError, FileNotFoundError) as exc:
        print(f"rerank_text_snapshot: {exc}", file=sys.stderr)
        return 1

    print(f"run_id={run_id}")
    print(f"output={output_path}")
    print(f"report={report_path}")
    print(f"analysis_complete={data['analysis_complete']}")
    print(f"unresolved={len(data['unresolved'])}")
    for row in data["coverage"]["per_arm"]:
        print(
            f"{row['qid']} {row['arm']}: "
            f"members={row['member_count']} "
            f"resolved={row['resolved_count']} "
            f"unresolved={row['unresolved_count']}"
        )
    return 0 if data["analysis_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
