---
title: Metrics, QC, and labels
parent: README.md
section: 6.6, 6.7, 7
---

# Metrics, QC, and labels (§6.6, §6.7, §7)

[Index](README.md) · Prev: [04 — Eval harness](04-phase1-eval-harness.md) · Next: [Ablation matrix](06-ablation-matrix.md)

## 6.6 LLM pre-grading (`llm_pregrade.py`)

**Model:** `llama3.2` via existing `langchain_ollama.py` client, same 25s timeout.
Kept for v1 because already installed. If QC shows the grader is too noisy, the v2
plan can upgrade.

**Prompt template** (one call per `(query, candidate)` pair):

```
You are a movie-relevance grader. Given a USER QUERY and a MOVIE's metadata,
assign a relevance grade and a confidence level.

GRADES:
  3 = perfect match (the query clearly describes this exact movie)
  2 = good match (most of the query's themes/plot elements present)
  1 = related (some shared themes/genre but not a strong match)
  0 = irrelevant (no meaningful connection)

CONFIDENCE:
  high   = metadata clearly supports the grade
  medium = metadata partially supports; ambiguity exists
  low    = metadata too thin / could plausibly be a different grade

Ground your grade STRICTLY in the metadata. Do not guess plot details
not present. If the overview is empty or generic, default to confidence: low.

USER QUERY: {query}

MOVIE:
  Title: {title} ({year})
  Genres: {genres}
  Overview: {overview}
  Keywords: {keywords}
  Tagline: {tagline}

Reply as JSON:
{"grade": <0-3>, "confidence": "<high|medium|low>", "reason": "<one sentence>"}
```

**Operational rules:**
- Cache per `(query, tmdb_id, model)`; re-runs are idempotent.
- Failures (timeout, malformed JSON) emit a synthetic record with `grade: null` and `confidence: "low"`; these auto-flag for manual review.
- Validate JSON parse rate ≥ 95% before bulk grading 160+ calls; iterate prompt if below.

## 6.7 Manual review workflow (`review_app.py`)

**Primary UX: Gradio page** (project already uses Gradio). One item per page:

```
[Query: a mind-bending movie about dreams, memory, and reality]

  Movie: Inception (2010)        TMDB id: 27205
  Genres: Action, Adventure, Sci-Fi
  Overview: ...
  Keywords: ...

  LLM grade: 3 (high confidence)
  LLM reason: "Overview explicitly mentions dreams, subconscious heists..."
  Flag reasons: top_5_of_hybrid, pipeline_disagreement

  Your grade: [ 0 ]  [ 1 ]  [ 2 ]  [ 3 ]   [Confirm LLM = 3]
  Notes: ___________________

  [Skip]  [Save and Next]    Progress: 12 / 47
```

- State lives entirely in `gold_labels.jsonl`. Closing the browser is safe; reopening resumes from the next unreviewed item.
- "Confirm LLM" is one-click acceptance of the LLM grade.
- "Skip" leaves `user_grade: null`; revisitable.

**Fallback UX: raw JSONL edit.** The schema is human-readable; opening `review_sheet.jsonl` in any editor and filling `user_grade` fields manually also works.

## 7.1 Grade → relevance mapping

```
silver/gold grade  →  relevance value used in graded NDCG
       3           →  1.0   (perfect)
       2           →  0.7   (good)
       1           →  0.3   (related)
       0           →  0.0   (irrelevant)
      null         →  blocks final metrics if reached top-5; auto-added to review
```

Raw 0–3 grades preserved in `metrics.json` for later re-scoring.

## 7.2 Null-label policy

For **final** metrics, every top-5 candidate (per evaluated mode, per query) must have an effective label (silver or gold). If any top-5 item has `grade: null`:

- Block final metrics computation for that mode on that query.
- Auto-add the item to `review_sheet.jsonl` with reason `null_label_blocks_final`.
- Final metrics compute only after all blocks resolve.

For **provisional** metrics (silver only), null exclusion is allowed but the count of excluded items is reported alongside each metric.

## 7.3 Metric formulas

For query `q` with top-K result list `R_q = [r_1, ..., r_K]`:

```
Hit@5(q)       = 1 if any r_i in top-5 has grade ≥ 2, else 0
Strict Hit@5(q)= 1 if any r_i in top-5 has grade == 3, else 0

MRR@5(q)       = 1 / rank_of_first_grade_ge_2  in top-5 if any, else 0
Strict MRR@5(q)= 1 / rank_of_first_grade_3     in top-5 if any, else 0

DCG@5(q)       = Σ_{i=1..5}  rel(r_i) / log2(i + 1)
iDCG@5(q)      = DCG of the ideal top-5, built from the union of graded
                 candidates for q across all evaluated modes
NDCG@5(q)      = DCG@5(q) / iDCG@5(q) if iDCG > 0, else null (excluded)
```

iDCG labeled as **pool-based** in all output: relevance is only known for retrieved candidates, not for every possible relevant movie in the dataset.

**Rank convention:** stored ranks in JSONL artifacts are **0-based** (`per_mode.rank` starts at 0). The metric formulas above use **1-based** indexing for math (`i = 1..5`). `compute_metrics.py` handles the conversion (`rank_storage + 1 = i`). Unit tests verify the conversion on a tiny synthetic example.

## 7.4 Confidence intervals

- **Per-mode metrics:** stratified bootstrap over queries, B = 1000.
- **Ablation deltas:** **paired** bootstrap on per-query metric deltas. A change is inconclusive if the delta CI includes 0, regardless of CI width.
- CI half-widths reported alongside every metric.

## 7.5 Per-axis breakdown

For each axis (era, genre, vocab_distance, length, ambiguity), compute metrics on the sub-slice. Slices with n < 5 flagged `low_sample`; not used for decisions.

## 7.6 Provisional vs final outputs

| File | Inputs | Status flag | Decision use |
|---|---|---|---|
| `metrics_provisional.json` | silver only | `provisional: true` | Sanity-check harness; never drives prioritization |
| `metrics.json` | merged labels (gold overrides silver) + QC validated | `provisional: false` | Authoritative for fix prioritization, ablation, re-baseline |

Scripts reading metrics must check the `provisional` flag and refuse to make decisions on provisional ones.

## 7.7 QC analysis (`qc_analyze.py`)

Runs after gold labels exist. Compares gold vs silver on the 20% random QC sample (drawn from items not otherwise flagged for review).

**`qc_report.json` schema:**

```json
{
  "qc_sample_size": 22,
  "items_evaluated": 22,
  "agreement_exact": 0.59,
  "agreement_within_1": 0.86,
  "disagreement_ge1_rate": 0.14,
  "disagreement_ge2_rate": 0.045,
  "disagreement_ge2_items": [
    {"qid": "q07", "tmdb_id": 1726, "silver_grade": 3, "gold_grade": 1, "silver_reason": "...", "gold_notes": "..."}
  ],
  "by_silver_confidence": {
    "high":   {"n": 14, "agreement_within_1": 0.93},
    "medium": {"n":  6, "agreement_within_1": 0.83},
    "low":    {"n":  2, "agreement_within_1": 0.50}
  },
  "decision": "freeze | expand_manual | review_outlier_query",
  "decision_reason": "...",
  "next_action": "..."
}
```

## 7.8 Adaptive expansion decision logic

```
if disagreement_ge1_rate > 0.25:
    decision = "expand_manual"
elif disagreement_ge2_count == 1:
    decision = "review_outlier_query"
    # Manually review that query in full. If isolated, accept. If similar pattern
    # appears in flagged_similar items, escalate.
elif disagreement_ge2_count >= 2 and form_a_pattern():
    decision = "expand_manual"
else:
    decision = "freeze"
```

**`form_a_pattern()`** requires at least 2 of the multi-level disagreements to share one of: same `vocab_distance` bucket; same `silver_confidence` bucket; same `ambiguity` bucket; same failure type (e.g., over-grades zero-overlap candidates, under-grades genre matches); same query family (manually tagged when surfacing).

**Single ≥2-level disagreement → full review of that query, not broad expansion.** Broad tags like `genre=comedy` alone are not sufficient evidence; require a more specific pattern.

## 7.9 Adaptive expansion loop

- When `decision == "expand_manual"`, `build_review_sheet.py --expand` pulls the next 20% of unreviewed items, prioritized by (low confidence → high candidate rank in any mode → random).
- Appends to the existing `review_sheet.jsonl` (does not start over).
- User grades the new rows. `qc_analyze.py` re-runs.
- Loop until `decision == "freeze"` or manual review caps at 60% of all items.
- At the 60% cap: mark the LLM grader as **unreliable for v1**; recommend either more gold labeling on v2 or a stronger grading model.
