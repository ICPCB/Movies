---
title: Reference
parent: README.md
section: 19
---

# 19. Reference

[Index](README.md) · Prev: [Validation, done, risks](10-validation-done-risks.md)

- `docs/ARCHITECTURE.md` — current architecture reference (note: stale on config values per [01 §3.2](01-pre-audit-observations.md#32-docsarchitecturemd-is-stale-on-several-config-values); treat `src/config.py` as authoritative).
- `src/config.py` — authoritative configuration constants.
- `scripts/quality_smoke_test.py` — existing smoke test (insufficient as eval; see [02 — Success metrics](02-success-metrics.md)).
- `src/utils/dedup.py` — current dedup logic (see [01 §3.1](01-pre-audit-observations.md#31-tmdb-id-is-available-but-get_movie_key-ignores-it) for known stale assumption).
- `src/retrieval/query_processor.py` — `normalize_query()` and `expand_retrieval_query()`; deterministic English query expansion with hardcoded domain triggers.
- `02. Embed_BGEM3.py` — ChromaDB ingestion script (read-only audit scope).
- `01.clean_data.py` — TMDB → cleaned CSV pipeline (read-only audit scope).
