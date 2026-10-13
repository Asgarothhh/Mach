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

from mts_rag import InMemoryKnowledgeRetriever

ChunkFactory = Callable[..., ChunkMetadata]
RetrieverFactory = Callable[..., InMemoryKnowledgeRetriever]

# One clock read at the start, then one per stage boundary: after revision resolution,
# after filtering, after scoring, before building the result.
BOUNDARY_READS = 4


def _clock(readings: list[float]) -> Callable[[], float]:
    values: Iterator[float] = iter(readings)
    last = readings[-1]

    def clock() -> float:
        return next(values, last)

    return clock


async def _retrieve(retriever: InMemoryKnowledgeRetriever, tenant_id: str) -> RetrievalResult:
    return await retriever.retrieve(
        "roaming internet price",
        tenant_id=tenant_id,
        language="en",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=200,
    )


@pytest.mark.asyncio
async def test_deadline_exceeded_raises_typed(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever(clock=_clock([10.0, 10.25]))
    retriever.publish(tenant_a, "rev-1", [make_chunk()])

    with pytest.raises(RetrievalDeadlineExceeded) as exc_info:
        await _retrieve(retriever, tenant_a)

    assert isinstance(exc_info.value, RetrievalUnavailable)
    assert not exc_info.value.retryable


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_boundary", range(1, BOUNDARY_READS + 1))
async def test_deadline_not_partial_result(
    make_chunk: ChunkFactory,
    make_retriever: RetrieverFactory,
    tenant_a: str,
    failing_boundary: int,
) -> None:
    readings = [10.0] * failing_boundary + [10.5]
    retriever = make_retriever(clock=_clock(readings))
    retriever.publish(tenant_a, "rev-1", [make_chunk()])

    with pytest.raises(RetrievalDeadlineExceeded):
        await _retrieve(retriever, tenant_a)


@pytest.mark.asyncio
async def test_cancellation_propagates(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [make_chunk()])

    task = asyncio.create_task(_retrieve(retriever, tenant_a))
    await asyncio.sleep(0)
    assert not task.done()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cancelled_error_from_dependency_not_swallowed(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    calls = 0

    def clock() -> float:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise asyncio.CancelledError
        return 10.0

    retriever = make_retriever(clock=clock)
    retriever.publish(tenant_a, "rev-1", [make_chunk()])

    with pytest.raises(asyncio.CancelledError):
        await _retrieve(retriever, tenant_a)


@pytest.mark.asyncio
async def test_duration_ms_from_injected_clock(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever(clock=_clock([10.0, 10.05, 10.1, 10.12, 10.125]))
    retriever.publish(tenant_a, "rev-1", [make_chunk()])

    result = await _retrieve(retriever, tenant_a)

    assert result.duration_ms == 125
