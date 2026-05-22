# RERANK-01A Text Source Repair

Ticket: RERANK-01A
Timestamp: 2026-05-22T16:09:13Z
Run: `2026-05-19-1846-nogit`
Scope: hermetic eval/report only; no src/* edits; no model, embedder, GPU, Ollama, or network.

## Root cause

The pipeline uses two id semantics. Semantic candidates (`src/retrieval/semantic.py:74-108`, field recipe `semantic.py:89-106`) carry real TMDB ids from Chroma doc ids `tmdb_{id}` and Chroma metadata text. BM25-only candidates (`src/retrieval/bm25.py:163-187`, id stamp `bm25.py:168-169`, field recipe `bm25.py:169-185`) carry `int(idx)`, the 0-based `movies_clean.csv` row index, and CSV-row text. RRF fusion (`src/retrieval/fusion.py:50,65-73`) gives the semantic dict precedence, so a candidate found by both stages keeps semantic id and text semantics.

## tmdb 8353 reconciliation

DECOMP `8353` as a BM25-only id means `movies_clean.csv` row 8353, title `Supernova`, CSV TMDB id `10384`.
Real TMDB id `8353` means Chroma id `tmdb_8353`, title `Limite`. The earlier Supernova/Limite mismatch is therefore explained by the DECOMP label, not by a safe text source for BM25-only rows.

## Coverage

| qid | arm | members | resolved | unresolved | complete |
|---|---|---:|---:|---:|---|
| q05 | pinned | 67 | 67 | 0 | True |
| q05 | no_llm | 67 | 67 | 0 | True |
| q10 | pinned | 67 | 67 | 0 | True |
| q10 | no_llm | 67 | 67 | 0 | True |

## Source-stage breakdown

| source_stage | members |
|---|---:|
| bm25_only | 64 |
| semantic | 69 |
| semantic+bm25 | 135 |

| resolved_from | members |
|---|---:|
| chroma:movies | 204 |
| movies_clean.csv:iloc | 64 |

## Snapshot

Snapshot: `eval/runs/2026-05-19-1846-nogit/analysis/rerank_failure/q05_q10_text_snapshot.json`
Schema: each resolved member carries `movie_key`, `decomp_id`, `source_stage`, `id_semantics`, `resolved_from`, the reconstructed text fields, `document_text`, and `document_fields` for the RERANK-01 re-run to consume directly.

## Phase 5 gate

Phase 5 remains BLOCKED.
