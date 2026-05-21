---
title: Phase 1 — Eval harness design
parent: README.md
section: 6 (excl. 6.6, 6.7)
---

# 6. Eval harness design — structure, runs, and reproducibility

[Index](README.md) · Prev: [Six-phase plan](03-six-phase-plan.md) · Next: [05 — Metrics, QC, and labels](05-metrics-qc-and-labels.md) (contains §6.6, §6.7)

## 6.1 Directory layout

```
eval/
├── README.md
├── queries/
│   └── v1.jsonl                              ← 20 queries with diversity tags
├── runs/
│   ├── 2026-05-19-1530-3680020/              ← timestamped + short-sha run dir
│   │   ├── run_manifest.json
│   │   ├── config_snapshot.json              ← auto-dumped from src/config.py
│   │   ├── candidates.jsonl
│   │   ├── silver_labels.jsonl
│   │   ├── review_sheet.jsonl
│   │   ├── gold_labels.jsonl
│   │   ├── qc_report.json
│   │   ├── metrics_provisional.json
│   │   └── metrics.json
│   ├── 2026-05-19-1730-3680020-ablation-rrf_k_5/
│   │   └── (same shape, plus parent_run reference)
│   └── current_run.txt                       ← text file w/ latest run_id (Windows-safe)
└── scripts/
    ├── generate_queries.py
    ├── run_pipelines.py
    ├── llm_pregrade.py
    ├── build_review_sheet.py
    ├── review_app.py                          ← Gradio review UI
    ├── merge_labels.py
    ├── compute_metrics.py
    ├── qc_analyze.py
    └── ablate.py
```

**Windows compatibility:** the "latest run" pointer is `eval/runs/current_run.txt`
containing the run_id, not a symlink — Windows symlinks/junctions are unreliable.

## 6.2 Data schemas

**`queries/v1.jsonl`** (one record per line):
```json
{
  "qid": "q01",
  "query": "a mind-bending movie about dreams, memory, and reality",
  "tags": {
    "era": "2000-2015",
    "genre": ["sf", "thriller"],
    "vocab_distance": "high",
    "length": "short",
    "specificity": "medium",
    "ambiguity": "low"
  },
  "notes": "vocab-mismatch axis: 'mind-bending' rarely appears in TMDB overviews"
}
```

**`candidates.jsonl`** — primary key `tmdb_id` (int), `movie_key` kept as secondary:
```json
{
  "qid": "q01",
  "tmdb_id": 27205,
  "movie_key": "title:inception|year:2010",
  "title": "Inception",
  "year": 2010,
  "overview": "...",
  "genres": "...",
  "keywords": "...",
  "tagline": "...",
  "per_mode": {
    "basic":    {"rank": 0,  "semantic_score": 0.83, "final_score": 0.83},
    "advanced": {"rank": 2,  "semantic_score": 0.81, "bm25_score": 7.2,
                 "rrf_score": 0.029, "rerank_score": 4.1, "final_score": 4.31},
    "hybrid":   {"rank": 0,  "semantic_score": 0.83, "bm25_score": 7.2,
                 "rrf_score": 0.031, "rerank_score": 4.2, "final_score": 4.42}
  },
  "in_top_k_of": ["basic", "hybrid"],
  "source": "union"
}
```

**`silver_labels.jsonl`**:
```json
{"qid": "q01", "tmdb_id": 27205, "grade": 3, "confidence": "high",
 "reason": "Overview explicitly mentions dreams, subconscious heists, layered reality.",
 "model": "llama3.2", "ts": "2026-05-19T15:30:42Z"}
```

**`review_sheet.jsonl`** (flagged items only):
```json
{"qid": "q01", "tmdb_id": 27205,
 "flag_reasons": ["top_5_of_hybrid", "pipeline_disagreement"],
 "llm_grade": 3, "llm_confidence": "high", "llm_reason": "...",
 "user_grade": null, "user_notes": null, "reviewed_at": null}
```

Flag reasons populated automatically:
- `top_5_of_<mode>` — always reviewed.
- `llm_low_confidence` — LLM emitted `confidence: low`.
- `pipeline_disagreement` — appears in top-5 of one mode but not top-15 of another.
- `random_qc` — drawn from unflagged items, 20% of remaining.
- `null_label_blocks_final` — `grade: null` reached a top-5 slot; see
  [05 §7.2](05-metrics-qc-and-labels.md#72-null-label-policy).

**`gold_labels.jsonl`** — same shape as silver; written when user_grade is non-null.

**`qc_report.json`** — see [05 §7.7](05-metrics-qc-and-labels.md#77-qc-analysis-qc_analyzepy).

**`run_manifest.json`**:
```json
{
  "run_id": "2026-05-19-1530-3680020",
  "git_sha": "3680020",
  "git_dirty": false,
  "dataset_row_count": 27762,
  "chroma_collection_count": 27762,
  "embedding_model": "BAAI/bge-m3",
  "reranker_model": "BAAI/bge-reranker-v2-m3",
  "llm_model": "llama3.2",
  "rng_seed": 42,
  "timestamps": {"start": "...", "candidates_done": "...", "silver_done": "...", "gold_done": "...", "final_metrics_done": "..."}
}
```

**`config_snapshot.json`** — auto-derived. The script imports `src.config` and dumps
every `UPPER_CASE` non-callable, non-module attribute. Never hand-maintained.

## 6.3 Run lifecycle

```
new run requested
  → mkdir eval/runs/<timestamp>-<short_sha>/
  → write run_manifest.json (incl. git_dirty flag and rng_seed)
  → write config_snapshot.json (auto-derived from src.config)
  → run_pipelines.py   → candidates.jsonl
  → llm_pregrade.py    → silver_labels.jsonl
  → compute_metrics.py → metrics_provisional.json (provisional: true)
  → build_review_sheet.py → review_sheet.jsonl
  → review_app.py      ← user grades flagged items, writes gold_labels.jsonl
  → qc_analyze.py      → qc_report.json with decision
  → merge_labels.py    → effective labels (gold overrides silver)
  → compute_metrics.py → metrics.json (provisional: false)
  → update eval/runs/current_run.txt
```

## 6.4 Query generation strategy

`generate_queries.py` produces v1 (20 queries). User reviews in a single pass before
grading begins. Target distribution:

| Axis | Distribution |
|---|---|
| Era | 4 pre-1980, 5 1980–2000, 6 2000–2015, 5 2015+ |
| Genre | ≥2 each from drama, thriller, SF, animation, horror, comedy; rest free |
| Vocabulary distance | **8 high** (mood/theme words rare in CSV), 8 medium, 4 low |
| Length | 8 short (≤8 words), 8 medium, 4 long |
| Ambiguity | 4 one-clear-answer, 12 small-set, 4 many-plausible |

High-vocab-distance queries deliberately use synonyms that *do not* appear in the
source overview. This is the test of whether semantic embeddings + query expansion +
HyDE actually work for the user's stated concern.

## 6.5 Candidate union construction (`run_pipelines.py`)

For each query:

1. Run Basic + Advanced + Hybrid, each invoked with `top_k=15` so the pipeline's
   *final output list* contains 15 items per mode (after the pipeline's own
   rerank/dedup/trim).
2. Dedup union by `tmdb_id` (primary), `movie_key` (secondary cross-check).
3. Sort union by best rank across all modes (top-1 in any mode goes first; ranks
   are 0-based throughout the JSONL artifacts).
4. Apply **soft cap = 8**; **hard max = 15**.
5. **Top-5 of any mode is guaranteed in the union, never trimmed out** — because
   Hit@5/MRR@5/NDCG@5 all depend on the top-5 being graded.
6. For each surviving candidate, preserve `per_mode` evidence as in the schema.

If two pipeline candidates share `tmdb_id` but produce different `movie_key`s, log a
dedup-bug warning that feeds the Phase 3 audit (a duplicate `movie_key` for distinct
`tmdb_id`s is a `get_movie_key()` collision).

## 6.8 Reproducibility

- `rng_seed` recorded in `run_manifest.json`; used for QC sampling and bootstrap CIs.
- `config_snapshot.json` auto-derived from `src/config.py` at run start.
- `git_sha` and `git_dirty` recorded. Final metrics on a dirty tree carry a `dirty`
  flag and are inadmissible for prioritization decisions.
- All scripts read from `eval/runs/<run_id>/`, not from process globals. Multiple
  runs coexist without interference.

Continues in [05 — Metrics, QC, and labels](05-metrics-qc-and-labels.md) (§6.6, §6.7, §7).
