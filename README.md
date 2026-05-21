# CineMatch

CineMatch is a Python movie recommendation app built on the TMDB dataset. It lets a user describe the kind of movie they want in natural language, then returns ranked movie recommendations through a Gradio web UI.

The project combines dense semantic search, BM25 keyword retrieval, reciprocal rank fusion, cross-encoder reranking, and optional local LLM explanations through Ollama.

## Features

- Gradio web interface for interactive movie search.
- Three recommendation modes:
  - Basic: BGE-M3 semantic search only.
  - Advanced: query expansion, semantic search, BM25, RRF fusion, reranking, and optional explanations.
  - Hybrid: semantic search plus BM25, RRF fusion, reranking, and optional explanations.
- TMDB movie posters and metadata in the result cards.
- English TMDB dataset cleaning pipeline.
- Persistent ChromaDB vector index using `BAAI/bge-m3`.
- Optional local LLM support using `llama3.2` through Ollama.

## Project Structure

```text
.
|-- app.py                         # Gradio UI entry point
|-- 01.clean_data.py               # Cleans the raw TMDB CSV
|-- 02. Embed_BGEM3.py             # Builds the ChromaDB embedding index
|-- recommend_bgem3.py             # Legacy wrapper for the advanced pipeline
|-- hybrid_recommend.py            # Legacy wrapper for the hybrid pipeline
|-- data/
|   |-- TMDB_movie_dataset_v11.csv # Raw TMDB dataset
|   |-- movies_clean.csv           # Cleaned dataset
|   `-- chroma_bgem3/              # Persisted ChromaDB vector store
|-- docs/
|   `-- ARCHITECTURE.md            # Detailed architecture notes
|-- scripts/
|   `-- quality_smoke_test.py      # Pipeline smoke test and benchmark script
`-- src/
    |-- config.py                  # Shared paths, model names, and retrieval settings
    |-- models.py                  # Lazy model loaders
    |-- llm/                       # Ollama and prompt helpers
    |-- pipelines/                 # Basic, advanced, and hybrid pipelines
    |-- retrieval/                 # Semantic, BM25, fusion, reranking, filters
    `-- utils/                     # Deduplication and debug helpers
```

## Requirements

- Python 3.10 or newer
- A working `data/movies_clean.csv`
- A working `data/chroma_bgem3/` vector index
- Optional: Ollama with the `llama3.2` model for LLM query expansion and explanations

Install the main Python packages:

```bash
pip install gradio pandas numpy torch sentence-transformers chromadb rank-bm25 langchain-ollama tqdm
```

If you want LLM features, install Ollama separately and pull the configured model:

```bash
ollama pull llama3.2
```

## Quick Start

From the project root:

```bash
python app.py
```

The app starts a Gradio server on:

```text
http://127.0.0.1:7860
```

In the UI, enter a movie description, choose a pipeline, set the number of results, and click Search Movies.

## Rebuild the Data

If the cleaned CSV and vector index already exist, you can skip this section.

Start with the raw TMDB file at:

```text
data/TMDB_movie_dataset_v11.csv
```

Clean the dataset:

```bash
python 01.clean_data.py
```

Build the BGE-M3 ChromaDB index:

```bash
python "02. Embed_BGEM3.py"
```

Note: the embedding script refuses to add vectors to a non-empty Chroma collection. If you intentionally want to rebuild embeddings from scratch, remove the existing `data/chroma_bgem3/` directory first.

## Pipeline Modes

| Mode | Description | Best for |
| --- | --- | --- |
| Basic | Semantic search with BGE-M3 only | Fast searches |
| Advanced | Query expansion, semantic search, BM25, RRF fusion, reranking, optional explanations | Accurate semantic and keyword matching |
| Hybrid | Semantic search, BM25, RRF fusion, reranking, optional explanations | Best overall ranking quality |

## Smoke Test

Run the benchmark smoke test from the project root:

```bash
python scripts/quality_smoke_test.py
```

Useful options:

```bash
python scripts/quality_smoke_test.py --modes Basic Hybrid
python scripts/quality_smoke_test.py --top-k 5 --no-llm
```

## Configuration

Main settings live in `src/config.py`, including:

- Data paths
- ChromaDB collection name
- Embedding model
- Reranker model
- Ollama model
- Candidate pool sizes
- Dataset stats and ingest-scope constants
- BM25 field weights
- Hybrid fusion weights
- LLM timeout and explanation limits

Run `python scripts/print_dataset_stats.py` after rebuilding data to confirm the `DATASET_*` constants still match the live CSV.

## Notes

- The app is optimized for English TMDB metadata.
- The first search can be slow because embedding and reranking models are loaded lazily.
- LLM features are optional. If `langchain-ollama` or Ollama is unavailable, the recommender still works without generated explanations.
- More detailed internals are documented in `docs/ARCHITECTURE.md`.
