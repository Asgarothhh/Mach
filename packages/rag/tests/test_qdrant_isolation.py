from collections.abc import Callable
from typing import Any

import pytest
from mts_contracts.knowledge import (
    ChunkMetadata,
    EvidenceStatus,
    IndexRevisionNotFound,
    RetrievalFilters,
    RetrievalResult,
    TenantIsolationError,
)

from mts_rag.qdrant import QdrantHybridRetriever
from mts_rag.testing import InMemoryQdrantGateway


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
TENANT_B = "other-tenant"
TEXT = "Roaming internet costs 5 BYN per day."


@pytest.mark.asyncio
async def test_same_text_other_tenant_never_returned(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant()
    await retriever.publish(tenant_a, "rev-a", [make_chunk(chunk_id="shared", text=TEXT)])
    await retriever.publish(
        TENANT_B, "rev-b", [make_chunk(chunk_id="shared", tenant_id=TENANT_B, text=TEXT)]
    )
    result = await _retrieve(retriever, tenant_a)
    assert result.evidence_status is EvidenceStatus.SUFFICIENT
    assert [chunk.metadata.tenant_id for chunk in result.chunks] == [tenant_a]
    assert all(item.chunk_id != "b-only" for item in result.candidates)


@pytest.mark.asyncio
async def test_foreign_and_unknown_revision_same_message(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _ = make_qdrant()
    await retriever.publish(tenant_a, "rev-a", [make_chunk()])
    await retriever.publish(TENANT_B, "rev-b", [make_chunk(tenant_id=TENANT_B)])
    with pytest.raises(IndexRevisionNotFound) as other:
        await _retrieve(retriever, tenant_a, index_revision="rev-b")
    with pytest.raises(IndexRevisionNotFound) as unknown:
        await _retrieve(retriever, tenant_a, index_revision="rev-missing")
    assert str(other.value) == str(unknown.value) == "index revision not found"
    assert "rev-b" not in str(other.value)
    assert TENANT_B not in str(other.value)


@pytest.mark.asyncio
async def test_tampered_alias_and_foreign_payload(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    await retriever.publish(tenant_a, "rev-a", [make_chunk()])
    await retriever.publish(TENANT_B, "rev-b", [make_chunk(tenant_id=TENANT_B)])
    await gateway.post_aliases(
        [
            {"delete_alias": {"alias_name": f"kbtest_unit__{tenant_a}__active"}},
            {
                "create_alias": {
                    "collection_name": f"kbtest_unit__{TENANT_B}__rev-b",
                    "alias_name": f"kbtest_unit__{tenant_a}__active",
                }
            },
        ]
    )
    retriever._alias_cache.clear()
    with pytest.raises(IndexRevisionNotFound):
        await _retrieve(retriever, tenant_a)

    gateway.foreign_payload = True
    retriever._alias_cache.clear()
    await gateway.post_aliases(
        [
            {"delete_alias": {"alias_name": f"kbtest_unit__{tenant_a}__active"}},
            {
                "create_alias": {
                    "collection_name": f"kbtest_unit__{tenant_a}__rev-a",
                    "alias_name": f"kbtest_unit__{tenant_a}__active",
                }
            },
        ]
    )
    with pytest.raises(TenantIsolationError):
        await _retrieve(retriever, tenant_a)


@pytest.mark.asyncio
async def test_every_search_includes_tenant_must(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    await retriever.publish(tenant_a, "rev-a", [make_chunk()])
    gateway.captured_searches.clear()
    await _retrieve(retriever, tenant_a, filters=RetrievalFilters())
    assert gateway.captured_searches
    for search in gateway.captured_searches:
        clause = search["filter"]
        tenant_clauses = [
            item
            for item in clause["must"]
            if item.get("key") == "tenant_id" and item.get("match", {}).get("value") == tenant_a
        ]
        assert tenant_clauses
