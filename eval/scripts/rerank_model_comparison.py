"""RERANK-02 q05/q10 content-gap and cross-encoder comparison."""

from __future__ import annotations

import argparse
import gc
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from eval.scripts import _run_io


SCHEMA_VERSION = "rerank-02-model-comparison.v1"
QIDS = ("q05", "q10")
CONTROL_ARMS = ("pinned", "no_llm")
HEADLINE_ARM = "no_llm"
TOP5_CUTOFF = 5
VRAM_BUDGET_GB = 8.0

TEXT_SNAPSHOT_RELATIVE_PATH = (
    Path("analysis") / "rerank_failure" / "q05_q10_text_snapshot.json"
)
CHARACTERIZATION_RELATIVE_PATH = (
    Path("analysis") / "rerank_failure" / "q05_q10_reranker_characterization.json"
)
DECOMP_RELATIVE_PATH = (
    Path("analysis") / "decomp" / "q05_q10_pool_decomposition.json"
)
OUTPUT_RELATIVE_PATH = (
    Path("analysis") / "rerank_failure" / "q05_q10_model_comparison.json"
)
LOADER_DIAGNOSTIC_RELATIVE_PATH = (
    Path("analysis") / "rerank_failure" / "q05_q10_loader_diagnostic.json"
)
REPORT_PATH = (
    _run_io.PROJECT_ROOT
    / "docs"
    / "superpowers"
    / "reports"
    / "rerank-02-model-comparison.md"
)

WORD_RE = re.compile(r"[a-z0-9]+")

SNAPSHOT_ALLOW_PATTERNS = (
    "*.bin",
    "*.json",
    "*.model",
    "*.py",
    "*.safetensors",
    "*.txt",
    "merges.txt",
    "modules.json",
    "sentencepiece.bpe.model",
    "spm.model",
    "tokenizer.*",
    "vocab.*",
)


@dataclass(frozen=True)
class ModelSpec:
    role: str
    model_id: str
    trust_remote_code: bool
    batch_size: int
    max_length: Optional[int]
    expected_peak_vram_gb: float
    expected_time_minutes: str


MODEL_SPECS = (
    ModelSpec(
        role="primary_multilingual",
        model_id="Alibaba-NLP/gte-multilingual-reranker-base",
        trust_remote_code=True,
        batch_size=4,
        max_length=8192,
        expected_peak_vram_gb=4.5,
        expected_time_minutes="10-20 including one-time snapshot download",
    ),
    ModelSpec(
        role="small_contrast",
        model_id="cross-encoder/ms-marco-MiniLM-L6-v2",
        trust_remote_code=False,
        batch_size=32,
        max_length=512,
        expected_peak_vram_gb=1.0,
        expected_time_minutes="2-5 including one-time snapshot download",
    ),
)


class RerankModelComparisonError(ValueError):
    """Raised when RERANK-02 cannot safely build the comparison artifact."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def read_json_object(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RerankModelComparisonError(f"{path}: invalid JSON") from exc
    if not isinstance(data, dict):
        raise RerankModelComparisonError(f"{path}: JSON root must be an object")
    return data


def token_set(text: Any) -> set[str]:
    return set(WORD_RE.findall(str(text or "").lower()))


def overlap_metrics(query: Any, text: Any) -> Dict[str, Any]:
    query_tokens = token_set(query)
    text_tokens = token_set(text)
    overlap = query_tokens & text_tokens
    union = query_tokens | text_tokens
    return {
        "query_token_count": len(query_tokens),
        "document_token_count": len(text_tokens),
        "overlap_count": len(overlap),
        "jaccard": round((len(overlap) / len(union)) if union else 0.0, 6),
        "overlap_tokens": sorted(overlap),
    }


def field_overlap_metrics(
    *,
    rerank_query: str,
    fields: Mapping[str, Any],
) -> Dict[str, Any]:
    field_names = ("genres", "keywords", "overview")
    field_metrics = {
        name: overlap_metrics(rerank_query, fields.get(name, ""))
        for name in field_names
    }
    combined_text = " ".join(str(fields.get(name, "") or "") for name in field_names)
    field_metrics["combined"] = overlap_metrics(rerank_query, combined_text)
    return field_metrics


def evaluate_content_gap(
    target_overlap: Mapping[str, Any],
    false_positive_overlaps: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    target_combined = target_overlap["overlap"]["combined"]
    target_count = int(target_combined["overlap_count"])
    target_jaccard = float(target_combined["jaccard"])
    margins = []
    jaccard_margins = []
    strictly_higher = 0

    for row in false_positive_overlaps:
        combined = row["overlap"]["combined"]
        margin = int(combined["overlap_count"]) - target_count
        jaccard_margin = round(float(combined["jaccard"]) - target_jaccard, 6)
        margins.append(margin)
        jaccard_margins.append(jaccard_margin)
        if margin > 0:
            strictly_higher += 1

    signal = bool(margins) and strictly_higher == len(margins)
    return {
        "finding": "content_gap_present" if signal else "content_gap_absent",
        "signal": signal,
        "false_positive_count": len(false_positive_overlaps),
        "strictly_higher_false_positive_count": strictly_higher,
        "target_combined_overlap_count": target_count,
        "target_combined_jaccard": target_jaccard,
        "min_overlap_count_margin": min(margins) if margins else None,
        "max_overlap_count_margin": max(margins) if margins else None,
        "min_jaccard_margin": min(jaccard_margins) if jaccard_margins else None,
        "max_jaccard_margin": max(jaccard_margins) if jaccard_margins else None,
        "rule": (
            "content_gap signal requires every false positive above the target "
            "to have strictly higher combined query-token overlap than the target"
        ),
    }


def ranked_records(
    records: Sequence[Mapping[str, Any]],
    *,
    score_key: str,
    key_field: str = "movie_key",
) -> list[Dict[str, Any]]:
    def sort_key(record: Mapping[str, Any]) -> tuple[int, float, int, str]:
        score = record.get(score_key)
        if score is None:
            return (1, 0.0, int(record.get("pool_index", 0)), str(record[key_field]))
        return (
            0,
            -float(score),
            int(record.get("pool_index", 0)),
            str(record[key_field]),
        )

    ranked = []
    for rank, record in enumerate(sorted(records, key=sort_key)):
        row = dict(record)
        row["rank_zero_based"] = rank
        row["rank_one_based"] = rank + 1
        ranked.append(row)
    return ranked


def target_rank(
    records: Sequence[Mapping[str, Any]],
    *,
    target_movie_key: str,
    score_key: str,
) -> Dict[str, Any]:
    ranked = ranked_records(records, score_key=score_key)
    for row in ranked:
        if row["movie_key"] == target_movie_key:
            return {
                "rank_zero_based": row["rank_zero_based"],
                "rank_one_based": row["rank_one_based"],
                "score": row.get(score_key),
                "ranked": ranked,
            }
    raise RerankModelComparisonError(f"target missing from ranked pool: {target_movie_key}")


def load_inputs(run_id: str) -> Dict[str, Any]:
    run_path = _run_io.run_dir(run_id)
    paths = {
        "text_snapshot": run_path / TEXT_SNAPSHOT_RELATIVE_PATH,
        "characterization": run_path / CHARACTERIZATION_RELATIVE_PATH,
        "decomp": run_path / DECOMP_RELATIVE_PATH,
    }
    missing = [path for path in paths.values() if not path.exists()]
    if missing:
        raise RerankModelComparisonError(
            "required input file missing: " + ", ".join(str(path) for path in missing)
        )
    return {name: read_json_object(path) for name, path in paths.items()}


def index_per_qid(data: Mapping[str, Any], *, source_name: str) -> Dict[str, Mapping[str, Any]]:
    rows = data.get("per_qid")
    if not isinstance(rows, list):
        raise RerankModelComparisonError(f"{source_name}: per_qid must be a list")
    indexed: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise RerankModelComparisonError(f"{source_name}: per_qid row must be object")
        qid = str(row.get("qid", ""))
        indexed[qid] = row
    for qid in QIDS:
        if qid not in indexed:
            raise RerankModelComparisonError(f"{source_name}: missing {qid}")
    return indexed


def snapshot_member_index(snapshot: Mapping[str, Any]) -> Dict[tuple[str, str, str], Mapping[str, Any]]:
    indexed: Dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for qid_row in snapshot.get("per_qid", []):
        qid = str(qid_row.get("qid", ""))
        for arm, arm_data in dict(qid_row.get("arms", {})).items():
            for member in arm_data.get("members", []):
                key = (qid, str(arm), str(member.get("movie_key", "")))
                indexed[key] = member
    return indexed


def candidate_overlap_record(
    *,
    rerank_query: str,
    candidate: Mapping[str, Any],
    member: Mapping[str, Any],
) -> Dict[str, Any]:
    fields = {
        "genres": member.get("genres", ""),
        "keywords": member.get("keywords", ""),
        "overview": member.get("overview", ""),
    }
    document_text = str(member.get("document_text", ""))
    overlap = field_overlap_metrics(rerank_query=rerank_query, fields=fields)
    overlap["document_text"] = overlap_metrics(rerank_query, document_text)
    return {
        "role": str(candidate.get("role", "")),
        "tmdb_id": candidate.get("tmdb_id", member.get("tmdb_id")),
        "movie_key": str(candidate.get("movie_key", member.get("movie_key", ""))),
        "title": str(candidate.get("title", member.get("title", ""))),
        "year": candidate.get("year", member.get("year")),
        "baseline_rerank_rank_zero_based": candidate.get("rerank_rank"),
        "baseline_rerank_score": candidate.get("rerank_score"),
        "text_fields": fields,
        "overlap": overlap,
    }


def build_phase_a(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = inputs["text_snapshot"]
    characterization = inputs["characterization"]
    snapshot_by_key = snapshot_member_index(snapshot)
    characterization_by_qid = index_per_qid(
        characterization,
        source_name="characterization",
    )

    per_qid = []
    for qid in QIDS:
        characterized = characterization_by_qid[qid]
        qid_arms = {}
        for arm in CONTROL_ARMS:
            arm_data = characterized["arms"][arm]
            rerank_query = str(arm_data["rerank_query"])
            target_candidate = arm_data["target"]
            target_key = str(target_candidate["movie_key"])
            target_member = snapshot_by_key.get((qid, arm, target_key))
            if target_member is None:
                raise RerankModelComparisonError(
                    f"text snapshot missing target: {qid} {arm} {target_key}"
                )
            target = candidate_overlap_record(
                rerank_query=rerank_query,
                candidate=target_candidate,
                member=target_member,
            )

            false_positives = []
            for candidate in arm_data.get("false_positives_above_target", []):
                movie_key = str(candidate["movie_key"])
                member = snapshot_by_key.get((qid, arm, movie_key))
                if member is None:
                    raise RerankModelComparisonError(
                        f"text snapshot missing false positive: {qid} {arm} {movie_key}"
                    )
                false_positives.append(
                    candidate_overlap_record(
                        rerank_query=rerank_query,
                        candidate=candidate,
                        member=member,
                    )
                )

            content_gap = evaluate_content_gap(target, false_positives)
            qid_arms[arm] = {
                "rerank_query": rerank_query,
                "target": target,
                "false_positives_above_target": false_positives,
                "content_gap": content_gap,
            }
        signals = [bool(qid_arms[arm]["content_gap"]["signal"]) for arm in CONTROL_ARMS]
        if all(signals):
            qid_finding = "content_gap_present"
        elif any(signals):
            qid_finding = "mixed"
        else:
            qid_finding = "content_gap_absent"
        per_qid.append(
            {
                "qid": qid,
                "tmdb_id": characterized.get("tmdb_id"),
                "title": characterized.get("title"),
                "arms": qid_arms,
                "finding": qid_finding,
            }
        )

    headline_signals = [
        row["arms"][HEADLINE_ARM]["content_gap"]["signal"] for row in per_qid
    ]
    return {
        "status": "complete",
        "method": {
            "tokenization": "lowercase word tokens via [a-z0-9]+",
            "overlap": (
                "set intersection count and set Jaccard between rerank_query "
                "and document genres/keywords/overview"
            ),
            "content_gap_rule": (
                "every false positive above the target has strictly higher "
                "combined overlap_count than the target"
            ),
            "model_calls": False,
            "network_required": False,
            "gpu_required": False,
        },
        "per_qid": per_qid,
        "summary": {
            "headline_arm": HEADLINE_ARM,
            "headline_content_gap_signal_count": sum(1 for item in headline_signals if item),
            "headline_content_gap_required_count": len(headline_signals),
            "headline_content_gap_all_present": all(headline_signals),
        },
    }


def decomp_baselines(decomp: Mapping[str, Any]) -> Dict[tuple[str, str], Dict[str, Any]]:
    by_qid = index_per_qid(decomp, source_name="decomp")
    baselines: Dict[tuple[str, str], Dict[str, Any]] = {}
    for qid in QIDS:
        for arm in CONTROL_ARMS:
            rows = list(by_qid[qid]["arms"][arm].get("extended_pool_rows", []))
            target_rows = [row for row in rows if bool(row.get("is_target"))]
            if len(target_rows) != 1:
                raise RerankModelComparisonError(
                    f"expected one target row in decomp: {qid} {arm}"
                )
            target = target_rows[0]
            baselines[(qid, arm)] = {
                "target_movie_key": str(target["movie_key"]),
                "target_title": target.get("title"),
                "target_tmdb_id": target.get("tmdb_id"),
                "target_rank_zero_based": target.get("rerank_rank"),
                "target_rank_one_based": (
                    int(target["rerank_rank"]) + 1
                    if target.get("rerank_rank") is not None
                    else None
                ),
                "target_score": target.get("rerank_score"),
                "pool_size": len(rows),
                "model_id": "BAAI/bge-reranker-v2-m3",
                "source": str(DECOMP_RELATIVE_PATH).replace("\\", "/"),
            }
    return baselines


def build_phase_b_pairs(snapshot: Mapping[str, Any]) -> list[Dict[str, Any]]:
    pairs = []
    snapshot_by_qid = index_per_qid(snapshot, source_name="text_snapshot")
    for qid in QIDS:
        for arm in CONTROL_ARMS:
            arm_data = snapshot_by_qid[qid]["arms"][arm]
            rerank_query = str(arm_data["rerank_query"])
            for member in arm_data.get("members", []):
                pairs.append(
                    {
                        "qid": qid,
                        "arm": arm,
                        "pool_index": int(member.get("pool_index", len(pairs))),
                        "movie_key": str(member["movie_key"]),
                        "title": str(member.get("title", "")),
                        "year": member.get("year"),
                        "is_target": bool(member.get("is_target")),
                        "rerank_query": rerank_query,
                        "document_text": str(member.get("document_text", "")),
                    }
                )
    return pairs


def expected_phase_b_budget(pair_count: int) -> Dict[str, Any]:
    return {
        "authorized_by": "Human-approved RERANK-02 prompt",
        "scope": "q05/q10, pinned/no_llm, exact text-snapshot extended-pool pairs only",
        "pair_count": pair_count,
        "full_corpus_rerank": False,
        "device_required": "cuda",
        "vram_budget_gb": VRAM_BUDGET_GB,
        "models": [
            {
                "role": spec.role,
                "model_id": spec.model_id,
                "trust_remote_code": spec.trust_remote_code,
                "expected_peak_vram_gb": spec.expected_peak_vram_gb,
                "expected_time_minutes": spec.expected_time_minutes,
                "expected_network": "one Hugging Face snapshot download or cache hit",
            }
            for spec in MODEL_SPECS
        ],
    }


def bytes_to_gb(value: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    return round(value / (1024**3), 4)


def local_tree_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def model_info_size_bytes(info: Any) -> Optional[int]:
    siblings = getattr(info, "siblings", None)
    if not siblings:
        return None
    total = 0
    saw_size = False
    for sibling in siblings:
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            total += size
            saw_size = True
    return total if saw_size else None


def tensor_prefix(values: Any, *, count: int = 8) -> list[int]:
    try:
        return [int(value) for value in values[:count].detach().cpu().tolist()]
    except Exception:
        return []


def repair_position_ids_if_needed(model: Any, torch_module: Any) -> Dict[str, Any]:
    """Repair Alibaba/new-impl's non-persistent RoPE position buffer if corrupt."""
    details: Dict[str, Any] = {
        "checked": False,
        "repaired": False,
        "reason": "position_ids buffer not found",
    }
    embeddings = getattr(getattr(model, "new", None), "embeddings", None)
    position_ids = getattr(embeddings, "position_ids", None)
    max_position_embeddings = getattr(
        getattr(model, "config", None),
        "max_position_embeddings",
        None,
    )
    if embeddings is None or position_ids is None or max_position_embeddings is None:
        return details

    sample_count = min(8, int(max_position_embeddings), int(position_ids.numel()))
    expected_prefix = list(range(sample_count))
    before_prefix = tensor_prefix(position_ids, count=sample_count)
    is_valid = before_prefix == expected_prefix and int(position_ids.numel()) >= int(
        max_position_embeddings
    )
    details = {
        "checked": True,
        "repaired": False,
        "reason": "position_ids already valid",
        "max_position_embeddings": int(max_position_embeddings),
        "before_prefix": before_prefix,
        "expected_prefix": expected_prefix,
        "device_before": str(position_ids.device),
    }
    if is_valid:
        details["after_prefix"] = before_prefix
        details["device_after"] = str(position_ids.device)
        return details

    repaired = torch_module.arange(
        int(max_position_embeddings),
        device=position_ids.device,
        dtype=torch_module.long,
    )
    embeddings.register_buffer("position_ids", repaired, persistent=False)
    after = getattr(embeddings, "position_ids")
    details.update(
        {
            "repaired": True,
            "reason": "position_ids prefix/length did not match arange",
            "after_prefix": tensor_prefix(after, count=sample_count),
            "device_after": str(after.device),
        }
    )
    return details


def load_phase_b_libraries() -> Dict[str, Any]:
    try:
        import torch
        from huggingface_hub import HfApi, snapshot_download
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RerankModelComparisonError(
            "Phase B dependency missing from venv; no pip install attempted: "
            f"{exc}"
        ) from exc
    return {
        "torch": torch,
        "HfApi": HfApi,
        "snapshot_download": snapshot_download,
        "AutoModelForSequenceClassification": AutoModelForSequenceClassification,
        "AutoTokenizer": AutoTokenizer,
    }


def load_transformer_reranker(
    *,
    spec: ModelSpec,
    model_path: str,
    libraries: Mapping[str, Any],
    device: Any,
) -> tuple[Any, Any, Dict[str, Any]]:
    torch = libraries["torch"]
    tokenizer = libraries["AutoTokenizer"].from_pretrained(
        model_path,
        trust_remote_code=spec.trust_remote_code,
    )
    model_kwargs: Dict[str, Any] = {"trust_remote_code": spec.trust_remote_code}
    if str(device).startswith("cuda"):
        model_kwargs["dtype"] = torch.float16
    model = libraries["AutoModelForSequenceClassification"].from_pretrained(
        model_path,
        **model_kwargs,
    )
    loader = {
        "loader": "transformers.AutoModelForSequenceClassification",
        "tokenizer_input_format": "list[tuple[query, document]]",
        "trust_remote_code": spec.trust_remote_code,
        "dtype": "float16" if str(device).startswith("cuda") else "default",
        "position_ids": repair_position_ids_if_needed(model, torch),
    }
    model.to(device)
    embeddings = getattr(getattr(model, "new", None), "embeddings", None)
    position_ids = getattr(embeddings, "position_ids", None)
    if position_ids is not None:
        loader["position_ids"]["device_after_model_to"] = str(position_ids.device)
        loader["position_ids"]["prefix_after_model_to"] = tensor_prefix(position_ids)
    model.eval()
    return tokenizer, model, loader


def resolve_and_download_model(spec: ModelSpec, libraries: Mapping[str, Any]) -> Dict[str, Any]:
    api = libraries["HfApi"]()
    try:
        info = api.model_info(spec.model_id, files_metadata=True)
    except TypeError:
        info = api.model_info(spec.model_id)
    revision = getattr(info, "sha", None)
    local_path = libraries["snapshot_download"](
        repo_id=spec.model_id,
        revision=revision,
        allow_patterns=list(SNAPSHOT_ALLOW_PATTERNS),
    )
    local = Path(local_path)
    return {
        "resolved_revision": revision,
        "reported_repo_bytes": model_info_size_bytes(info),
        "reported_repo_gb": bytes_to_gb(model_info_size_bytes(info)),
        "local_snapshot_path": str(local),
        "local_snapshot_bytes": local_tree_size(local),
        "local_snapshot_gb": bytes_to_gb(local_tree_size(local)),
    }


def score_pairs_with_transformers(
    *,
    spec: ModelSpec,
    model_path: str,
    pairs: Sequence[Mapping[str, Any]],
    libraries: Mapping[str, Any],
    device: Any,
) -> tuple[list[float], Dict[str, Any]]:
    torch = libraries["torch"]
    tokenizer, model, loader = load_transformer_reranker(
        spec=spec,
        model_path=model_path,
        libraries=libraries,
        device=device,
    )

    scores: list[float] = []
    logit_shapes: list[list[int]] = []
    try:
        for start in range(0, len(pairs), spec.batch_size):
            batch = pairs[start : start + spec.batch_size]
            pair_texts = [
                (str(pair["rerank_query"]), str(pair["document_text"]))
                for pair in batch
            ]
            encoded = tokenizer(
                pair_texts,
                padding=True,
                truncation=True,
                max_length=spec.max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            with torch.inference_mode():
                outputs = model(**encoded, return_dict=True)
            logits = outputs.logits.detach().float().cpu()
            logit_shapes.append([int(item) for item in logits.shape])
            if len(logits.shape) == 1:
                batch_scores = logits.tolist()
            elif logits.shape[-1] == 1:
                batch_scores = logits.view(-1).tolist()
            else:
                batch_scores = logits[:, -1].tolist()
            scores.extend(float(score) for score in batch_scores)
    finally:
        del model
        del tokenizer
    loader["logit_shapes"] = logit_shapes
    return scores, loader


def build_model_rank_results(
    *,
    model_id: str,
    pairs: Sequence[Mapping[str, Any]],
    scores: Sequence[float],
    baselines: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    if len(pairs) != len(scores):
        raise RerankModelComparisonError(
            f"score count mismatch for {model_id}: {len(scores)} != {len(pairs)}"
        )
    scored = []
    for pair, score in zip(pairs, scores):
        row = dict(pair)
        row["model_score"] = score
        scored.append(row)

    per_qid = []
    for qid in QIDS:
        arms: Dict[str, Any] = {}
        for arm in CONTROL_ARMS:
            baseline = dict(baselines[(qid, arm)])
            arm_records = [
                row for row in scored if row["qid"] == qid and row["arm"] == arm
            ]
            ranked = ranked_records(arm_records, score_key="model_score")
            target_key = str(baseline["target_movie_key"])
            target_rows = [row for row in ranked if row["movie_key"] == target_key]
            if len(target_rows) != 1:
                raise RerankModelComparisonError(
                    f"model result missing target: {model_id} {qid} {arm}"
                )
            target = target_rows[0]
            baseline_rank = baseline["target_rank_zero_based"]
            model_rank = target["rank_zero_based"]
            arms[arm] = {
                "baseline": baseline,
                "alternative": {
                    "model_id": model_id,
                    "target_rank_zero_based": model_rank,
                    "target_rank_one_based": target["rank_one_based"],
                    "target_score": target["model_score"],
                    "target_title": target.get("title"),
                    "pool_size": len(ranked),
                },
                "rescued_to_top5": (
                    baseline_rank is not None
                    and int(baseline_rank) >= TOP5_CUTOFF
                    and int(model_rank) < TOP5_CUTOFF
                ),
                "scored_pool": [
                    {
                        "rank_zero_based": row["rank_zero_based"],
                        "rank_one_based": row["rank_one_based"],
                        "movie_key": row["movie_key"],
                        "title": row.get("title"),
                        "year": row.get("year"),
                        "is_target": row.get("is_target"),
                        "model_score": row.get("model_score"),
                    }
                    for row in ranked
                ],
            }
        per_qid.append({"qid": qid, "arms": arms})
    return per_qid


def score_one_model(
    *,
    spec: ModelSpec,
    pairs: Sequence[Mapping[str, Any]],
    baselines: Mapping[tuple[str, str], Mapping[str, Any]],
    libraries: Mapping[str, Any],
    device: Any,
) -> Dict[str, Any]:
    torch = libraries["torch"]
    started = time.monotonic()
    result: Dict[str, Any] = {
        "role": spec.role,
        "model_id": spec.model_id,
        "trust_remote_code": spec.trust_remote_code,
        "status": "started",
        "expected_peak_vram_gb": spec.expected_peak_vram_gb,
        "expected_time_minutes": spec.expected_time_minutes,
        "batch_size": spec.batch_size,
        "max_length": spec.max_length,
    }
    try:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
        snapshot = resolve_and_download_model(spec, libraries)
        result["download"] = snapshot
        scores, loader = score_pairs_with_transformers(
            spec=spec,
            model_path=str(snapshot["local_snapshot_path"]),
            pairs=pairs,
            libraries=libraries,
            device=device,
        )
        result["loader"] = loader
        peak_allocated_gb = bytes_to_gb(torch.cuda.max_memory_allocated(device))
        peak_reserved_gb = bytes_to_gb(torch.cuda.max_memory_reserved(device))
        result["actual"] = {
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "peak_allocated_gb": peak_allocated_gb,
            "peak_reserved_gb": peak_reserved_gb,
            "pair_count": len(pairs),
        }
        if (
            peak_allocated_gb is not None
            and peak_allocated_gb > VRAM_BUDGET_GB
            or peak_reserved_gb is not None
            and peak_reserved_gb > VRAM_BUDGET_GB
        ):
            result["status"] = "vram_exceeded"
            result["error"] = f"model exceeded {VRAM_BUDGET_GB} GB VRAM budget"
        else:
            result["status"] = "success"
            result["resolved_revision"] = snapshot.get("resolved_revision")
            result["per_qid"] = build_model_rank_results(
                model_id=spec.model_id,
                pairs=pairs,
                scores=scores,
                baselines=baselines,
            )
    except RuntimeError as exc:
        result["actual"] = {"elapsed_seconds": round(time.monotonic() - started, 3)}
        message = str(exc)
        if "device-side assert" in message.lower() or "cudaerrorassert" in message.lower():
            raise RerankModelComparisonError(
                f"CUDA device-side assert while scoring {spec.model_id}: {message}"
            ) from exc
        if "out of memory" in message.lower():
            result["status"] = "vram_exceeded"
        else:
            result["status"] = "failed"
        result["error"] = message
    except Exception as exc:
        result["actual"] = {"elapsed_seconds": round(time.monotonic() - started, 3)}
        if "device-side assert" in str(exc).lower() or "cudaerrorassert" in str(exc).lower():
            raise RerankModelComparisonError(
                f"CUDA device-side assert while scoring {spec.model_id}: {exc}"
            ) from exc
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        gc.collect()
        try:
            torch.cuda.empty_cache()
        except Exception as exc:
            if "device-side assert" in str(exc).lower() or "cudaerrorassert" in str(exc).lower():
                raise RerankModelComparisonError(
                    f"CUDA device-side assert during cleanup for {spec.model_id}: {exc}"
                ) from exc
    return result


def loader_smoke_pairs(snapshot: Mapping[str, Any], *, count: int) -> list[Dict[str, Any]]:
    pairs = build_phase_b_pairs(snapshot)
    if len(pairs) < count:
        raise RerankModelComparisonError(
            f"text snapshot has only {len(pairs)} pairs; requested {count}"
        )
    return pairs[:count]


def run_loader_smoke(
    *,
    inputs: Mapping[str, Any],
    device_name: str,
    count: int,
) -> Dict[str, Any]:
    spec = MODEL_SPECS[0]
    pairs = loader_smoke_pairs(inputs["text_snapshot"], count=count)
    libraries = load_phase_b_libraries()
    torch = libraries["torch"]
    if device_name == "cuda":
        if not torch.cuda.is_available():
            raise RerankModelComparisonError("CUDA smoke requested but CUDA is unavailable")
        device = torch.device("cuda")
        device_details = {
            "device": "cuda",
            "cuda_device_name": torch.cuda.get_device_properties(device).name,
            "cuda_total_memory_gb": bytes_to_gb(
                torch.cuda.get_device_properties(device).total_memory
            ),
        }
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
    elif device_name == "cpu":
        device = torch.device("cpu")
        device_details = {"device": "cpu"}
    else:
        raise RerankModelComparisonError(f"unsupported smoke device: {device_name}")

    started = time.monotonic()
    snapshot = resolve_and_download_model(spec, libraries)
    scores, loader = score_pairs_with_transformers(
        spec=spec,
        model_path=str(snapshot["local_snapshot_path"]),
        pairs=pairs,
        libraries=libraries,
        device=device,
    )
    actual: Dict[str, Any] = {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "pair_count": len(pairs),
    }
    if device_name == "cuda":
        torch.cuda.synchronize(device)
        actual["peak_allocated_gb"] = bytes_to_gb(torch.cuda.max_memory_allocated(device))
        actual["peak_reserved_gb"] = bytes_to_gb(torch.cuda.max_memory_reserved(device))
    return {
        "status": "pass",
        "model_id": spec.model_id,
        "device": device_details,
        "snapshot": snapshot,
        "loader": loader,
        "actual": actual,
        "pairs": [
            {
                "qid": pair["qid"],
                "arm": pair["arm"],
                "pool_index": pair["pool_index"],
                "movie_key": pair["movie_key"],
                "title": pair["title"],
                "is_target": pair["is_target"],
            }
            for pair in pairs
        ],
        "scores": scores,
    }


def run_phase_b(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    pairs = build_phase_b_pairs(inputs["text_snapshot"])
    baselines = decomp_baselines(inputs["decomp"])
    expected = expected_phase_b_budget(len(pairs))
    libraries = load_phase_b_libraries()
    torch = libraries["torch"]
    if not torch.cuda.is_available():
        raise RerankModelComparisonError(
            "Phase B requires CUDA for the approved reranker run; CUDA is unavailable"
        )
    device = torch.device("cuda")
    props = torch.cuda.get_device_properties(device)

    started_at = utc_timestamp()
    started = time.monotonic()
    model_results = []
    for spec in MODEL_SPECS:
        model_results.append(
            score_one_model(
                spec=spec,
                pairs=pairs,
                baselines=baselines,
                libraries=libraries,
                device=device,
            )
        )

    success_count = sum(1 for item in model_results if item.get("status") == "success")
    if success_count == len(model_results):
        status = "complete"
    elif success_count > 0:
        status = "partial"
    else:
        status = "failed"

    return {
        "status": status,
        "expected": expected,
        "actual": {
            "started_at": started_at,
            "finished_at": utc_timestamp(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "device": "cuda",
            "cuda_device_name": props.name,
            "cuda_total_memory_gb": bytes_to_gb(props.total_memory),
            "successful_model_count": success_count,
            "failed_model_count": len(model_results) - success_count,
        },
        "models": model_results,
    }


def model_rescues(phase_b: Mapping[str, Any]) -> list[Dict[str, Any]]:
    rescues = []
    for model in phase_b.get("models", []):
        if model.get("status") != "success":
            continue
        for qid_row in model.get("per_qid", []):
            qid = qid_row["qid"]
            for arm, arm_data in qid_row.get("arms", {}).items():
                if not arm_data.get("rescued_to_top5"):
                    continue
                alt = arm_data["alternative"]
                base = arm_data["baseline"]
                rescues.append(
                    {
                        "model_id": model["model_id"],
                        "qid": qid,
                        "arm": arm,
                        "baseline_rank_zero_based": base["target_rank_zero_based"],
                        "model_rank_zero_based": alt["target_rank_zero_based"],
                        "model_rank_one_based": alt["target_rank_one_based"],
                    }
                )
    return rescues


def headline_content_gap_rows(phase_a: Mapping[str, Any]) -> list[Dict[str, Any]]:
    rows = []
    for qid_row in phase_a.get("per_qid", []):
        arm_data = qid_row["arms"][HEADLINE_ARM]
        gap = arm_data["content_gap"]
        rows.append(
            {
                "qid": qid_row["qid"],
                "arm": HEADLINE_ARM,
                "signal": bool(gap["signal"]),
                "target_overlap_count": gap["target_combined_overlap_count"],
                "min_overlap_count_margin": gap["min_overlap_count_margin"],
                "false_positive_count": gap["false_positive_count"],
            }
        )
    return rows


def successful_model_count(phase_b: Mapping[str, Any]) -> int:
    return sum(1 for model in phase_b.get("models", []) if model.get("status") == "success")


def decide_outcome(phase_a: Mapping[str, Any], phase_b: Mapping[str, Any]) -> Dict[str, Any]:
    evidence: list[str] = []
    content_rows = headline_content_gap_rows(phase_a)
    for row in content_rows:
        evidence.append(
            f"Phase A {row['qid']}/{row['arm']}: content_gap={row['signal']} "
            f"target_combined_overlap={row['target_overlap_count']} "
            f"min_false_positive_margin={row['min_overlap_count_margin']} "
            f"false_positives={row['false_positive_count']}"
        )

    rescues = model_rescues(phase_b)
    if rescues:
        best = sorted(rescues, key=lambda item: (item["model_rank_zero_based"], item["model_id"]))[0]
        evidence.append(
            f"Phase B {best['model_id']} rescued {best['qid']}/{best['arm']} "
            f"from baseline rank {best['baseline_rank_zero_based']} to "
            f"rank {best['model_rank_zero_based']} (zero-based)"
        )
        return {
            "value": "model_capability_confirmed",
            "model": best["model_id"],
            "qid": best["qid"],
            "arm": best["arm"],
            "rank_zero_based": best["model_rank_zero_based"],
            "rank_one_based": best["model_rank_one_based"],
            "evidence": evidence,
            "phase5_unblocked": False,
        }

    success_count = successful_model_count(phase_b)
    for model in phase_b.get("models", []):
        if model.get("status") == "success":
            for qid_row in model.get("per_qid", []):
                for arm, arm_data in qid_row.get("arms", {}).items():
                    if arm != HEADLINE_ARM:
                        continue
                    evidence.append(
                        f"Phase B {model['model_id']} {qid_row['qid']}/{arm}: "
                        f"baseline_rank={arm_data['baseline']['target_rank_zero_based']} "
                        f"model_rank={arm_data['alternative']['target_rank_zero_based']}"
                    )
        elif model.get("status"):
            evidence.append(
                f"Phase B {model.get('model_id')}: status={model.get('status')} "
                f"error={model.get('error')}"
            )

    if phase_b.get("status") in {"not_run", "blocked"} or success_count == 0:
        evidence.append("Phase B has no successful alternative-model rank evidence")
        return {
            "value": "inconclusive",
            "evidence": evidence,
            "phase5_unblocked": False,
        }

    if content_rows and all(row["signal"] for row in content_rows):
        return {
            "value": "content_gap_dominant",
            "evidence": evidence,
            "phase5_unblocked": False,
        }

    if content_rows and not any(row["signal"] for row in content_rows):
        return {
            "value": "model_capability_ruled_out",
            "evidence": evidence,
            "phase5_unblocked": False,
        }

    return {
        "value": "inconclusive",
        "evidence": evidence,
        "phase5_unblocked": False,
    }


def build_artifact(
    *,
    run_id: str,
    phase: str,
    inputs: Mapping[str, Any],
) -> Dict[str, Any]:
    phase_a = build_phase_a(inputs)
    if phase == "a":
        phase_b = {
            "status": "not_run",
            "expected": expected_phase_b_budget(
                len(build_phase_b_pairs(inputs["text_snapshot"]))
            ),
            "models": [],
        }
    elif phase == "b":
        phase_b = run_phase_b(inputs)
    else:
        raise RerankModelComparisonError(f"unsupported phase: {phase}")

    decision = decide_outcome(phase_a, phase_b)
    return {
        "schema_version": SCHEMA_VERSION,
        "ticket": "RERANK-02",
        "run_id": run_id,
        "generated_at": utc_timestamp(),
        "scope": {
            "qids": list(QIDS),
            "arms": list(CONTROL_ARMS),
            "headline_arm": HEADLINE_ARM,
            "top5_cutoff_zero_based": TOP5_CUTOFF,
            "phase5_gate": "blocked",
            "src_edit": False,
            "llm_call": False,
        },
        "source_artifacts": {
            "text_snapshot": str(TEXT_SNAPSHOT_RELATIVE_PATH).replace("\\", "/"),
            "characterization": str(CHARACTERIZATION_RELATIVE_PATH).replace("\\", "/"),
            "decomp": str(DECOMP_RELATIVE_PATH).replace("\\", "/"),
        },
        "phase_a": phase_a,
        "phase_b": phase_b,
        "decision": decision,
        "phase5_gate": "blocked",
    }


def write_loader_diagnostic(path: Path, diagnostic: Mapping[str, Any]) -> None:
    _run_io._atomic_write_json(path, diagnostic)


def loader_diagnostic_path(run_id: str) -> Path:
    return _run_io.run_dir(run_id) / LOADER_DIAGNOSTIC_RELATIVE_PATH


def format_rank(value: Any) -> str:
    return "" if value is None else str(value)


def markdown_overlap_table(qid: str, arm: str, arm_data: Mapping[str, Any]) -> str:
    rows = [arm_data["target"]] + list(arm_data["false_positives_above_target"])
    lines = [
        f"#### {qid} / {arm}",
        "",
        f"rerank_query: `{arm_data['rerank_query']}`",
        "",
        (
            "| role | title | rank0 | genres | keywords | overview | combined | doc | "
            "combined_jaccard |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        overlap = row["overlap"]
        lines.append(
            "| {role} | {title} | {rank} | {genres} | {keywords} | {overview} | "
            "{combined} | {document} | {jaccard:.6f} |".format(
                role=row["role"],
                title=str(row["title"]).replace("|", "\\|"),
                rank=format_rank(row.get("baseline_rerank_rank_zero_based")),
                genres=overlap["genres"]["overlap_count"],
                keywords=overlap["keywords"]["overlap_count"],
                overview=overlap["overview"]["overlap_count"],
                combined=overlap["combined"]["overlap_count"],
                document=overlap["document_text"]["overlap_count"],
                jaccard=float(overlap["combined"]["jaccard"]),
            )
        )
    gap = arm_data["content_gap"]
    lines.extend(
        [
            "",
            (
                f"content_gap: `{gap['finding']}`; signal={gap['signal']}; "
                f"min_overlap_count_margin={gap['min_overlap_count_margin']}."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def markdown_phase_b_table(phase_b: Mapping[str, Any]) -> str:
    if phase_b.get("status") == "not_run":
        return "Phase B has not been run yet.\n"
    lines = [
        "| model | qid | arm | baseline rank0 | model rank0 | rescued top5 | target score |",
        "|---|---|---|---:|---:|---|---:|",
    ]
    any_rows = False
    for model in phase_b.get("models", []):
        if model.get("status") != "success":
            lines.append(
                "| {model} |  |  |  |  | status={status} |  |".format(
                    model=model.get("model_id", ""),
                    status=model.get("status", ""),
                )
            )
            any_rows = True
            continue
        for qid_row in model.get("per_qid", []):
            for arm, arm_data in qid_row.get("arms", {}).items():
                lines.append(
                    "| {model} | {qid} | {arm} | {base} | {rank} | {rescued} | {score:.6f} |".format(
                        model=model["model_id"],
                        qid=qid_row["qid"],
                        arm=arm,
                        base=arm_data["baseline"]["target_rank_zero_based"],
                        rank=arm_data["alternative"]["target_rank_zero_based"],
                        rescued=arm_data["rescued_to_top5"],
                        score=float(arm_data["alternative"]["target_score"]),
                    )
                )
                any_rows = True
    return "\n".join(lines if any_rows else ["No model rank rows recorded."]) + "\n"


def markdown_cost_table(phase_b: Mapping[str, Any]) -> str:
    lines = [
        "| item | value |",
        "|---|---|",
        f"| expected pair count | {phase_b.get('expected', {}).get('pair_count', '')} |",
        f"| expected VRAM budget | {VRAM_BUDGET_GB} GB |",
        f"| actual status | {phase_b.get('status')} |",
    ]
    actual = phase_b.get("actual", {})
    if actual:
        lines.extend(
            [
                f"| actual elapsed seconds | {actual.get('elapsed_seconds')} |",
                f"| CUDA device | {actual.get('cuda_device_name')} |",
                f"| CUDA total memory GB | {actual.get('cuda_total_memory_gb')} |",
            ]
        )
    for model in phase_b.get("models", []):
        actual_model = model.get("actual", {})
        download = model.get("download", {})
        lines.extend(
            [
                f"| {model.get('model_id')} status | {model.get('status')} |",
                f"| {model.get('model_id')} revision | {model.get('resolved_revision') or download.get('resolved_revision')} |",
                f"| {model.get('model_id')} local snapshot GB | {download.get('local_snapshot_gb')} |",
                f"| {model.get('model_id')} peak allocated GB | {actual_model.get('peak_allocated_gb')} |",
                f"| {model.get('model_id')} peak reserved GB | {actual_model.get('peak_reserved_gb')} |",
                f"| {model.get('model_id')} tokenizer input | {model.get('loader', {}).get('tokenizer_input_format')} |",
                f"| {model.get('model_id')} position ids repaired | {model.get('loader', {}).get('position_ids', {}).get('repaired')} |",
            ]
        )
        if model.get("error"):
            lines.append(f"| {model.get('model_id')} error | {model.get('error')} |")
    return "\n".join(lines) + "\n"


def write_report(path: Path, artifact: Mapping[str, Any]) -> None:
    lines = [
        "# RERANK-02 Model Comparison",
        "",
        f"- Ticket: {artifact['ticket']}",
        f"- Timestamp: {artifact['generated_at']}",
        f"- Run: {artifact['run_id']}",
        "- Scope: q05/q10, pinned/no_llm, eval-only; no src edits; no LLM calls.",
        "",
        "## Phase A - Lexical Content Gap",
        "",
    ]
    for qid_row in artifact["phase_a"]["per_qid"]:
        for arm in CONTROL_ARMS:
            lines.append(markdown_overlap_table(qid_row["qid"], arm, qid_row["arms"][arm]))

    lines.extend(
        [
            "## Phase B - Alternative Cross-Encoder Ranks",
            "",
            markdown_phase_b_table(artifact["phase_b"]),
            "## Cost, Time, VRAM",
            "",
            markdown_cost_table(artifact["phase_b"]),
            "## Decision",
            "",
            f"`{artifact['decision']['value']}`",
            "",
        ]
    )
    for item in artifact["decision"].get("evidence", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "Rejected alternatives are reflected by the Phase A content-gap rows and "
            "Phase B rank rows above. The decision is rank-based because model score "
            "scales are not comparable across cross-encoders.",
            "",
            "## What This Means For Phase 5",
            "",
            "A `model_capability_confirmed` result does not unblock Phase 5. A model "
            "swap would first need a separate full gold/silver-set rerank regression "
            "evaluation proving it does not regress other queries.",
            "",
            "## Phase 5 Gate",
            "",
            "Phase 5 remains BLOCKED.",
            "",
        ]
    )
    _run_io._atomic_write_text(path, "\n".join(lines))


def run(*, run_id: Optional[str], phase: str) -> tuple[str, Path, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    inputs = load_inputs(actual_run_id)
    artifact = build_artifact(run_id=actual_run_id, phase=phase, inputs=inputs)
    output_path = _run_io.run_dir(actual_run_id) / OUTPUT_RELATIVE_PATH
    _run_io._atomic_write_json(output_path, artifact)
    write_report(REPORT_PATH, artifact)
    return actual_run_id, output_path, REPORT_PATH, artifact


def run_smoke(
    *,
    run_id: Optional[str],
    device_name: str,
    count: int,
) -> tuple[str, Path, Dict[str, Any]]:
    actual_run_id = run_id or _run_io.latest_run()
    inputs = load_inputs(actual_run_id)
    smoke = run_loader_smoke(inputs=inputs, device_name=device_name, count=count)
    diagnostic_path = loader_diagnostic_path(actual_run_id)
    existing: Dict[str, Any] = {}
    if diagnostic_path.exists():
        existing = read_json_object(diagnostic_path)
    diagnostic = {
        "schema_version": "rerank-02b-loader-diagnostic.v1",
        "ticket": "RERANK-02B-LOADER-DIAGNOSTIC",
        "run_id": actual_run_id,
        "generated_at": utc_timestamp(),
        "scope": {
            "model_id": MODEL_SPECS[0].model_id,
            "pair_source": str(TEXT_SNAPSHOT_RELATIVE_PATH).replace("\\", "/"),
            "smoke_pair_count": count,
            "full_corpus_rerank": False,
            "src_edit": False,
            "phase5_gate": "blocked",
        },
        "smoke": dict(existing.get("smoke", {})),
        "loader_decision": "correct_loader_confirmed",
        "phase5_gate": "blocked",
    }
    diagnostic["smoke"][device_name] = smoke
    if not all(
        diagnostic["smoke"].get(name, {}).get("status") == "pass"
        for name in ("cpu", "cuda")
    ):
        diagnostic["loader_decision"] = "inconclusive"
    write_loader_diagnostic(diagnostic_path, diagnostic)
    return actual_run_id, diagnostic_path, diagnostic


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", dest="run_id", default=None)
    parser.add_argument("--phase", choices=("a", "b", "smoke"), required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--smoke-count", type=int, default=3)
    args = parser.parse_args(argv)

    if args.phase == "smoke":
        run_id, diagnostic_path, diagnostic = run_smoke(
            run_id=args.run_id,
            device_name=args.device,
            count=args.smoke_count,
        )
        print(f"run_id={run_id}")
        print(f"loader_diagnostic={diagnostic_path}")
        print(f"device={args.device}")
        print(f"smoke={diagnostic['smoke'][args.device]['status']}")
        print(f"loader_decision={diagnostic['loader_decision']}")
        return 0

    run_id, output_path, report_path, artifact = run(
        run_id=args.run_id,
        phase=args.phase,
    )
    print(f"run_id={run_id}")
    print(f"artifact={output_path}")
    print(f"report={report_path}")
    print(f"phase_a={artifact['phase_a']['status']}")
    print(f"phase_b={artifact['phase_b']['status']}")
    print(f"decision={artifact['decision']['value']}")
    for model in artifact["phase_b"].get("models", []):
        print(f"model={model.get('model_id')} status={model.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
