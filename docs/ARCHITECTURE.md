# CineMatch — Architecture Reference

> Maintained by inspection of source files.
> Last updated: 2026-06-12 (project finalization)
>
> **2026-06-11 note:** the legacy Gradio UI (`app.py`, port 7860) described in sections 4–20 has been **removed**, along with the legacy wrappers `recommend_bgem3.py` and `hybrid_recommend.py`. The serving entry points are the FastAPI backend (`api/`) and the React web app (`web/`) — see `PROJECT_OVERVIEW.md`. The `src/` retrieval-engine internals documented below are unchanged and still authoritative; read `app.py` references as describing the retired UI layer only.
>
> **2026-06-12 note:** section 1 (tree) and section 1b (serving + intent architecture) below reflect the final project state, including the `engine/`, `api/`, `web/`, `training/`, and `labels/` layers added after the original document was written.

---

## 1. Project Tree Overview (final, 2026-06-12)

```
Movies/
│
├── 01.clean_data.py              ← One-shot data-cleaning script (raw TMDB → movies_clean.csv)
├── 02. Embed_BGEM3.py            ← One-shot ChromaDB ingestion script (BGE-M3 index build)
├── README.md                     ← Setup, run, and test commands (root overview)
├── docs/PROJECT_OVERVIEW.md      ← Architecture, mood system, data provenance, eval results
├── docs/CINEMATCH_ULTRAPLAN.md   ← Master plan the app was built from
│
├── web/                          ← React 19 + Vite + Tailwind v4 UI (port 5173, proxies /api)
├── api/                          ← FastAPI backend (port 8000)
│   ├── main.py                   ← App factory, health, model warm-up
│   ├── routes_search.py          ← /api/search (mood / description / hybrid / category / random)
│   ├── routes_library.py         ← favorites, watchlist, history
│   └── db.py, db_models.py       ← SQLite (data/cinematch.db) via SQLAlchemy
│
├── engine/                       ← Intent layer between api/ and src/ (src/ is read-only to it)
│   ├── intent_parser.py          ← Two-tier parser: tier-1 lexicon, tier-2 few-shot Ollama
│   ├── intent_schema.py          ← Intent JSON contract + validation
│   ├── intent_query_builder.py   ← Intent → retrieval query / filters / boosts
│   ├── mood_labels.py            ← Per-movie film-mood label lookup
│   ├── movie_store.py            ← movies_clean.csv access
│   └── recommender.py            ← Orchestrates retrieval + mood filtering/boosting
│
├── src/                          ← PROTECTED production retrieval engine (sections 3–13 below)
│   ├── config.py                 ← All shared constants (paths, models, pools, weights)
│   ├── models.py                 ← Lazy singletons: BGE-M3 + bge-reranker-v2-m3
│   ├── retrieval/                ← semantic.py, bm25.py, fusion.py (RRF), reranker.py, filters.py
│   ├── pipelines/                ← basic.py, advanced.py, hybrid.py
│   ├── llm/                      ← langchain_ollama.py (expand/explain), prompts.py
│   └── utils/dedup.py            ← Stable movie keys + dedup
│
├── labels/                       ← Mood vocabularies (18 user / 24 film), user→film map,
│                                   27,758 deterministic per-movie film-mood labels + validators
├── training/                     ← Intent-LoRA dataset pipeline (see §1b)
│   ├── build_intent_dataset.py   ← Deterministic 3,600-record generator (seeded, byte-stable)
│   ├── prompt_format.py          ← Single source of truth for the LoRA prompt template
│   └── *.jsonl                   ← Generated dataset (6 categories × 600)
│
├── eval/                         ← Eval harness: graded relevance metrics, intent_v1 eval,
│   ├── queries/intent_v1.jsonl   ← 84-query held-out intent eval (7 slices × 12)
│   ├── scripts/                  ← run_pipelines, compute_metrics, intent_parser_eval, latency
│   └── runs/                     ← Run artifacts (gitignored except tracked gold/metrics)
│
├── scripts/                      ← quality_smoke_test.py, print_dataset_stats.py
├── docs/                         ← All project documentation (this file, overview, ultraplan,
│                                   intent-lora-spec.md, CHECKPOINT_LEDGER.md)
├── data/                         ← TMDB raw CSV, movies_clean.csv, chroma_bgem3/, cinematch.db
└── cinematch-llama/              ← (gitignored, local-only) Llama-3.2-1B base weights, training
                                    venv, LoRA adapters, probe artifacts
```

### File roles by category

| Category | Files |
|---|---|
| Serving entry points | `api/main.py` (FastAPI, port 8000), `web/` (Vite dev server, port 5173) |
| Intent layer | `engine/intent_parser.py`, `engine/intent_schema.py`, `engine/intent_query_builder.py`, `engine/recommender.py` |
| Config | `src/config.py` (+ `CINEMATCH_*` env vars layered by `api/`) |
| Model loading | `src/models.py` |
| Retrieval | `src/retrieval/semantic.py`, `bm25.py`, `fusion.py`, `reranker.py`, `filters.py`, `query_processor.py` |
| Pipelines | `src/pipelines/basic.py`, `advanced.py`, `hybrid.py` |
| LLM / explanation | `src/llm/langchain_ollama.py`, `src/llm/prompts.py` |
| Mood labels | `labels/*.json`, `labels/movie_mood_labels.jsonl`, `labels/build_movie_mood_labels.py`, `labels/validate_labels.py` |
| LoRA training | `training/build_intent_dataset.py`, `training/prompt_format.py`, `cinematch-llama/scripts/*` (local) |
| Eval | `eval/scripts/*`, `eval/queries/intent_v1.jsonl`, `eval/tests/*` |
| Scripts / tests | `scripts/quality_smoke_test.py`, `scripts/print_dataset_stats.py`, `api/tests/`, `src/tests/`, `training/test_prompt_format.py` |
| Data | `data/movies_clean.csv`, `data/chroma_bgem3/`, `data/cinematch.db` |
| One-shot scripts | `01.clean_data.py`, `02. Embed_BGEM3.py` |

---

## 1b. Serving and Intent Architecture (2026-06-12)

Request flow:

```
web/ (React)  →  api/ (FastAPI)  →  engine/ (intent + mood)  →  src/ (retrieval, protected)
                                          │
                                          └── labels/ (film-mood labels, vocabularies)
```

1. **Intent parsing** (`engine/intent_parser.py`): tier-1 is a deterministic
   user-mood lexicon (18 categories, mapped to 24 film moods via
   `labels/user_mood_map.json`); tier-2 is few-shot `llama3.2` on Ollama for
   plot/hybrid/avoid parsing. Output is the validated intent JSON contract in
   `engine/intent_schema.py`.
2. **Query building** (`engine/intent_query_builder.py`): intent →
   free-text retrieval query + genre/era filters + film-mood rank boosts.
3. **Retrieval** (`src/`): BGE-M3 semantic + field-boosted BM25 → RRF fusion →
   `bge-reranker-v2-m3` cross-encoder rerank (sections 3–13 below remain the
   authoritative reference for these internals).
4. **Mood application** (`engine/recommender.py`): film-mood filters and rank
   nudges are applied post-retrieval; `src/` is never modified.

**Intent-LoRA pipeline** (offline, local-only): `training/build_intent_dataset.py`
deterministically generates 3,600 records (seeded, byte-identical on rebuild,
held-out filter against `eval/queries/intent_v1.jsonl`) →
`cinematch-llama/scripts/train_intent_lora.py` trains a LoRA adapter on local
Llama-3.2-1B base weights using the fixed prompt contract in
`training/prompt_format.py` → `generate_intent_predictions.py` +
`grade_intent_predictions.py` grade against intent_v1 and the held-out test
split. Status 2026-06-12: adapter v6 e4 **passed** the spec §5 acceptance gate
(plot F1 0.9583 > 0.9412 tier-2 bar; validity and mode accuracy 1.0 on all
7 slices; 20-query novel-vocabulary probe 17/20 exact) but is **not wired into
serving** — runtime intent parsing remains tier-1 lexicon + tier-2 few-shot
Ollama until an explicit serving ticket lands. Spec and audit trail:
`docs/intent-lora-spec.md`, `docs/CHECKPOINT_LEDGER.md`.

---
## 2. High-Level Project Summary

**CineMatch** is an English-query movie recommendation and semantic search system built on English TMDB metadata after ingest filtering. The indexed movies may have any original language when English metadata is available. A user describes a film in natural language and the system returns the most relevant movies ranked by one of three pipeline modes.

**Dataset:** `data/movies_clean.csv` — derived from `TMDB_movie_dataset_v11.csv` by `01.clean_data.py`. It contains title, overview, genres, keywords, tagline, release_date, year, vote_average, vote_count, poster_path, and a pre-built `document` field used for embedding.

### Dataset & Scope

Dataset row counts and ingest filter values live in `src/config.py` as `DATASET_*` constants. Documentation references these by name, not by hardcoded number. Run `python scripts/print_dataset_stats.py` to verify constants match the live CSV.

**Recommendation modes:**

| Mode | What it does |
|---|---|
| Basic | BGE-M3 semantic search only. Fastest. |
| Advanced | LLM query expansion → semantic + BM25 → RRF fusion → BGE CrossEncoder reranker → optional LLM explanation. |
| Hybrid | Semantic + BM25 → RRF fusion → reranker → optional LLM explanation. Most accurate. |

**Models used:**
- Embedding: `BAAI/bge-m3` (SentenceTransformer) — used both at index time and at query time.
- Reranker: `BAAI/bge-reranker-v2-m3` (CrossEncoder) — used in Advanced and Hybrid modes.
- LLM: `llama3.2` via Ollama (optional, used for query expansion in Advanced/Hybrid when enabled and for explanations in Advanced/Hybrid).

**Main user flow:** User types a query in the Gradio UI → selects a pipeline mode → hits Search → `app.py` calls the chosen pipeline → pipeline returns a list of scored movie dicts → `app.py` renders them as HTML cards with poster, title, genres, year, TMDB rating, match score, rerank score, and AI explanation.

**Final output per movie card:** rank badge · poster image · year · TMDB star rating · `final_score` ("match") pill · `rerank_score` pill (if present) · title · genres · overview excerpt · AI Match Reason box (if LLM explanation present).

---

## 3. End-to-End Data Flow

```
User types query in Gradio UI
│
▼  app.py :: recommend_ui()
   Reads: query, top_k, use_llm, pipeline_mode
   Calls the matching pipeline run() function
│
▼  src/retrieval/query_processor.py :: normalize_query()
   Input:  raw query string
   Output: normalized English query string
   Modifies ranking: indirectly (cleaner query → better embedding match)
│
├─[Advanced only]─────────────────────────────────────────────────────────┐
│  src/llm/langchain_ollama.py :: expand_query()                          │
│  Input:  normalized query                                               │
│  Output: LLM-rewritten richer query (or original on timeout/failure)    │
│  Model:  llama3.2 via Ollama                                            │
└──────────────────────────────────────────────────────────────────────── ┤
│
▼  src/retrieval/filters.py :: parse_filters()
   Input:  raw query string
   Output: ChromaDB `where` dict for year range / vote_average, or {}
   Affects: which documents ChromaDB returns
│
▼  src/retrieval/semantic.py :: semantic_search()
   Input:  (normalized/expanded) query, top_k=CANDIDATE_POOL, optional filters
   Calls:  src/models.py :: get_embedder() — BGE-M3 SentenceTransformer
           ChromaDB collection.query()
   Output: list[dict] each with:
           id, title, release_date, year, genres, overview, poster_path,
           vote_average, vote_count, keywords, movie_key,
           semantic_score (float, 0–1), semantic_rank (int),
           final_score = semantic_score, debug{}
   Dedup:  deduplicate_movies() called before return
   Modifies ranking: yes — sorted by cosine similarity
│
├─[Advanced + Hybrid]──────────────────────────────────────────────────── ┐
│  src/retrieval/bm25.py :: bm25_search()                                │
│  Input:  normalized query, top_k=CANDIDATE_POOL                        │
│  Loads:  movies_clean.csv into pandas; builds 5 BM25Okapi field indexes│
│  Output: list[dict] each with:                                         │
│          id, title, year, genres, overview, keywords, tagline,         │
│          movie_key, bm25_score, bm25_rank, final_score=bm25_score     │
│  Dedup:  deduplicate_movies() called before return                     │
│                                                                        │
│  src/retrieval/fusion.py :: rrf_fusion()                               │
│  Input:  semantic list + BM25 list, top_k=RERANK_POOL                 │
│  Formula: rrf_score += weight / (RRF_K + rank + 1), RRF_K=60         │
│  Output: merged list sorted by rrf_score desc, final_score=rrf_score  │
│  Dedup:  deduplicate_movies() called on fused output                  │
└────────────────────────────────────────────────────────────────────── ┤
│
├─[Advanced + Hybrid]──────────────────────────────────────────────────── ┐
│  src/retrieval/reranker.py :: rerank()                                 │
│  Input:  query + candidate list (up to RERANK_TOP_K=50 after dedup)   │
│  Builds: document string per movie (title, year, genres, overview,     │
│          keywords) via build_movie_document()                          │
│  Calls:  src/models.py :: get_reranker() — BGE CrossEncoder           │
│  Scores: CrossEncoder.predict(pairs) → float per candidate            │
│  Output: list sorted by final_score (rerank + light priors)            │
│  Dedup:  deduplicate_movies() before AND after scoring                 │
└────────────────────────────────────────────────────────────────────── ┤
│
▼  Pipeline trims to top_k, deduplicates again
│
├─[Advanced + Hybrid, if use_llm=True]──────────────────────────────────  ┐
│  src/llm/langchain_ollama.py :: explain_movies_batch()                 │
│  Input:  query + top EXPLAIN_TOP_K(3) movies                          │
│  Sends to LLM: title, year, genres, overview[:360], keywords[:200]    │
│  Does NOT send: semantic_score, rrf_score, rerank_score               │
│  Output: list[str] explanations (fallback if LLM fails/times out)     │
│  Remaining movies: _fallback_explanation() deterministic text         │
└────────────────────────────────────────────────────────────────────── ┤
│
▼  app.py :: recommend_ui()
   Final safety dedup: deduplicate_movies(movies, prefer_score="final_score")[:top_k]
   Calls:  render_movie_cards()
   Output: HTML string — movie cards rendered into gr.HTML component
```

---

## 4. Basic Mode Pipeline

**Files involved:** `src/pipelines/basic.py`, `src/retrieval/query_processor.py`, `src/retrieval/filters.py`, `src/retrieval/semantic.py`, `src/utils/dedup.py`

```
User query
→ query_processor.normalize_query()      [English query normalization]
→ filters.parse_filters()                [optional year/rating filter]
→ semantic.semantic_search(top_k = max(top_k*4, top_k))
    → get_embedder() (BGE-M3)
    → ChromaDB cosine query
    → deduplicate_movies(prefer_score="semantic_score")
→ deduplicate_movies(prefer_score="semantic_score")   [pipeline-level]
→ set final_score = semantic_score for each movie
→ sort by final_score descending
→ return top_k results
```

| Property | Value |
|---|---|
| Semantic search | YES |
| BM25 | NO |
| RRF | NO |
| Reranker | NO |
| LLM expansion | NO |
| LLM explanation | NO |
| `final_score` | = `semantic_score` (cosine similarity, 0–1) |
| Deduplication | After semantic search + after pipeline sort |

**Why Basic is faster:** No model loading beyond the embedder, no BM25 index, no cross-encoder inference, no LLM call. The only compute is one embedding encode + one ChromaDB vector query.

**Candidate size:** `max(top_k * 4, top_k)` — e.g. if top_k=6 the semantic search fetches 24 candidates before dedup+trim.

---

## 5. Advanced Mode Pipeline

**Files involved:** `src/pipelines/advanced.py`, `src/retrieval/query_processor.py`, `src/retrieval/filters.py`, `src/retrieval/semantic.py`, `src/retrieval/bm25.py`, `src/retrieval/fusion.py`, `src/retrieval/reranker.py`, `src/utils/dedup.py`, `src/llm/langchain_ollama.py`, `src/llm/prompts.py`

```
User query
→ normalize_query()
→ expand_query() [LLM rewrite via Ollama llama3.2; falls back to original on failure]
→ expand_retrieval_query() [deterministic metadata terms for recall]
→ parse_filters()
→ semantic_search(top_k=CANDIDATE_POOL=300)
    → BGE-M3 encode → ChromaDB → semantic_score, semantic_rank
    → deduplicate (internal)
→ optional hyde_generate() when USE_HYDE_IN_ADVANCED and LLM_RETRIEVAL_ENABLED are true
    → semantic_search(hyde, top_k=CANDIDATE_POOL=300)
    → _rrf_two_semantic() fuses expanded-query and HyDE semantic lists
→ bm25_search(top_k=CANDIDATE_POOL=300)
    → field-aware BM25 over title/overview/genres/keywords/tagline
→ rrf_fusion(semantic_candidates, bm25_candidates, top_k=RERANK_POOL=80)
→ deduplicate_movies(prefer_score="rrf_score")   [pipeline-level]
→ rerank(expand_retrieval_query(normalized_query), candidates, top_k=top_k, rerank_pool=RERANK_TOP_K=50)
    → deduplicate_movies (before scoring)
    → build_movie_document() per candidate
    → CrossEncoder.predict() → rerank_score, final_score = rerank_score + quality/upstream priors
    → deduplicate_movies (after scoring)
    → sort by final_score
→ deduplicate_movies(prefer_score="final_score")
→ sort by final_score
→ trim to top_k
→ explain_movies_batch(query, top EXPLAIN_TOP_K=3)
    → single Ollama call with title/year/genres/overview/keywords
    → fallback for movies beyond EXPLAIN_TOP_K or on LLM failure
```

| Property | Value |
|---|---|
| Semantic search | YES (CANDIDATE_POOL=300) |
| BM25 | YES (CANDIDATE_POOL=300) |
| RRF | YES (semantic + BM25 fusion) |
| Reranker | YES (BGE bge-reranker-v2-m3) |
| LLM expansion | YES (expand_query before semantic search) |
| LLM explanation | YES (after final selection, top 3) |
| `final_score` | = `rerank_score` + vote-count quality prior + upstream retrieval prior + source-agreement bonus |

**Score lifecycle in Advanced:**
1. `semantic_score` created in `semantic.py`
2. `bm25_score` created in `bm25.py`
3. `rrf_score` created in `fusion.py`; `final_score = rrf_score` before reranking
4. `rerank_score` created in `reranker.py`
5. `final_score` becomes calibrated reranker score: `rerank_score` + quality/upstream/source-agreement priors

**LLM calls in Advanced:** with LLM retrieval enabled, Advanced can call expansion once and HyDE once before retrieval, then batch explanation once after final selection. `--no-llm` and the app LLM checkbox disable retrieval-side LLM calls.

---

## 6. Hybrid Mode Pipeline

**Files involved:** `src/pipelines/hybrid.py`, `src/retrieval/query_processor.py`, `src/retrieval/semantic.py`, `src/retrieval/bm25.py`, `src/retrieval/fusion.py`, `src/retrieval/reranker.py`, `src/utils/dedup.py`, `src/llm/langchain_ollama.py`

```
User query
→ normalize_query()
│
├──────────────────────────────────────────────────────────────────────
│  semantic_search(top_k=CANDIDATE_POOL=300)
│      semantic_score, semantic_rank, final_score=semantic_score
│      deduplicate internally
│      → sem [list of ~100 movies]
│
│  bm25_search(top_k=CANDIDATE_POOL=300)
│      weighted BM25 over 5 fields (title×1.0, overview×2.5, genres×1.0,
│      keywords×1.0, tagline×0.5)
│      bm25_score, bm25_rank, final_score=bm25_score
│      deduplicate internally
│      → bm [list of ~100 movies]
│  (semantic and BM25 run sequentially; could be parallelized in future)
├──────────────────────────────────────────────────────────────────────
│
→ deduplicate sem (prefer_score="semantic_score")
→ deduplicate bm  (prefer_score="bm25_score")
│
→ rrf_fusion(sem, bm, top_k=RERANK_POOL=80)
│      key: movie_key (stable title+year or movie_id)
│      rrf_score += weight / (RRF_K=60 + rank + 1)
│      SEMANTIC_WEIGHT=1.0, BM25_WEIGHT=1.0
│      movies appearing in both lists → single fused entry
│      preserves semantic_score, semantic_rank, bm25_score, bm25_rank
│      final_score = rrf_score
│      deduplicate on fused output
│      sorted by rrf_score desc, trimmed to top 50
│
→ deduplicate fused (prefer_score="rrf_score")
│
→ rerank(expand_retrieval_query(normalized_query), fused, top_k=top_k, rerank_pool=RERANK_TOP_K=50)
│      deduplicate before scoring
│      build_movie_document() → title + year + genres + overview[:600] + keywords[:200]
│      CrossEncoder.predict()
│      rerank_score set, final_score = rerank_score + quality/upstream priors
│      deduplicate after scoring
│      sort by final_score desc
│
→ deduplicate (prefer_score="final_score")
→ sort by final_score
→ trim to top_k
│
→ explain_movies_batch(query, top EXPLAIN_TOP_K=3)
│      single Ollama call; fallback for the rest
│
→ return final
```

| Property | Value |
|---|---|
| Semantic search | YES (CANDIDATE_POOL=300) |
| BM25 | YES (CANDIDATE_POOL=300, 5-field weighted) |
| RRF | YES (K=60, symmetric 1.0/1.0 weights) |
| Reranker | YES (BGE bge-reranker-v2-m3, RERANK_TOP_K=50) |
| LLM expansion | YES when `HYBRID_USE_LLM_EXPANSION=True`; safe fallback when Ollama is down |
| LLM explanation | YES (after final selection, top 3) |
| `final_score` | = `rrf_score` before reranking, then calibrated reranker score after |

---

## 7. Retrieval System

### Semantic Search (`src/retrieval/semantic.py`)

- **Model:** `BAAI/bge-m3` via `SentenceTransformer`, loaded as a lazy singleton from `src/models.py`.
- **Vector store:** ChromaDB `PersistentClient` at `data/chroma_bgem3/`, collection name `"movies"`, cosine distance space.
- **Query process:** Query is encoded with `normalize_embeddings=True` → cosine distance returned by ChromaDB → `semantic_score = 1 - distance`, clamped to `[0, 1]`.
- **Fields stored in ChromaDB metadata:** title, genres, release_date, vote_average, poster_path, overview (truncated to 500 chars). Keywords and tagline are **not** in ChromaDB metadata — they come from BM25's CSV path.
- **Deduplication:** `deduplicate_movies()` called immediately before returning.
- **ChromaDB ID format:** `"movie_{i}"` where `i` is the CSV row index from ingestion.

**Important note about metadata in ChromaDB vs CSV:** The `02. Embed_BGEM3.py` script stored only 6 metadata fields (title, genres, release_date, vote_average, poster_path, overview). Fields like `keywords`, `keywords_clean`, `genres_clean`, `tagline`, `vote_count`, `year` are **not** in ChromaDB metadata — semantic.py reconstructs `year` from `release_date` and adds `keywords` as an empty string (falling back to the metadata's absent key). The BM25 pipeline gets richer metadata because it reads the full CSV directly.

### BM25 Search (`src/retrieval/bm25.py`)

- **Implementation:** `rank_bm25.BM25Okapi` — one index per field.
- **Dataset:** Reads `data/movies_clean.csv` once into pandas on first call; cached in `_df` module-level global.
- **Fields indexed:**

| Field | Source column | Boost weight |
|---|---|---|
| title | `title` | 1.0 |
| overview | `overview` | 2.5 |
| genres | `genres_clean` | 1.0 |
| keywords | `keywords_clean` | 1.0 |
| tagline | `tagline` | 0.5 |

- **Tokenizer:** `re.compile(r"[a-z0-9]+")` lowercased — strips all punctuation.
- **Composite score:** `BM25_TITLE_BOOST * title_scores + ... + BM25_OVERVIEW_BOOST * overview_scores` (numpy vectorized).
- **Pool size:** `max(top_k * 2, top_k + 20)` pulled before dedup to ensure enough survivors.
- **Deduplication:** `deduplicate_movies()` called before final `top_k` truncation; `bm25_rank` re-stamped after dedup to be contiguous.

**Semantic vs BM25 difference:**
- Semantic search captures conceptual/thematic similarity using dense vector embeddings — it finds movies whose *meaning* matches the query even without shared keywords.
- BM25 captures keyword co-occurrence using inverted index term statistics — it finds movies that *literally contain* the same words as the query, weighted by field importance.

---

## 8. Fusion System (`src/retrieval/fusion.py`)

**Function:** `rrf_fusion(semantic_results, bm25_results, top_k=RERANK_POOL)`

**Formula:**
```
rrf_score[movie_key] += weight / (RRF_K + rank + 1)
```
where `RRF_K = 60`, `SEMANTIC_WEIGHT = 1.0`, `BM25_WEIGHT = 1.0`.

**Key used:** `movie_key` from `src/utils/dedup.get_movie_key()` — not list index, not raw id.

**Process:**
1. Iterate semantic list: for each movie compute its semantic contribution, initialise or update `fused[key]`.
2. Iterate BM25 list: for each movie compute its BM25 contribution; if already in `fused`, merge missing metadata (BM25 carries `keywords`, `tagline` that semantic might lack); update rrf_score accumulator.
3. Stamp `rrf_score` and `final_score = rrf_score` on every fused entry.
4. `deduplicate_movies(results, prefer_score="rrf_score")` — defence-in-depth.
5. Sort by `rrf_score` descending, return `[:top_k]`.

**Scores preserved:** `semantic_score`, `semantic_rank`, `bm25_score`, `bm25_rank`, `rrf_score` all live side-by-side on the fused dict.

**Metadata merge strategy:** BM25 fills in fields that are `None/""/0` on the semantic-side entry — this is how `keywords` and `tagline` propagate into the fused candidate for the reranker's `build_movie_document()`.

---

## 9. Reranker System (`src/retrieval/reranker.py`)

**Function:** `rerank(query, movies, top_k, rerank_pool=RERANK_TOP_K)`

**Model:** `BAAI/bge-reranker-v2-m3` (CrossEncoder), loaded as a lazy singleton via `src/models.py :: get_reranker()`.

**Document construction** (`build_movie_document()`):
```
Title: {title} ({year}).
Genres: {genres}.
Tagline: {tagline[:200]}
Overview: {overview[:600]}
Keywords: {keywords[:200]}
```
Overview is intentionally the longest component (600 chars) so the cross-encoder's attention budget is dominated by plot content rather than the short title field.

**Process:**
1. `deduplicate_movies(candidates, prefer_score="final_score")` — ensures no duplicate enters the cross-encoder.
2. Take `pool = deduped[:rerank_pool]` (max 50 candidates by default).
3. Build `[[query, doc] for doc in pool]`.
4. `CrossEncoder.predict(pairs)` → one float score per pair.
5. Stamp `rerank_score = float(s)` and calibrated `final_score` on each candidate.
6. `deduplicate_movies(pool, prefer_score="final_score")` removes any key collision introduced by title+year normalization edge cases.
7. Sort by `final_score` descending, return `[:top_k]`.

The reranker does **not** call the LLM. Its score is purely from the cross-encoder model.

---

## 10. Deduplication System (`src/utils/dedup.py`)

**Functions:** `get_movie_key()`, `deduplicate_movies()`, `find_duplicate_keys()`, `attach_movie_keys()`

### Key generation (`get_movie_key`)

Priority:
1. `movie_id` field → `"movie_id:{v}"` (real external TMDB id, rarely present in this dataset)
2. normalized `title` + extracted `year` → `"title:{normalized_title}|year:{year}"` ← **primary path**
3. `id` field (CSV row index, last resort) → `"id:{v}"`

Title normalization: lowercase → strip non-alphanumeric → collapse whitespace.

**Why title+year beats `id`:** The `id` field exposed by semantic.py and BM25 is the CSV row index — not a real TMDB identifier. The cleaned CSV can contain the same movie across multiple rows (different entries for the same film). Keying on title+year collapses those duplicates correctly.

### Deduplication call sites

| Call site | File | Score preference |
|---|---|---|
| After semantic retrieval | `semantic.py` | `"semantic_score"` |
| After BM25 retrieval (before dedup-based truncation) | `bm25.py` | `"bm25_score"` |
| Inside RRF fusion (on fused output) | `fusion.py` | `"rrf_score"` |
| After RRF in hybrid pipeline | `hybrid.py` | `"rrf_score"` |
| Before reranking | `reranker.py` | `"final_score"` |
| After reranking | `reranker.py` | `"rerank_score"` |
| After pipeline result in basic/advanced/hybrid | pipeline files | `"semantic_score"` / `"rerank_score"` |
| Final safety net in `app.py` | `app.py` | `"final_score"` |

### Merge on collision

When two candidates share the same `movie_key`, the stronger one (by `prefer_score`) is the **keeper**. Then `_merge_into(keeper, loser)` fills in any score fields the keeper is missing from the loser — so a movie that appeared in both semantic and BM25 lists ends up with both `semantic_score` and `bm25_score` on the same dict.

### Duplicate risks

- Two CSV rows can represent the same title+year movie with slightly different genres or overviews (e.g. re-releases, different editions). The dedup system merges them by title+year.
- A movie with a missing year gets key `"title:{name}|year:"` — two such movies could collide if they share a title. Low risk but theoretically possible.

---

## 11. Score Lifecycle

| Score field | Created in | Meaning | Modes that use it | Affects ranking | Displayed in UI |
|---|---|---|---|---|---|
| `semantic_score` | `semantic.py` | Cosine similarity between query embedding and document embedding (0–1) | All | Yes (Basic final sort; input to RRF rank) | Indirectly — contributes to `final_score` in Basic |
| `semantic_rank` | `semantic.py` | 0-based position in ChromaDB results | Hybrid (RRF uses it) | No direct sort | No |
| `bm25_score` | `bm25.py` | Weighted multi-field BM25 composite score (unbounded float) | Hybrid | Yes (input to RRF rank) | No |
| `bm25_rank` | `bm25.py` | 0-based position after dedup | Hybrid (RRF uses it) | No direct sort | No |
| `rrf_score` | `fusion.py` | Reciprocal Rank Fusion aggregate (small float, ~0.006–0.03) | Hybrid | Yes (sort before reranking) | No |
| `rerank_score` | `reranker.py` | CrossEncoder logit (can be negative; higher = better match) | Advanced, Hybrid | Yes (final sort) | Yes — purple pill labeled "🎯 {score}" |
| `final_score` | Set by each pipeline | Authoritative ordering score for that pipeline: Basic=semantic, post-RRF=rrf, post-rerank=rerank | All | Yes — always used for final sort | Yes — cyan pill labeled "{score} match" |

**What the UI "match" score shows:** `final_score` — always the score the pipeline actually ordered by. If `final_score` is absent, `app.py` falls back to `rerank_score → rrf_score → semantic_score` in that order (this is a display-only fallback; pipelines always set `final_score`).

**What the UI "🎯" rerank pill shows:** `rerank_score` — only visible when Advanced or Hybrid mode was used (where the reranker ran).

---

## 12. LLM and Explanation System

**Files:** `src/llm/langchain_ollama.py`, `src/llm/prompts.py`

### Which modes use LLM

| Mode | Query expansion | Explanation |
|---|---|---|
| Basic | NO | NO |
| Advanced | YES when `LLM_RETRIEVAL_ENABLED` is true | YES (if `with_explanation=True`) |
| Hybrid | YES when `HYBRID_USE_LLM_EXPANSION` and `LLM_RETRIEVAL_ENABLED` are true | YES (if `with_explanation=True`) |

### When LLM is called

- **Expansion** (Advanced and Hybrid when enabled): called once *before* semantic/BM25 retrieval, on the normalized query.
- **Explanation**: called once *after* the final top movies are selected, for the top `EXPLAIN_TOP_K=3` movies as a single batch call.

### What metadata is sent to LLM for explanation

Sent: title, year, genres, overview (truncated to 360 chars), keywords (truncated to 200 chars).

Not sent: semantic_score, bm25_score, rrf_score, rerank_score, final_score, vote_average, vote_count, poster_path, production_companies.

### Hallucination reduction

- System prompt explicitly forbids: plot details not in metadata, scenes, cast, awards, reviews, audience reactions, hidden meanings.
- The LLM is told to explicitly flag weak matches rather than invent connections.
- The `"same title, different plot"` formulation is specifically banned unless the overview truly supports it.
- Short replies (< 5 words) and replies that echo the query verbatim are rejected and replaced with the deterministic fallback.

### Fallback explanation (`_fallback_explanation`)

Deterministic, metadata-only. Logic:
1. If overview is missing → state match is weak due to limited metadata.
2. If query tokens overlap with overview/keyword tokens → name the shared terms.
3. If query tokens overlap with genre tokens only → say it is a limited genre match.
4. Otherwise → state match is weak, no terms overlap.

Never invents facts. Always grounds claims in what is present.

### Failure handling

Every LLM call (`expand_query`, `explain_movies_batch`) is wrapped in `concurrent.futures` with `LLM_TIMEOUT_SECONDS=25`. On `TimeoutError` or any `Exception`, the call returns the original query (expansion) or the fallback explanations (batch explain). The UI never fails due to LLM unavailability.

If `langchain-ollama` is not installed, `_AVAILABLE=False` disables all LLM paths silently; fallback explanations are always used.

### LLM is never called inside retrieval loops

Confirmed: no LLM call in `semantic.py`, `bm25.py`, `fusion.py`, or `reranker.py`. LLM is only invoked from pipeline files (`advanced.py`, `hybrid.py`) and only after final selection.

---

## 13. Config and Constants (`src/config.py`)

| Constant | Value | Purpose |
|---|---|---|
| `BASE_DIR` | `Path(__file__).parent.parent` | Project root |
| `DATA_DIR` | `BASE_DIR / "data"` | Data folder |
| `CHROMA_DIR` | `str(DATA_DIR / "chroma_bgem3")` | ChromaDB path |
| `MOVIES_CSV` | `str(DATA_DIR / "movies_clean.csv")` | BM25 dataset path |
| `COLLECTION_NAME` | `"movies"` | ChromaDB collection name |
| `DATASET_ROW_COUNT` | Source of truth in code | Cleaned/indexed movie row count |
| `DATASET_SOURCE` | Source of truth in code | Dataset provenance label |
| `DATASET_LANGUAGE_FILTER` | Source of truth in code | Active ingest language scope |
| `DATASET_MIN_VOTE_COUNT` | Source of truth in code | Minimum vote-count filter used by ingest |
| `EMBEDDING_MODEL` | `"BAAI/bge-m3"` | BGE-M3 embedding model |
| `RERANKER_MODEL` | `"BAAI/bge-reranker-v2-m3"` | BGE CrossEncoder |
| `LLM_MODEL` | `"llama3.2"` | Ollama model for expansion + explanation |
| `CANDIDATE_POOL` | `300` | Semantic and BM25 each retrieve this many |
| `RERANK_POOL` | `80` | RRF top-k fed into reranker pipeline |
| `RERANK_TOP_K` | `50` | Actual cross-encoder candidate count |
| `RERANK_VOTE_COUNT_WEIGHT` | `0.20` | Light vote-count prior after reranking |
| `RERANK_UPSTREAM_WEIGHT` | `0.12` | Preserves RRF/source retrieval strength after reranking |
| `RERANK_SOURCE_AGREEMENT_BONUS` | `0.05` | Small bonus when semantic and BM25 both found the candidate |
| `FINAL_TOP_K` | `5` | Default UI output size |
| `EXPLAIN_TOP_K` | `3` | Max LLM explanations per query |
| `INITIAL_TOP_K` | `= CANDIDATE_POOL` | Backward-compat alias |
| `BM25_TITLE_BOOST` | `1.0` | BM25 title field weight |
| `BM25_OVERVIEW_BOOST` | `2.5` | BM25 overview field weight (deliberately highest) |
| `BM25_GENRES_BOOST` | `1.0` | BM25 genres field weight |
| `BM25_KEYWORDS_BOOST` | `1.0` | BM25 keywords field weight |
| `BM25_TAGLINE_BOOST` | `0.5` | BM25 tagline field weight (lowest) |
| `RRF_K` | `60` | Standard RRF smoothing constant |
| `SEMANTIC_WEIGHT` | `1.0` | RRF semantic side weight |
| `BM25_WEIGHT` | `1.0` | RRF BM25 side weight |
| `HYBRID_USE_LLM_EXPANSION` | `True` | Lets Hybrid use LLM query expansion before deterministic expansion |
| `LLM_RETRIEVAL_ENABLED` | `True` | Runtime gate for LLM expansion and HyDE |
| `LLM_TIMEOUT_SECONDS` | `25` | Per-LLM-call timeout |
| `ENABLE_LLM_EXPLANATION` | `True` | Global LLM toggle |
| `LLM_MAX_RESULTS_TO_EXPLAIN` | `= EXPLAIN_TOP_K` | Alias used elsewhere |
| `DEBUG_RETRIEVAL` | `False` | Debug flag (currently unused in code logic) |
| `TMDB_IMAGE_BASE` | `"https://image.tmdb.org/t/p/w500"` | Poster URL base |

**Hardcoded paths check:** `01.clean_data.py` and `02. Embed_BGEM3.py` hardcode `"data/TMDB_movie_dataset_v11.csv"` and `"data/movies_clean.csv"` as strings (they are one-shot scripts, not imported at runtime — acceptable). All runtime files (`bm25.py`, `semantic.py`) use `MOVIES_CSV` and `CHROMA_DIR` from `config.py`. No runtime file hardcodes paths.

---

## 14. UI / App Behavior (`app.py`)

**Entry point:** `app.py` — run with `python app.py` → Gradio on `127.0.0.1:7860`.

**Gradio components:**
- `gr.Textbox` — query input (3-line)
- `gr.Dropdown` — pipeline mode selector (Basic / Advanced / Hybrid)
- `gr.Slider` — `top_k` (1–20, default 6)
- `gr.Checkbox` — `use_llm` toggle for LLM expansion/HyDE and explanations
- `gr.Button` — "Search Movies"
- `gr.HTML` — results output area
- `gr.Examples` — pre-set English example queries

**Handler:** `recommend_ui(query, top_k, use_llm, pipeline_mode)` sets the runtime LLM retrieval gate from the checkbox, dispatches to the correct pipeline `run()` function based on the dropdown string value, then calls `render_movie_cards()`.

**Final safety dedup:** `deduplicate_movies(movies, prefer_score="final_score")[:top_k]` runs on every result before rendering — this is the last line of defence against any duplicate that escaped the pipeline.

**Movie card rendering** (`render_movie_cards`): produces an HTML `<article>` per movie with:
- Rank badge (`#1`, `#2`, …)
- Poster image (from `TMDB_IMAGE_BASE + poster_path`) or placeholder
- Year pill, ⭐ TMDB rating pill, match score pill (cyan), rerank score pill (purple, only if present)
- Title (h3), genres (pink), overview text
- "AI Match Reason" box if `explanation` is non-empty

**Business logic in app.py:** Minimal. The only logic is: query validation (empty check), pipeline dispatch, the final dedup call, and HTML rendering. All retrieval, ranking, and explanation logic lives in `src/`.

---

## 15. Legacy Files

| File | Still used? | Delegates to | Notes |
|---|---|---|---|
| `recommend_bgem3.py` | Potentially (external callers) | `src/pipelines/advanced.py` | Thin wrapper with `recommend()` function; parameters `use_expansion`, `use_rerank`, `verbose` are accepted but ignored (Advanced always does them). Safe to keep for compatibility. Do not add new logic here. |
| `hybrid_recommend.py` | Potentially (external callers) | `src/pipelines/hybrid.py` | Thin wrapper with `hybrid_recommend()` function; `verbose` parameter accepted but ignored; `with_explanation` forced to `False`. Safe to keep. Do not add new logic here. |
| `01.clean_data.py` | Only to regenerate dataset | None | One-shot preprocessing. Run once when re-cleaning TMDB_movie_dataset_v11.csv. Not imported at runtime. |
| `02. Embed_BGEM3.py` | Only to rebuild ChromaDB | None | One-shot embedding ingestion. Run once to populate `data/chroma_bgem3/`. Not imported at runtime. Resume-safe (checks `already_done` count). |

**For new code:** Always use the `src/` structure. Never add retrieval or pipeline logic to the legacy wrappers.

---

## 16. Scripts and Tests (`scripts/quality_smoke_test.py`)

**Run commands:**
```bash
# Full run — all modes, top-6, with LLM
python scripts/quality_smoke_test.py

# Skip LLM (faster, deterministic fallback only)
python scripts/quality_smoke_test.py --no-llm

# Specific modes only
python scripts/quality_smoke_test.py --modes basic hybrid

# Custom top-k
python scripts/quality_smoke_test.py --top-k 5 --no-llm

# Custom queries
python scripts/quality_smoke_test.py --queries "movie about artificial intelligence"
```

**Benchmark queries (from AGENTS.md):**
1. "a stranded astronaut trying to survive on Mars"
2. "a mind-bending movie about dreams, memory, and reality"
3. "a dark revenge thriller where someone hunts down the people who wronged them"
4. "animated family adventure about friendship and growing up"
5. "a detective investigates a mysterious murder with many twists"
6. "movie about a toy cowboy and a space ranger becoming friends"

**Per result, printed:** `movie_key`, title, year, genres, `sem`, `bm25`, `rrf`, `rerank`, `final` scores, explanation text.

**Warnings triggered if:**
- Fewer than `min(top_k, 3)` results returned
- Duplicate `movie_key` in final list
- Duplicate `title+year` in final list
- Any movie missing `final_score`
- Hybrid mode produced no `rrf_score`
- Advanced/Hybrid produced no `rerank_score`
- Any explanation looks generic/unsupported (e.g. "must watch", "critically acclaimed", "same title")

**Compile check (syntax validation):**
```bash
python -m compileall app.py src scripts
python -m compileall recommend_bgem3.py hybrid_recommend.py
```

---

## 17. Architecture Compliance Checklist

| Rule | Status | Evidence | Notes |
|---|---|---|---|
| Same embedding model for indexing and querying | PASS | `02. Embed_BGEM3.py` uses `"BAAI/bge-m3"`. `src/config.py::EMBEDDING_MODEL = "BAAI/bge-m3"`. `semantic.py` calls `get_embedder()` which loads `EMBEDDING_MODEL`. | Fully consistent. |
| `BAAI/bge-m3` is used | PASS | `src/config.py` line 10. | |
| ChromaDB path is preserved | PASS | `config.py::CHROMA_DIR = str(DATA_DIR / "chroma_bgem3")`. `semantic.py` uses `CHROMA_DIR`. `02. Embed_BGEM3.py` uses same literal string. | |
| Dataset path is consistent | PASS | `config.py::MOVIES_CSV`. `bm25.py` imports `MOVIES_CSV`. `01.clean_data.py` writes `"data/movies_clean.csv"` (script-local hardcode, acceptable for one-shot). | |
| `app.py` is mostly UI | PASS | `app.py` contains only HTML helpers, a dispatcher, a final dedup call, and CSS. No retrieval logic. | |
| Retrieval logic is in `src/retrieval/` | PASS | `semantic.py`, `bm25.py`, `fusion.py`, `reranker.py`, `filters.py`, `query_processor.py` all in `src/retrieval/`. | |
| Pipeline logic is in `src/pipelines/` | PASS | `basic.py`, `advanced.py`, `hybrid.py` in `src/pipelines/`. | |
| LLM logic is in `src/llm/` | PASS | `langchain_ollama.py`, `prompts.py` in `src/llm/`. | |
| Shared model loading is centralized | PASS | `src/models.py` provides `get_embedder()` and `get_reranker()` as lazy singletons. | Uses global `_embedder`/`_reranker` vars, not `lru_cache`. Functionally equivalent to AGENTS.md recommendation. |
| Basic mode does not use LLM | PASS | `src/pipelines/basic.py` has no LLM import or call. `explanation = ""` for all results. | |
| LLM is not called inside retrieval/reranker loops | PASS | No LLM import in `semantic.py`, `bm25.py`, `fusion.py`, `reranker.py`. | |
| Advanced uses semantic + BM25 + RRF + reranker | PASS | `advanced.py` calls `semantic_search`, `bm25_search`, `rrf_fusion`, `rerank`. | |
| Hybrid uses semantic + BM25 + RRF + reranker | PASS | `hybrid.py` calls `semantic_search`, `bm25_search`, `rrf_fusion`, `rerank`. | |
| Final results are deduplicated | PASS | Dedup at each stage + final safety net in `app.py`. | |
| Score fields are separated | PASS | `semantic_score`, `bm25_score`, `rrf_score`, `rerank_score`, `final_score` are distinct dict keys; none overwrite each other except `final_score` which is intentionally updated through the pipeline. | |
| ChromaDB metadata contains keywords | WARNING | `02. Embed_BGEM3.py` stored only 6 metadata fields; `keywords` was not included. `semantic.py` returns `keywords: meta.get("keywords", "")` which will be `""` for ChromaDB-sourced candidates. Keywords are available when BM25 merges them in via fusion. | Advanced and Hybrid now both benefit from BM25 metadata merge for fused candidates, but semantic-only candidates can still have empty keywords. |

---

## 18. Current Strengths and Risks

### Strengths

- **Clean module separation:** UI, pipelines, retrieval, LLM, and utilities are each in their own layer. No cross-layer shortcuts.
- **Consistent deduplication:** 8 dedup call sites across the pipeline ensure the same movie cannot appear twice, even with the messy TMDB duplicate rows.
- **BM25 field weighting is well-calibrated:** Overview carries 2.5× weight vs. title at 1.0×, directly preventing title-keyword dominance that was a known problem.
- **Fallback chain:** LLM timeout → deterministic fallback → UI still shows results. The system is resilient to Ollama being slow or unavailable.
- **Metadata-grounded explanations:** The fallback explanation explicitly flags weak matches instead of hallucinating. The LLM prompts forbid invention.
- **Smoke test is practical:** It prints every score field, warns on duplicates, warns on missing scores, and detects generic explanations. Useful for catching regressions.
- **English metadata scope:** `query_processor.py` normalizes English user queries and adds deterministic metadata terms for candidate recall.
- **Resume-safe ingestion:** `02. Embed_BGEM3.py` checks `already_done` before re-embedding, so interrupted ingestion can be resumed.

### Risks

- **Keywords missing from ChromaDB metadata:** ChromaDB-sourced candidates still have empty keywords because keywords were not stored at ingestion time. Advanced and Hybrid now both merge BM25 metadata before reranking, so fused candidates get keywords, but semantic-only candidates can still have empty keyword text.
- **`vote_count` absent from ChromaDB metadata:** `semantic.py` returns `vote_count: int(meta.get("vote_count", 0))` — but `vote_count` was not stored in ChromaDB metadata by `02. Embed_BGEM3.py`. This always returns 0 for semantic-only candidates. The UI shows TMDB star rating (`vote_average`) correctly but `vote_count` is lost.
- **`genres_clean` vs `genres` inconsistency:** ChromaDB stores `genres` (raw TMDB format); BM25 reads `genres_clean`. The `genres` field shown in movie cards comes from ChromaDB's raw value for semantic results and from `genres_clean` for BM25 results. After RRF merge, BM25 fills in missing fields — but the displayed genres may differ slightly between modes.
- **Sequential LLM expansion + explanation:** In Advanced and Hybrid (when `HYBRID_USE_LLM_EXPANSION` is enabled), `expand_query` is called before retrieval and `explain_movies_batch` after. If Ollama is slow this can add 25 + 25 = 50 seconds of latency before timeout kicks in.
- **`RERANK_TOP_K=50` vs `RERANK_POOL=80`:** In `reranker.py`, the `rerank_pool` parameter defaults to `RERANK_TOP_K=50`, but `hybrid.py` and `advanced.py` pass `rerank_pool=RERANK_TOP_K`. The config `RERANK_POOL=80` is used as `top_k` in `rrf_fusion`. This is correct but the two constants (`RERANK_POOL` and `RERANK_TOP_K`) have similar names and different roles — easy to confuse.
- **No GPU guarantee:** `src/models.py` falls back to CPU automatically. On CPU, the BGE-M3 embedder and the CrossEncoder can be slow for large candidate pools.
- **BM25 index rebuilt on first call:** The BM25 index is not persisted; it is rebuilt in memory every process start from the CSV. With the current cleaned CSV size (see `DATASET_ROW_COUNT`) this takes a few seconds. Not a latency problem for long-running servers, but relevant for smoke tests.
- **`DEBUG_RETRIEVAL=False` unused:** The config has a debug flag but no code currently checks it — debug prints use unconditional `print()` calls instead. Verbose logs always appear in the console.

---

## 19. Suggested Next Steps

### Must fix now (actual bugs or inconsistencies)

1. **Keywords missing from ChromaDB metadata:** During ingestion (`02. Embed_BGEM3.py`), `keywords` (or `keywords_clean`) was not included in the `metadatas` dict. BM25 now supplies keywords for fused Advanced/Hybrid candidates, but semantic-only candidates still have empty keywords. Fix: add `"keywords": str(row.get("keywords_clean", ""))[:300]` to the metadata dict in `02. Embed_BGEM3.py` and re-run ingestion. This would require rebuilding ChromaDB — do not do this unless explicitly requested.

2. **`vote_count` always 0 for semantic results:** `vote_count` was not stored in ChromaDB metadata. `semantic.py` returns `int(meta.get("vote_count", 0))` which always gives 0. Not currently displayed in the UI but could affect future filtering logic.

### Nice to have

- Document the `DEBUG_RETRIEVAL` flag: either remove it (since it is unused) or wire it to suppress the `print()` calls in `bm25.py` and `models.py`.
- Rename `RERANK_POOL` to `RRF_OUTPUT_POOL` or `FUSION_TOP_K` to distinguish it clearly from `RERANK_TOP_K` (the cross-encoder pool size). Currently both names suggest reranking.
- Add `vote_count` and `keywords` (and optionally `tagline`) to the ChromaDB metadata schema documentation so future ingestion scripts know what fields to include.
- The `AGENTS.md` target structure lists `src/utils/formatting.py` and `src/utils/cache.py` as future files — currently neither exists. `_fallback_explanation` lives in `langchain_ollama.py` (AGENTS.md suggested `prompts.py` or `formatting.py`). Not a bug but worth noting.

### Later latency optimization

- **Batch LLM explanations are already done** (single call for top-3). Further gains: reduce `LLM_MAX_RESULTS_TO_EXPLAIN` from 3 to 2 if explanations are slow.
- **Parallelize semantic + BM25 retrieval** in `hybrid.py` using `concurrent.futures` or `asyncio` — both calls are independent and currently sequential.
- **Cache BM25 index** to disk using `pickle` or `shelve` so process restart does not rebuild from CSV.
- **Measure per-stage latency** — add `time.perf_counter()` around each stage in the pipelines and log it to console under `DEBUG_RETRIEVAL`. This will reveal where latency bottlenecks actually are before optimizing.
- **Cap `explain_movies_batch` to fewer movies** (e.g. 2 instead of 3) as a quick LLM latency knob.
- **Limit ChromaDB candidate pool size** only after measuring whether 100 is needed — for some queries a smaller initial pool (e.g. 60) might give equivalent quality with faster ANN lookup.

---

## 20. Final Short Summary

### What is the current architecture?

CineMatch is a modular Python recommendation system with a Gradio UI (`app.py`) that delegates to three pipeline variants (`src/pipelines/`). The retrieval layer (`src/retrieval/`) implements BGE-M3 semantic search via ChromaDB, field-aware BM25 over a pandas DataFrame, RRF fusion, and CrossEncoder reranking. The LLM layer (`src/llm/`) handles optional query expansion and metadata-grounded explanations via Ollama. A shared deduplication utility (`src/utils/dedup.py`) uses a stable `title+year` key to prevent duplicate movies at every stage. Configuration is centralized in `src/config.py` and model loading is centralized in `src/models.py`.

### Which pipeline should I trust for best quality?

**Hybrid** — it combines the semantic depth of BGE-M3 with the keyword precision of BM25, fuses them fairly via RRF, and applies the CrossEncoder reranker as a final quality gate. It is the most accurate pipeline for general queries and is set as the default in `app.py`.

### Which files should I read first as a developer?

1. `AGENTS.md` — project rules, constraints, and pipeline specs
2. `src/config.py` — all constants and paths
3. `src/pipelines/hybrid.py` — most complete pipeline; understand this first
4. `src/utils/dedup.py` — deduplication is central to correctness
5. `src/retrieval/fusion.py` — RRF logic, metadata merge strategy
6. `src/retrieval/reranker.py` — cross-encoder input construction
7. `app.py` — UI structure and final safety net

### Which commands should I run to validate the project?

```bash
# Syntax check all runtime modules
python -m compileall app.py src scripts

# Quality smoke test — all modes, deterministic only (fast)
python scripts/quality_smoke_test.py --no-llm

# Full smoke test with LLM explanations (slower, requires Ollama running)
python scripts/quality_smoke_test.py

# Legacy wrapper syntax check
python -m compileall recommend_bgem3.py hybrid_recommend.py

# Start the app
python app.py
```
