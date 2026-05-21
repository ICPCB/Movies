"""Debug timing helpers, gated on src.config.DEBUG_RETRIEVAL.

The context manager is silent when the flag is False, so wrapping every
pipeline stage with `with timed(...)` adds no user-visible noise in
normal operation. When the flag is True, each stage prints elapsed
milliseconds so a maintainer can see where a slow query spends its time
without changing any pipeline code.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from src.config import DEBUG_RETRIEVAL


@contextmanager
def timed(stage: str, mode: str = ""):
    """Print elapsed ms for `stage` (optionally tagged with `mode`)
    when DEBUG_RETRIEVAL is True. No-op otherwise."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        if DEBUG_RETRIEVAL:
            ms = (time.perf_counter() - t0) * 1000
            tag = f"{mode} " if mode else ""
            print(f"[debug] {tag}{stage}: {ms:.1f} ms")
