# RERANK-01 q05/q10 Cross-Encoder Characterization

Ticket: RERANK-01
Timestamp: 2026-05-22T15:33:21Z
Run: `2026-05-19-1846-nogit`
Scope: eval/report only; no src/* edits; hermetic.

## Method

The runner consumed the DECOMP-01 pool decomposition, `candidates.jsonl`, `data/movies_clean.csv`, and localization for consistency checks. It imported only `_run_io` and the pure `build_movie_document` function from `src.retrieval.reranker`; it made no model, GPU, LLM, Ollama, network, or reranker scoring call.

## Per-arm characterization

### q05 pinned

| role | tmdb_id | title | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |
|---|---:|---|---:|---:|---:|---:|---:|---|
| target | 144204 | Thanatomorphose | 4 | 0.018819 | 0.000000 | 473 | 379 | title, genres, tagline, overview |
| false_positive | 24218 | The Bold, the Corrupt and the Beautiful | 0 | 0.077919 | 0.059100 | null | null | UNRESOLVED |
| false_positive | 43950 | Amer | 1 | 0.023060 | 0.004241 | 463 | 295 | title, genres, tagline, overview, keywords |
| false_positive | 21993 | On the Job | 2 | 0.022343 | 0.003523 | null | null | UNRESOLVED |
| false_positive | 641 | Requiem for a Dream | 3 | 0.020371 | 0.001552 | 458 | 180 | title, genres, overview, keywords |

### q05 no_llm

| role | tmdb_id | title | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |
|---|---:|---|---:|---:|---:|---:|---:|---|
| target | 144204 | Thanatomorphose | 5 | 0.018819 | 0.000000 | 473 | 379 | title, genres, tagline, overview |
| false_positive | 53404 | Love Crime | 0 | 0.050894 | 0.032075 | 367 | 161 | title, genres, tagline, overview, keywords |
| false_positive | 25394 | Posse | 1 | 0.031223 | 0.012404 | null | null | UNRESOLVED |
| false_positive | 43950 | Amer | 2 | 0.023060 | 0.004241 | 463 | 295 | title, genres, tagline, overview, keywords |
| false_positive | 8353 | Supernova | 3 | 0.020278 | 0.001459 | null | null | UNRESOLVED |
| false_positive | 33828 | Criminal Lovers | 4 | 0.019327 | 0.000508 | 580 | 367 | title, genres, tagline, overview, keywords |

### q10 pinned

| role | tmdb_id | title | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |
|---|---:|---|---:|---:|---:|---:|---:|---|
| target | 8329 | [REC] | 7 | 0.066515 | 0.000000 | 379 | 148 | title, genres, tagline, overview, keywords |
| false_positive | 159638 | Ghost Team One | 0 | 0.177426 | 0.110911 | 245 | 104 | title, genres, tagline, overview, keywords |
| false_positive | 97795 | Apartment 143 | 1 | 0.119650 | 0.053135 | 793 | 602 | title, genres, tagline, overview, keywords |
| false_positive | 50698 | Grave Encounters | 2 | 0.101083 | 0.034568 | 478 | 204 | title, genres, tagline, overview, keywords |
| false_positive | 466344 | The Houses October Built 2 | 3 | 0.089299 | 0.022784 | 511 | 347 | title, genres, tagline, overview, keywords |
| false_positive | 443319 | Phoenix Forgotten | 4 | 0.080222 | 0.013707 | 373 | 218 | title, genres, tagline, overview, keywords |
| false_positive | 207475 | The Ouija Experiment | 5 | 0.071373 | 0.004858 | 425 | 285 | title, genres, tagline, overview, keywords |
| false_positive | 470528 | The Blackwell Ghost | 6 | 0.069399 | 0.002884 | 455 | 253 | title, genres, overview, keywords |

### q10 no_llm

| role | tmdb_id | title | rerank_rank | rerank_score | score_gap_vs_target | doc_len | overview_chars | fields_present |
|---|---:|---|---:|---:|---:|---:|---:|---|
| target | 8329 | [REC] | 7 | 0.066515 | 0.000000 | 379 | 148 | title, genres, tagline, overview, keywords |
| false_positive | 159638 | Ghost Team One | 0 | 0.177426 | 0.110911 | 245 | 104 | title, genres, tagline, overview, keywords |
| false_positive | 174678 | Mr. Jones | 1 | 0.146631 | 0.080116 | 602 | 479 | title, genres, tagline, overview, keywords |
| false_positive | 97795 | Apartment 143 | 2 | 0.119650 | 0.053135 | 793 | 602 | title, genres, tagline, overview, keywords |
| false_positive | 50698 | Grave Encounters | 3 | 0.101084 | 0.034569 | 478 | 204 | title, genres, tagline, overview, keywords |
| false_positive | 466344 | The Houses October Built 2 | 4 | 0.089299 | 0.022784 | 511 | 347 | title, genres, tagline, overview, keywords |
| false_positive | 127626 | Hollow | 5 | 0.080809 | 0.014294 | 602 | 511 | title, genres, overview, keywords |
| false_positive | 470528 | The Blackwell Ghost | 6 | 0.069399 | 0.002884 | 455 | 253 | title, genres, overview, keywords |

## Stage-disagreement summary

| qid | arm | attribution | reranker_demoted_well_retrieved_target | secondary |
|---|---|---|---:|---|
| q05 | pinned | rrf_recall | False | final_blend |
| q05 | no_llm | reranker | True | final_blend |
| q10 | pinned | rrf_recall | False | final_blend |
| q10 | no_llm | reranker | True | none |

## Failure mode

Classification: `inconclusive`

Evidence:
- unresolved required document text: qid=q05 role=false_positive tmdb_id=24218 title='The Bold, the Corrupt and the Beautiful' rerank_rank=0 reason=missing_from_candidates_and_movies_clean
- unresolved required document text: qid=q05 role=false_positive tmdb_id=21993 title='On the Job' rerank_rank=2 reason=missing_from_candidates_and_movies_clean
- unresolved required document text: qid=q05 role=false_positive tmdb_id=25394 title='Posse' rerank_rank=1 reason=missing_from_candidates_and_movies_clean
- unresolved required document text: qid=q05 role=false_positive tmdb_id=8353 title='Supernova' rerank_rank=3 reason=movies_clean_title_mismatch: expected='Supernova' actual='Limite'
- q05 pinned: attribution=rrf_recall, rrf_rank=66, rerank_rank=4, final_rank=54.
- q05 no_llm: attribution=reranker, rrf_rank=1, rerank_rank=5, final_rank=10.
- q10 pinned: attribution=rrf_recall, rrf_rank=53, rerank_rank=7, final_rank=12.
- q10 no_llm: attribution=reranker, rrf_rank=10, rerank_rank=7, final_rank=7.

Rejected competing classifications:
- `document_text_degenerate`: Cannot distinguish true degenerate target text from missing allowed-source coverage for false positives.
- `metadata_genre_mismatch`: Cannot compare metadata composition for every false positive above the target.
- `model_capability_limit_hypothesis`: Cannot isolate model behavior until exact false-positive document text is reconstructed.
- `stage_disagreement_only`: The no_llm arms still show reranker-stage demotion, but the text-pair evidence is incomplete.

## Recommended RERANK-02 scope

RERANK-02 should first repair or snapshot the missing allowed document sources for the unresolved false positives, then run a model-backed comparison on the same q05/q10 no_llm pairs against an alternative cross-encoder. Keep pinned arms as RRF/final-blend context, not as the primary reranker signal.

## Phase 5 gate

Phase 5 remains BLOCKED.
