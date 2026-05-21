"""Parse metadata filters from natural-language movie queries."""
from __future__ import annotations

import re


def parse_filters(query: str) -> dict:
    filters: dict = {}
    q = str(query or "").lower()

    m = re.search(r"(?:from|between)\s*(\d{4})\s*(?:to|and|-)\s*(\d{4})", q)
    if m:
        lo, hi = sorted((int(m.group(1)), int(m.group(2))))
        filters["year"] = {"$gte": lo, "$lte": hi}
    else:
        m = re.search(r"(?:after|since|from|newer than)\s*(\d{4})", q)
        if m:
            filters.setdefault("year", {})["$gte"] = int(m.group(1))

    m = re.search(r"(?:before|until|older than)\s*(\d{4})", q)
    if m:
        filters.setdefault("year", {})["$lte"] = int(m.group(1))

    m = re.search(r"\b(19[2-9]0|20[0-2]0)s\b", q)
    if m:
        lo = int(m.group(1))
        filters["year"] = {"$gte": lo, "$lte": lo + 9}

    for decade, (lo, hi) in [
        ("80s", (1980, 1989)),
        ("90s", (1990, 1999)),
        ("2000s", (2000, 2009)),
    ]:
        if decade in q:
            filters["year"] = {"$gte": lo, "$lte": hi}
            break

    if any(kw in q for kw in [
        "highly rated",
        "top rated",
        "critically acclaimed",
        "best",
    ]):
        filters["vote_average"] = {"$gte": 7.5}

    return filters
