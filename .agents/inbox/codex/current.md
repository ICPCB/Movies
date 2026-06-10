# Ticket WEB-2A — CineMatch backend foundation (FastAPI + SQLite + intent schema)

Goal:
Create the new backend foundation for the CineMatch web app: a FastAPI service in a new `api/` package and a new `engine/` package, with SQLite persistence (favorites / watchlist-with-watched / search history / recommendation cache / mood labels), a strict user-intent JSON schema + validator, and an intent→query builder. Deterministic and fully testable WITHOUT loading any ML model. This implements §2, §7 (cinematch.db), §9 (query builder skeleton), and §12 of CINEMATCH_ULTRAPLAN.md (read it first).

Current repo state:
- Branch `main`, HEAD `8a4bc15`. Production engine lives in `src/` (PROTECTED — read-only). Gradio app `app.py` (read-only). Dataset `data/movies_clean.csv` (~160k rows; columns include: title, overview, genres, keywords, tagline, release_date, year, vote_average, vote_count, poster_path, document). ChromaDB at `data/chroma_bgem3/` (do NOT touch).
- `api/` and `engine/` do not exist yet — you create them.

Files to read but not change:
- CINEMATCH_ULTRAPLAN.md (sections 2, 7, 9, 10, 12)
- src/config.py, src/utils/dedup.py, src/pipelines/hybrid.py, src/pipelines/basic.py (interfaces only)
- AGENTS.md

Files allowed to change/create (exact):
- api/__init__.py
- api/main.py
- api/db.py
- api/db_models.py
- api/schemas.py
- api/routes_library.py
- api/routes_search.py
- api/tests/__init__.py
- api/tests/conftest.py
- api/tests/test_library.py
- api/tests/test_intent.py
- api/tests/test_search_routes.py
- engine/__init__.py
- engine/intent_schema.py
- engine/intent_query_builder.py
- engine/movie_store.py
- engine/recommender.py
- requirements-api.txt

Files forbidden to change: everything else, especially src/**, app.py, eval/**, data/**, docs/**, .agents/** (except your outbox report), labels/** (does not exist yet — do not create).

Exact implementation rules:

1. `engine/intent_schema.py`:
   - `INTENT_SCHEMA` dict (JSON-Schema draft 2020-12) for the intent object exactly as in ULTRAPLAN §2: fields mode (enum: mood, content, hybrid, category, random), user_moods (list[str]), desired_film_moods (list[str]), avoid_film_moods (list[str]), plot_elements (list[str]), genres_include/genres_exclude (list[str]), era {min_year, max_year, nullable ints}, tone {darkness: -1..1, intensity: 0..1}, constraints {min_rating nullable float}, free_text_query (str, required), confidence (0..1). additionalProperties: false.
   - `validate_intent(obj) -> tuple[bool, list[str]]` using `jsonschema` lib; on failure returns all error messages.
   - `empty_intent(free_text, mode="content") -> dict` helper producing a valid minimal intent.

2. `engine/intent_query_builder.py`:
   - `build_query(intent: dict) -> dict` returning `{"query_text": str, "filters": {"min_year","max_year","min_rating","genres_include","genres_exclude"}, "boosts": {"desired_film_moods","avoid_film_moods","tone"}}`.
   - query_text = join of plot_elements if present else free_text_query; for mood mode append desired_film_moods words to query_text. Pure function, no I/O, deterministic.

3. `engine/movie_store.py`:
   - Lazy singleton loading `data/movies_clean.csv` via pandas once; expose:
     - `get_movie(tmdb_id) -> dict | None` (movie profile per ULTRAPLAN §3, mood fields empty for now; include poster_path/backdrop_path if column exists, else "")
     - `list_genres() -> list[str]` (unique split of genres column)
     - `browse(genre=None, min_year=None, max_year=None, sort="popularity", page=1, page_size=24) -> list[dict]` — sort options: popularity→vote_count desc, rating→vote_average desc (tie-break vote_count), year→year desc. Deterministic ordering with stable tie-breaks.
     - `random_pick(min_votes=200, min_rating=6.0, seed: int | None = None) -> dict` — weighted by vote_count, seedable for tests.
   - The CSV path must come from `src.config.MOVIES_CSV` (import constant only — no behavior change).
   - Accept an optional injected DataFrame for tests (`movie_store.load(df=...)`) so tests never read the real 33 MB CSV.

4. `api/db.py` + `api/db_models.py`:
   - SQLAlchemy 2.x, SQLite at `data/cinematch.db`, WAL mode pragma, `get_session` dependency; DB URL overridable via env `CINEMATCH_DB_URL` (tests use in-memory/tmp).
   - Tables exactly: favorites(id PK, movie_key UNIQUE, tmdb_id, title, poster_path, added_at), watchlist(id PK, movie_key UNIQUE, tmdb_id, title, poster_path, watched BOOL default 0, added_at, watched_at NULLABLE), search_history(id PK, mode, query_text, intent_json TEXT, created_at), rec_cache(intent_hash PK, results_json TEXT, created_at, ttl_seconds INT), mood_labels(movie_key PK, film_mood_tags_json TEXT, provenance TEXT).
   - `create_all` on startup.

5. `api/routes_library.py`: CRUD per ULTRAPLAN §12 — GET/POST/DELETE /api/favorites (POST body: movie_key, tmdb_id, title, poster_path; DELETE /api/favorites/{movie_key}), GET/POST /api/watchlist, PATCH /api/watchlist/{movie_key} (toggles or sets `watched`, sets watched_at), DELETE /api/watchlist/{movie_key}, GET /api/history (latest 50), DELETE /api/history. Idempotent POSTs (upsert by movie_key).

6. `api/routes_search.py`:
   - POST /api/parse-intent {text, mode?} → tier-1 ONLY for now: returns `empty_intent(text, mode)` enriched by build_query — NO LLM call (Phase 7 adds tiers). Validates with validate_intent before returning.
   - POST /api/recommend {free_text?, intent?, mode, page=1, page_size=20} → resolves intent (validate; if invalid → empty_intent fallback), records search_history, checks rec_cache (hash = sha256 of canonical JSON of intent + page_size), on miss calls `engine.recommender.recommend(intent, pool_size)` and caches the full pool. Response: {results: [...], page, total_pool, cache_hit}.
   - GET /api/categories → list_genres + fixed era buckets. GET /api/random → random_pick. GET /api/movies/{tmdb_id} → get_movie or 404. GET /api/health → {status, model_warm: false}.

7. `engine/recommender.py`:
   - `recommend(intent, pool_size=100, pipeline=None) -> list[dict]`. Default pipeline lazily imports `src.pipelines.hybrid` and calls its existing public run function with the built query_text (read its signature first; pass with_explanation=False). Apply filters from build_query post-hoc (year/rating/genre filtering on returned dicts), add deterministic `match_reason` string (matched plot terms/genres). DO NOT modify anything in src; treat it as a library.
   - `pipeline` parameter is injectable; tests MUST inject a stub returning fixed movie dicts so no model loads.
   - Page slicing for reroll: page N = slice [(N-1)*page_size : N*page_size] of the pool.

8. `api/main.py`: FastAPI app, include routers, CORS allow http://localhost:5173, startup hook that calls create_all; model pre-warm ONLY when env `CINEMATCH_WARM=1` (never in tests; warm = call src.models.get_embedder/get_reranker in a background thread).

9. `requirements-api.txt`: fastapi, uvicorn[standard], sqlalchemy>=2, jsonschema, httpx, pytest (versions free). If imports missing in the environment, run `pip install -r requirements-api.txt` (this network use is authorized for dependency install only).

10. Tests (pytest, FastAPI TestClient, tmp sqlite via env var, injected DataFrame + stub pipeline — zero model loading, zero real-CSV reads, zero network):
   - test_intent.py: schema accepts valid intents (all 5 modes), rejects bad enum/extra field/out-of-range tone; empty_intent validates; build_query deterministic outputs.
   - test_library.py: favorites add/list/delete idempotent; watchlist add + PATCH watched toggle sets watched_at; history records and clears.
   - test_search_routes.py: /api/recommend with stub pipeline returns results + match_reason, second identical call returns cache_hit=true, page=2 returns next slice; /api/random seeded determinism; /api/movies 404; /api/parse-intent returns valid intent.

Acceptance criteria:
- All listed files exist; `python -m pytest api/tests -q` passes with NO model/CSV/network access (tests run < 30s).
- `python -c "from api.main import app"` succeeds.
- No file outside the allowed list is modified (`git status --short` shows only allowed paths + your outbox report).
- No src/* edits, no retrieval behavior change, no LLM/Ollama calls anywhere in api/ or engine/ (the only src usage is importing constants/pipeline functions as a library).

Validation commands (run exactly):
```
python -m pytest api/tests -q
python -c "from api.main import app; print('app ok')"
git status --short
```

Dependencies: none (Phase 0/1 complete).
Risk level: medium (new packages only; protected areas untouched).
Reviewer: Claude (lead session) — write report, do not commit.

Stop conditions: any need to edit src/* or app.py; pytest failure you cannot fix within allowed files; missing dependency that pip cannot install locally. On stop, report STOPPED with details.

Required final report → write to `.agents/outbox/codex/current_result.md`:
1. Verdict: PASS / FAIL / STOPPED / NEEDS_REVIEW
2. Files changed
3. Artifacts created
4. Validation commands and results (paste pytest tail)
5. Git status summary
6. Risks or caveats
7. Whether anything was committed (must be NO — Claude commits)
8. Exact next recommended step
