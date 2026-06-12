# CineMatch

CineMatch is a local-first movie recommendation app. Tell it how you **feel** ("lonely but want something warm, not depressing"), what you **want to watch** ("a spy betrayed by his organization"), or both — and it returns real, explainable movie picks from a 27,762-movie TMDB index, with a cinematic dark web UI for browsing, favoriting, and tracking what you've watched.

Everything runs on your machine: local BGE models, local ChromaDB, local SQLite, and a local Ollama LLM for the optional pieces. The only network touch is the TMDB image CDN for posters (no API key; placeholder fallback when offline).

The core principle is non-negotiable:

```text
AI parses user intent into structured JSON.
Movie database stores real movies.
Recommendation engine searches, filters, scores, and reranks real movies.
The model never invents a movie recommendation.
```

See [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) for the full architecture, data provenance, and evaluation story.

## Search modes

| Mode | Input | Engine path |
|---|---|---|
| Mood | feeling words / 18 mood chips | LoRA intent parser / mood chips → user/film-mood fields → filters and rank boosts over retrieval |
| Movie Description | plot/content text | BGE-M3 semantic + BM25 hybrid retrieval with cross-encoder reranking |
| Hybrid | feeling + plot | plot drives retrieval, mood filters/boosts the ranking |
| Category | genre / era picks | metadata browse, no models involved |
| Random | one click | quality-floored weighted random (200+ votes, rating ≥ 6.0) |

## How it's put together

```text
web/      React 19 + Vite + Tailwind v4 dark cinematic UI (port 5173)
api/      FastAPI backend — 16 routes, SQLite (favorites, watchlist,
          history, result cache, mood labels), model warm-up (port 8000)
engine/   Intent layer — LoRA parser with deterministic/Ollama fallbacks,
          intent schema + query builder, movie store, recommender adapter
src/      Production retrieval engine (protected) — BGE-M3 semantic +
          field-boosted BM25 → RRF fusion → cross-encoder rerank
labels/   Mood vocabularies, mapping tables, and 27,758 deterministic
          per-movie film-mood labels — all with honest provenance
eval/     Eval harness — graded relevance metrics, intent-parser eval,
          latency benchmark, regression gates
training/ Intent-LoRA dataset pipeline — deterministic 3,600-record
          generator + fixed prompt contract; the gate-passed V6 E4 adapter
          serves locally from the gitignored cinematch-llama/ directory
data/     movies_clean.csv (27,762 rows), chroma_bgem3/ vector index,
          cinematch.db app database (runtime-generated)
```

The `engine/` layer treats `src/` strictly as a read-only library: mood logic is applied as post-retrieval filters and rank nudges, never by modifying the retrieval engine itself.

## Requirements

- Python 3.10+ with a project venv (the API must run under it — see below)
- `cinematch-llama/.venv` with PyTorch, Transformers, PEFT, and bitsandbytes
  for the local intent-LoRA sidecar (loads the base model in 4-bit NF4 so it
  fits alongside the retrieval models on an 8 GB GPU)
- Node 18+ for the web frontend
- `data/movies_clean.csv` and the `data/chroma_bgem3/` vector index (ship with the project or rebuild below from the [Kaggle TMDB dataset](https://www.kaggle.com/datasets/asaniczka/tmdb-movies-dataset-2023-930k-movies))
- Optional: [Ollama](https://ollama.com) with `llama3.2` for explanations, LLM query expansion, and tier-2 intent parsing — everything degrades gracefully without it

Install backend dependencies into the venv:

```powershell
pip install pandas numpy torch sentence-transformers chromadb rank-bm25 langchain-ollama tqdm
pip install -r requirements-api.txt
```

Optional LLM features:

```powershell
ollama pull llama3.2
```

Frontend:

```powershell
npm install --prefix web
```

## Quick start (web app)

From the repo root, start the API under the venv (global Python lacks the engine deps):

```powershell
$env:CINEMATCH_WARM = "1"
venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

`CINEMATCH_WARM=1` pre-loads the embedding and reranker models in the background; `GET /api/health` reports `model_warm: true` when ready. Without it, the first search pays the model-loading cost.

The API automatically starts `scripts/lora_server.py` with
`cinematch-llama/.venv`. `GET /api/health` reports
`intent_lora_ready: true` when the V6 E4 adapter is ready. If the local model
or training venv is missing, intent parsing falls back to the deterministic
Tier-1 parser instead of breaking the web app.

In a second terminal, start the frontend:

```powershell
npm run dev --prefix web
```

Open **http://localhost:5173** — the Vite dev server proxies `/api` to port 8000.

## Rebuild the data

Skip this if `data/movies_clean.csv` and `data/chroma_bgem3/` already exist.

```powershell
# 1. Clean the raw Kaggle TMDB dump — download TMDB_movie_dataset_v11.csv from
#    https://www.kaggle.com/datasets/asaniczka/tmdb-movies-dataset-2023-930k-movies
#    and place it at data/TMDB_movie_dataset_v11.csv first
python 01.clean_data.py

# 2. Build the BGE-M3 ChromaDB index (refuses a non-empty collection;
#    delete data/chroma_bgem3/ first to rebuild from scratch)
python "02. Embed_BGEM3.py"

# 3. Regenerate the deterministic per-movie mood labels and validate
python labels/build_movie_mood_labels.py
python labels/validate_labels.py --movie-labels

# 4. Confirm the DATASET_* constants still match the live CSV
python scripts/print_dataset_stats.py
```

`data/cinematch.db` (favorites, watchlist, history, result cache) is created automatically on API startup.

## Configuration

Engine settings live in `src/config.py`: data paths, `BAAI/bge-m3` embedding model, `BAAI/bge-reranker-v2-m3` reranker, candidate pool sizes, BM25 field weights, RRF fusion constants, and LLM timeouts.

The API process layers its own runtime knobs on top via environment variables (the protected `src/` defaults are untouched for eval reproducibility):

| Env var | Default | Effect |
|---|---|---|
| `CINEMATCH_WARM` | off | `1` = pre-load models in the background at startup |
| `CINEMATCH_RERANK_POOL` | `100` | fused-candidate pool entering the rerank stage (eval keeps 800) |
| `CINEMATCH_LLM_EXPANSION` | off | `1` = enable Ollama query expansion on the serve path |
| `CINEMATCH_LORA_ENABLED` | `1` | `0` = disable the local LoRA parser and use the fallback parser |
| `CINEMATCH_LORA_URL` | `http://127.0.0.1:8765` | local LoRA sidecar address |
| `CINEMATCH_LORA_TIMEOUT` | `30` | per-request LoRA timeout in seconds |
| `CINEMATCH_LORA_4BIT` | `1` | `0` = load the sidecar base model in bf16 instead of 4-bit NF4 (needs ~2 GB more VRAM) |
| `CINEMATCH_DB_URL` | `sqlite:///data/cinematch.db` | SQLAlchemy database URL (tests use in-memory) |

## Tests and evaluation

```powershell
# API + engine unit tests (28 tests, hermetic — no models, CSV, or network)
venv\Scripts\python.exe -m pytest api/tests -q

# Eval-harness unit tests (model-free)
python -m unittest discover -s eval/tests -t .

# Training-pipeline unit tests (prompt format + dataset builder, model-free)
python -m pytest training -q

# Intent-parser eval (tier 1, deterministic, offline)
python -m eval.scripts.intent_parser_eval

# Latency benchmark + retrieval smoke test (need a running, warm API)
python eval/scripts/latency_benchmark.py
python scripts/quality_smoke_test.py --no-llm
```

The full graded-relevance eval pipeline (`eval/scripts/run_pipelines.py` → `llm_pregrade.py` → `compute_metrics.py`) computes Hit@K, strict-Hit@K, MRR@K, strict-MRR@K, and NDCG@K (K = 5/10/15) with bootstrap confidence intervals — see [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md#evaluation) and `eval/README.md`.

## Attribution

This product uses TMDB data ([Kaggle TMDB movie dataset v11](https://www.kaggle.com/datasets/asaniczka/tmdb-movies-dataset-2023-930k-movies)) and the TMDB image CDN. **Powered by TMDB** — not endorsed or certified by TMDB.

## More documentation

- [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — architecture, mood system, data provenance, evaluation results, development history
- `docs/ARCHITECTURE.md` — detailed engine internals and current serving/retrieval constants
- `docs/intent-lora-spec.md` — dataset spec and acceptance gate for the intent-parser LoRA
