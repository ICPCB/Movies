from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

CHROMA_DIR = str(DATA_DIR / "chroma_bgem3")
MOVIES_CSV = str(DATA_DIR / "movies_clean.csv")
COLLECTION_NAME = "movies"

# Dataset stats -- single source of truth.
# Update these when the ingest filter chain in 01.clean_data.py changes.
# Verify with: python scripts/print_dataset_stats.py
DATASET_ROW_COUNT: int = 27762
DATASET_SOURCE: str = "TMDB movie metadata"
DATASET_LANGUAGE_FILTER: str = "All original languages with English TMDB metadata"
DATASET_MIN_VOTE_COUNT: int = 50

EMBEDDING_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
LLM_MODEL = "llama3.2"

# Retrieval staging:
#   CANDIDATE_POOL — wide first pass (semantic / BM25 each return this many)
#   RERANK_POOL    — how many fused candidates the cross-encoder scores
#   FINAL_TOP_K    — default UI output size
#   EXPLAIN_TOP_K  — how many of the final results get an LLM explanation
#
# Increased from 300 to 1500 to capture movies ranked 1000+ semantically
# (e.g., Memento, Tenet for "palindromic timeline"). Complex queries with
# nuanced semantic intent need wider candidate pools. RRF fusion ensures
# duplicates across semantic/BM25 are deduplicated, so the wider pool
# doesn't significantly slow reranking. The cross-encoder remains the
# quality gate — this just gives it more diverse candidates to choose from.
CANDIDATE_POOL = 1500
RERANK_POOL = 800
RERANK_TOP_K = 50
FINAL_TOP_K = 5
EXPLAIN_TOP_K = 3

# Reranker calibration.
#
# The cross-encoder is the main relevance signal. However, for complex
# queries, we also need to balance upstream signals:
#
# - RERANK_VOTE_COUNT_WEIGHT: Reduced from 0.20 → 0.08. Vote count (popularity)
#   was over-suppressing nuanced semantic matches. Memento/Tenet have high votes
#   but should rank on relevance-to-query, not just popularity. Lighter weight
#   preserves quality tier while letting cross-encoder score decide.
#
# - RERANK_UPSTREAM_WEIGHT: Reduced from 0.20 → 0.12. The previous value
#   over-weighted upstream RRF evidence, causing the cross-encoder's
#   rerank_score to be overridden for candidates with high upstream scores
#   but moderate rerank scores (e.g., q10's [REC] target, Dep #7).
#
# - RERANK_SOURCE_AGREEMENT_BONUS: Increased from 0.05 → 0.10. When both
#   semantic and BM25 agree (movie appears in both retrieval results), it's
#   strong evidence of relevance. Boosting this helps complex queries where
#   both dense and sparse signals validate the match.
#
# Net effect: Cross-encoder score remains primary. Popularity is deemphasized.
# Upstream evidence is trusted. Movies that pass both retrieval stages get
# a meaningful boost. This fixes queries where semantic/BM25 consensus shows
# subtle intent that vote counts would otherwise drown out.
RERANK_VOTE_COUNT_WEIGHT = 0.08
RERANK_UPSTREAM_WEIGHT = 0.12
RERANK_SOURCE_AGREEMENT_BONUS = 0.10

# Kept for backward compatibility with older imports / wrappers.
INITIAL_TOP_K = CANDIDATE_POOL

# BM25 field boost weights.
#
# Title is the smallest weight on purpose. Without this rebalance, a movie
# whose title literally contains query words (e.g. "Stranded" for the Mars
# query, "Memory" for the dreams/memory query) outranks movies whose
# *overview* genuinely matches the query intent. Overview is what the
# user is actually describing, so it carries the most BM25 weight here.
BM25_TITLE_BOOST = 1.0
BM25_OVERVIEW_BOOST = 2.5
BM25_GENRES_BOOST = 1.0
BM25_KEYWORDS_BOOST = 1.0
BM25_TAGLINE_BOOST = 0.5

# RRF
# Reduced from 60 to 15 to give weak semantic matches better visibility.
# When a movie ranks 1000+ (like Memento at 1031), traditional RRF with K=60
# gives it tiny contribution: 1/(60+1031+1) ≈ 0.0009. Lower K amplifies
# these weak signals so the reranker can still evaluate them. K=15 keeps
# strong BM25 title matches from dominating, while boosting semantic intent.
RRF_K = 15
# Symmetric weighting on the two sources keeps the fusion honest — we let
# semantic and BM25 vote evenly and rely on the reranker to break ties.
# Lower BM25_WEIGHT (e.g. 0.8) if a benchmark case shows BM25 literal hits
# still drowning semantic intent after query expansion.
SEMANTIC_WEIGHT = 1.0
BM25_WEIGHT = 1.0

# Hybrid stability (Phase 3): when True, hybrid.py runs the same LLM
# query expansion Advanced uses, then routes the expanded query into
# BOTH semantic_search and bm25_search. The reranker sees only the
# deterministic, title-free intent query (not the LLM rewrite), so it can
# score by stated intent without inheriting an LLM-added answer.
# expand_query already has its own timeout/fallback, so this is safe when
# Ollama is down (it returns the normalized query unchanged).
HYBRID_USE_LLM_EXPANSION = True
LLM_RETRIEVAL_ENABLED = True

# Phase 6a — Hypothetical Document Embedding (HyDE).
#
# When True, advanced.py asks the LLM to write a short synthetic TMDB-
# style overview for the query and embeds THAT for semantic retrieval,
# instead of embedding the raw user query. This places the embedded
# vector inside the same prose distribution as real overviews, which
# helps the embedder land closer to the actual target movie even when
# the user's wording is vague or paraphrased. hyde_generate() returns
# "" on timeout/outage, in which case advanced.py falls back to the
# regular expanded query — so Ollama being down is safe.
USE_HYDE_IN_ADVANCED = True

# LLM call budget. Keep this small — explanations run sequentially in Ollama
# and a runaway prompt blocks the UI.
LLM_TIMEOUT_SECONDS = 25
ENABLE_LLM_EXPLANATION = True
LLM_MAX_RESULTS_TO_EXPLAIN = EXPLAIN_TOP_K

DEBUG_RETRIEVAL = False

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
