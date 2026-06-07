# Q05-01 — Residual q05 Investigation Report

Timestamp: 2026-06-07
Branch: `main`
Ticket: Q05-01
Status: COMPLETE

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
| **Dep #7** | Blend-weight simulation: q05 advanced/hybrid = `original_hit: false, new_hit: false, change: unchanged` across all 40 tested weight sets (including the 12 viable ones). Weight change does not affect q05. |

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

**Category: `reranker_architecture_issue`** — the cross-encoder cannot
distinguish the gold target from false positives for this query type.

### Justification

The core defect is that the cross-encoder (BAAI/bge-reranker-v2-m3)
assigns Thanatomorphose a rerank_score of only 0.0188, placing it at
rank 5 (0-based) in the no_llm arm — just outside the top-5 threshold.
Five other body-horror films receive higher scores despite being less
semantically precise matches for the query's "ambition mutates into
something intimate and disgusting" phrasing.

This is not a blend-weight issue (Dep #7 tested 40 weight combinations
and none rescues q05), not a retrieval issue in the no_llm arm (target
enters at RRF rank 1), and not a label issue (QL-01 confirmed the label
is defensible). The pinned arm has a compounding RRF recall problem
(rank 66), but the no_llm arm isolates the reranker as the sole
bottleneck: the target is presented to the cross-encoder at the best
possible position and still demoted.

All three tested cross-encoders fail to rescue q05/no_llm:

- **BAAI/bge-reranker-v2-m3** (baseline): rank 5 (outside top-5)
- **Alibaba-NLP/gte-multilingual-reranker-base**: rank 7 (worse)
- **cross-encoder/ms-marco-MiniLM-L6-v2**: rank 5 (unchanged)

The query requires understanding that "ambition mutates into something
intimate and disgusting" maps to a film about literal bodily
decomposition — a metaphorical-to-literal leap. The false positives
above the target (Color Out of Space, The Beast Within, Bad Biology,
Grace, Body) are all legitimate body-horror films, but none capture the
specific "ambition → mutation → intimacy" arc. The cross-encoder cannot
make this distinction because it relies on surface-level token overlap
rather than deep narrative understanding.

### Why not the other categories

- **query_expansion_issue:** The no_llm arm uses the raw query (no
  expansion) and still fails. The hybrid expansion was confirmed faithful
  by QL-01.
- **retrieval_candidate_quality:** In the no_llm arm, the target is
  retrieved at RRF rank 1. Candidate quality is not the issue.
- **document_text_mismatch:** RERANK-01A confirmed the target's document
  text is resolved correctly. The overview ("Bruised from a night of
  rough sex, a young woman is shocked to find that her body... has
  inexplicably begun to rot") is semantically rich and relevant.
- **label_candidate_ceiling:** The target is in the rerank pool (no_llm)
  and the cross-encoder scores it — it's not a ceiling issue. It's
  scored, just not scored high enough.

---

## 5. Recommended next investigation

### Option A: Rerank pool size increase (low risk, bounded)

Increase `RERANK_TOP_K` from 50 to ~70 to bring the pinned arm's target
(RRF rank 66) into the rerank pool. This would not fix the no_llm arm
(which is a pure reranker scoring issue), but would give the pinned arm
a chance.

**Risk:** larger rerank pool = more cross-encoder inference time per
query. Going from 50 to 70 adds ~40% more pairs. Impact on latency
should be measured before deploying.

**Limitation:** this only addresses the pinned arm. The no_llm arm would
remain broken (rerank rank 5, outside top-5).

### Option B: Document enrichment (medium risk, targeted)

Add keyword metadata to the target's document text. Thanatomorphose's
`keywords` field is empty (confirmed by RERANK-01B:
`field_presence.keywords = false`). Adding relevant keywords (e.g.,
"body horror, decomposition, bodily transformation, mutation") could help
the cross-encoder score it more accurately.

**Risk:** requires a data pipeline change or manual enrichment. Effect
is uncertain — the cross-encoder may not weight keywords heavily enough.

### Option C: Query-document prompt engineering (medium risk)

Restructure `build_movie_document()` to emphasize narrative arc signals
(tagline, overview themes) that help cross-encoders distinguish
metaphorical queries from surface-level genre matches.

**Risk:** changes document format for all queries; needs regression eval.

### Recommended starting point

**Option A** (pool size increase) is the lowest-risk bounded experiment.
It can be validated with the existing regression eval harness. Even if it
only fixes the pinned arm, it narrows the defect to a single arm and
provides additional evidence about whether the no_llm reranker issue is
the true ceiling.

---

## 6. Non-recommendations (ruled out by evidence)

| Strategy | Ruled out by | Reason |
|---|---|---|
| Blend-weight adjustment | Dep #7 | 40 weight combos tested; none rescues q05. q05 advanced/hybrid stays `false` across all viable sets. |
| Alibaba reranker swap | RERANK-02 + Dep #4 | Worsens q05 (rank 5→7 no_llm, 4→10 pinned). Also regresses 7/20 queries globally. |
| MiniLM reranker swap | RERANK-02 | No_llm rank stays at 5 (unchanged). Pinned improves (4→1) but MiniLM was not regression-tested globally. |
| Safe localized cutoff/reweight | DECOMP-01 | All 11 evaluated policies `all_targets_rescued = False`. No bounded policy rescues both pinned and no_llm arms. |
| Global reranker swap | Dep #4 | `gate_fail` — fixes q10 but regresses q01, q03, q04, q11, q12, q15, q18. |
