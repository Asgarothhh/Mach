"""Reciprocal Rank Fusion (SSOT §6.7.4)."""

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FusedItem:
    id: str
    score: float
    rank: int
    per_list_ranks: tuple[int | None, ...]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], *, k: int = 60, top_k: int | None = None
) -> list[FusedItem]:
    """Fuse ranked id lists with RRF: score(d) = sum over lists of 1 / (k + rank(d)).

    Ranks are 1-based positions in each input list. An id repeated within one list keeps its
    first position; later positions of other ids are not renumbered. Ordering is by score
    descending, then best single-list rank ascending, then id ascending.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    if top_k is not None and top_k < 1:
        raise ValueError("top_k must be >= 1")

    list_count = len(rankings)
    ranks: dict[str, list[int | None]] = {}
    for list_index, ranking in enumerate(rankings):
        for position, item_id in enumerate(ranking, start=1):
            item_ranks = ranks.setdefault(item_id, [None] * list_count)
            if item_ranks[list_index] is None:
                item_ranks[list_index] = position

    scored: list[tuple[float, int, str, tuple[int | None, ...]]] = []
    for item_id, item_ranks in ranks.items():
        present = [r for r in item_ranks if r is not None]
        # fsum is exactly rounded, so the score does not depend on the order of the lists.
        score = math.fsum(1.0 / (k + r) for r in present)
        scored.append((score, min(present), item_id, tuple(item_ranks)))

    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    if top_k is not None:
        scored = scored[:top_k]
    return [
        FusedItem(id=item_id, score=score, rank=rank, per_list_ranks=per_list_ranks)
        for rank, (score, _, item_id, per_list_ranks) in enumerate(scored, start=1)
    ]
