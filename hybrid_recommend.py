"""Backward-compatible wrapper — delegates to src/pipelines/hybrid.py."""
from src.pipelines import hybrid as _hyb
from src.config import FINAL_TOP_K


def hybrid_recommend(
    query: str,
    top_k: int = FINAL_TOP_K,
    verbose: bool = False,
) -> list[dict]:
    return _hyb.run(query, top_k=top_k, with_explanation=False)
