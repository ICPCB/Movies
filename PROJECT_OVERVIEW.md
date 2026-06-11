# CineMatch — Project Overview

CineMatch turns "I feel lonely but want something warm" or "a spy betrayed by his organization" into ranked, explainable picks from a local index of 27,762 real TMDB movies. This document explains how the system works end to end, where every piece of data comes from, and how the project was built and evaluated.

The contract that shapes every design decision:

```text
AI parses user intent into structured JSON.
Movie database stores real movies.
Recommendation engine searches, filters, scores, and reranks real movies.
The model never invents a movie recommendation.
```

LLMs are confined to three jobs — extracting structure from user text, optional query expansion, and phrasing explanations — and every one of them has a deterministic fallback. Ranking itself is always model-scored retrieval over the real index.

## 1. Request flow

```text
user text / mood chips                       (web/ React UI)
        │
        ▼
intent JSON  ─ tier-1 lexicon parser (always, <5 ms, deterministic)
             ─ tier-2 Ollama few-shot (optional, non-mood fields only)
        │                                    (engine/intent_parser.py)
        ▼
query text + filters + boosts                (engine/intent_query_builder.py)
        │
        ▼
hybrid retrieval over 27,762 movies          (src/ — protected engine)
  BGE-M3 semantic (pool 1500)  +  field-boosted BM25 (pool 1500)
        → RRF fusion (K=15, pool cap 800; API trims to 100)
        → cross-encoder rerank (BAAI/bge-reranker-v2-m3, top 50)
        → blend with vote-count and upstream priors → safety filter → dedup
        │
        ▼
intent layer post-processing                 (engine/recommender.py)
  era / rating / genre filters → film-mood rank nudges
  → deterministic match reasons → film_mood_tags attached
        │
        ▼
cached, paginated results                    (api/routes_search.py)
  SQLite rec_cache keyed on intent hash; reroll = next page of the
  same reranked pool; explanations fetched lazily after render
```

## 2. The intent layer (`engine/`)

One JSON schema (draft 2020-12, `additionalProperties: false`) serves all five modes — mood, content, hybrid, category, random. The key design decision: **`user_moods` (how the user feels) and film moods (what the film should be) are separate closed vocabularies**, bridged only by a fixed 18-entry mapping table. A lonely user gets warm films, not lonely ones — and no LLM ever decides that mapping.

**Tier 1 — deterministic lexicon (always runs, <5 ms).** Feeling words and multi-word phrases from a 205-word vocabulary (plus 72 body sensations) map to 18 feeling categories; greedy set cover picks the fewest categories explaining every matched word. Regexes extract era ("90s", "before 1999", "2000 to 2010"), 19 TMDB genres (with sci-fi synonyms), and minimum-rating constraints. Two guards keep it honest: feeling words count as *user* moods only when the text reads like a feeling ("I'm…", "feeling…") or the caller asked for mood mode — so "a tense thriller" never inverts into avoid-tense; and everything after a desire marker ("want", "in the mood for") describes the *film*, so those words become desired film moods, never user moods.

**Tier 2 — Ollama few-shot (optional).** When asked (`use_llm`), local `llama3.2` extracts only the non-mood fields — plot elements (max 8) and genres validated against the closed list. Mood fields always come from tier 1. Any failure — Ollama down, malformed JSON, schema violation — silently falls back to the tier-1 intent, so end-to-end schema validity is 100% by construction.

Measured on the 2026-06-11 eval (tier 1, deterministic):

| Metric | mood_v1 (50 queries) | content set (65 queries) |
|---|---|---|
| Schema validity | 1.00 | 1.00 |
| Mode accuracy | 0.98 | — |
| F1: user_moods / desired / avoid | 0.86 / 0.90 / 0.97 | — |
| Mood false-positive rate | — | 7.7% (5 queries, all genuinely mood-phrased) |

A LoRA-tuned local parser (Llama-3.2-1B, weights and a prior smoke run in the gitignored `cinematch-llama/`) is planned but deferred: the few-shot baseline ships first, and the adapter replaces it only if it wins on field-F1.

## 3. The retrieval engine (`src/` — protected)

The production engine predates the web app and is treated as a read-only library; all new behavior is layered on top. Per-request, the hybrid pipeline runs:

1. **Deterministic mood/query preprocessing** (`src/retrieval/mood_preprocessor.py`, `query_processor.py`) and regex filter parsing.
2. **Semantic search** — `BAAI/bge-m3` sentence embeddings over ChromaDB (cosine, pool 1500).
3. **BM25** — five field-specific indexes with boosts: overview 2.5, title/genres/keywords 1.0, tagline 0.5; deterministic synonym expansion.
4. **RRF fusion** — reciprocal-rank fusion with K=15 (deliberately low to amplify deep semantic hits), equal source weights, fused pool capped at `RERANK_POOL` (800 for eval; the API trims to 100 for interactivity).
5. **Cross-encoder rerank** — `BAAI/bge-reranker-v2-m3` scores the top 50 fused candidates against the deterministic intent query (never an LLM rewrite); the final score blends in a log-normalized vote-count prior (0.08) and the upstream fusion score (0.12).
6. **Safety filter + dedup** — dark-genre candidates are demoted (not removed) for safety-sensitive mood intents; every stage dedups on a stable title+year movie key.

Basic mode is semantic-only; Advanced adds HyDE (a synthetic overview embedded as a second semantic query). The Gradio app (`app.py`) exposes all three pipelines directly.

## 4. The mood system (`labels/`)

Every mood artifact has explicit, honest provenance — nothing AI-generated is ever recorded as human gold:

| Artifact | Size | Provenance |
|---|---|---|
| `user_mood_vocab.json` | 18 categories, 205 feeling words + 72 body sensations | `human_provided` (verbatim from the owner's Feelings & Body Sensations vocabulary) |
| `user_mood_map.json` | 18 entries: category → desired/avoid film moods | `authored_static_table` — the **only** bridge between user moods and film moods |
| `film_mood_vocab.json` | closed enum of 24 film moods | `authored_in_ultraplan` |
| `mood_rules.jsonl` | 213 rules (17 genre + 196 keyword) | AI-drafted (Gemini, prompt preserved in `labels/drafts/`), human-reviewed and fixed before acceptance |
| `movie_mood_labels.jsonl` | 27,758 movies, 96.2% with ≥1 tag | `deterministic_rules` — pure substring/equality rules, no LLM, byte-identical reruns |

`labels/validate_labels.py` is the hard gate: every tag must be in the 24-mood enum, every category must exist in both vocab and map, desired/avoid must not overlap, and the movie-label file must have exactly 27,758 unique keys with `deterministic_rules` provenance on every line.

At serving time the mood layer never touches retrieval scores. `engine/recommender.py` applies **scale-free rank nudges** to the reranked pool: a movie whose tags overlap the desired film moods rises 5 ranks per hit, an avoid-mood hit sinks it 8 ranks (both capped at 2 counted hits). Match reasons ("matches: spy, betrayal · warm") are assembled deterministically from the signals that actually fired.

## 5. Data

- **Source:** Kaggle TMDB movie dataset v11 (~597 MB raw). `01.clean_data.py` keeps released, non-adult movies with English metadata, ≥50-char overviews, and ≥50 votes, dedupes on title+year, and emits `data/movies_clean.csv` — **27,762 rows** (the authoritative count lives in `src/config.py: DATASET_ROW_COUNT`; the CSV's physical line count is higher because overviews contain newlines).
- **Vector index:** `02. Embed_BGEM3.py` embeds a structured document per movie with BGE-M3 into ChromaDB (`data/chroma_bgem3/`, ~277 MB, 27,762 vectors).
- **App database:** `data/cinematch.db` (SQLite, WAL) is created on API startup — favorites, watchlist (with watched tracking), search history, the recommendation cache, and a mood-labels table. It is runtime-generated and not version-controlled.
- **Attribution:** TMDB data and image CDN; "Powered by TMDB — not endorsed or certified by TMDB" appears in the UI footer. Posters/backdrops come from `image.tmdb.org` with a local placeholder fallback.

## 6. Backend (`api/`)

FastAPI with 16 routes under `/api`: `parse-intent`, `recommend`, `explain/{cache_key}/{movie_key}`, `categories`, `random`, `movies/{tmdb_id}`, `health`, plus full CRUD for favorites, watchlist (PATCH toggles watched), and history. Highlights:

- **Caching:** `rec_cache` keys on the SHA-256 of the canonical intent JSON + page size, storing the whole reranked pool with a 1-hour TTL — so pagination and reroll are near-free cache hits (~8 ms measured).
- **Speed:** the API process trims the fused pool to 100 candidates and disables LLM query expansion by default (env-overridable) *before* the engine is imported; eval processes keep the `src/` defaults, so historical metrics stay reproducible. `CINEMATCH_WARM=1` pre-loads models in a background thread, and the first cold pipeline call is serialized to protect ChromaDB initialization.
- **Async explanations:** `/api/recommend` never generates explanations. The UI fetches them lazily per movie from `/api/explain`, which runs Ollama (grounded-evidence contract, deterministic fallback) in a worker thread.

Measured latency (8-query benchmark against a warm local server, indicative): uncached p50 ≈ 1.76 s / p95 ≈ 2.64 s; cache hits p50 ≈ 8 ms. The plan's <800 ms target is not yet met — the remaining cost sits inside the protected engine (pure-Python BM25, cross-encoder throughput); `CINEMATCH_RERANK_POOL=50` would buy ~350 ms at a quality cost and is deliberately left as an owner decision.

## 7. Frontend (`web/`)

React 19 + TypeScript + Vite 6 + Tailwind v4. A dark cinematic theme — near-black `#0b0d12` base, warm gold `#e8b34b` accent, deep crimson washes, film-grain overlay, Outfit display type over Inter body — across three pages:

- **Discover (Home):** hero search with four tabs — Mood (18 chips generated from the label files; free text goes to the server's lexicon parser), Movie Description (hybrid mode if chips are also selected), Category (genres + six era buckets), Random ("Spin the reel"). Results render in a responsive 2–6 column poster grid with rating badges, mood pills, hover match reasons, pagination, and a Reroll button that advances through the cached pool.
- **Detail modal:** backdrop hero, metadata, mood tags, match reason, lazy-loaded explanation, and favorite / watchlist / watched actions.
- **Library & History:** server-backed favorites and watchlist (watched/unwatched filters), and re-runnable search history.

The UI never invents mood→film-mood mappings: chip data is generated from the same label files the backend uses.

## 8. Evaluation (`eval/`)

The harness predates the web app and gates every change to ranking behavior:

- **Pipeline:** `run_pipelines.py` (3 modes × all queries, top-15 candidates) → `llm_pregrade.py` (local-LLM silver grades 0–3, parse-rate gate ≥95%) → `compute_metrics.py`.
- **Metrics:** Hit@K, strict-Hit@K, MRR@K, strict-MRR@K, NDCG@K at K = 5/10/15, with stratified bootstrap 95% CIs and per-mode/per-axis breakdowns. (Recall and MAP are not computed.)
- **Label honesty:** silver labels are `silver_llm_pregrade`; human-reviewed regrades are recorded as `human_reviewed_ai_assisted`, never `human_gold`. Only the 2026-06-07 combined baseline carries final merged-gold metrics (basic/advanced/hybrid NDCG@5 = 0.797 / 0.797 / 0.762).
- **Regression gates:** new layers must not regress the non-mood baseline. The Phase-8 final-gate runs on all 65 content queries passed with deltas within ±0.02, and the web-app phases added zero diffs to `src/` or existing eval scripts by construction.
- **New for the web app:** `mood_v1.jsonl` (50 deterministic mood/hybrid queries — gold intent fields, no relevance labels yet), the intent-parser eval (§2), a latency benchmark, and a mood smoke test (8/8 sampled queries returned desired-mood-tagged results in the top 10).

Eval runs live in `eval/runs/` with manifest, config snapshot, candidates, labels, and metrics per run; most are untracked (`-nogit` convention) with curated artifacts whitelisted into git.

## 9. How it was built

The repo is run under a multi-agent governance protocol (`AGENTS.md`, `CLAUDE.md`): Claude Code as planner/reviewer/lead, Codex CLI for bounded implementation tickets, one write-capable agent at a time, exact-path file scopes, validation commands per ticket, and a checkpoint ledger (`docs/superpowers/AUTONOMOUS_CHECKPOINT_LEDGER.md`) recording evidence for every gate. Production retrieval code (`src/`) cannot be touched without an explicit ticket, and no gate passes on verbal report alone.

The web app shipped as eight phases on `main`, each validated and checkpointed:

| Phase | What shipped | Commit |
|---|---|---|
| 0 | Legacy cleanup | `f402156` |
| 1 | Master plan (`CINEMATCH_ULTRAPLAN.md`) | `8a4bc15` |
| 2 | FastAPI backend + intent schema + SQLite (Codex ticket WEB-2A) | `83d5df4` |
| 3 | Mood label layer — vocabularies, map, rules, 27,758 movie labels | `5af4ec0` |
| 4 | React frontend | `d320b15` |
| 5 | Speed pass — warm-up, hot-path config, async explanations, latency benchmark | `0545010` |
| 6 | Eval extension — mood_v1 queries + serving-path mood layer | `11f5315` |
| 7 | Two-tier intent parser + eval | `c089913` |
| 8 | Final documentation (this document) | — |

## 10. Known limitations and deferred work

- **Latency:** warm uncached searches land at ~1.8 s p50, above the 800 ms target; the remaining cost is inside the protected engine (see §6).
- **LoRA intent parser** (plan §14): dataset design and a smoke-tested training setup exist; deferred until it can beat the few-shot baseline on field-F1.
- **mood_v1 relevance labels:** the 50 mood queries have deterministic gold *intent* fields but no graded relevance labels yet — that needs a labeling ticket with honest provenance.
- **Chroma metadata gap:** keywords and vote_count aren't in ChromaDB metadata (BM25 supplies them post-fusion); re-ingesting is a protected long job, deferred.
- **Tier-1 genre negation:** "no horror please" still lexicon-matches Horror into `genres_include`; tier 2 compensates by setting `genres_exclude` when used.
- **Timestamps** in the app database are local time, not UTC.
- **Naming trap:** `RERANK_POOL` caps the *fused pool entering* the rerank stage; the cross-encoder itself scores `RERANK_TOP_K=50` candidates. `docs/ARCHITECTURE.md` predates the May 2026 retuning — `src/config.py` is authoritative for all pool sizes.
