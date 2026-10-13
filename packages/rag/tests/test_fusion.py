import itertools
import math

import pytest

from mts_rag.fusion import FusedItem, reciprocal_rank_fusion


def test_empty_input() -> None:
    assert reciprocal_rank_fusion([]) == []


def test_all_empty_lists() -> None:
    assert reciprocal_rank_fusion([[], [], []]) == []


def test_single_list_preserves_order() -> None:
    fused = reciprocal_rank_fusion([["c", "a", "b"]])
    assert [item.id for item in fused] == ["c", "a", "b"]
    assert [item.rank for item in fused] == [1, 2, 3]
    assert [item.per_list_ranks for item in fused] == [(1,), (2,), (3,)]


def test_known_scores_k60() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
    assert fused == [
        FusedItem(id="b", score=math.fsum([1 / 62, 1 / 61]), rank=1, per_list_ranks=(2, 1)),
        FusedItem(id="a", score=1 / 61, rank=2, per_list_ranks=(1, None)),
        FusedItem(id="c", score=1 / 62, rank=3, per_list_ranks=(None, 2)),
    ]


def test_tie_break_best_rank_then_id() -> None:
    # k=2: "b" at ranks (1, 4) scores 1/3 + 1/6 == 1/2, exactly the score of "a" at (2, 2).
    fused = reciprocal_rank_fusion([["b", "a"], ["q", "a", "r", "b"]], k=2)
    by_id = {item.id: item for item in fused}
    assert by_id["a"].score == by_id["b"].score == 0.5
    assert [item.id for item in fused][:2] == ["b", "a"]

    fused = reciprocal_rank_fusion([["b", "a"], ["a", "b"]])
    assert fused[0].score == fused[1].score
    assert [item.id for item in fused] == ["a", "b"]


def test_list_order_invariance() -> None:
    rankings = [["a", "b", "c", "d"], ["d", "c", "e"], ["b", "e", "a", "f", "g"]]
    expected = [(i.id, i.score, i.rank) for i in reciprocal_rank_fusion(rankings, k=7)]
    for permutation in itertools.permutations(rankings):
        fused = reciprocal_rank_fusion(list(permutation), k=7)
        assert [(i.id, i.score, i.rank) for i in fused] == expected


def test_duplicate_in_list_uses_first() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "a"]])
    by_id = {item.id: item for item in fused}
    assert by_id["a"].per_list_ranks == (1,)
    assert by_id["a"].score == 1 / 61
    assert by_id["b"].per_list_ranks == (2,)


def test_top_k_truncates() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c", "d"]], top_k=2)
    assert [item.id for item in fused] == ["a", "b"]
    assert [item.rank for item in fused] == [1, 2]


@pytest.mark.parametrize(("k", "top_k"), [(0, None), (-1, None), (60, 0), (60, -5)])
def test_invalid_k_raises(k: int, top_k: int | None) -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], k=k, top_k=top_k)
