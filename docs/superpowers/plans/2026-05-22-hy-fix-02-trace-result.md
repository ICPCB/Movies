# HY-FIX-02 Trace Result

Status: SELF-REVIEWED / PENDING CLAUDE REVIEW
Date: 2026-05-22
Trace artifact: eval/runs/2026-05-19-1846-nogit/analysis/hy_fix_rrf_pool/rrf_pool_trace.json

## Result

The q08 RRF-pool trace completed and reproduced HY-STAB-01 exactly for both
deterministic arms:

```text
q08 pinned | rrf_rank 183 | reproduced_ok True | ranks_below_cutoff 134 | in_pool_source_mix {'dual_source': 21, 'semantic_only': 16, 'bm25_only': 13} | target_source_count 1
q08 no_llm | rrf_rank 79 | reproduced_ok True | ranks_below_cutoff 30 | in_pool_source_mix {'dual_source': 16, 'semantic_only': 15, 'bm25_only': 19} | target_source_count 1
```

## Lever Read

Use the `no_llm` arm as the primary deterministic control per the HY-FIX-02
plan. q08 is 30 ranks below the top-50 cutoff there, so the trace points to
the cutoff lever (`RERANK_TOP_K`) as the smallest plausible first change.

The BM25-recall lever is not the lead choice from this trace because the
no_llm top-50 is not majority dual-source: 16 dual-source, 15 semantic-only,
19 BM25-only. The RRF-weighting lever is also not clearly proven from this
single q08 trace.

## Safety Note

The pinned arm remains much deeper at RRF rank 183. A modest cutoff increase
would admit q08 in the no_llm control if set to at least 80, but it would not
admit q08 in the pinned arm. Therefore HY-FIX-02B may be a small config/source
change, but it still needs a focused validation gate for accuracy and latency
before treating it as a project fix.

## Command Run

```powershell
.\venv\Scripts\python.exe -u -X faulthandler -m eval.scripts.hy_fix_rrf_pool_trace --run 2026-05-19-1846-nogit
```

The run loaded the local BGE-M3 embedder, BM25 index, and reranker. It did
not intentionally call Ollama; the model stack printed an unauthenticated
HF Hub warning while loading weights.
