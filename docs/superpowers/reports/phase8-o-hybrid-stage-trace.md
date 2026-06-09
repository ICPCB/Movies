# Phase 8-O Hybrid Stage Trace

Ticket: `8-O`
Verdict: `NEEDS_REVIEW`
Mode: saved-artifact analysis only

## Evidence Boundary

- Authoritative baseline: `eval/runs/2026-06-07-combined-nogit`
- Last authorized gated run: `eval/runs/2026-06-08-phase8j-gated-nogit`
- Diagnostic-only run: `eval/runs/2026-06-09-phase8-final-gate`
- Candidate ranks below are the stored zero-based `per_mode.rank` values.
- The candidate rows persist per-mode output rank and available score fields.
- They do not persist complete semantic, BM25, fused, or pre-rerank pools.
- A score on a persisted candidate is observed. Absence of a candidate does not
  identify which unpersisted intermediate stage removed it.
- `hybrid_stage_trace.py` and `hybrid_gap_trace.py` were not run because they
  write analysis artifacts under `eval/runs/`.
- `hybrid_live_trace.py` was not run because it executes live retrieval,
  reranking, and potentially LLM expansion.

Current source behavior was derived by calling only the side-effect-free
`extract_mood_intent` function:

| Query | Current emotion | Direction | Tones | Energy | Cleaned query |
|---|---|---|---|---|---|
| q59 | `lonely` | `comfort_me` | `warm` | `light_cozy` | `lonely - a movie that wraps around me like a warm blanket and reminds me that human connection is still possible even when everything feels empty` |
| q49 | `stressed` | `calm_me_down` | `light`, `funny` | `light_cozy` | `stressed - something light and funny to just zone out` |
| q53 | `null` | `make_me_laugh` | `funny` | `funny_energetic` | `the most absurd comedy` |

## q59 Hybrid

Original query:

`I feel lonely tonight and want a movie that wraps around me like a warm blanket and reminds me that human connection is still possible even when everything feels empty`

Approved targets:

- `Christmas Connection` (`474994`): grade 3,
  `human_reviewed_ai_assisted`; baseline basic-only candidate.
- `Someone, Somewhere` (`583268`): grade 2,
  `human_reviewed_ai_assisted`; the approved advanced/hybrid target.

Candidate evidence:

| Run | Someone, Somewhere advanced | Someone, Somewhere hybrid | Available stored scores |
|---|---|---|---|
| baseline | rank 1 | rank 2 | advanced: semantic `0.5824956298`, BM25 `58.5049338792`, RRF `0.0651128376`, rerank `0.0715481043`, final `0.2498137722`; hybrid: semantic `0.5739472508`, BM25 `36.4724284687`, RRF `0.0350915432`, rerank `0.0715481043`, final `0.1857207980` |
| authorized | absent from candidate union | absent from candidate union | unavailable |
| diagnostic only | absent from candidate union | absent from candidate union | unavailable |

`Christmas Connection` remains basic rank 0 in all three runs and has no
advanced or hybrid block.

The diagnostic run has silver-only advanced positives `The Hours` at rank 0
and `The Human Voice` at rank 4. Neither appears in hybrid. These rows show an
advanced/hybrid output divergence but are not human-reviewed replacements for
the approved target.

Earliest observable disappearance:

- The first directly observed loss is at the persisted candidate-union/per-mode
  output boundary after the baseline.
- Semantic pool: `NOT OBSERVABLE`.
- BM25 pool: `NOT OBSERVABLE`.
- Fusion membership/rank: `NOT OBSERVABLE`.
- Pre-rerank pool/rank: `NOT OBSERVABLE`.
- Therefore a rerank demotion is not demonstrated, and retrieval/fusion loss
  cannot be separated.

Ownership:

- Direct evidence: approved-target candidate recall is absent from all later
  persisted modes; diagnostic advanced and hybrid produce different outputs.
- Inference only: likely `retrieval recall` or `candidate union/fusion`.
- `mood_preprocessor/query cleaning` is not established as the first failing
  owner. The `lonely -` prefix did not restore the approved target.
- Minimal localized fix: not defensible.
- Exact implementation files: `NEEDS_REVIEW`.

## q49 Hybrid

Original query:

`super stressed from work need something light and funny to just zone out`

Approved target:

- `Office Space` (`1542`): grade 3,
  `human_reviewed_ai_assisted`.

Candidate evidence:

| Run | Office Space basic | Office Space advanced | Office Space hybrid |
|---|---|---|---|
| baseline | rank 4, semantic/final `0.5567066073` | rank 2 | absent |
| authorized | rank 4, semantic/final `0.5567066073` | absent | absent |
| diagnostic only | rank 4, semantic/final `0.5567066073` | absent | absent |

Baseline advanced scores were semantic `0.6589383483`, BM25 `73.1849830062`,
RRF `0.0577153828`, rerank `0.0227497928`, and final `0.1816220847`.

The authorized run's hybrid HIT came from `Let It Snow` at rank 3 with silver
grade 2, not from the approved `Office Space` target. The diagnostic run
removed that provisional silver HIT. This is separate silver/pregrade and
candidate-set instability; it does not prove an `Office Space` rank movement.

Earliest observable disappearance:

- `Office Space` is not present in persisted hybrid output in any compared run.
- Semantic pool: `NOT OBSERVABLE`.
- BM25 pool: `NOT OBSERVABLE`.
- Fusion membership/rank: `NOT OBSERVABLE`.
- Pre-rerank pool/rank: `NOT OBSERVABLE`.
- No hybrid stored rank or score movement exists for this target.

Ownership:

- Direct evidence: basic is stable while hybrid never persists the approved
  target; one authorized hybrid HIT depends on a different silver-only row.
- Inference only: likely `retrieval recall` or `candidate union/fusion`, with
  separate `label/pregrade drift` affecting the reported HIT/MISS status.
- The artifacts do not distinguish query expansion, retrieval, fusion, or
  pre-rerank loss.
- Minimal localized fix: not defensible.
- Exact implementation files: `NEEDS_REVIEW`.

## q49 Advanced Context

`Office Space` moves from baseline advanced rank 2 to absent in both later
candidate unions for advanced, while basic remains byte-stable at rank 4 with
the same semantic/final score.

The current `stressed -` query shaping was present for the diagnostic run, but
`Office Space` remained absent. Thus the current mood-preprocessor change is
not sufficient evidence for recovery and cannot be confirmed as the sole
owner. The loss could occur in query expansion, semantic/BM25 retrieval,
fusion, or the unpersisted pre-rerank pool.

Likely owner classification: unresolved between
`mood_preprocessor/query cleaning`, `retrieval recall`, and
`candidate union/fusion`.

Minimal localized fix: not currently defensible.
Exact implementation files: `NEEDS_REVIEW`.

## q53 Regression Guard

Preserved disposition:

- `Pee-wee's Big Adventure` (`5070`): grade 3,
  `human_reviewed_ai_assisted`.
- `Absolutely Anything` (`86828`): grade 1,
  `human_reviewed_ai_assisted`; its absence is not a material regression.
- No q53 implementation change is proposed.

Evidence:

- Baseline basic HIT: `Ernest Scared Stupid` grade 3 at rank 2.
- Baseline hybrid: `Pee-wee` rank 1; `Absolutely Anything` rank 4.
- Authorized basic remains HIT at rank 2.
- Authorized `Pee-wee` hybrid rank moves `1 -> 3`; BM25
  `132.0991038159 -> 107.0523945541`, RRF
  `0.0625 -> 0.0555555556`, rerank is unchanged at
  `0.0091762794`, and final score moves
  `0.1725229287 -> 0.1531021434`.
- The authorized silver grade for `Pee-wee` changed `2 -> 1`, but q53-H
  supersedes that pregrade with human-reviewed grade 3. This is
  `label/pregrade drift`, not retrieval loss.
- `Absolutely Anything` disappears after baseline, but q53-H grade 1 makes
  that loss non-material.
- The diagnostic-only run is HIT in all modes through other candidates:
  basic `Ernest Scared Stupid` rank 2, advanced
  `The Mitchells vs. the Machines` rank 4, hybrid `Dumb and Dumber` rank 2.

The authorized run does not provide an all-mode q53 HIT: advanced remains a
MISS. The diagnostic all-mode HIT cannot close the guard because that run is
not PASS evidence.

## Ownership Decision

Exact minimal implementation ownership is not defensible from saved artifacts.
For q59 hybrid and q49 hybrid, the earliest observed loss is only the persisted
candidate/per-mode output boundary. All earlier stage membership is
`NOT OBSERVABLE`.

Proposed exact implementation files:

- q59 hybrid: `NEEDS_REVIEW`
- q49 hybrid: `NEEDS_REVIEW`
- q49 advanced: `NEEDS_REVIEW`
- q53: no implementation change

No implementation ticket, production change, eval, model call, network call,
label change, provenance change, or run-artifact write is authorized by this
result.

## Provenance Guard

Current baseline label provenance remains:

- `human_reviewed_ai_assisted`: 15
- `null_parse_error_fixed`: 1
- `silver_llm_pregrade`: 628
- `human_gold`: 0

q65 Option A is unchanged.

