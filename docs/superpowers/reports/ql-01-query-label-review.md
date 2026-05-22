# QL-01 — Query/Label Review (basic-succeeds / hybrid-fails cluster)

Timestamp: 2026-05-22T04:12:00Z
Branch: `automation/cinematch-accuracy-audit-full`
Ticket: QL-01
Mode: review/eval-only — no `src/*`, no label/query mutation, no model calls
Status: COMPLETE / SELF-REVIEWED
Evidence artifact: `eval/runs/2026-05-19-1846-nogit/analysis/query_label_review/q05_q07_q10_review.json`

---

## Label provenance — read first

q05, q07, and q10 ran on **silver / LLM-pregrade labels only**. Every label
for these three queries is `label_source: "silver"` with `gold_grade: null`;
the eval-consumed `grade` equals the `silver_grade` produced by the `llama3.2`
pregrade. The merged `gold_labels.jsonl` does contain human-gold rows, but only
for q03/q08/q12/q13 — never for this cluster.

Therefore a **`silver_label_issue` finding in this report is a recommendation
to run an RG-style human regrade**, not a dispute of an existing human gold
grade. No QL-01 finding edits any label or query; QL-01 only classifies and
recommends.

## Method

Each query is classified into exactly one of five buckets: `query_wording_issue`,
`silver_label_issue`, `hybrid_expansion_issue`, `reranker_blend_issue_later_eval`,
`inconclusive`. The QL-01 script emits a deterministic coarse `rule_based_lean`
(`reranker_blend_issue_later_eval` / `needs_analyst_review` / `inconclusive`);
this report assigns the final classification with cited evidence. Where the
final classification differs from the script lean, that is stated explicitly.

A cross-cutting fact from the evidence artifact: for all three queries the
hybrid intent expansion (`hybrid_expansion_text`) is a faithful, on-topic
rewrite of the original query. **No query in this cluster is a
`hybrid_expansion_issue`** — the expansion step is not the fault.

---

## Per-query findings

### q05 — Thanatomorphose (tmdb 144204) → `reranker_blend_issue_later_eval`

- **Script lean:** `needs_analyst_review` (R2 — arms not both rerank-demoted).
- **Final classification:** `reranker_blend_issue_later_eval`.

**Evidence.**
- Query: "a body horror story where ambition mutates into something intimate
  and disgusting." Silver target Thanatomorphose, grade 3, confidence high,
  reason cites the tagline "Rotting from the inside out." Thanatomorphose is a
  genuine body-horror film — the label is defensible.
- Hybrid expansion is faithful ("…body horror, psychological mutation, visceral
  invasion, grotesque intimacy").
- Both deterministic arms fail with a fixed/zero expansion: `pinned` =
  `retrieved_dropped_before_rerank_pool` (RRF rank 66, below the rerank pool);
  `no_llm` = `rerank_recovered_final_demoted` (rerank rank 4 → final rank 9).
- `target_retrieved_by_mode`: basic only — Thanatomorphose never enters the
  live hybrid or advanced candidate union.

**Rationale.** The query is acceptable (the eval set is intentionally
vocab-mismatched), the silver label is defensible, and the expansion is
faithful. The failure is query-independent pipeline mechanics — recall depth
in one arm, final-blend demotion in the other. This is a genuine code defect,
and it is exactly the mixed defect HY-FIX-04 already analysed and found has no
*provable* safe localized fix from current artifacts.

**Follow-up.** Defer to a decomposition-enriched eval ticket (full rerank-pool
and final-blend score decomposition) before any Phase 5 code change.

### q07 — My Babysitter's a Vampire (tmdb 63700) → `silver_label_issue`

- **Script lean:** `reranker_blend_issue_later_eval` (R1 — both arms rerank-demoted).
- **Final classification:** `silver_label_issue` — *the report overrides the
  mechanical lean; see rationale.*

**Evidence.**
- Query: "a mockumentary about vampires sharing chores, rent, and eternal
  grudges." This is an unambiguous description of **What We Do in the Shadows
  (2014)**.
- The candidate set **contains What We Do in the Shadows (2014), tmdb 246741 —
  labelled silver grade 2**. The silver grade-3 "perfect" target is instead
  **My Babysitter's a Vampire (2010)**, a teen TV comedy that is *not* a
  mockumentary and not about vampire flatmates.
- The silver pregrade reason for the grade-3 target is self-evidently weak:
  "genres including 'Fantasy' and 'Horror', which are common in
  mockumentary-style vampire films" — it asserts a mockumentary fit the film
  does not have.
- The hybrid intent expansion is faithful and accurate ("mockumentary film
  about vampires sharing household responsibilities, financial obligations,
  and long-standing resentments").
- `target_retrieved_by_mode`: My Babysitter's a Vampire is retrieved **only by
  basic** (keyword overlap on "vampire"). Basic's strict hit for q07 is itself
  an artifact — it gets credit for ranking a mislabelled film at rank 5.

**Rationale.** The deterministic arms do show My Babysitter's a Vampire being
rerank-demoted (hence the script's R1 lean), but that demotion is the
**cross-encoder behaving correctly** — it scores a poorly-matched film low. The
root cause is not the ranker; it is that the LLM pregrade crowned the wrong
film. The two-layer design anticipates exactly this: the script reports the
mechanical observation, the report applies the label-quality judgment the
script cannot.

**Follow-up.** RG-style human regrade of q07: re-grade What We Do in the
Shadows (2014, tmdb 246741) and My Babysitter's a Vampire (tmdb 63700) — the
intended grade-3 target is almost certainly WWDITS 2014. Note the metrics
implication: after a regrade, q07's *hybrid* result would still miss top-5
(WWDITS 2014 sits at hybrid rank 6), so a residual `reranker_blend` near-miss
may surface for q07 once the label is corrected.

### q10 — [REC] (tmdb 8329) → `reranker_blend_issue_later_eval`

- **Script lean:** `needs_analyst_review` (R2 — arms not both rerank-demoted).
- **Final classification:** `reranker_blend_issue_later_eval`.

**Evidence.**
- Query: "found footage friends chased through a haunted apartment maze."
  Silver target [REC], grade 3, confidence high, reason cites the keywords
  "found footage", "haunted apartment", "chased". [REC] is a found-footage
  horror film set in an apartment building — the label is **correct and
  well-justified**.
- Hybrid expansion is faithful ("found footage group of friends navigate
  labyrinthine haunted apartment complex…").
- `target_retrieved_by_mode`: all three modes retrieve [REC]. Both
  deterministic arms still fail: `pinned` = `retrieved_dropped_before_rerank_pool`
  (RRF 53); `no_llm` = `rerank_demoted` (rerank rank 6 → final rank 7). Hybrid
  ranks [REC] at 8, versus basic 4 / advanced 3.

**Rationale.** Query good, label indisputably correct, expansion faithful, and
the target is retrieved — yet hybrid still demotes it out of the top 5 while
the two simpler modes do not. This is the cleanest genuine pipeline defect in
the cluster. It matches HY-FIX-04's mixed-defect finding: no provable safe
localized fix from current artifacts.

**Follow-up.** Defer to the same decomposition-enriched eval ticket as q05.

---

## Summary

| Query | Target | Classification | Root cause | Follow-up |
|-------|--------|----------------|------------|-----------|
| q05 | Thanatomorphose | `reranker_blend_issue_later_eval` | Recall depth + final-blend mechanics; query/label/expansion all sound | Decomposition-enriched eval, then Phase 5 |
| q07 | My Babysitter's a Vampire | `silver_label_issue` | LLM pregrade crowned the wrong film; What We Do in the Shadows (2014) is the real answer, mislabelled grade 2 | RG-style human regrade of q07 |
| q10 | [REC] | `reranker_blend_issue_later_eval` | Hybrid rerank/blend demotes a correctly-labelled, retrieved target | Decomposition-enriched eval, then Phase 5 |

No query classified as `query_wording_issue`, `hybrid_expansion_issue`, or
`inconclusive`.

## Overall recommendation — the Phase 5 gate

**Phase 5 code fixes are not justified to dispatch now.**

- **q07 is a data defect, not a code defect.** A code fix would be wrong — the
  reranker is behaving correctly. q07 diverts to a label-regrade track.
- **q05 and q10 are genuine pipeline defects**, so they are Phase 5 *territory* —
  but HY-FIX-01..04 already proved no safe *localized* `src/*` fix is provable
  from the current artifacts. They are blocked on missing evidence
  (full pool-score decomposition), not on a missing decision.

So QL-01's gate verdict: **do not enter Phase 5 yet.** Split into two
independent tracks:

- **Track A — label regrade (q07).** A new RG-style ticket: build a regrade
  sheet for q07, have a human re-grade What We Do in the Shadows (2014) and
  My Babysitter's a Vampire, run `check_regrade_sheet` + `merge_labels` to
  refresh authoritative metrics. External-review gated (it changes labels).
  This also partially corrects the hybrid strict-gap, which is currently
  inflated by a mislabelled query.

- **Track B — decomposition-enriched eval (q05, q10).** A new eval/instrumentation
  ticket that captures the full rerank-pool and final-blend score decomposition
  HY-FIX repeatedly lacked, so a safe localized fix for the mixed q05/q10
  defects can be proven or ruled out. Only then do q05/q10 Phase 5 fix tickets
  become justified.

Tracks A and B are independent and can run in parallel. Phase 5 begins only
after Track B yields decisive evidence.

## Validation

- `python -m compileall eval/scripts` — passed.
- `python -m unittest discover -s eval/tests` — 183 tests OK (171 prior + 12
  QL-01).
- `python -m eval.scripts.ql_query_label_review --run 2026-05-19-1846-nogit` —
  wrote the evidence artifact; schema check passed.
- `git diff --name-only -- src/` — empty. No label or query file modified.
