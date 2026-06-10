"""End-to-end latency benchmark for the CineMatch API (ULTRAPLAN phase 5).

Measures perceived /api/recommend latency against a RUNNING server (default
http://127.0.0.1:8000), so models stay in one process and the numbers reflect
what the web UI actually experiences. Uncached and cache-hit requests are
reported separately with p50/p95.

Usage:
    python eval/scripts/latency_benchmark.py [--base-url URL] [--out PATH]

The script never writes search history (log_history=false) and touches only
its output artifact. Stdlib only — runs under any Python.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


QUERIES: list[dict] = [
    {"free_text": "a slow burn heist thriller in winter", "mode": "content"},
    {"free_text": "feel-good comedy about unlikely friends", "mode": "content"},
    {"free_text": "mind-bending science fiction about memory", "mode": "content"},
    {"free_text": "warm heartwarming hopeful uplifting", "mode": "mood"},
    {"free_text": "epic inspiring underdog sports story", "mode": "hybrid"},
    {"free_text": "romantic drama set in paris", "mode": "content"},
    {"free_text": "lighthearted funny feel-good family adventure", "mode": "mood"},
    {"free_text": "tense submarine cold war standoff", "mode": "content"},
]


def post_recommend(base_url: str, body: dict, timeout: float) -> tuple[float, dict]:
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/recommend",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return elapsed_ms, data


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def summarize(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "p50_ms": round(statistics.median(values), 1),
        "p95_ms": round(percentile(values, 0.95), 1),
        "min_ms": round(min(values), 1),
        "max_ms": round(max(values), 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--page-size", type=int, default=18)
    parser.add_argument(
        "--out",
        default=None,
        help="Artifact path; default eval/runs/<date>-latency-nogit/latency.json",
    )
    args = parser.parse_args()

    try:
        with urllib.request.urlopen(f"{args.base_url}/api/health", timeout=10) as resp:
            health = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as cause:
        print(f"ERROR: API not reachable at {args.base_url}: {cause}", file=sys.stderr)
        return 1

    samples = []
    uncached: list[float] = []
    cached: list[float] = []
    for query in QUERIES:
        body = {**query, "page_size": args.page_size, "log_history": False}
        for attempt in ("first", "repeat"):
            elapsed_ms, data = post_recommend(args.base_url, body, args.timeout)
            bucket = cached if data.get("cache_hit") else uncached
            bucket.append(elapsed_ms)
            samples.append(
                {
                    "query": query["free_text"],
                    "mode": query["mode"],
                    "attempt": attempt,
                    "cache_hit": bool(data.get("cache_hit")),
                    "elapsed_ms": round(elapsed_ms, 1),
                    "total_pool": data.get("total_pool"),
                }
            )
            print(
                f"[{query['mode']:>7}] {elapsed_ms:8.1f} ms "
                f"(cache_hit={data.get('cache_hit')}) {query['free_text']!r}"
            )

    report = {
        "base_url": args.base_url,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "model_warm_at_start": bool(health.get("model_warm")),
        "page_size": args.page_size,
        "summary": {
            "uncached": summarize(uncached),
            "cache_hit": summarize(cached),
        },
        "samples": samples,
    }

    out_path = (
        Path(args.out)
        if args.out
        else Path("eval/runs")
        / f"{datetime.now():%Y-%m-%d}-latency-nogit"
        / "latency.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {out_path}")
    print(f"uncached: {report['summary']['uncached']}")
    print(f"cache_hit: {report['summary']['cache_hit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
