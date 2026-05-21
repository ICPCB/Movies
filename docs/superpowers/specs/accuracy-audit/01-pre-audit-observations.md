---
title: Pre-audit observations
parent: README.md
section: 3
---

# 3. Pre-audit observations

[Index](README.md) · Prev: [Purpose & goals](00-purpose-goals-and-rules.md) · Next: [Success metrics](02-success-metrics.md)

These were surfaced during planning. They influence the eval harness's data identity
and are flagged here so the harness uses them correctly from day one. They become
formal audit findings in Phase 3, not Phase 1 fixes.

## 3.1 TMDB id is available but `get_movie_key()` ignores it

- `01.clean_data.py:152` keeps `id` as the numeric TMDB id from the source CSV.
- `02. Embed_BGEM3.py:145` stores it in ChromaDB metadata as `tmdb_id` and as the
  document id prefix `tmdb_{id}`.
- `src/retrieval/semantic.py:78-90` parses the document id and returns the real TMDB id
  as the `id` field in result dicts.
- `src/utils/dedup.py:75-97` only checks `movie_id` (which never exists), then falls
  through to title+year. Its docstring (lines 8–14) claims the CSV has no id column —
  that is stale.

**Implication for the eval harness:** candidate identity is keyed on `tmdb_id` (int),
with `movie_key` (the current `get_movie_key()` output) stored as a secondary field.
Any case where two candidates share `tmdb_id` but have different `movie_key`s becomes
an automatic dedup-bug signal feeding the Phase 3 audit.

## 3.2 `docs/ARCHITECTURE.md` is stale on several config values

The architecture doc still references the pre-calibration values:

| Constant | Doc claims | Actual in `src/config.py` |
|---|---|---|
| `CANDIDATE_POOL` | 300 | 1500 |
| `RERANK_POOL` | 80 | 800 |
| `RRF_K` | 60 | 15 |
| `RERANK_VOTE_COUNT_WEIGHT` | 0.20 | 0.08 |
| `RERANK_UPSTREAM_WEIGHT` | 0.12 | 0.20 |
| `RERANK_SOURCE_AGREEMENT_BONUS` | 0.05 | 0.10 |

Each current value has reasoning attached in `src/config.py` comments — these were
deliberate calibrations to handle queries like "palindromic timeline" (Memento, Tenet).
**The audit must use the actual config values, not the doc.** The doc itself is a
Phase 3 finding.

## 3.3 `AGENTS.md` is staged-then-deleted in the working tree

`git status` shows `AD AGENTS.md`. The architecture doc references project rules in
`AGENTS.md` but the file is not present locally. This is a Phase 3 documentation
hygiene finding; the spec does not depend on `AGENTS.md`.

---

Next: [02 — Success metrics](02-success-metrics.md)
