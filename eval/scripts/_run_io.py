"""Run-directory and manifest helpers for the eval harness."""

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = PROJECT_ROOT / "eval"
RUNS_DIR = EVAL_DIR / "runs"

_PROJECT_ROOT_STR = str(PROJECT_ROOT)
if _PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT_STR)

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RUN_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}([-_].*)?$")
_TIMESTAMP_STAGES = {
    "start",
    "candidates_done",
    "silver_done",
    "provisional_metrics_done",
}


def _coerce_utc(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _utc_timestamp(now: Optional[datetime] = None) -> str:
    value = _coerce_utc(now).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def new_run_id(now: Optional[datetime] = None) -> str:
    """Return a UTC minute-precision run id for no-git mode."""
    return f"{_coerce_utc(now).strftime('%Y-%m-%d-%H%M')}-nogit"


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    if ".." in run_id or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id contains unsupported path characters")


def run_dir(run_id: str) -> Path:
    """Return the absolute run directory path for a run id."""
    _validate_run_id(run_id)
    return RUNS_DIR / run_id


def ensure_run_dir(run_id: str) -> Path:
    """Create and return the run directory. Safe to call repeatedly."""
    path = run_dir(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2) + "\n")


def _load_manifest(run_id: str) -> Dict[str, Any]:
    path = run_dir(run_id) / "run_manifest.json"
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("run_manifest.json must contain an object")
    return data


def write_manifest(
    run_id: str,
    *,
    rng_seed: int = 42,
    extras: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Write and return the run manifest for a run."""
    from src import config

    dataset_row_count = getattr(config, "DATASET_ROW_COUNT", None)
    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "git_sha": None,
        "git_dirty": None,
        "git_mode": "no_git",
        "dataset_row_count": dataset_row_count,
        "chroma_collection_count": dataset_row_count,
        "embedding_model": getattr(config, "EMBEDDING_MODEL", None),
        "reranker_model": getattr(config, "RERANKER_MODEL", None),
        "llm_model": getattr(config, "LLM_MODEL", None),
        "rng_seed": rng_seed,
        "warnings": [],
        "timestamps": {
            "start": _utc_timestamp(),
            "candidates_done": None,
            "silver_done": None,
            "provisional_metrics_done": None,
        },
    }

    if extras:
        for key, value in extras.items():
            if key == "timestamps" and isinstance(value, dict):
                timestamps = dict(manifest["timestamps"])
                timestamps.update(value)
                manifest["timestamps"] = timestamps
            else:
                manifest[key] = value

    _atomic_write_json(ensure_run_dir(run_id) / "run_manifest.json", manifest)
    return manifest


def _coerce_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_coerce_json_value(item) for item in value]
    if isinstance(value, list):
        return [_coerce_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce_json_value(item) for key, item in value.items()}
    return value


def snapshot_config() -> Dict[str, Any]:
    """Return a JSON-serializable snapshot of public src.config constants."""
    from src import config

    snapshot: Dict[str, Any] = {}
    skipped = []
    for name in sorted(dir(config)):
        if not name.isupper():
            continue
        value = getattr(config, name)
        if callable(value) or type(value).__name__ == "module":
            continue
        coerced = _coerce_json_value(value)
        try:
            json.dumps(coerced)
        except TypeError as exc:
            skipped.append(f"{name}: {exc}")
            continue
        snapshot[name] = coerced
    snapshot["_skipped"] = skipped
    return snapshot


def write_config_snapshot(run_id: str) -> Dict[str, Any]:
    """Write and return config_snapshot.json for a run."""
    snapshot = snapshot_config()
    _atomic_write_json(ensure_run_dir(run_id) / "config_snapshot.json", snapshot)
    return snapshot


def append_warning(run_id: str, message: str) -> Dict[str, Any]:
    """Append a warning to run_manifest.json and return the updated manifest."""
    if not isinstance(message, str):
        raise ValueError("message must be a string")
    manifest = _load_manifest(run_id)
    warnings = manifest.setdefault("warnings", [])
    if not isinstance(warnings, list):
        raise ValueError("run_manifest.json warnings must be a list")
    warnings.append(message)
    _atomic_write_json(run_dir(run_id) / "run_manifest.json", manifest)
    return manifest


def update_timestamp(run_id: str, stage: str) -> Dict[str, Any]:
    """Stamp a manifest timestamp stage with the current UTC second."""
    if stage not in _TIMESTAMP_STAGES:
        allowed = ", ".join(sorted(_TIMESTAMP_STAGES))
        raise ValueError(f"stage must be one of: {allowed}")
    manifest = _load_manifest(run_id)
    timestamps = manifest.setdefault("timestamps", {})
    if not isinstance(timestamps, dict):
        raise ValueError("run_manifest.json timestamps must be an object")
    timestamps[stage] = _utc_timestamp()
    _atomic_write_json(run_dir(run_id) / "run_manifest.json", manifest)
    return manifest


def latest_run() -> str:
    """Return current_run.txt if present, otherwise the newest run directory."""
    pointer = RUNS_DIR / "current_run.txt"
    if pointer.exists():
        run_id = pointer.read_text(encoding="utf-8").strip()
        _validate_run_id(run_id)
        return run_id

    if not RUNS_DIR.exists():
        raise FileNotFoundError(
            "no canonical eval runs found in eval/runs/ "
            "(expected directory names like YYYY-MM-DD-HHMM-*)"
        )

    run_ids = sorted(
        path.name
        for path in RUNS_DIR.iterdir()
        if path.is_dir() and _RUN_TIMESTAMP_RE.fullmatch(path.name)
    )
    if not run_ids:
        raise FileNotFoundError(
            "no canonical eval runs found in eval/runs/ "
            "(expected directory names like YYYY-MM-DD-HHMM-*)"
        )
    return run_ids[-1]
