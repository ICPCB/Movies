"""Localize HY-STAB-01 fixed defects from finished trace artifacts."""

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval.scripts import _run_io


SCHEMA_VERSION = "hy-fix-01.v1"
FIXED_DEFECT_QIDS = ("q05", "q07", "q08", "q10")
PRIORITY_ORDER = ("q08", "q07", "q05", "q10")
STAGE_PIPELINE = ("semantic", "bm25", "rrf", "rerank", "final")

SOURCE_ARTIFACTS = {
    "stability_trace": (
        "analysis/hybrid_expansion_stability/stability_trace.jsonl"
    ),
    "stability_diagnosis": (
        "analysis/hybrid_expansion_stability/stability_diagnosis.json"
    ),
}
OUTPUT_RELATIVE_PATH = Path("analysis") / "hy_fix_localize" / "localization.json"

CONFIG_KEYS = ("CANDIDATE_POOL", "RERANK_POOL", "RERANK_TOP_K", "FINAL_TOP_K")
SUMMARY_KEYS = (
    "recall_depth_fusion_pool",
    "reranker_scoring",
    "final_blend",
    "mixed",
    "none",
    "inconclusive",
)
FIX_CATEGORY_BY_LOSS = {
    "unretrieved": "recall_depth_fusion_pool",
    "retrieved_dropped_at_fusion": "recall_depth_fusion_pool",
    "retrieved_dropped_before_rerank_pool": "recall_depth_fusion_pool",
    "rerank_demoted": "reranker_scoring",
    "rerank_recovered_final_demoted": "final_blend",
    "hybrid_top5_hit": "none",
    "other": "inconclusive",
}

_CONTROL_ARMS = ("pinned", "no_llm")
_LIVE_ARM = "live"
_DETERMINISM_FIELDS = STAGE_PIPELINE + ("loss_classification",)
_CATEGORY_ORDER = {
    "recall_depth_fusion_pool": 0,
    "reranker_scoring": 1,
    "final_blend": 2,
    "none": 3,
    "inconclusive": 4,
}


class HyFixLocalizeError(ValueError):
    """Raised when HY-FIX-01 localization preconditions are not met."""


def fix_category_for_loss(loss_stage):
    """Return the static HY-FIX-01 fix category for an existing loss stage."""
    try:
        return FIX_CATEGORY_BY_LOSS[loss_stage]
    except KeyError as exc:
        raise HyFixLocalizeError(f"unsupported loss_stage: {loss_stage!r}") from exc


def build_localization(run_id):
    """Build the localization payload without writing it."""
    trace_rows, diagnosis = _load_inputs(run_id)
    fixed_defect_qids, targets = _fixed_defect_targets(diagnosis)
    trace_index = _index_trace_rows(trace_rows)
    config = _config_from_diagnosis(diagnosis)

    per_target = []
    for target in targets:
        qid = target["qid"]
        tmdb_id = target["tmdb_id"]
        arms = {}
        for arm in _CONTROL_ARMS:
            rows = _rows_for(trace_index, arm, qid, tmdb_id)
            arms[arm] = _build_deterministic_arm(arm, qid, tmdb_id, rows)
        arms[_LIVE_ARM] = _build_live_arm(
            _rows_for(trace_index, _LIVE_ARM, qid, tmdb_id)
        )

        pinned_category = arms["pinned"]["fix_category"]
        no_llm_category = arms["no_llm"]["fix_category"]
        arms_agree = pinned_category == no_llm_category
        consolidated = pinned_category if arms_agree else "mixed"

        entry = {
            "qid": qid,
            "tmdb_id": tmdb_id,
            "title": target["title"],
            "attribution": "fixed_defect",
            "arms": arms,
            "consolidated_fix_category": consolidated,
            "arms_agree": arms_agree,
        }
        entry["notes"] = _notes_for_target(entry, config)
        per_target.append(entry)

    summary = _fix_category_summary(per_target)
    recommended_sequence = _recommended_sequence(per_target)
    if tuple(recommended_sequence) != PRIORITY_ORDER:
        raise HyFixLocalizeError(
            "recommended_sequence mismatch: "
            f"{recommended_sequence!r} != {list(PRIORITY_ORDER)!r}"
        )

    per_target_by_qid = {target["qid"]: target for target in per_target}
    recommended_first_fix = per_target_by_qid[
        recommended_sequence[0]
    ]["consolidated_fix_category"]

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": _utc_timestamp(),
        "source_artifacts": dict(SOURCE_ARTIFACTS),
        "fixed_defect_qids": list(fixed_defect_qids),
        "priority_order": list(PRIORITY_ORDER),
        "stage_pipeline": list(STAGE_PIPELINE),
        "config": config,
        "per_target": per_target,
        "fix_category_summary": summary,
        "recommended_sequence": recommended_sequence,
        "recommended_first_fix": recommended_first_fix,
    }


def write_localization(run_id):
    """Build and write localization.json, returning the output path and data."""
    data = build_localization(run_id)
    output_path = _run_io.run_dir(run_id) / OUTPUT_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_io._atomic_write_json(output_path, data)
    return output_path, data


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Localize HY-STAB-01 fixed defects from finished JSON."
    )
    parser.add_argument("--run", default=None, help="Eval run id")
    args = parser.parse_args(argv)

    try:
        run_id = args.run or _run_io.latest_run()
        output_path, data = write_localization(run_id)
    except (HyFixLocalizeError, FileNotFoundError) as exc:
        print(f"hy_fix_localize: {exc}", file=sys.stderr)
        return 1

    print(f"run_id={data['run_id']}")
    print(f"output={output_path}")
    print(f"fixed_defect_qids={data['fixed_defect_qids']}")
    print(f"fix_category_summary={data['fix_category_summary']}")
    print(f"recommended_first_fix={data['recommended_first_fix']}")
    return 0


def _load_inputs(run_id):
    run_path = _run_io.run_dir(run_id)
    trace_path = run_path / SOURCE_ARTIFACTS["stability_trace"]
    diagnosis_path = run_path / SOURCE_ARTIFACTS["stability_diagnosis"]
    missing = [path for path in (trace_path, diagnosis_path) if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise HyFixLocalizeError(f"required input file missing: {missing_text}")

    with open(diagnosis_path, "r", encoding="utf-8") as handle:
        diagnosis = json.load(handle)

    trace_rows = []
    with open(trace_path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if not isinstance(row, dict):
                raise HyFixLocalizeError(
                    f"stability_trace.jsonl line {line_number} is not an object"
                )
            trace_rows.append(row)

    return trace_rows, diagnosis


def _fixed_defect_targets(diagnosis):
    entries = diagnosis.get("instability_attribution")
    if not isinstance(entries, list):
        raise HyFixLocalizeError(
            "stability_diagnosis.json missing instability_attribution list"
        )

    targets_by_qid = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("attribution") != "fixed_defect":
            continue
        qid = entry.get("qid")
        if not isinstance(qid, str):
            raise HyFixLocalizeError("fixed_defect entry missing qid")
        if qid in targets_by_qid:
            raise HyFixLocalizeError(f"duplicate fixed_defect qid: {qid}")
        for key in ("tmdb_id", "title"):
            if key not in entry:
                raise HyFixLocalizeError(f"fixed_defect {qid} missing {key}")
        targets_by_qid[qid] = entry

    fixed_defect_qids = tuple(sorted(targets_by_qid))
    if fixed_defect_qids != FIXED_DEFECT_QIDS:
        raise HyFixLocalizeError(
            "fixed_defect qids mismatch: "
            f"{list(fixed_defect_qids)!r} != {list(FIXED_DEFECT_QIDS)!r}"
        )

    return fixed_defect_qids, [targets_by_qid[qid] for qid in fixed_defect_qids]


def _config_from_diagnosis(diagnosis):
    trace_meta = diagnosis.get("trace_meta")
    if not isinstance(trace_meta, dict):
        raise HyFixLocalizeError("stability_diagnosis.json missing trace_meta")
    source_config = trace_meta.get("config")
    if not isinstance(source_config, dict):
        raise HyFixLocalizeError("stability_diagnosis.json missing trace_meta.config")

    config = {}
    for key in CONFIG_KEYS:
        if key not in source_config:
            raise HyFixLocalizeError(f"trace_meta.config missing {key}")
        config[key] = _json_clone(source_config[key])
    return config


def _index_trace_rows(trace_rows):
    index = {}
    for row in trace_rows:
        try:
            key = (row["arm"], row["qid"], row["tmdb_id"])
        except KeyError as exc:
            raise HyFixLocalizeError(
                f"stability_trace row missing {exc.args[0]}"
            ) from exc
        index.setdefault(key, []).append(row)
    return index


def _rows_for(trace_index, arm, qid, tmdb_id):
    rows = list(trace_index.get((arm, qid, tmdb_id), ()))
    rows.sort(key=lambda row: row.get("repeat", 0))
    return rows


def _build_deterministic_arm(arm, qid, tmdb_id, rows):
    if not rows:
        raise HyFixLocalizeError(
            f"missing {arm} trace rows for {qid} tmdb_id={tmdb_id}"
        )

    repeat_zero = _repeat_zero(rows, arm, qid)
    expected = _determinism_fingerprint(repeat_zero)
    for row in rows:
        if _determinism_fingerprint(row) != expected:
            raise HyFixLocalizeError(
                f"{arm} arm is not deterministic for {qid}: "
                f"repeat {row.get('repeat')} differs from repeat 0"
            )

    loss_stage = repeat_zero["loss_classification"]
    return {
        "deterministic": True,
        "stage_table": _stage_table(repeat_zero),
        "loss_stage": loss_stage,
        "fix_category": fix_category_for_loss(loss_stage),
    }


def _build_live_arm(rows):
    final_ranks = []
    loss_stage_per_repeat = []
    for row in rows:
        loss_stage_per_repeat.append(row["loss_classification"])
        final = row.get("final") or {}
        rank = final.get("final_rank")
        if rank is not None:
            final_ranks.append(rank)

    if final_ranks:
        final_rank_summary = {
            "min": min(final_ranks),
            "median": statistics.median(final_ranks),
            "max": max(final_ranks),
            "n_present": len(final_ranks),
        }
    else:
        final_rank_summary = {
            "min": None,
            "median": None,
            "max": None,
            "n_present": 0,
        }

    return {
        "deterministic": False,
        "repeats": len(rows),
        "loss_stage_per_repeat": loss_stage_per_repeat,
        "final_rank_summary": final_rank_summary,
    }


def _repeat_zero(rows, arm, qid):
    for row in rows:
        if row.get("repeat") == 0:
            return row
    raise HyFixLocalizeError(f"missing repeat 0 for {arm} {qid}")


def _stage_table(row):
    table = {}
    for stage in STAGE_PIPELINE:
        if stage not in row:
            raise HyFixLocalizeError(
                f"trace row for {row.get('qid')} missing {stage}"
            )
        table[stage] = _json_clone(row[stage])
    return table


def _determinism_fingerprint(row):
    data = {}
    for field in _DETERMINISM_FIELDS:
        if field not in row:
            raise HyFixLocalizeError(
                f"trace row for {row.get('qid')} missing {field}"
            )
        data[field] = row[field]
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _fix_category_summary(per_target):
    summary = {key: 0 for key in SUMMARY_KEYS}
    for target in per_target:
        category = target["consolidated_fix_category"]
        if category not in summary:
            raise HyFixLocalizeError(f"unsupported fix category: {category}")
        summary[category] += 1

    if sum(summary.values()) != len(FIXED_DEFECT_QIDS):
        raise HyFixLocalizeError("fix_category_summary does not sum to 4")
    return summary


def _recommended_sequence(per_target):
    clean = [target for target in per_target if target["arms_agree"]]
    mixed = [target for target in per_target if not target["arms_agree"]]
    clean.sort(
        key=lambda target: (
            _CATEGORY_ORDER.get(target["consolidated_fix_category"], 99),
            target["qid"],
        )
    )
    mixed.sort(key=lambda target: target["qid"])
    return [target["qid"] for target in clean + mixed]


def _notes_for_target(target, config):
    qid = target["qid"]
    arms = target["arms"]
    pinned = arms["pinned"]
    no_llm = arms["no_llm"]
    consolidated = target["consolidated_fix_category"]

    if consolidated == "mixed":
        return (
            f"{qid} is mixed: pinned loss_stage={pinned['loss_stage']} "
            f"({pinned['fix_category']}), no_llm loss_stage={no_llm['loss_stage']} "
            f"({no_llm['fix_category']})."
        )

    pinned_loss = pinned["loss_stage"]
    no_llm_loss = no_llm["loss_stage"]
    if pinned_loss != no_llm_loss:
        return _category_note(qid, consolidated, pinned, no_llm)

    return _loss_stage_note(qid, pinned_loss, pinned, no_llm, config)


def _category_note(qid, category, pinned, no_llm):
    return (
        f"{qid} maps to {category} in both deterministic arms: "
        f"pinned loss_stage={pinned['loss_stage']}, "
        f"no_llm loss_stage={no_llm['loss_stage']}."
    )


def _loss_stage_note(qid, loss_stage, pinned, no_llm, config):
    final_top_k = config["FINAL_TOP_K"]
    rerank_top_k = config["RERANK_TOP_K"]

    if loss_stage == "unretrieved":
        return (
            f"{qid} is absent from semantic and bm25 retrieval in both "
            "deterministic arms."
        )
    if loss_stage == "retrieved_dropped_at_fusion":
        return (
            f"{qid} appears before fusion but is absent from RRF in both "
            "deterministic arms."
        )
    if loss_stage == "retrieved_dropped_before_rerank_pool":
        return (
            f"{qid} reaches RRF at ranks "
            f"{_stage_value(pinned, 'rrf', 'rank')}/"
            f"{_stage_value(pinned, 'rrf', 'list_len')} and "
            f"{_stage_value(no_llm, 'rrf', 'rank')}/"
            f"{_stage_value(no_llm, 'rrf', 'list_len')}; "
            f"the cross-encoder pool is top {rerank_top_k}, so it is lost "
            "before reranking."
        )
    if loss_stage == "rerank_demoted":
        return (
            f"{qid} enters the rerank pool with rerank ranks "
            f"{_stage_value(pinned, 'rerank', 'rerank_rank')} and "
            f"{_stage_value(no_llm, 'rerank', 'rerank_rank')}; "
            f"the final top-k cutoff is {final_top_k}."
        )
    if loss_stage == "rerank_recovered_final_demoted":
        return (
            f"{qid} has rerank ranks "
            f"{_stage_value(pinned, 'rerank', 'rerank_rank')} and "
            f"{_stage_value(no_llm, 'rerank', 'rerank_rank')} but final ranks "
            f"{_stage_value(pinned, 'final', 'final_rank')} and "
            f"{_stage_value(no_llm, 'final', 'final_rank')}."
        )
    if loss_stage == "hybrid_top5_hit":
        return (
            f"{qid} is already in the final top {final_top_k} in both "
            "deterministic arms."
        )
    return f"{qid} has loss_stage={loss_stage} in both deterministic arms."


def _stage_value(arm_data, stage, field):
    value = arm_data["stage_table"][stage].get(field)
    return "null" if value is None else value


def _json_clone(value):
    return json.loads(json.dumps(value))


def _utc_timestamp():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
