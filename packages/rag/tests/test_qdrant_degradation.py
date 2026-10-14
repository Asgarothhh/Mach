from collections.abc import Callable, Sequence
from typing import Any, Literal

import pytest
from mts_contracts.knowledge import (
    ChunkMetadata,
    DegradationReason,
    RetrievalFilters,
    RetrievalMode,
    RetrievalResult,
    RetrievalUnavailable,
)

from mts_rag.qdrant import QdrantHybridRetriever
from mts_rag.testing import (
    FailingEmbedder,
    FailingReranker,
    HashingFakeEmbedder,
    InMemoryQdrantGateway,
    SlowEmbedder,
    SlowReranker,
)


async def _retrieve(
    retriever: QdrantHybridRetriever,
    tenant_id: str,
    query: str = "roaming internet price per day",
    **overrides: Any,
) -> RetrievalResult:
    arguments: dict[str, Any] = {
        "language": "en",
        "audience": "caller",
        "filters": RetrievalFilters(),
        "index_revision": "active",
        "deadline_ms": 1000,
    }
    arguments.update(overrides)
    return await retriever.retrieve(query, tenant_id=tenant_id, **arguments)


ChunkFactory = Callable[..., ChunkMetadata]
MakeQdrant = Callable[..., tuple[QdrantHybridRetriever, InMemoryQdrantGateway]]


class _CountingEmbedder(HashingFakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]:
        self.calls += 1
        return super().embed(texts, kind=kind)


@pytest.mark.asyncio
async def test_embedder_failure_sparse_only(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant()
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    retriever.set_embedder(FailingEmbedder())
    result = await _retrieve(retriever, tenant_a)
    assert result.retrieval_mode is RetrievalMode.SPARSE_ONLY
    assert DegradationReason.EMBEDDER_UNAVAILABLE in result.degraded


@pytest.mark.asyncio
async def test_missing_dense_vector(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    sparse_only, gateway = make_qdrant(embedder=None)
    await sparse_only.publish(tenant_a, "rev-1", [make_chunk()])
    embedder = _CountingEmbedder()
    hybrid, _ = make_qdrant(gateway=gateway, embedder=embedder)
    result = await _retrieve(hybrid, tenant_a)
    assert result.retrieval_mode is RetrievalMode.SPARSE_ONLY
    assert DegradationReason.DENSE_UNAVAILABLE in result.degraded
    assert embedder.calls == 0


@pytest.mark.asyncio
async def test_gateway_down_unavailable(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    gateway.down = True
    retriever._version_ok = None
    with pytest.raises(RetrievalUnavailable):
        await _retrieve(retriever, tenant_a)


@pytest.mark.asyncio
async def test_reranker_failure_keeps_rrf(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant(reranker=FailingReranker())
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    result = await _retrieve(retriever, tenant_a)
    assert result.chunks
    assert DegradationReason.RERANKER_UNAVAILABLE in result.degraded
    assert result.candidates[0].rerank_score is None


@pytest.mark.asyncio
async def test_busy_embedder_degrades_immediately(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant(embedder=SlowEmbedder(delay_s=0.5))
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    first = _retrieve(retriever, tenant_a)
    second = _retrieve(retriever, tenant_a)
    results = await _gather_two(first, second)
    assert any(
        DegradationReason.EMBEDDER_UNAVAILABLE in item.degraded
        or item.retrieval_mode is RetrievalMode.SPARSE_ONLY
        for item in results
    )


@pytest.mark.asyncio
async def test_slow_reranker_degrades(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant(reranker=SlowReranker(delay_s=1.0))
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    result = await _retrieve(retriever, tenant_a)
    assert DegradationReason.RERANKER_UNAVAILABLE in result.degraded


async def _gather_two(first: Any, second: Any) -> list[RetrievalResult]:
    import asyncio

    return list(await asyncio.gather(first, second))
