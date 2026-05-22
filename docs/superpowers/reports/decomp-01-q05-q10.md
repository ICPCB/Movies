# DECOMP-01 q05/q10 Pool Decomposition

Timestamp: 2026-05-22T14:48:22Z
Run: `2026-05-19-1846-nogit`
Ticket: DECOMP-01
Scope: eval/report only; no `src/*` edits.

## Method

The runner reused recorded HY-STAB deterministic arm queries for `pinned` and `no_llm`, reran the current 50-candidate baseline, then reran an extended 67-candidate rerank pool for q05 and q10.
Each extended pool row records semantic, BM25, RRF, rerank, final scores, and the final-blend inputs, weights, and contributions.

## Cost And Time

- Expected cost: $0.00.
- Expected runtime budget: 900s; expected total rerank pairs: 468.
- Actual cost: $0.00; actual runtime: 40.881s.
- Max observed VRAM: 5320 MiB (budget 7800 MiB).

## Policy Results

| Policy | All Targets Rescued | Max Non-target Changes | Max Rank-change Magnitude | Safe |
|---|---:|---:|---:|---:|
| `rerank_cutoff_67_current_blend` | False | 41 | 289 | False |
| `final_blend_rerank_only_standard_cutoff` | False | 48 | 682 | False |
| `cutoff_67_plus_final_blend_rerank_only` | False | 50 | 825 | False |
| `final_blend_half_priors_standard_cutoff` | False | 36 | 76 | False |
| `cutoff_67_plus_final_blend_half_priors` | False | 47 | 345 | False |
| `final_blend_remove_quality_prior_standard_cutoff` | False | 41 | 124 | False |
| `cutoff_67_plus_final_blend_remove_quality_prior` | False | 42 | 295 | False |
| `final_blend_remove_upstream_prior_standard_cutoff` | False | 48 | 400 | False |
| `cutoff_67_plus_final_blend_remove_upstream_prior` | False | 49 | 576 | False |
| `final_blend_remove_source_agreement_standard_cutoff` | False | 45 | 536 | False |
| `cutoff_67_plus_final_blend_remove_source_agreement` | False | 47 | 543 | False |

## Phase 5 Gate

Phase 5 remains blocked.
No evaluated bounded rerank-cutoff or final-blend reweight policy rescued q05 and q10 across both pinned and no_llm deterministic arms.

## Decision

safe_localized_fix_ruled_out
