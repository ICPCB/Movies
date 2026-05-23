"""RERANK-REGRESSION-EVAL: full 20-query gold/silver-set reranker-swap eval.

Two stages:
  Stage 1 (--stage capture): for all 20 queries x {basic, advanced, hybrid},
    run the production pipelines with LLM calls stubbed to identity and the
    rerank symbol monkey-patched in src.pipelines.{advanced,hybrid} namespaces
    so the input pool, document text, and blend inputs are captured for each
    rerank call.  basic mode does not rerank (verified) so its top-15 ranked
    list is captured directly as an invariant.
  Stage 2 (--stage score): re-score the captured rerank pools with the
    baseline (`BAAI/bge-reranker-v2-m3` via CrossEncoder) and the alternative
    (`Alibaba-NLP/gte-multilingual-reranker-base` via the RERANK-02B
    transformers adapter), reproduce the exact final-score blend from
    src/retrieval/reranker.py, recompute metrics via the imported
    compute_metrics module against the read-only gold_labels.jsonl, and emit
    one mechanical gate_verdict.

Per the reviewed plan (docs/superpowers/plans/2026-05-23-rerank-regression-eval-plan.md)
this script never edits src/* and makes no LLM call in its scoring path.
The four external-review fixes are applied:
  1. top-15 records retained per (qid, mode, model);
  2. None / null-excluded compute_metrics value -> gate_inconclusive;
  3. q10 fix condition pinned to `hybrid` mode;
  4. monkey-patch src.pipelines.advanced.rerank and src.pipelines.hybrid.rerank
     (the bound names) with a basic-mode invariant check.

This module is read-only with respect to `src/*`.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


from eval.scripts import _run_io
from eval.scripts import compute_metrics as cm
from eval.scripts import rerank_model_comparison as rmc


# ---------- constants ----------
POOL_SNAPSHOT_SCHEMA = "rerank-regression-pool.v1"
COMPARISON_SCHEMA = "rerank-regression-comparison.v1"

ALL_MODES: Tuple[str, ...] = ("basic", "advanced", "hybrid")
MODES_WITH_RERANK: Tuple[str, ...] = ("advanced", "hybrid")
BASIC_MODE = "basic"

BASELINE_MODEL = "BAAI/bge-reranker-v2-m3"
ALT_MODEL_ID = "Alibaba-NLP/gte-multilingual-reranker-base"

# Headline aggregate metrics tested for non-regression, per mode:
HEADLINE_METRICS: Tuple[str, ...] = ("strict_hit_at_5", "strict_hit_at_10", "mrr_at_5")
PER_QUERY_METRIC = "strict_hit_at_5"  # per-query hit/miss unit
Q10_FIX_QID = "q10"
Q10_FIX_MODE = "hybrid"

ANALYSIS_SUBDIR = "analysis/rerank_regression"
POOL_SNAPSHOT_FILE = "full_set_pool_snapshot.json"
COMPARISON_FILE = "regression_comparison.json"


# ---------- utilities ----------
def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        f = float(value)
        if not math.isfinite(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _candidate_tmdb_id(m: Mapping[str, Any]) -> int:
    """Resolve a movie's tmdb_id from the (tmdb_id | id | movie_id) chain.

    Mirrors eval/scripts/run_pipelines._candidate_tmdb_id. `semantic_search`
    returns movies with the key `id`, not `tmdb_id`; the original
    `candidates.jsonl` builder relies on this fallback, and we must too —
    otherwise label lookups by (qid, tmdb_id) return None for every row.
    """
    for key in ("tmdb_id", "id", "movie_id"):
        value = m.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


# ---------- blend reproduction (mirrors src/retrieval/reranker.py exactly) ----------
def blend_final_scores(
    rerank_scores: Sequence[float],
    pool: Sequence[Mapping[str, Any]],
) -> List[float]:
    """Reproduce the final-score blend from src/retrieval/reranker.py:rerank.

    final_score_i = rerank_score_i
        + RERANK_VOTE_COUNT_WEIGHT * vote_prior_i
        + RERANK_UPSTREAM_WEIGHT * upstream_prior_i
        + RERANK_SOURCE_AGREEMENT_BONUS * source_agreement_i
    """
    from src.config import (
        RERANK_VOTE_COUNT_WEIGHT,
        RERANK_UPSTREAM_WEIGHT,
        RERANK_SOURCE_AGREEMENT_BONUS,
    )
    if len(rerank_scores) != len(pool):
        raise ValueError(
            f"blend_final_scores: score/pool length mismatch ({len(rerank_scores)} vs {len(pool)})"
        )
    if not pool:
        return []
    max_votes = max(_coerce_int(m.get("vote_count", 0)) for m in pool)
    max_vote_log = math.log1p(max_votes) or 1.0
    upstream_values = [_coerce_float(m.get("upstream_raw", 0.0)) for m in pool]
    max_upstream = max(upstream_values) or 1.0
    out: List[float] = []
    for score, m, upstream_raw in zip(rerank_scores, pool, upstream_values):
        vote_prior = math.log1p(_coerce_int(m.get("vote_count", 0))) / max_vote_log
        upstream_prior = upstream_raw / max_upstream
        source_agreement = 1.0 if (
            m.get("semantic_rank") is not None and m.get("bm25_rank") is not None
        ) else 0.0
        final = (
            float(score)
            + RERANK_VOTE_COUNT_WEIGHT * vote_prior
            + RERANK_UPSTREAM_WEIGHT * upstream_prior
            + RERANK_SOURCE_AGREEMENT_BONUS * source_agreement
        )
        out.append(final)
    return out


# ---------- Stage 1: pool capture ----------
def _install_llm_stubs() -> Dict[str, Any]:
    """Stub LLM functions to remove any non-determinism.  No LLM call in capture."""
    import src.llm.langchain_ollama as llm_mod

    originals = {
        "expand_query": llm_mod.expand_query,
        "hyde_generate": llm_mod.hyde_generate,
        "explain_movies_batch": llm_mod.explain_movies_batch,
    }

    def stub_expand_query(q: str) -> str:
        return q

    def stub_hyde_generate(q: str) -> str:
        return ""

    def stub_explain_movies_batch(query: str, movies: List[dict]) -> List[str]:
        return ["" for _ in movies]

    llm_mod.expand_query = stub_expand_query
    llm_mod.hyde_generate = stub_hyde_generate
    llm_mod.explain_movies_batch = stub_explain_movies_batch

    # Rebind in pipeline namespaces (they did `from ... import expand_query, ...`):
    from src.pipelines import advanced as adv_mod
    from src.pipelines import hybrid as hyb_mod
    adv_mod.expand_query = stub_expand_query
    adv_mod.hyde_generate = stub_hyde_generate
    adv_mod.explain_movies_batch = stub_explain_movies_batch
    hyb_mod.expand_query = stub_expand_query
    hyb_mod.explain_movies_batch = stub_explain_movies_batch

    return originals


def _install_capture_wrappers(captures: Dict[Tuple[str, str], Dict[str, Any]], state: Dict[str, str]) -> Dict[str, Any]:
    """Patch src.pipelines.{advanced,hybrid}.rerank with capture wrappers.

    Asserts basic does not import the rerank symbol (basic does not rerank).
    """
    from src.pipelines import advanced as adv_mod
    from src.pipelines import hybrid as hyb_mod
    from src.pipelines import basic as basic_mod

    # Basic invariant: basic.py must not bind `rerank` in its namespace.
    assert "rerank" not in vars(basic_mod), (
        "basic.py unexpectedly bound a `rerank` symbol; basic must not rerank."
    )

    real_rerank = adv_mod.rerank  # both bound to src.retrieval.reranker.rerank
    assert hyb_mod.rerank is real_rerank, (
        "advanced and hybrid bound different rerank references; check imports."
    )

    def make_wrapper(mode_name: str):
        def wrapper(query, movies, top_k=None, rerank_pool=None):
            from src.retrieval.reranker import build_movie_document, _upstream_score
            from src.utils.dedup import deduplicate_movies
            from src.config import RERANK_TOP_K, FINAL_TOP_K

            effective_top_k = top_k if top_k is not None else FINAL_TOP_K
            effective_pool = rerank_pool if rerank_pool is not None else RERANK_TOP_K

            # Mirror src.retrieval.reranker.rerank's pre-rerank pool selection so
            # the captured pool is the SAME pool the cross-encoder will score.
            deduped = deduplicate_movies(list(movies), prefer_score="final_score")
            deduped.sort(
                key=lambda m: _coerce_float(m.get("final_score", 0.0)),
                reverse=True,
            )
            pool = deduped[:effective_pool]

            pool_records: List[Dict[str, Any]] = []
            for m in pool:
                pool_records.append({
                    "tmdb_id": _candidate_tmdb_id(m),
                    "movie_key": _coerce_text(m.get("movie_key", "")),
                    "title": _coerce_text(m.get("title", "")),
                    "year": _coerce_int(m.get("year", 0)),
                    "vote_count": _coerce_int(m.get("vote_count", 0)),
                    "semantic_score": _coerce_float(m.get("semantic_score", 0.0)),
                    "bm25_score": _coerce_float(m.get("bm25_score", 0.0)),
                    "rrf_score": _coerce_float(m.get("rrf_score", 0.0)),
                    "semantic_rrf": _coerce_float(m.get("semantic_rrf", 0.0)),
                    "final_score_upstream": _coerce_float(m.get("final_score", 0.0)),
                    "semantic_rank": m.get("semantic_rank"),
                    "bm25_rank": m.get("bm25_rank"),
                    # _upstream_score uses the first non-zero of a fallback list:
                    "upstream_raw": float(_upstream_score(m)),
                    "document_text": build_movie_document(m),
                    "rerank_query": _coerce_text(query),
                })

            # Delegate to the real reranker (which uses the production
            # bge-reranker-v2-m3 model via get_reranker()).
            final_top = real_rerank(
                query, movies, top_k=effective_top_k, rerank_pool=effective_pool,
            )

            qid = state.get("qid")
            assert qid is not None, "capture wrapper called outside a tracked query"
            captures[(qid, mode_name)] = {
                "rerank_query": _coerce_text(query),
                "pool": pool_records,
                "baseline_top": [
                    {
                        "rank": rank,
                        "tmdb_id": _candidate_tmdb_id(m),
                        "movie_key": _coerce_text(m.get("movie_key", "")),
                        "title": _coerce_text(m.get("title", "")),
                        "rerank_score": _coerce_float(m.get("rerank_score", 0.0)),
                        "final_score": _coerce_float(m.get("final_score", 0.0)),
                    }
                    for rank, m in enumerate(final_top)
                ],
            }
            return final_top

        return wrapper

    adv_wrapper = make_wrapper("advanced")
    hyb_wrapper = make_wrapper("hybrid")
    adv_mod.rerank = adv_wrapper
    hyb_mod.rerank = hyb_wrapper

    # Assert each patched name resolved to a callable:
    assert callable(adv_mod.rerank)
    assert callable(hyb_mod.rerank)

    return {"real_rerank": real_rerank}


def _restore(originals: Mapping[str, Any]) -> None:
    """Best-effort restore (mainly for tests; the eval process exits anyway)."""
    import src.llm.langchain_ollama as llm_mod
    for name, fn in originals.items():
        setattr(llm_mod, name, fn)


def stage_capture(run_id: str, queries_path: Path) -> Dict[str, Any]:
    """Run all 20 queries x 3 modes, capture rerank pools and basic top-15."""
    started = time.time()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    # Install LLM stubs and capture wrappers BEFORE importing pipelines so the
    # pipeline imports pick up the stubs (their `from ... import` happens at
    # module load).  We import pipelines via _install_capture_wrappers.
    captures: Dict[Tuple[str, str], Dict[str, Any]] = {}
    state: Dict[str, str] = {"qid": None}

    # First import the LLM module so its symbols are addressable, then stub.
    originals = _install_llm_stubs()
    _install_capture_wrappers(captures, state)

    # Now import the pipelines and run.
    from src.pipelines import basic, advanced, hybrid

    queries = _read_jsonl(queries_path)
    assert len(queries) > 0, f"no queries in {queries_path}"

    per_query: List[Dict[str, Any]] = []
    for q in queries:
        qid = str(q["qid"])
        query_text = str(q["query"])
        state["qid"] = qid

        per_mode_capture: Dict[str, Any] = {}

        # basic mode: no rerank, capture top-15 directly.
        basic_top = basic.run(query_text, top_k=15)
        per_mode_capture["basic"] = {
            "rerank_query": None,
            "pool": None,
            "baseline_top": [
                {
                    "rank": rank,
                    "tmdb_id": _candidate_tmdb_id(m),
                    "movie_key": _coerce_text(m.get("movie_key", "")),
                    "title": _coerce_text(m.get("title", "")),
                    "final_score": _coerce_float(m.get("final_score", 0.0)),
                }
                for rank, m in enumerate(basic_top)
            ],
        }

        # advanced: capture wrapper records into captures[(qid, "advanced")].
        try:
            advanced.run(query_text, top_k=15)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"advanced pipeline failed for {qid}: {exc}") from exc
        per_mode_capture["advanced"] = captures[(qid, "advanced")]

        # hybrid: capture wrapper records into captures[(qid, "hybrid")].
        try:
            hybrid.run(query_text, top_k=15)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"hybrid pipeline failed for {qid}: {exc}") from exc
        per_mode_capture["hybrid"] = captures[(qid, "hybrid")]

        per_query.append({
            "qid": qid,
            "query": query_text,
            "modes": per_mode_capture,
        })
        print(f"  captured {qid} basic={len(per_mode_capture['basic']['baseline_top'])} "
              f"adv_pool={len(per_mode_capture['advanced']['pool'])} "
              f"hyb_pool={len(per_mode_capture['hybrid']['pool'])}", flush=True)

    elapsed = time.time() - started

    snapshot = {
        "schema_version": POOL_SNAPSHOT_SCHEMA,
        "ticket": "RERANK-REGRESSION-EVAL",
        "stage": "capture",
        "run_id": run_id,
        "generated_at": utc_now(),
        "elapsed_seconds": round(elapsed, 3),
        "scope": {
            "queries_total": len(queries),
            "modes": list(ALL_MODES),
            "modes_with_rerank": list(MODES_WITH_RERANK),
            "deterministic_arm": "no_llm (expand_query/hyde_generate/explain_movies_batch stubbed to identity)",
            "baseline_model_used_in_capture": BASELINE_MODEL,
        },
        "queries": per_query,
    }
    _restore(originals)
    return snapshot


# ---------- Stage 2: score + gate ----------
def _baseline_score_pairs(pairs: Sequence[Tuple[str, str]]) -> List[float]:
    """Score (query, document) pairs with bge-reranker-v2-m3 via CrossEncoder."""
    if not pairs:
        return []
    from sentence_transformers import CrossEncoder
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  baseline loader: CrossEncoder {BASELINE_MODEL} on {device}", flush=True)
    model = CrossEncoder(BASELINE_MODEL, device=device)
    try:
        scores = model.predict(
            [[q, d] for q, d in pairs],
            show_progress_bar=False,
        )
    finally:
        try:
            del model
        except Exception:  # noqa: BLE001
            pass
        try:
            import torch as _torch
            _torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass
    return [float(s) for s in scores]


def _alt_score_pairs(pairs: Sequence[Tuple[str, str]]) -> Tuple[List[float], Dict[str, Any]]:
    """Score pairs with the alt model via the RERANK-02B transformers adapter."""
    if not pairs:
        return [], {"model_id": ALT_MODEL_ID, "scored_pairs": 0}
    libraries = rmc.load_phase_b_libraries()
    torch = libraries["torch"]
    spec = next(s for s in rmc.MODEL_SPECS if s.model_id == ALT_MODEL_ID)
    download = rmc.resolve_and_download_model(spec, libraries)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  alt loader: transformers {ALT_MODEL_ID} on {device}", flush=True)

    pair_records: List[Dict[str, Any]] = [
        {"rerank_query": q, "document_text": d} for q, d in pairs
    ]
    scores, loader_details = rmc.score_pairs_with_transformers(
        spec=spec,
        model_path=download["local_snapshot_path"],
        pairs=pair_records,
        libraries=libraries,
        device=device,
    )
    try:
        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass
    return [float(s) for s in scores], {
        "model_id": spec.model_id,
        "resolved_revision": download.get("resolved_revision"),
        "local_snapshot_gb": download.get("local_snapshot_gb"),
        "loader": loader_details,
        "scored_pairs": len(scores),
    }


def _build_ranked_top15(
    pool: Sequence[Mapping[str, Any]],
    rerank_scores: Sequence[float],
) -> List[Dict[str, Any]]:
    """Blend scores+priors, sort by final_score desc, return top-15."""
    final_scores = blend_final_scores(rerank_scores, pool)
    indexed = list(enumerate(zip(pool, rerank_scores, final_scores)))
    indexed.sort(key=lambda item: item[1][2], reverse=True)
    out: List[Dict[str, Any]] = []
    for rank, (orig_idx, (m, rerank_score, final_score)) in enumerate(indexed[:15]):
        out.append({
            "rank": rank,
            "tmdb_id": _candidate_tmdb_id(m),
            "movie_key": _coerce_text(m.get("movie_key", "")),
            "title": _coerce_text(m.get("title", "")),
            "rerank_score": float(rerank_score),
            "final_score": float(final_score),
            "pool_index": orig_idx,
        })
    return out


def _build_candidates_for_metrics(
    snapshot: Mapping[str, Any],
    per_qid_top15_by_mode_by_model: Mapping[str, Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]]],
    model_key: str,
    snapshot_basic_lookup: Mapping[str, Sequence[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    """Assemble per-mode union candidate records for compute_metrics."""
    records: List[Dict[str, Any]] = []
    for q in snapshot["queries"]:
        qid = q["qid"]
        # Collect tmdb_id -> {mode: rank, mode: rank, ...}
        per_movie: Dict[int, Dict[str, Any]] = {}
        # basic mode (invariant across models):
        for entry in snapshot_basic_lookup[qid]:
            tmdb_id = _coerce_int(entry["tmdb_id"])
            per_movie.setdefault(tmdb_id, {"info": entry, "per_mode": {}})
            per_movie[tmdb_id]["per_mode"]["basic"] = {"rank": int(entry["rank"])}
        # advanced + hybrid for this model:
        for mode in MODES_WITH_RERANK:
            for entry in per_qid_top15_by_mode_by_model[qid][model_key][mode]:
                tmdb_id = _coerce_int(entry["tmdb_id"])
                per_movie.setdefault(tmdb_id, {"info": entry, "per_mode": {}})
                per_movie[tmdb_id]["per_mode"][mode] = {"rank": int(entry["rank"])}

        for tmdb_id, payload in per_movie.items():
            info = payload["info"]
            records.append({
                "qid": qid,
                "tmdb_id": tmdb_id,
                "movie_key": _coerce_text(info.get("movie_key", "")),
                "title": _coerce_text(info.get("title", "")),
                "year": _coerce_int(info.get("year", 0)),
                "overview": "",
                "genres": "",
                "keywords": "",
                "tagline": "",
                "per_mode": payload["per_mode"],
                "in_top_k_of": list(payload["per_mode"].keys()),
                "source": "union",
            })
    return records


def _per_query_strict_hit_at_5(
    candidates: Sequence[Mapping[str, Any]],
    labels: Mapping[Tuple[str, int], Optional[int]],
) -> Dict[str, Dict[str, Optional[float]]]:
    """Compute per-query strict_hit@5 (grade==3 hit) per mode.  None if null-blocked."""
    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for c in candidates:
        grouped.setdefault(str(c["qid"]), []).append(c)
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for qid, recs in grouped.items():
        out[qid] = {}
        for mode in ALL_MODES:
            rows = []
            for c in recs:
                md = c.get("per_mode", {}).get(mode)
                if md is None:
                    continue
                if int(md["rank"]) >= 5:
                    continue
                rows.append({
                    "tmdb_id": _coerce_int(c["tmdb_id"]),
                    "grade": labels.get((qid, _coerce_int(c["tmdb_id"]))),
                })
            value, _ = cm._hit_at_k(rows, lambda g: g == 3)
            out[qid][mode] = value
    return out


def _per_query_strict_hit_target_q10_hybrid(
    per_query: Mapping[str, Mapping[str, Optional[float]]],
) -> Optional[float]:
    q10 = per_query.get(Q10_FIX_QID)
    if q10 is None:
        return None
    return q10.get(Q10_FIX_MODE)


def _basic_byMode_summary_equal(
    bm_a: Mapping[str, Any], bm_b: Mapping[str, Any],
) -> Tuple[bool, List[str]]:
    """Compare basic-mode aggregate summaries; return (equal, diffs).

    Basic mode does not rerank, so its own top-K ordering must be identical
    between the baseline run and the alt run.  We compare the rank-list
    families: hit / strict_hit / mrr / strict_mrr at all TOP_KS.

    NOTE: `ndcg` is INTENTIONALLY excluded.  `compute_metrics._ideal_dcg_for_query`
    computes a per-query ideal DCG over ALL candidates (basic+advanced+hybrid
    union); when the alt model promotes a higher-graded movie into the
    advanced/hybrid top-15 (raising the per-query union's best grades), the
    per-query ideal_dcg grows, and basic.ndcg = basic_dcg / ideal_dcg
    correspondingly shrinks — even though basic's own top-K ordering and DCG
    numerator are identical.  This is a known compute_metrics artifact, not a
    basic-mode regression.  Likewise excluded_null counters can shift if the
    union changes which movies have null grades at @15.
    """
    a = bm_a.get(BASIC_MODE) or {}
    b = bm_b.get(BASIC_MODE) or {}
    diffs: List[str] = []
    rank_list_families = ("hit", "strict_hit", "mrr", "strict_mrr")
    for k in cm.TOP_KS:
        for family in rank_list_families:
            key = cm._metric_key(family, k)
            va = a.get(key)
            vb = b.get(key)
            if va != vb:
                diffs.append(f"basic.{key}: {va} != {vb}")
    return (len(diffs) == 0, diffs)


def _gate_verdict(
    by_mode_baseline: Mapping[str, Any],
    by_mode_alt: Mapping[str, Any],
    per_q_baseline: Mapping[str, Mapping[str, Optional[float]]],
    per_q_alt: Mapping[str, Mapping[str, Optional[float]]],
    basic_invariant_diffs: Sequence[str],
    baseline_self_check: Mapping[str, Any],
) -> Dict[str, Any]:
    reasons: List[str] = []

    # 0. baseline self-check on q05/q10 must have passed:
    if not baseline_self_check.get("passed", False):
        reasons.append(
            f"baseline self-check failed: {baseline_self_check.get('details')}"
        )

    # 1. basic-mode invariant:
    if basic_invariant_diffs:
        reasons.extend(f"basic invariant violated: {d}" for d in basic_invariant_diffs)

    # 2. null-metric inconclusive sweep:
    # Per plan §5: compute_metrics returning a None / null-excluded value for
    # any headline metric in either run -> gate_inconclusive. The signal is
    # either (a) a literal None aggregate (ndcg can produce None), (b) a
    # baseline/alt mismatch in queries_excluded_null, OR (c) queries_excluded_null
    # > 0 in either run — the last case means at least one query has an
    # unlabeled candidate in top-K, so the @10/@15 aggregate is partially
    # masked by `_mean_or_zero` filtering Nones (a 0.0 there does NOT mean a
    # legitimate 0/N strict-hit).
    null_violations: List[str] = []
    for mode in ALL_MODES:
        mb = by_mode_baseline.get(mode) or {}
        ma = by_mode_alt.get(mode) or {}
        for hm in HEADLINE_METRICS:
            if mb.get(hm) is None:
                null_violations.append(f"baseline {mode}.{hm} is None")
            if ma.get(hm) is None:
                null_violations.append(f"alt {mode}.{hm} is None")
        eb = int(mb.get("queries_excluded_null") or 0)
        ea = int(ma.get("queries_excluded_null") or 0)
        if eb != ea:
            null_violations.append(
                f"queries_excluded_null differs in {mode}: baseline={eb} alt={ea}"
            )
        if eb > 0:
            null_violations.append(
                f"baseline {mode}.queries_excluded_null = {eb} > 0 (label-coverage gap; "
                f"some queries have unlabeled candidates in top-10/@15 -> @10/@15 aggregates unreliable)"
            )
        if ea > 0:
            null_violations.append(
                f"alt {mode}.queries_excluded_null = {ea} > 0 (label-coverage gap)"
            )

    # If basic invariant violated OR null violations OR self-check failed -> inconclusive
    if reasons or null_violations:
        return {
            "value": "gate_inconclusive",
            "reasons": list(reasons) + null_violations,
            "phase5_unblocked": False,
        }

    # 3. aggregate non-regression on headline metrics (tolerance 0.0):
    regressions: List[str] = []
    for mode in ALL_MODES:
        mb = by_mode_baseline.get(mode) or {}
        ma = by_mode_alt.get(mode) or {}
        for hm in HEADLINE_METRICS:
            vb = mb.get(hm)
            va = ma.get(hm)
            if vb is None or va is None:
                regressions.append(f"null metric {mode}.{hm}: baseline={vb} alt={va}")
                continue
            if float(va) + 1e-12 < float(vb):
                regressions.append(
                    f"aggregate regression {mode}.{hm}: alt={va} < baseline={vb}"
                )

    # 4. per-query strict_hit@5 hit -> miss flips, summed across all modes:
    flips: List[str] = []
    qids = set(per_q_baseline) | set(per_q_alt)
    for qid in sorted(qids):
        for mode in ALL_MODES:
            vb = per_q_baseline.get(qid, {}).get(mode)
            va = per_q_alt.get(qid, {}).get(mode)
            if vb is None or va is None:
                # Treat any None per-query value as inconclusive signal:
                regressions.append(
                    f"per-query {qid}.{mode}.{PER_QUERY_METRIC} null: "
                    f"baseline={vb} alt={va}"
                )
                continue
            if vb >= 1.0 and va < 1.0:
                flips.append(f"{qid}/{mode} hit->miss (baseline={vb} alt={va})")

    # 5. q10 hybrid fix landed:
    q10_hybrid_alt = _per_query_strict_hit_target_q10_hybrid(per_q_alt)
    q10_hybrid_baseline = _per_query_strict_hit_target_q10_hybrid(per_q_baseline)
    q10_fixed = (q10_hybrid_alt is not None and q10_hybrid_alt >= 1.0)

    if regressions:
        return {
            "value": "gate_inconclusive" if any("null" in r for r in regressions) else "gate_fail",
            "reasons": regressions + (flips if flips else []),
            "q10_hybrid_baseline_strict_hit_at_5": q10_hybrid_baseline,
            "q10_hybrid_alt_strict_hit_at_5": q10_hybrid_alt,
            "q10_fixed": q10_fixed,
            "phase5_unblocked": False,
        }

    if flips:
        return {
            "value": "gate_fail",
            "reasons": flips,
            "q10_hybrid_baseline_strict_hit_at_5": q10_hybrid_baseline,
            "q10_hybrid_alt_strict_hit_at_5": q10_hybrid_alt,
            "q10_fixed": q10_fixed,
            "phase5_unblocked": False,
        }

    if not q10_fixed:
        return {
            "value": "gate_fail",
            "reasons": [
                f"q10 not fixed in hybrid mode: alt strict_hit@5 = {q10_hybrid_alt}"
            ],
            "q10_hybrid_baseline_strict_hit_at_5": q10_hybrid_baseline,
            "q10_hybrid_alt_strict_hit_at_5": q10_hybrid_alt,
            "q10_fixed": False,
            "phase5_unblocked": False,
        }

    return {
        "value": "gate_pass",
        "reasons": ["aggregate non-regression, no per-query flips, q10 fixed in hybrid"],
        "q10_hybrid_baseline_strict_hit_at_5": q10_hybrid_baseline,
        "q10_hybrid_alt_strict_hit_at_5": q10_hybrid_alt,
        "q10_fixed": True,
        "phase5_unblocked": False,  # ALWAYS False — gate_pass only authorizes a NEW Phase 5 PLAN
    }


def stage_score(run_id: str, snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Re-score captured pools with baseline + alt, recompute metrics, gate."""
    started = time.time()

    # Build flat (qid, mode, pool_idx, query, doc) records for batched scoring.
    flat_pairs: List[Tuple[str, str, int, str, str]] = []  # (qid, mode, idx, query, doc)
    pool_index_by_mode: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for q in snapshot["queries"]:
        qid = q["qid"]
        for mode in MODES_WITH_RERANK:
            arm = q["modes"][mode]
            pool = arm["pool"]
            pool_index_by_mode[(qid, mode)] = pool
            for idx, m in enumerate(pool):
                flat_pairs.append((qid, mode, idx, arm["rerank_query"], m["document_text"]))

    pair_only = [(q, d) for (_, _, _, q, d) in flat_pairs]
    print(f"  total advanced+hybrid pairs to score: {len(pair_only)}")

    # --- baseline re-score ---
    baseline_scores_flat = _baseline_score_pairs(pair_only)
    # --- alt re-score ---
    alt_scores_flat, alt_loader_meta = _alt_score_pairs(pair_only)

    # Sanity:
    assert len(baseline_scores_flat) == len(flat_pairs), \
        f"baseline scores={len(baseline_scores_flat)} pairs={len(flat_pairs)}"
    assert len(alt_scores_flat) == len(flat_pairs), \
        f"alt scores={len(alt_scores_flat)} pairs={len(flat_pairs)}"

    # Re-group scores by (qid, mode):
    baseline_scores_by_arm: Dict[Tuple[str, str], List[float]] = {}
    alt_scores_by_arm: Dict[Tuple[str, str], List[float]] = {}
    for (qid, mode, idx, _q, _d), bs, alts in zip(
        flat_pairs, baseline_scores_flat, alt_scores_flat
    ):
        baseline_scores_by_arm.setdefault((qid, mode), []).append(bs)
        alt_scores_by_arm.setdefault((qid, mode), []).append(alts)

    # Build top-15 per (qid, mode, model):
    per_qid_top15: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}
    for q in snapshot["queries"]:
        qid = q["qid"]
        per_qid_top15[qid] = {"baseline": {}, "alt": {}}
        for mode in MODES_WITH_RERANK:
            pool = pool_index_by_mode[(qid, mode)]
            per_qid_top15[qid]["baseline"][mode] = _build_ranked_top15(
                pool, baseline_scores_by_arm[(qid, mode)],
            )
            per_qid_top15[qid]["alt"][mode] = _build_ranked_top15(
                pool, alt_scores_by_arm[(qid, mode)],
            )

    # Baseline self-check on q05/q10: re-scored baseline ranks should reproduce
    # the recorded `baseline_top` ordering from Stage 1 in the same mode.  We
    # accept this if the top-5 movie_keys match (the original capture used
    # FINAL_TOP_K=5 -> top-5 returned in baseline_top).
    self_check: Dict[str, Any] = {"comparisons": {}, "passed": True, "details": []}
    for qid in ("q05", "q10"):
        for mode in MODES_WITH_RERANK:
            captured = snapshot["queries"]
            q_record = next((q for q in captured if q["qid"] == qid), None)
            if q_record is None:
                self_check["passed"] = False
                self_check["details"].append(f"missing {qid} in snapshot")
                continue
            recorded_top = q_record["modes"][mode]["baseline_top"]
            n_compare = min(5, len(recorded_top))
            recorded_keys = [r["movie_key"] for r in recorded_top[:n_compare]]
            rescored = per_qid_top15[qid]["baseline"][mode][:n_compare]
            rescored_keys = [r["movie_key"] for r in rescored]
            ok = recorded_keys == rescored_keys
            self_check["comparisons"][f"{qid}/{mode}"] = {
                "n_compared": n_compare,
                "recorded_top": recorded_keys,
                "rescored_top": rescored_keys,
                "ok": ok,
            }
            if not ok:
                self_check["passed"] = False
                self_check["details"].append(
                    f"baseline self-check mismatch for {qid}/{mode}: "
                    f"recorded={recorded_keys} vs rescored={rescored_keys}"
                )

    # Build basic-mode lookup (model-invariant):
    basic_lookup: Dict[str, List[Dict[str, Any]]] = {}
    for q in snapshot["queries"]:
        basic_lookup[q["qid"]] = q["modes"]["basic"]["baseline_top"]

    # Build candidate sets for compute_metrics:
    cand_baseline = _build_candidates_for_metrics(
        snapshot, per_qid_top15, "baseline", basic_lookup,
    )
    cand_alt = _build_candidates_for_metrics(
        snapshot, per_qid_top15, "alt", basic_lookup,
    )

    # Load labels (merged gold+silver) and queries:
    run_dir = _run_io.run_dir(run_id)
    gold_path = run_dir / "gold_labels.jsonl"
    queries_path = _run_io.EVAL_DIR / "queries" / "v1.jsonl"
    labels_raw = _read_jsonl(gold_path)
    label_map = {
        (str(r["qid"]), int(r["tmdb_id"])): r.get("grade")
        for r in labels_raw
    }
    query_records = cm._load_queries(queries_path)

    # Recompute metrics via the imported compute_metrics module:
    metrics_baseline = cm.compute_metrics(
        run_id=run_id,
        candidates=cand_baseline,
        silver_labels=labels_raw,
        query_records=query_records,
        bootstrap_b=0,  # deterministic; we don't need CI for the regression eval
        seed=42,
    )
    metrics_alt = cm.compute_metrics(
        run_id=run_id,
        candidates=cand_alt,
        silver_labels=labels_raw,
        query_records=query_records,
        bootstrap_b=0,
        seed=42,
    )

    # Per-query strict_hit@5 hit/miss per mode:
    per_q_baseline = _per_query_strict_hit_at_5(cand_baseline, label_map)
    per_q_alt = _per_query_strict_hit_at_5(cand_alt, label_map)

    # Basic invariant check:
    basic_equal, basic_diffs = _basic_byMode_summary_equal(
        metrics_baseline["by_mode"], metrics_alt["by_mode"],
    )

    verdict = _gate_verdict(
        metrics_baseline["by_mode"],
        metrics_alt["by_mode"],
        per_q_baseline,
        per_q_alt,
        basic_diffs,
        self_check,
    )

    elapsed = time.time() - started

    comparison = {
        "schema_version": COMPARISON_SCHEMA,
        "ticket": "RERANK-REGRESSION-EVAL",
        "stage": "score",
        "run_id": run_id,
        "generated_at": utc_now(),
        "elapsed_seconds": round(elapsed, 3),
        "models": {
            "baseline": {"model_id": BASELINE_MODEL, "loader": "sentence_transformers.CrossEncoder"},
            "alternative": alt_loader_meta,
        },
        "scope": {
            "queries_total": len(snapshot["queries"]),
            "modes": list(ALL_MODES),
            "modes_with_rerank": list(MODES_WITH_RERANK),
            "total_scored_pairs_per_model": len(flat_pairs),
        },
        "baseline_self_check": self_check,
        "basic_invariant": {"passed": basic_equal, "diffs": basic_diffs},
        "metrics_baseline_by_mode": metrics_baseline["by_mode"],
        "metrics_alt_by_mode": metrics_alt["by_mode"],
        "per_query_strict_hit_at_5_baseline": per_q_baseline,
        "per_query_strict_hit_at_5_alt": per_q_alt,
        "gate_verdict": verdict,
        "phase5_gate": "blocked",
        "phase5_note": (
            "A gate_pass only authorizes a NEW Phase 5 plan to be AUTHORED and "
            "Human-reviewed; it does NOT unblock Phase 5 or authorize any src/* edit."
        ),
    }
    return comparison


# ---------- CLI ----------
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RERANK-REGRESSION-EVAL: full 20-query reranker-swap eval."
    )
    parser.add_argument("--run", required=True, help="run id, e.g. 2026-05-19-1846-nogit")
    parser.add_argument(
        "--stage",
        choices=("capture", "score", "all"),
        default="all",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=None,
        help="queries jsonl path (defaults to eval/queries/v1.jsonl)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    queries_path = args.queries or (_run_io.EVAL_DIR / "queries" / "v1.jsonl")
    out_dir = _run_io.run_dir(args.run) / ANALYSIS_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / POOL_SNAPSHOT_FILE
    comparison_path = out_dir / COMPARISON_FILE

    snapshot: Optional[Dict[str, Any]] = None
    if args.stage in ("capture", "all"):
        print(f"[capture] starting; queries={queries_path}", flush=True)
        snapshot = stage_capture(args.run, queries_path)
        _atomic_write_json(snapshot_path, snapshot)
        print(f"[capture] wrote {snapshot_path}", flush=True)
    if args.stage in ("score", "all"):
        if snapshot is None:
            print(f"[score] loading snapshot {snapshot_path}", flush=True)
            with snapshot_path.open("r", encoding="utf-8") as f:
                snapshot = json.load(f)
        print("[score] starting", flush=True)
        comparison = stage_score(args.run, snapshot)
        _atomic_write_json(comparison_path, comparison)
        print(f"[score] wrote {comparison_path}", flush=True)
        print(f"[score] gate_verdict = {comparison['gate_verdict']['value']}", flush=True)
        # If gate is anything but pass, exit 0 anyway (the artifact carries the verdict).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
