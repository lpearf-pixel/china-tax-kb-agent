from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


def rrf_fuse(rankings: Iterable[list[str]], k: int = 60) -> dict[str, float]:
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, candidate_id in enumerate(ranking, 1):
            scores[candidate_id] += 1.0 / (k + rank)
    return dict(scores)
