# Q05-01 — Residual q05 Investigation Report

Timestamp: 2026-06-07 (updated)
Branch: `main`
Ticket: Q05-01
Status: COMPLETE (updated with Step A-B findings)

---

## 1. Query summary

- **Query (q05):** "a body horror story where ambition mutates into
  something intimate and disgusting"
- **Gold target:** Thanatomorphose (2012), tmdb_id 144204, grade 3
  (silver, llama3.2 pregrade, confidence high)
- **Label rationale:** "Rotting from the inside out" — a genuine
  body-horror film about a woman's body inexplicably decomposing.
  The label is defensible (QL-01 confirmed query/label/expansion sound).
- **User intent:** find a body-horror film where ambition transforms
  into something visceral and grotesque. Thanatomorphose is a strong
  semantic match.

---

## 2. Evidence table

| Analysis | q05-relevant finding |
|---|---|
| **QL-01** | Classified as `reranker_blend_issue_later_eval`: genuine pipeline defect, query/label/expansion all sound. Hybrid expansion is faithful. |
| **DECOMP-01** | Pinned arm: RRF rank 66, rerank rank 4, final rank 54 (50 candidates leapfrog). No_llm arm: RRF rank 1, rerank rank 5, final rank 10 (7 candidates leapfrog). No safe localized cutoff/reweight policy rescues both arms. |
| **RERANK-01B** | Pinned: `retrieved_dropped_before_rerank_pool` (RRF 66 > pool size 50). No_llm: clean reranker demotion (rerank rank 5, outside top-5 at 0-based indexing). |
| **RERANK-02** | Alibaba worsens q05: pinned rank 4→10, no_llm rank 5→7. MiniLM improves pinned (4→1) but no_llm stays at 5 (still outside top-5). Neither alt model rescues q05 across both arms. |
| **Dep #5** | Alt reranker (Alibaba) not viable as global replacement — regresses 7/20 queries. q05 not rescued by the alt model. |
| **Dep #7** | Blend-weight simulation: q05 advanced/hybrid = `original_hit: false, new_hit: false, change: unchanged` across all 40 tested weight sets (including the 12 viable ones). Weight change does not affect q05. **Caveat:** simulation uses Dep #4 pool snapshot where q05 target is not in `baseline_top` (top-15 reranked), so the simulation structurally cannot rescue q05 regardless of weights. |
| **Step A** | RERANK_TOP_K=70 simulation: pool size increase alone does not fix q05. source_agreement penalty is the dominant factor, not pool size. |
| **Step B** | Using DECOMP-01 extended pool with post-Phase 5-A weights (upstream=0.12): agreement=0.02 → no_llm rank 2 (**HIT**); agreement=0.00 → no_llm rank 0. Pinned arm unsalvageable by agreement alone (rank 40-46). BM25 never finds target (keywords EMPTY, zero lexical overlap). |

---

## 3. Stage-by-stage breakdown

### Pipeline stages

```
Retrieval (semantic + BM25, 1500 each)
  → RRF fusion (ranked list)
    → Rerank pool (top 50 by RRF score)
      → Cross-encoder reranking (BAAI/bge-reranker-v2-m3)
        → Final blend (rerank_score + vote + upstream + agreement)
          → Top-5 output
```

### Pinned arm (LLM expansion fixed to a recorded good expansion)

| Stage | Rank | Score | Note |
|---|---|---|---|
| RRF fusion | **66** | — | Target retrieved but at rank 66 — below the rerank pool cutoff of 50 |
| Rerank pool | excluded | — | Rank 66 > RERANK_TOP_K (50), so the target is never presented to the cross-encoder |
| Rerank scoring | 4 (extended pool) | 0.0188 | When artificially included in a 67-candidate extended pool, the cross-encoder ranks it 4th — a strong rerank score |
| Final blend | **54** (extended pool) | 0.1139 | 50 candidates leapfrog it via upstream_prior and source_agreement bonuses |

**Pinned arm diagnosis:** The target is lost at the RRF fusion stage. It
ranks 66th in RRF (out of range of the 50-candidate rerank pool), so the
cross-encoder never sees it. The LLM expansion retrieves many
thematically adjacent horror films that crowd out the target in the RRF
ranking. When the extended pool is used (DECOMP-01), the cross-encoder
correctly identifies the target (rank 4), but the final blend formula
demotes it to rank 54 because it has `source_agreement = 0.0` (retrieved
by only one stage) and a low `upstream_prior` (0.282 vs competitors at
0.8–1.0).

### No_llm arm (raw query, no LLM expansion)

| Stage | Rank | Score | Note |
|---|---|---|---|
| RRF fusion | **1** | — | Target is the top RRF candidate |
| Rerank pool | in pool | — | Rank 1 is well within the top-50 pool |
| Rerank scoring | **5** | 0.0188 | Cross-encoder demotes it from rank 1 to rank 5 (0-based) — just outside top-5 |
| Final blend | **10** | 0.2551 | 7 candidates leapfrog it; despite high upstream_prior (0.978), source_agreement = 0.0 costs it |

**No_llm arm diagnosis:** The target enters the rerank pool at rank 1
(best possible RRF position), but the cross-encoder demotes it to rank 5
(0-based). Five other candidates receive higher rerank_scores. In the
final blend, despite having the highest upstream_prior (0.978), the
target has `source_agreement = 0.0` (it was retrieved by only one
retrieval method). Meanwhile, 7 competitors that have
`source_agreement = 1.0` (retrieved by both semantic and BM25) each get
a +0.10 bonus, pushing them ahead. The target falls to final rank 10.

---

## 4. Root cause classification

**Category (revised): `blend_formula_penalty`** — the
`source_agreement` bonus in the final blend penalizes the target
relative to competitors that BM25 also retrieves.

### Original classification (pre-Step B): `reranker_architecture_issue`

The original analysis (pre-Phase 5-A, upstream=0.20) concluded that the
cross-encoder was the sole bottleneck. Step B invalidates this: with
upstream=0.12 (post Phase 5-A), reducing `RERANK_SOURCE_AGREEMENT_BONUS`
from 0.10 to 0.02 moves q05/no_llm from rank 14 to rank 2 (HIT).

The cross-encoder still demotes the target from rerank rank 1 (RRF) to
rerank rank 5 (0-based), which is a genuine limitation. But the target's
rerank_score (0.0188) is competitive enough to land in the top-5 when
the +0.10 source_agreement bonus doesn't inflate competitors.

### Revised justification

The bottleneck is the interaction between two factors:

1. **BM25 blindspot:** Thanatomorphose has an EMPTY `keywords` field and
   no lexical overlap with query terms ("ambition", "mutates",
   "intimate", "disgusting"). BM25 never retrieves it, so
   `source_agreement = 0.0`. Meanwhile, competitors like Color Out of
   Space, The Beast Within, and Bad Biology are found by both semantic
   and BM25, giving them `source_agreement = 1.0`.

2. **Agreement bonus amplification:** At `RERANK_SOURCE_AGREEMENT_BONUS
   = 0.10`, every competitor with sa=1.0 gets a +0.10 lift. This is
   larger than the target's rerank_score advantage over many competitors,
   causing 7+ candidates to leapfrog it in the final blend.

### Step B simulation results (DECOMP-01 pool, upstream=0.12)

| Pool | ag=0.10 | ag=0.05 | ag=0.02 | ag=0.00 |
|---|---|---|---|---|
| no_llm/standard(50) | rank 14 MISS | rank 6 MISS | rank 2 **HIT** | rank 0 **HIT** |
| no_llm/extended(67) | rank 20 MISS | rank 7 MISS | rank 2 **HIT** | rank 0 **HIT** |
| pinned/standard(50) | not in pool | not in pool | not in pool | not in pool |
| pinned/extended(67) | rank 46 MISS | rank 46 MISS | rank 46 MISS | rank 40 MISS |

### Dep #7 simulation caveat

Dep #7 reported `new_hit: false` for q05 at all weight sets including
agreement=0.02. This is because the Dep #4 pool snapshot captures only
the top-15 baseline reranked entries per query, and q05's target is not
in that top-15 for advanced/hybrid modes. The simulation structurally
cannot rescue q05 regardless of weights. The DECOMP-01 analysis (which
includes the full pool) is the correct data source for q05 blend
simulations.

### Cross-encoder contribution (still relevant, not primary)

The cross-encoder does demote the target from RRF rank 1 to rerank
rank 5 (0-based) in the no_llm arm. Three tested cross-encoders all
fail to place it in the top-5 by rerank score alone:

- **BAAI/bge-reranker-v2-m3** (baseline): rank 5
- **Alibaba-NLP/gte-multilingual-reranker-base**: rank 7 (worse)
- **cross-encoder/ms-marco-MiniLM-L6-v2**: rank 5 (unchanged)

However, with the agreement penalty removed (ag=0.02), the target's
combined rerank_score + upstream_prior is sufficient to reach rank 2.
The cross-encoder limitation is a contributing factor but not the
binding constraint.

### Why not the other categories

- **query_expansion_issue:** no_llm arm uses raw query and the fix
  works there. Expansion is not the problem.
- **retrieval_candidate_quality:** Target enters at RRF rank 1 (no_llm).
- **reranker_architecture_issue:** Partially true (rerank rank 5), but
  agreement=0.02 rescues the target despite the reranker demotion.
  The reranker is a contributing factor, not the binding constraint.
- **document_text_mismatch:** Overview is semantically rich and relevant.
- **label_candidate_ceiling:** Target is in pool and scored.

---

## 5. Recommended next steps

### Step A result: RERANK_TOP_K=70 — INSUFFICIENT

Pool size increase alone does not fix q05. The source_agreement penalty
is the dominant factor, not pool size. Increasing to 70 brings the
pinned target into the pool, but it still lands at rank 40-46 because
50+ competitors with source_agreement=1.0 leapfrog it.

### Step B result: source_agreement reduction — VIABLE for no_llm

Reducing `RERANK_SOURCE_AGREEMENT_BONUS` from 0.10 to 0.02 moves
q05/no_llm to rank 2 (HIT) on both standard and extended pools with
current production upstream=0.12.

**Regression risk:** Dep #7 tested agreement=0.02 across all 20 queries
(advanced + hybrid) and found **zero regressions** among the 12 viable
weight sets. Agreement=0.00 also shows zero regressions in a targeted
simulation using the Dep #4 pool snapshot.

**Limitation:** This only fixes the no_llm arm. The pinned arm
(advanced/hybrid with LLM expansion) remains broken because the target
ranks 66th in RRF — agreement reduction cannot overcome a 50-candidate
pool exclusion.

### Option 1: Reduce RERANK_SOURCE_AGREEMENT_BONUS (0.10 → 0.02)

**Scope:** single line in `src/config.py`
**Fixes:** q05/no_llm arm (rank 14 → rank 2)
**Regressions:** none found in Dep #7 simulation (12/40 viable sets)
**Risk:** low — smallest possible production change; validated by
existing regression harness

This is the recommended production patch for no_llm/basic mode coverage.

### Option 2: Document enrichment for Thanatomorphose (Step C)

Add keywords to `data/movies_clean.csv` for Thanatomorphose. Currently
the keywords field is EMPTY, so BM25 never retrieves it (zero lexical
overlap with query terms). Adding keywords like "body horror,
decomposition, mutation, bodily transformation" would give the target
`source_agreement = 1.0`, eliminating the penalty entirely.

**Fixes:** both arms — if BM25 finds the target, it enters the pool
with sa=1.0 in both pinned and no_llm modes.
**Risk:** medium — data change, need to verify BM25 retrieval and
re-run regression eval.
**Benefit:** root-cause fix rather than penalty reduction.

### Option 3: Combined approach

1. Reduce `RERANK_SOURCE_AGREEMENT_BONUS` 0.10 → 0.02 (fixes no_llm)
2. Enrich Thanatomorphose keywords (fixes pinned arm via BM25)

This covers both arms but requires two changes and a data pipeline step.

### Recommended path

**Option 1** (agreement bonus 0.10 → 0.02) is the smallest bounded
change with zero known regressions. It fixes q05 in the no_llm arm.
The pinned arm requires Step C (document enrichment) as a separate
follow-up, since no blend-weight change can rescue a target excluded
from the rerank pool.

---

## 6. Non-recommendations (ruled out by evidence)

| Strategy | Ruled out by | Reason |
|---|---|---|
| RERANK_TOP_K increase alone | Step A | Pool size does not fix q05. source_agreement penalty is the binding constraint, not pool size. |
| Alibaba reranker swap | RERANK-02 + Dep #4 | Worsens q05 (rank 5→7 no_llm, 4→10 pinned). Also regresses 7/20 queries globally. |
| MiniLM reranker swap | RERANK-02 | No_llm rank stays at 5 (unchanged). Pinned improves (4→1) but MiniLM was not regression-tested globally. |
| Safe localized cutoff/reweight | DECOMP-01 | All 11 evaluated policies `all_targets_rescued = False`. No bounded policy rescues both pinned and no_llm arms. |
| Global reranker swap | Dep #4 | `gate_fail` — fixes q10 but regresses q01, q03, q04, q11, q12, q15, q18. |
| upstream_weight adjustment alone | Dep #7 (partial) | Already reduced 0.20→0.12 (Phase 5-A). Further reduction not tested and not needed — agreement is the binding factor. |

## 7. BM25 blindspot analysis (Step B2)

Thanatomorphose is invisible to BM25 because:

1. **Keywords field:** EMPTY (no keywords at all in `data/movies_clean.csv`)
2. **Lexical overlap:** Query terms ("ambition", "mutates", "intimate",
   "disgusting") have zero overlap with the movie's description vocabulary
   ("rot", "decaying", "putrid", "bruised", "rough sex")
3. **Genre match:** Only "Horror" — no subgenre keywords like "body horror"
4. **Tagline:** "Rotting from the inside out" — relevant but uses different
   vocabulary

This is why `source_agreement = 0.0` for this target in both arms.
The semantic retriever finds it (semantic_rank=0 in no_llm), but BM25
does not. Enriching the keywords field would fix the BM25 blindspot
and give the target sa=1.0, eliminating the penalty entirely.
