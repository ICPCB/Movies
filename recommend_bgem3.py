"""Backward-compatible wrapper — delegates to src/pipelines/advanced.py."""
from src.pipelines import advanced as _adv
from src.config import FINAL_TOP_K


def recommend(
    query: str,
    top_k: int = FINAL_TOP_K,
    use_expansion: bool = True,
    use_rerank: bool = True,
    with_explanation: bool = True,
    verbose: bool = False,
) -> list[dict]:
    return _adv.run(query, top_k=top_k, with_explanation=with_explanation)
