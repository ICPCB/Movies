---
title: Code audit method
parent: README.md
section: 9
---

# 9. Code audit method

[Index](README.md) · Prev: [Ablation matrix](06-ablation-matrix.md) · Next: [Prioritization & tickets](08-prioritization-and-ticket-schema.md)

## 9.1 Scope

| Layer | Files | Why |
|---|---|---|
| Retrieval | `src/retrieval/{semantic,bm25,fusion,reranker,filters,query_processor}.py` | Where ranking quality is made or lost |
| Pipelines | `src/pipelines/{basic,advanced,hybrid}.py` | Orchestration bugs, sequencing, missing dedup |
| LLM | `src/llm/{langchain_ollama,prompts}.py` | Prompt quality, timeout handling, fallbacks |
| Shared | `src/utils/dedup.py`, `src/models.py`, `src/config.py` | Dedup correctness, model loading, magic numbers |
| Smoke test | `scripts/quality_smoke_test.py` | Does it catch the failure modes we find? |
| Data pipeline (read-only, narrow) | `01.clean_data.py`, `02. Embed_BGEM3.py` | **Only where they affect index/data quality, schema, metadata availability, or ChromaDB ingestion.** Not a general refactor audit. |

Explicitly out of scope: `app.py` UI rendering, legacy wrappers (`recommend_bgem3.py`, `hybrid_recommend.py`).

## 9.2 Finding categories

| Cat | Meaning | Example |
|---|---|---|
| **C1 Correctness** | Code does something other than what it claims | Stale `get_movie_key()` docstring + outdated logic |
| **C2 Library-misuse** | Deprecated, suboptimal, or against documented best practice | `CrossEncoder.predict()` without `batch_size` |
| **C3 Configuration** | Magic numbers without justification, or conflicting with library defaults | A constant lacking rationale |
| **C4 Quality-leak** | Information that could improve ranking is silently dropped | Missing fields from ChromaDB metadata |
| **C5 Test-gap** | Smoke test misses a real failure mode | No assertion that `final_score` is monotonic by rank |
| **C6 Latency / performance-risk** | Correct but too slow / costly for local use | Rerank pool too large, missing batching, repeated CSV reloads |

C6 does not outrank correctness or quality, but it informs implementation prioritization (a high-impact fix that doubles latency may need a smaller variant).

## 9.3 Confidence-based filtering

- **High / medium confidence** findings → `audit/findings.md` (actionable).
- **Low confidence** findings → `audit/notes_low_confidence.md` (preserved, not actionable).

This keeps actionable findings clean while not throwing away ideas that may become relevant later.

## 9.4 Per-module audit checklist (excerpt)

The full checklist is one item per question, yes/no/N/A. "No" generates a finding. Some critical questions per module:

**`semantic.py`:**
- `normalize_embeddings=True` consistent between index time and query time?
- Cosine distance → similarity correctly clamped to [0, 1]?
- Year reconstruction from `release_date` handles missing/malformed values?
- ChromaDB metadata read pattern handles fields that may be missing?

**`bm25.py`:**
- Tokenizer matches what the index was built with?
- Field weights match `config.py` constants exactly (no hardcoded duplicates)?
- CSV cached per process (no re-read)?
- Returns the same `id` semantics as semantic (real TMDB id)?

**`fusion.py`:**
- RRF formula matches the standard `1 / (K + rank + 1)` — and `rank` is 0-based or 1-based consistently?
- Per-mode scores preserved on fused entries?
- Metadata-merge doesn't overwrite richer values with sparser ones?

**`reranker.py`:**
- Document construction order matches BGE training convention?
- `CrossEncoder.predict()` called with proper `batch_size`? (context7 lookup)
- Overview truncation length justified vs reranker's `max_length`?
- Prior weights added on a **calibrated** scale — rerank logits are unbounded, so adding a flat 0.08/0.20/0.10 weight is meaningless unless the raw values are normalized first?
- Dedup before AND after scoring?

**`dedup.py`:** already flagged stale TMDB-id handling. Also:
- Title normalization handles unicode (e.g., "Amélie" vs "Amelie")?
- Score-preference fallback order matches the canonical lifecycle?

**`models.py`:**
- Lazy singleton actually lazy?
- GPU/CPU fallback warned to user?
- Reranker `max_length` explicit?

**`langchain_ollama.py`:**
- Timeout actually enforced (not just set on client)?
- Fallback path returns same shape as success path (no callers crashing)?
- HyDE prompt grounded in the query (not free-form drift)?

**`prompts.py`:**
- Hallucination-forbid instructions phrased positively (negative-only instructions are often ignored by modern LLMs)?
- Output format strict enough that JSON parsing succeeds reliably?

**Pipelines:**
- Each retrieval call uses correct `top_k` per current `src/config.py`?
- Dedup at every documented call site?
- `final_score` set on every result?

**`quality_smoke_test.py`:**
- Asserts no duplicates?
- Asserts `final_score` monotonic by rank?
- Covers the failure modes the audit finds?

**`01.clean_data.py` / `02. Embed_BGEM3.py`** (read-only, narrow):
- Does `02. Embed_BGEM3.py` actually store the metadata fields the runtime expects (notably keywords, vote_count, tagline)? **Known gap** — confirm exact list.
- Are filter thresholds in `01.clean_data.py` reasonable (MIN_OVERVIEW_LENGTH=50, MIN_VOTE_COUNT=50)?

## 9.5 context7 best-practice protocol

For each library, the audit queries context7 for current best practice and cross-checks against the code.

| Library | Specific things to verify |
|---|---|
| `sentence-transformers` (BGE-M3 encoding) | Encoding kwargs, recommended `max_length`, batch sizing |
| `sentence-transformers` (CrossEncoder) | `predict()` kwargs, batch sizing, `max_length` for BGE-reranker-v2-m3, **score scale interpretation** |
| `rank_bm25` | `BM25Okapi` vs `BM25L` vs `BM25Plus`; tokenizer guidance; parameter recommendations |
| `chromadb` | PersistentClient best practices, metadata schema design, `where` query syntax, HNSW parameters |
| `langchain-ollama` | Current preferred client class, timeout semantics, structured-output guidance |
| BGE-M3 model card (HF) | Document length guidance; dense vs sparse vs ColBERT modes |
| BGE-reranker-v2-m3 model card | Input format expectations, score interpretation, English-only constraints |

**Protocol per library:**
1. `context7 resolve-library-id` → canonical library id.
2. `context7 query-docs` → focused query (e.g., "CrossEncoder predict batch_size and max_length for reranking" — not just "CrossEncoder").
3. Read the returned snippet.
4. Compare against code (grep the API, read the call site).
5. If they diverge → finding (C2 or C3) citing the doc snippet.
6. If context7 has no clear best practice for something → no speculative finding.

**Caching:** every context7 query saved to `audit/context7_notes/<library>.md` with:
- Library/package version if available
- Date and time of the lookup
- Exact query used
- Short summary of the relevant best-practice snippet

## 9.6 Findings schema (`audit/findings.md`)

Each finding has these fields:

- **Title** and ID (F-NNN)
- **Category** (C1–C6)
- **Confidence** (high / medium)
- **Location** (file:line)
- **Evidence** (concrete code/doc references)
- **Library/external reference** (context7 doc + version + query, when applicable)
- **Expected impact** (qualitative: minor / moderate / major)
- **Hypothesized metric impact** (which metric, what direction)
- **Suggested fix sketch** (one paragraph, not the full implementation)
- **Detection method** (`code_reading` | `eval_metric` | `ablation` | `context7` | `smoke_test`)
- **Fix owner suggestion** (Claude | Codex | Copilot | ChatGPT Plus | Human-review)
- **Phase 5 priority** (TBD until phase 4 ablation completes)

## 9.7 What the audit does NOT do

- No code edits.
- No speculative findings (low-confidence go to `notes_low_confidence.md`, not `findings.md`).
- No general "this code could be cleaner" comments.
- No findings on UI, legacy wrappers, or one-shot scripts unless they affect index quality.
