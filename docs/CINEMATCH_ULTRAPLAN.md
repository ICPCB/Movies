# CINEMATCH ULTRAPLAN

Master plan for evolving CineMatch into a full local movie-recommendation web app.
Approved 2026-06-10 (single Human approval; run is fully autonomous from here).

Core principle (non-negotiable):

```text
AI parses user intent into structured JSON.
Movie database stores real movies.
Recommendation engine searches, filters, scores, and reranks real movies.
The model never invents a movie recommendation.
```

Everything runs **local**: local Ollama LLM, local BGE models, local ChromaDB, local SQLite. The only network touch is the TMDB image CDN for poster `<img>` URLs (free, no API key; placeholder fallback when offline).

---

## 1. Product vision

Tell CineMatch how you **feel** ("lonely but want something warm, not depressing"), what you **want to watch** ("a spy betrayed by his organization"), or **both** — and get real, explainable movie picks in under a second, with a cinematic dark UI for browsing, favoriting, and tracking what you've watched.

Three search styles + two browse styles:

| Mode | Input | Engine path |
|---|---|---|
| Mood | feeling words / mood chips | user-mood lexicon → film-mood filter/boost over retrieval |
| Movie Description | plot/content text | semantic + BM25 hybrid retrieval (existing engine) |
| Hybrid | feeling + plot | plot drives retrieval, mood filters/boosts |
| Category | genre/era picks | metadata browse, no LLM |
| Random | one click | quality-floored weighted random |

## 2. User intent JSON schema

One schema for all modes. **`user_moods` (how the user feels) and `film_moods` (what the film should be) are separate fields with separate vocabularies** — a lonely user wants a warm film, not a lonely one. The translation goes through a fixed mapping table (§8), never free LLM judgment.

```json
{
  "mode": "mood | content | hybrid | category | random",
  "user_moods": ["lonely"],
  "desired_film_moods": ["warm", "heartwarming"],
  "avoid_film_moods": ["bleak", "depressing"],
  "plot_elements": ["spy", "betrayed by his organization", "clear his name"],
  "genres_include": [], "genres_exclude": [],
  "era": { "min_year": null, "max_year": null },
  "tone": { "darkness": -0.5, "intensity": 0.7 },
  "constraints": { "min_rating": null },
  "free_text_query": "<original user text>",
  "confidence": 0.0
}
```

Validation: JSON Schema + closed-enum checks. Parser failure of any kind → fall back to raw-text hybrid retrieval. Search never blocks on the LLM.

## 3. Movie profile JSON schema

Built from `data/movies_clean.csv` + derived fields:

```json
{
  "tmdb_id": 0, "movie_key": "<src/utils/dedup.get_movie_key>",
  "title": "", "year": 0, "genres": [], "overview": "",
  "keywords": [], "tagline": "",
  "vote_average": 0.0, "vote_count": 0, "popularity": 0.0,
  "poster_path": "", "backdrop_path": "",
  "film_mood_tags": ["warm"],
  "tone_scores": { "darkness": 0.0, "intensity": 0.0 }
}
```

`film_mood_tags` come from the deterministic labeling pass (§8) and live in a sidecar file + SQLite, never mutating `movies_clean.csv`.

## 4. Mood-based parsing

Tier 1 (hot path, <5 ms): deterministic lexicon. The ~230-word Feelings & Body Sensations vocabulary (user-provided, §8) maps each detected feeling word → one of 18 feeling categories → desired/avoid film moods via the fixed 18-entry map. Extends the pattern of `src/retrieval/mood_preprocessor.py` (new module; `src/` untouched).

Tier 2 (only when Tier 1 confidence is low): local Ollama llama3.2 few-shot → strict intent JSON, schema-validated. Raw-text retrieval results render immediately while Tier 2 refines.

## 5. Content/plot-based parsing

Plot text goes to the existing hybrid retrieval (BGE-M3 semantic + BM25 → RRF) — this is what Phase 8 eval already validated. The parser adds structure on top: `plot_elements` (entities/actions/themes), genre hints, era — used for filters and boosts, never as a replacement for retrieval.

## 6. Hybrid parsing

Parser fills both mood and plot fields. Plot is the primary retrieval signal; mood is a post-retrieval layer: `desired_film_moods` overlap bonus, `avoid_film_moods` penalty, tone-darkness penalty. Weights are config constants in the new app layer (same style as `src/config.py`).

## 7. Movie database preparation

- **Reuse as-is:** `data/movies_clean.csv` (160,511 rows cleaned from Kaggle TMDB v11) and `data/chroma_bgem3/` (27,762 embedded movies, BGE-M3). Cleaning pipeline provenance: `01.clean_data.py`, `02.Embed_BGEM3.py` (kept).
- **License:** Kaggle TMDB dataset is free; TMDB requires attribution — UI footer shows "This product uses TMDB data. Powered by TMDB." No TMDB API key needed (CSV + image CDN only).
- **Images:** `https://image.tmdb.org/t/p/w342{poster_path}` / `w780{backdrop_path}`; local placeholder when offline.
- **Known gap (deferred):** keywords + vote_count are not in ChromaDB metadata; BM25 supplies them post-fusion. Re-ingest is a protected long job — only if a later ticket needs it.
- **New app DB** `data/cinematch.db` (SQLite, WAL mode):
  - `favorites(movie_key, tmdb_id, added_at)`
  - `watchlist(movie_key, tmdb_id, watched BOOL, added_at, watched_at)`
  - `search_history(id, mode, query_text, intent_json, created_at)`
  - `rec_cache(intent_hash, results_json, created_at, ttl)`
  - `mood_labels(movie_key, film_mood_tags_json, provenance)`

## 8. Movie mood/content labeling

User-mood vocabulary seed: **Feelings & Body Sensations list (Practices-FeelingsSensations.pdf, supplied by the project owner)** — ~230 unique feeling words in 18 categories + ~70 body sensations. Stored verbatim; zero hallucination risk.

| File | Lines/entries | Content | Provenance |
|---|---|---|---|
| `labels/user_mood_vocab.json` | ~230 words → 18 categories (+~70 body sensations mapped to nearest category) | user feeling word → feeling category | `human_provided` |
| `labels/user_mood_map.json` | 18 entries | feeling category → desired + avoid film moods | static authored table |
| `labels/film_mood_vocab.json` | ~24 entries | closed enum of FILM moods | authored |
| `labels/mood_rules.jsonl` | ~200 lines | TMDB genre/keyword → film mood rules | authored rules |
| `labels/movie_mood_labels.jsonl` | **27,762 lines** (one per indexed movie) | per-movie film_mood_tags from rules; fully deterministic, no LLM | `deterministic_rules` |
| `eval/queries/mood_v1.jsonl` | ~50 lines | mood/hybrid eval queries | authored |
| `training/intent_pairs.jsonl` | 3,000 train + 300 val + 300 test | query → intent JSON | `ai_draft` → `cross_model_reviewed` |

**Draft → review → validate chain for generative artifacts:** Gemini CLI drafts (fallback Codex CLI); 9 parallel Claude Haiku subagents + Codex review disjoint slices (invalid tags, user/film-mood confusion, nonsense mappings); the final gate is always the **deterministic validator** — every tag must be in the closed enums, every movie_key must exist in the dataset; invalid line = rejected, never silently kept. Provenance recorded honestly; never `human_gold`.

## 9. Retrieval / search

Existing engine **unchanged** (`src/*` protected): BGE-M3 semantic (pool 1500) + field-boosted BM25 → RRF (K=15) → cross-encoder rerank. New thin layer in `engine/` translates intent JSON → query text + filters + boosts. Category = pure metadata filter over the CSV (no LLM, no embedding). Random = weighted random above a quality floor (vote_count ≥ 200, vote_average ≥ 6.0, tunable).

## 10. Scoring / reranking + latency budget

Post-rerank intent adjustments (new layer): film-mood overlap bonus, avoid-mood penalty, era/genre soft filters, dedup via existing `deduplicate_movies()`. Match reasons are generated **deterministically** from the signals that fired ("matches: spy, betrayal · warm · 90s"); Ollama phrasing streams in afterward using the existing grounded-or-fallback discipline in `src/llm/`.

Hot-path budget (warm, target <800 ms perceived):

| Stage | Budget |
|---|---|
| Tier-1 intent parse (lexicon) | <5 ms |
| Query embed (BGE-M3, warm singleton) | 50–150 ms |
| BM25 (in-memory) + RRF | <35 ms |
| Cross-encoder rerank, interactive pool **100** (eval mode keeps 800) | 200–500 ms |
| Mood/intent adjustments + dedup | <10 ms |
| `rec_cache` hit (repeat/near-dup intent) | <50 ms total |

Reroll = next slice of the already-reranked pool (deterministic). Explanations and Tier-2 parsing are async — never on the render path.

## 11. Evaluation

- Reuse `eval/` harness, metrics (NDCG@5, MRR, Recall@K, MAP), and provenance flow.
- Add `eval/queries/mood_v1.jsonl` (~50 mood/hybrid queries built from the 18 categories).
- Intent-parser eval: JSON-validity rate ≥99%, per-field F1 vs held-out test pairs; few-shot baseline vs LoRA.
- Gate: new layers must not regress existing hybrid-mode metrics (compare against `eval/runs/2026-06-07-combined-nogit` baseline).
- New latency benchmark script: p50/p95 per stage, saved as a run artifact.

## 12. Backend API

FastAPI in new `api/` package (no `src/*` edits), models pre-warmed at startup via `src/models.py` singletons:

```text
POST /api/recommend        {intent | free_text, mode, page}  → ranked real movies + match reasons
POST /api/parse-intent     {text} → intent JSON (tier1 + optional tier2)
GET  /api/movies/{tmdb_id} → full profile (+ mood tags)
GET  /api/categories       → genre/era browse rows
GET  /api/random           → quality-floored random pick
GET/POST/DELETE /api/favorites
GET/POST/PATCH  /api/watchlist     (PATCH toggles watched)
GET/DELETE      /api/history
GET  /api/explain/{cache_key}/{movie_key} → async Ollama explanation
GET  /api/health
```

SQLite via SQLAlchemy; `rec_cache` keyed by normalized-intent hash; CORS for the Vite dev server.

## 13. Frontend UI/UX

React + Vite + Tailwind. Dark cinematic theme: near-black `#0b0d12` base, warm gold `#e8b34b` + deep red accents, Outfit/Inter type, rounded-2xl poster cards, hover scale + glow, skeleton loaders, backdrop-blur top nav. Not an admin dashboard; movies only.

- **Home:** hero search with mode tabs (Mood / Movie Description / Category / Random), mood chips (from the 18 categories), poster category rows.
- **Results:** responsive 2→6-column card grid — poster, title, year, genres, rating, mood tags, match reason; **Reroll** button; pagination.
- **Detail modal:** backdrop hero, overview, metadata, actions: ♥ favorite · + watchlist · ✓ watched.
- **Library:** favorites + watchlist with watched/unwatched filter. **History:** past searches, re-runnable.
- Footer: "Powered by TMDB" attribution.

## 14. Intent-parser training plan (Llama-3.2-1B + LoRA)

**Local weights CONFIRMED (2026-06-10):** `cinematch-llama/Llama-3.2-1B/` (model.safetensors 2.36 GB, **base** variant — single EOS 128001, no chat template; fine for LoRA structured-output training). The folder also contains a reusable prior smoke run: `scripts/train_stage1.py` + `test_stage1.py`, `config/stage1_smoke.yaml`, `mood_examples_seed_v1_120.jsonl` (120 mood seed examples), `stage1/data/` train/val/test splits, and `outputs/stage1_smoke_lora/` adapters (checkpoints 20/30 + test report). Phase 7 builds on this instead of starting cold. Folder is gitignored (`cinematch-llama/`) — weights/adapters are never committed.

**Owner decision (2026-06-11):** base variant re-verified (eos 128001, no chat template, eos token `<|end_of_text|>`); train the local **base** weights with the fixed prompt-format contract (spec §6.1, `training/prompt_format.py`). Downloading Llama-3.2-1B-Instruct is the fallback only if the spec §5 eval gate fails.

1. PEFT LoRA on the local base weights: r=16, α=32, dropout 0.05, target q/k/v/o projections; 3,600-pair dataset (§8, seeded from the existing 120 mood examples); 2–3 epochs; metric = JSON validity + field-F1 on held-out test.
2. Runtime stays few-shot Ollama llama3.2 until the adapter beats the few-shot baseline on field-F1; baseline ships first regardless.
3. Optional manual disk cleanup (owner's call, not automated): `Llama-3.2-1B/original/` (2.36 GB duplicate `.pth` format, only needed for llama-stack) and `outputs/stage1_smoke_lora/checkpoint-20/` (~80 MB superseded by checkpoint-30).

## 15. MVP scope

- **M0:** cleanup ✔ + this plan + FastAPI + SQLite + React shell + Description search end-to-end fast.
- **M1:** mood chips + lexicon layer, Category, Random, favorites/watchlist/watched, history, cache, reroll/pagination, async explanations.
- **M2:** mood label files, eval extension, few-shot intent parser, LoRA if unblocked.
- **Out of scope:** auth/multi-user, live TMDB API enrichment, cloud deployment.

## 16. Immediate next steps

Phase 2 backend foundation → Phase 3 mood layer → Phase 4 frontend → Phase 5 speed pass → Phase 6 eval extension → Phase 7 intent parser → Phase 8 final docs (README.md + PROJECT_OVERVIEW.md). One ticket at a time, ledger checkpoint after each phase, Codex CLI for bounded implementation tickets, codegraph/graphify for lookups.

**Resilience:** on any model usage/rate limit (Gemini, Codex, Haiku, or this session), the run waits and resumes from ledger + `.remember/remember.md` state — never aborts, never silently skips.

## Assumptions

- The 27,762-movie ChromaDB index is the recommendation universe (quality-filtered subset of the 160k cleaned rows).
- TMDB image CDN counts as static assets, not an "API," under the local-only rule.
- Ollama with llama3.2 is installed and runnable locally (graceful disable already exists in `src/llm/`).
- The existing `src/` engine remains protected; all new behavior lives in `api/`, `engine/`, `labels/`, `web/`.
- Interactive rerank pool 100 is an app-layer config; eval reproduces historical behavior with pool 800.

## Blockers (auto-fallback, non-pausing)

- `meta-llama/Llama-3.2-1B-Instruct` is gated → substitute local model / few-shot parser (logged).
- Offline machine → posters show placeholders; everything else unaffected.
- `.tmp/` + two `.pytest_cache` dirs are permission-locked → gitignored, deleted when unlocked.
