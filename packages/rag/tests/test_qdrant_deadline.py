import asyncio
from collections.abc import Callable, Iterator

import pytest
from mts_contracts.knowledge import (
    ChunkMetadata,
    RetrievalDeadlineExceeded,
    RetrievalFilters,
    RetrievalResult,
    RetrievalUnavailable,
)

from mts_rag.qdrant import QdrantHybridRetriever
from mts_rag.testing import InMemoryQdrantGateway, SlowEmbedder


async def _retrieve(retriever: QdrantHybridRetriever, tenant_id: str) -> RetrievalResult:
    return await retriever.retrieve(
        "roaming internet price per day",
        tenant_id=tenant_id,
        language="en",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=200,
    )


ChunkFactory = Callable[..., ChunkMetadata]
MakeQdrant = Callable[..., tuple[QdrantHybridRetriever, InMemoryQdrantGateway]]


def _clock(readings: list[float]) -> Callable[[], float]:
    values: Iterator[float] = iter(readings)
    last = readings[-1]

    def clock() -> float:
        return next(values, last)

    return clock


@pytest.mark.asyncio
async def test_deadline_exceeded_typed_and_not_retryable(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant(clock=_clock([0.0, 0.0, 1.0]))
    await retriever.publish(tenant_a, "rev-1", [make_chunk()], activate=True)
    with pytest.raises(RetrievalDeadlineExceeded) as exc_info:
        await _retrieve(retriever, tenant_a)
    assert isinstance(exc_info.value, RetrievalUnavailable)
    assert not exc_info.value.retryable


@pytest.mark.asyncio
async def test_cancellation_during_retrieve(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant(embedder=SlowEmbedder(delay_s=0.3))
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    before = {task for task in asyncio.all_tasks() if not task.done()}
    task = asyncio.create_task(_retrieve(retriever, tenant_a))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
    current = asyncio.current_task()
    leftover = [
        item
        for item in asyncio.all_tasks()
        if item is not current and not item.done() and item not in before
    ]
    assert leftover == []
