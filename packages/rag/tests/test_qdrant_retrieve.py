from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from mts_contracts.knowledge import (
    Audience,
    ChunkMetadata,
    ConflictReason,
    EvidenceStatus,
    FilterExclusionReason,
    IndexRevisionNotFound,
    RetrievalConfig,
    RetrievalFilters,
    RetrievalMode,
    RetrievalResult,
    StaleReason,
)

from mts_rag.cache import dump_result
from mts_rag.fusion import FusedItem, reciprocal_rank_fusion
from mts_rag.qdrant import QdrantHybridRetriever, QdrantRetrieverSettings
from mts_rag.testing import FakeReranker, InMemoryQdrantGateway

ChunkFactory = Callable[..., ChunkMetadata]
MakeQdrant = Callable[..., tuple[QdrantHybridRetriever, InMemoryQdrantGateway]]
QUERY = "roaming internet price per day"


async def _retrieve(
    retriever: QdrantHybridRetriever,
    tenant_id: str,
    query: str = QUERY,
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


@pytest.mark.asyncio
async def test_hybrid_happy_path(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _gateway = make_qdrant()
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    result = await _retrieve(retriever, tenant_a)
    assert result.retrieval_mode is RetrievalMode.HYBRID
    assert result.index_revision == "rev-1"
    assert result.evidence_status is EvidenceStatus.SUFFICIENT
    assert result.applied_filters.tenant_id == tenant_a
    assert result.applied_filters.language == "en"
    assert result.applied_filters.audience is Audience.CALLER
    assert result.chunks
    assert result.excluded_counts == ()
    assert result.degraded == ()


@pytest.mark.asyncio
async def test_rrf_called_with_all_lists(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _gateway = make_qdrant()
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    calls: list[tuple[Any, int, int | None]] = []

    def spy(rankings: list[list[str]], *, k: int = 60, top_k: int | None = None) -> list[FusedItem]:
        calls.append((rankings, k, top_k))
        return reciprocal_rank_fusion(rankings, k=k, top_k=top_k)

    namespace = QdrantHybridRetriever.retrieve.__globals__
    original = namespace["reciprocal_rank_fusion"]
    namespace["reciprocal_rank_fusion"] = spy
    try:
        await _retrieve(retriever, tenant_a)
    finally:
        namespace["reciprocal_rank_fusion"] = original
    assert calls
    rankings, k, top_k = calls[0]
    config = retriever.settings.config
    assert k == config.rrf_k
    assert top_k == config.rrf_top_k
    assert len(rankings) >= 2


@pytest.mark.asyncio
async def test_context_top_k_and_evidence_statuses(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str, now: datetime
) -> None:
    settings = QdrantRetrieverSettings(
        collection_prefix="kbtest_unit",
        config=RetrievalConfig(context_top_k=1, stale_after=timedelta(days=1)),
    )
    retriever, _gateway = make_qdrant(settings=settings)
    await retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(
                chunk_id="full",
                text="roaming internet price per day",
                crawled_at=now,
            ),
            make_chunk(
                chunk_id="most",
                text="roaming internet price",
                crawled_at=now,
            ),
        ],
    )
    result = await _retrieve(retriever, tenant_a)
    assert len(result.chunks) <= 1
    assert result.evidence_status is EvidenceStatus.SUFFICIENT

    empty, _ = make_qdrant()
    await empty.publish(tenant_a, "rev-empty", [])
    none = await _retrieve(empty, tenant_a)
    assert none.evidence_status is EvidenceStatus.NO_EVIDENCE

    miss, _ = make_qdrant()
    await miss.publish(tenant_a, "rev-miss", [make_chunk(text="television subscription")])
    no_hit = await _retrieve(miss, tenant_a, "recipe borscht grandmother")
    assert no_hit.evidence_status in {EvidenceStatus.NO_EVIDENCE, EvidenceStatus.LOW_RELEVANCE}

    stale, _ = make_qdrant()
    await stale.publish(
        tenant_a,
        "rev-stale",
        [make_chunk(chunk_id="expired", valid_to=now - timedelta(days=1))],
    )
    stale_result = await _retrieve(stale, tenant_a)
    assert stale_result.evidence_status is EvidenceStatus.STALE_ONLY
    assert stale_result.outdated_matches >= 1


@pytest.mark.asyncio
async def test_conflict_and_crawl_age(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str, now: datetime
) -> None:
    settings = QdrantRetrieverSettings(
        collection_prefix="kbtest_unit",
        config=RetrievalConfig(stale_after=timedelta(days=1)),
    )
    retriever, _ = make_qdrant(settings=settings)
    await retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(chunk_id="v1", revision_id="doc-rev-1"),
            make_chunk(chunk_id="v2", revision_id="doc-rev-2"),
        ],
    )
    result = await _retrieve(retriever, tenant_a)
    assert result.evidence_status is EvidenceStatus.EVIDENCE_CONFLICT
    assert result.conflicts[0].reason is ConflictReason.MULTIPLE_ACTIVE_REVISIONS

    aged, _ = make_qdrant(settings=settings)
    await aged.publish(
        tenant_a,
        "rev-age",
        [
            make_chunk(chunk_id="fresh", crawled_at=now - timedelta(hours=1)),
            make_chunk(chunk_id="old", crawled_at=now - timedelta(days=3), document_id="d" * 64),
        ],
    )
    aged_result = await _retrieve(aged, tenant_a)
    old_chunk = next(
        (chunk for chunk in aged_result.chunks if chunk.metadata.chunk_id == "old"),
        None,
    )
    if old_chunk is not None:
        assert old_chunk.is_stale is True
        assert old_chunk.stale_reasons == (StaleReason.CRAWL_AGE_EXCEEDED,)


@pytest.mark.asyncio
async def test_filters_before_ranking_and_unknown_revision(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant()
    await retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(chunk_id="ok"),
            make_chunk(chunk_id="tv", service="tv", text="roaming internet price per day tv"),
        ],
    )
    result = await _retrieve(retriever, tenant_a, filters=RetrievalFilters(services=("roaming",)))
    assert all(chunk.metadata.service == "roaming" for chunk in result.chunks)
    assert all(item.chunk_id != "tv" for item in result.candidates)
    assert result.excluded_counts == ((FilterExclusionReason.SERVICE_MISMATCH, 1),)
    with pytest.raises(IndexRevisionNotFound) as exc:
        await _retrieve(retriever, tenant_a, index_revision="rev-missing")
    assert str(exc.value) == "index revision not found"


@pytest.mark.asyncio
async def test_reranker_fills_diagnostics(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant(reranker=FakeReranker())
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    result = await _retrieve(retriever, tenant_a)
    assert result.candidates[0].rerank_score is not None
    assert result.candidates[0].rerank_rank == 1


@pytest.mark.asyncio
async def test_retrieve_cache_skips_second_search(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    first = await _retrieve(retriever, tenant_a)
    searches = len(gateway.captured_searches)
    second = await _retrieve(retriever, tenant_a)
    assert second.evidence_status is first.evidence_status
    assert second.chunks[0].metadata.chunk_id == first.chunks[0].metadata.chunk_id
    assert len(gateway.captured_searches) == searches
    assert dump_result(first)["query_variants"] == ["cached"]


@pytest.mark.asyncio
async def test_expired_chunks_are_counted(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str, now: datetime
) -> None:
    retriever, _ = make_qdrant()
    await retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(),
            make_chunk(chunk_id="expired", valid_to=now - timedelta(days=1)),
            make_chunk(chunk_id="ru", language="ru", text="роуминг интернет 5 BYN"),
        ],
    )
    result = await _retrieve(retriever, tenant_a)
    assert dict(result.excluded_counts)[FilterExclusionReason.EXPIRED] == 1
    assert dict(result.excluded_counts)[FilterExclusionReason.LANGUAGE_MISMATCH] == 1
