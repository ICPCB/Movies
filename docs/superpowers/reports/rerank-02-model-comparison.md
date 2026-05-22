# RERANK-02 Model Comparison

- Ticket: RERANK-02
- Timestamp: 2026-05-22T17:40:24Z
- Run: 2026-05-19-1846-nogit
- Scope: q05/q10, pinned/no_llm, eval-only; no src edits; no LLM calls.

## Phase A - Lexical Content Gap

#### q05 / pinned

rerank_query: `a body horror story where ambition mutates into something intimate and disgusting`

| role | title | rank0 | genres | keywords | overview | combined | doc | combined_jaccard |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target | Thanatomorphose | 4 | 1 | 0 | 2 | 3 | 3 | 0.046154 |
| false_positive | The Bold, the Corrupt and the Beautiful | 0 | 0 | 0 | 3 | 3 | 3 | 0.044118 |
| false_positive | Amer | 1 | 1 | 0 | 3 | 4 | 4 | 0.070175 |
| false_positive | On the Job | 2 | 0 | 0 | 2 | 2 | 2 | 0.025316 |
| false_positive | Requiem for a Dream | 3 | 0 | 0 | 4 | 4 | 4 | 0.048193 |

content_gap: `content_gap_absent`; signal=False; min_overlap_count_margin=-1.

#### q05 / no_llm

rerank_query: `a body horror story where ambition mutates into something intimate and disgusting`

| role | title | rank0 | genres | keywords | overview | combined | doc | combined_jaccard |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target | Thanatomorphose | 5 | 1 | 0 | 2 | 3 | 3 | 0.046154 |
| false_positive | Love Crime | 0 | 0 | 1 | 2 | 3 | 3 | 0.065217 |
| false_positive | Posse | 1 | 0 | 1 | 2 | 3 | 3 | 0.100000 |
| false_positive | Amer | 2 | 1 | 0 | 3 | 4 | 4 | 0.070175 |
| false_positive | Supernova | 3 | 1 | 0 | 5 | 6 | 7 | 0.100000 |
| false_positive | Criminal Lovers | 4 | 1 | 1 | 5 | 6 | 6 | 0.086957 |

content_gap: `content_gap_absent`; signal=False; min_overlap_count_margin=0.

#### q10 / pinned

rerank_query: `found footage friends chased through a haunted apartment maze`

| role | title | rank0 | genres | keywords | overview | combined | doc | combined_jaccard |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target | [REC] | 7 | 0 | 2 | 2 | 4 | 4 | 0.100000 |
| false_positive | Ghost Team One | 0 | 0 | 2 | 2 | 4 | 4 | 0.129032 |
| false_positive | Apartment 143 | 1 | 0 | 3 | 2 | 4 | 4 | 0.045977 |
| false_positive | Grave Encounters | 2 | 0 | 2 | 2 | 4 | 4 | 0.088889 |
| false_positive | The Houses October Built 2 | 3 | 0 | 4 | 3 | 5 | 5 | 0.083333 |
| false_positive | Phoenix Forgotten | 4 | 0 | 2 | 1 | 2 | 2 | 0.047619 |
| false_positive | The Ouija Experiment | 5 | 0 | 2 | 2 | 4 | 4 | 0.080000 |
| false_positive | The Blackwell Ghost | 6 | 0 | 3 | 3 | 4 | 4 | 0.080000 |

content_gap: `content_gap_absent`; signal=False; min_overlap_count_margin=-2.

#### q10 / no_llm

rerank_query: `found footage friends chased through a haunted apartment maze`

| role | title | rank0 | genres | keywords | overview | combined | doc | combined_jaccard |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target | [REC] | 7 | 0 | 2 | 2 | 4 | 4 | 0.100000 |
| false_positive | Ghost Team One | 0 | 0 | 2 | 2 | 4 | 4 | 0.129032 |
| false_positive | Mr. Jones | 1 | 0 | 2 | 2 | 3 | 3 | 0.045455 |
| false_positive | Apartment 143 | 2 | 0 | 3 | 2 | 4 | 4 | 0.045977 |
| false_positive | Grave Encounters | 3 | 0 | 2 | 2 | 4 | 4 | 0.088889 |
| false_positive | The Houses October Built 2 | 4 | 0 | 4 | 3 | 5 | 5 | 0.083333 |
| false_positive | Hollow | 5 | 0 | 2 | 3 | 5 | 5 | 0.064935 |
| false_positive | The Blackwell Ghost | 6 | 0 | 3 | 3 | 4 | 4 | 0.080000 |

content_gap: `content_gap_absent`; signal=False; min_overlap_count_margin=-1.

## Phase B - Alternative Cross-Encoder Ranks

| model | qid | arm | baseline rank0 | model rank0 | rescued top5 | target score |
|---|---|---|---:|---:|---|---:|
| Alibaba-NLP/gte-multilingual-reranker-base | q05 | pinned | 4 | 10 | False | 0.802734 |
| Alibaba-NLP/gte-multilingual-reranker-base | q05 | no_llm | 5 | 7 | False | 0.805664 |
| Alibaba-NLP/gte-multilingual-reranker-base | q10 | pinned | 7 | 2 | True | 0.947754 |
| Alibaba-NLP/gte-multilingual-reranker-base | q10 | no_llm | 7 | 1 | True | 0.947754 |
| cross-encoder/ms-marco-MiniLM-L6-v2 | q05 | pinned | 4 | 1 | False | -5.265625 |
| cross-encoder/ms-marco-MiniLM-L6-v2 | q05 | no_llm | 5 | 5 | False | -5.265625 |
| cross-encoder/ms-marco-MiniLM-L6-v2 | q10 | pinned | 7 | 3 | True | -2.867188 |
| cross-encoder/ms-marco-MiniLM-L6-v2 | q10 | no_llm | 7 | 3 | True | -2.865234 |

## Cost, Time, VRAM

| item | value |
|---|---|
| expected pair count | 268 |
| expected VRAM budget | 8.0 GB |
| actual status | complete |
| actual elapsed seconds | 30.32 |
| CUDA device | NVIDIA GeForce RTX 4070 Laptop GPU |
| CUDA total memory GB | 7.9956 |
| Alibaba-NLP/gte-multilingual-reranker-base status | success |
| Alibaba-NLP/gte-multilingual-reranker-base revision | 8215cf04918ba6f7b6a62bb44238ce2953d8831c |
| Alibaba-NLP/gte-multilingual-reranker-base local snapshot GB | 0.5858 |
| Alibaba-NLP/gte-multilingual-reranker-base peak allocated GB | 0.6292 |
| Alibaba-NLP/gte-multilingual-reranker-base peak reserved GB | 0.6621 |
| Alibaba-NLP/gte-multilingual-reranker-base tokenizer input | list[tuple[query, document]] |
| Alibaba-NLP/gte-multilingual-reranker-base position ids repaired | True |
| cross-encoder/ms-marco-MiniLM-L6-v2 status | success |
| cross-encoder/ms-marco-MiniLM-L6-v2 revision | c5ee24cb16019beea0893ab7796b1df96625c6b8 |
| cross-encoder/ms-marco-MiniLM-L6-v2 local snapshot GB | 0.2763 |
| cross-encoder/ms-marco-MiniLM-L6-v2 peak allocated GB | 0.1033 |
| cross-encoder/ms-marco-MiniLM-L6-v2 peak reserved GB | 0.127 |
| cross-encoder/ms-marco-MiniLM-L6-v2 tokenizer input | list[tuple[query, document]] |
| cross-encoder/ms-marco-MiniLM-L6-v2 position ids repaired | False |

## Decision

`model_capability_confirmed`

- Phase A q05/no_llm: content_gap=False target_combined_overlap=3 min_false_positive_margin=0 false_positives=5
- Phase A q10/no_llm: content_gap=False target_combined_overlap=4 min_false_positive_margin=-1 false_positives=7
- Phase B Alibaba-NLP/gte-multilingual-reranker-base rescued q10/no_llm from baseline rank 7 to rank 1 (zero-based)

Rejected alternatives are reflected by the Phase A content-gap rows and Phase B rank rows above. The decision is rank-based because model score scales are not comparable across cross-encoders.

## What This Means For Phase 5

A `model_capability_confirmed` result does not unblock Phase 5. A model swap would first need a separate full gold/silver-set rerank regression evaluation proving it does not regress other queries.

## Phase 5 Gate

Phase 5 remains BLOCKED.
