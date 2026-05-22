# RERANK-01 q05/q10 Cross-Encoder Characterization

Ticket: RERANK-01B
Timestamp: 2026-05-22T16:20:46Z
Run: `2026-05-19-1846-nogit`
Scope: eval/report only; no src/* edits; hermetic.

## Method

The runner consumed the DECOMP-01 pool decomposition, the RERANK-01A text snapshot keyed by `(qid, arm, movie_key)`, and localization for consistency checks. It consumed snapshot `document_text` verbatim, kept reranker scores and ranks from DECOMP-01, imported no `src/*` code, and made no model, GPU, LLM, Ollama, network, or reranker scoring call.

## Completeness

- analysis_complete: `True`
- unresolved_text_members: `0`

## Per-arm characterization

### q05 pinned

| role | tmdb_id | title | source_stage | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| target | 144204 | Thanatomorphose | semantic | 4 | 0.018819 | 0.000000 | 473 | 379 | title, release_date, year, genres, tagline, overview |
| false_positive | 24218 | The Bold, the Corrupt and the Beautiful | bm25_only | 0 | 0.077919 | 0.059100 | 643 | 336 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 43950 | Amer | semantic+bm25 | 1 | 0.023060 | 0.004241 | 463 | 295 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 21993 | On the Job | bm25_only | 2 | 0.022343 | 0.003523 | 615 | 434 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 641 | Requiem for a Dream | semantic+bm25 | 3 | 0.020371 | 0.001552 | 458 | 180 | title, release_date, year, genres, overview, keywords |

### q05 no_llm

| role | tmdb_id | title | source_stage | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| target | 144204 | Thanatomorphose | semantic | 5 | 0.018819 | 0.000000 | 473 | 379 | title, release_date, year, genres, tagline, overview |
| false_positive | 53404 | Love Crime | semantic+bm25 | 0 | 0.050894 | 0.032075 | 367 | 161 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 25394 | Posse | bm25_only | 1 | 0.031223 | 0.012404 | 309 | 111 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 43950 | Amer | semantic+bm25 | 2 | 0.023060 | 0.004241 | 463 | 295 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 8353 | Supernova | bm25_only | 3 | 0.020278 | 0.001459 | 518 | 303 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 33828 | Criminal Lovers | semantic+bm25 | 4 | 0.019327 | 0.000508 | 580 | 367 | title, release_date, year, genres, tagline, overview, keywords |

### q10 pinned

| role | tmdb_id | title | source_stage | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| target | 8329 | [REC] | semantic+bm25 | 7 | 0.066515 | 0.000000 | 379 | 148 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 159638 | Ghost Team One | semantic+bm25 | 0 | 0.177426 | 0.110911 | 245 | 104 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 97795 | Apartment 143 | semantic+bm25 | 1 | 0.119650 | 0.053135 | 793 | 602 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 50698 | Grave Encounters | semantic+bm25 | 2 | 0.101083 | 0.034568 | 478 | 204 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 466344 | The Houses October Built 2 | semantic+bm25 | 3 | 0.089299 | 0.022784 | 498 | 347 | title, release_date, year, genres, overview, keywords |
| false_positive | 443319 | Phoenix Forgotten | semantic+bm25 | 4 | 0.080222 | 0.013707 | 373 | 218 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 207475 | The Ouija Experiment | semantic+bm25 | 5 | 0.071373 | 0.004858 | 425 | 285 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 470528 | The Blackwell Ghost | semantic+bm25 | 6 | 0.069399 | 0.002884 | 455 | 253 | title, release_date, year, genres, overview, keywords |

### q10 no_llm

| role | tmdb_id | title | source_stage | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| target | 8329 | [REC] | semantic+bm25 | 7 | 0.066515 | 0.000000 | 379 | 148 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 159638 | Ghost Team One | semantic+bm25 | 0 | 0.177426 | 0.110911 | 245 | 104 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 174678 | Mr. Jones | semantic+bm25 | 1 | 0.146631 | 0.080116 | 602 | 479 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 97795 | Apartment 143 | semantic+bm25 | 2 | 0.119650 | 0.053135 | 793 | 602 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 50698 | Grave Encounters | semantic+bm25 | 3 | 0.101084 | 0.034569 | 478 | 204 | title, release_date, year, genres, tagline, overview, keywords |
| false_positive | 466344 | The Houses October Built 2 | semantic+bm25 | 4 | 0.089299 | 0.022784 | 498 | 347 | title, release_date, year, genres, overview, keywords |
| false_positive | 127626 | Hollow | semantic+bm25 | 5 | 0.080809 | 0.014294 | 602 | 511 | title, release_date, year, genres, overview, keywords |
| false_positive | 470528 | The Blackwell Ghost | semantic+bm25 | 6 | 0.069399 | 0.002884 | 455 | 253 | title, release_date, year, genres, overview, keywords |

## Stage-disagreement summary

| qid | arm | attribution | reranker_demoted_well_retrieved_target | secondary |
|---|---|---|---:|---|
| q05 | pinned | rrf_recall | False | final_blend |
| q05 | no_llm | reranker | True | final_blend |
| q10 | pinned | rrf_recall | False | final_blend |
| q10 | no_llm | reranker | True | none |

## Failure mode

Classification: `model_capability_limit_hypothesis`

Evidence:
- q05 no_llm: target RRF rank 1 but rerank rank 5 with rerank_score 0.018819; 5 false positives outrank it.
- q10 no_llm: target RRF rank 10 but rerank rank 7 with rerank_score 0.066515; 7 false positives outrank it.
- q05: target title/domain signal is atypical: 'Thanatomorphose'.
- q10: target title/domain signal is atypical: '[REC]'.
- q05 pinned: attribution=rrf_recall, rrf_rank=66, rerank_rank=4, final_rank=54.
- q05 no_llm: attribution=reranker, rrf_rank=1, rerank_rank=5, final_rank=10.
- q10 pinned: attribution=rrf_recall, rrf_rank=53, rerank_rank=7, final_rank=12.
- q10 no_llm: attribution=reranker, rrf_rank=10, rerank_rank=7, final_rank=7.

Rejected competing classifications:
- `document_text_degenerate`: Target documents are overview-bearing.
- `stage_disagreement_only`: The no_llm arms contain reranker demotion.

## Recommended RERANK-02 scope

RERANK-02 should compare bge-reranker-v2-m3 with an alternative cross-encoder on the exact reconstructed q05/q10 no_llm pairs.

## Phase 5 gate

Phase 5 remains BLOCKED.
