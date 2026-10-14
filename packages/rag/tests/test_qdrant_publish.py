from collections.abc import Callable, Sequence
from typing import Any, Literal

import pytest
from mts_contracts.knowledge import (
    ChunkMetadata,
    IndexRevisionNotFound,
    RetrievalFilters,
    TenantIsolationError,
)

from mts_rag.qdrant import IndexPublishError, QdrantHybridRetriever
from mts_rag.qdrant_http import GatewayNotFound
from mts_rag.sparse import SPARSE_VECTOR_NAME
from mts_rag.testing import HashingFakeEmbedder, InMemoryQdrantGateway

ChunkFactory = Callable[..., ChunkMetadata]
MakeQdrant = Callable[..., tuple[QdrantHybridRetriever, InMemoryQdrantGateway]]


@pytest.mark.asyncio
async def test_publish_collection_has_named_vectors(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    info = await gateway.get_collection("kbtest_unit__acme-it-demo__rev-1")
    vectors = info["config"]["params"]["vectors"]
    sparse = info["config"]["params"]["sparse_vectors"]
    assert "dense_fake_hash64_v1" in vectors
    assert vectors["dense_fake_hash64_v1"]["size"] == 64
    assert vectors["dense_fake_hash64_v1"]["distance"] == "Cosine"
    assert SPARSE_VECTOR_NAME in sparse


@pytest.mark.asyncio
async def test_publish_sparse_only_without_embedder(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant(embedder=None)
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    info = await gateway.get_collection("kbtest_unit__acme-it-demo__rev-1")
    assert info["config"]["params"]["vectors"] == {}
    assert SPARSE_VECTOR_NAME in info["config"]["params"]["sparse_vectors"]


@pytest.mark.asyncio
async def test_payload_has_all_keys(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    chunk = make_chunk()
    await retriever.publish(tenant_a, "rev-1", [chunk])
    points = await gateway.scroll("kbtest_unit__acme-it-demo__rev-1", {"limit": 10})
    payload = points[0]["payload"]
    for key in ChunkMetadata.model_fields:
        assert key in payload
    assert "valid_from_us" in payload
    assert "valid_to_us" in payload
    assert payload["payload_schema"] == 1


@pytest.mark.asyncio
async def test_publish_rejects_foreign_duplicate_and_reserved(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, _gateway = make_qdrant()
    with pytest.raises(TenantIsolationError):
        await retriever.publish(
            tenant_a, "rev-1", [make_chunk(), make_chunk(chunk_id="x", tenant_id="other-tenant")]
        )
    with pytest.raises(ValueError, match="duplicate"):
        await retriever.publish(tenant_a, "rev-1", [make_chunk(), make_chunk()])
    with pytest.raises(ValueError, match="reserved"):
        await retriever.publish(tenant_a, "active", [make_chunk()])
    with pytest.raises(ValueError, match="invalid index revision"):
        await retriever.publish(tenant_a, "rev:1", [make_chunk()])


@pytest.mark.asyncio
async def test_republish_is_idempotent_without_delete(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    deletes: list[str] = []
    original = gateway.delete_collection

    async def spy(name: str) -> None:
        deletes.append(name)
        await original(name)

    gateway.delete_collection = spy  # type: ignore[method-assign]
    await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    await retriever.publish(
        tenant_a, "rev-1", [make_chunk(text="Roaming internet costs 5 BYN per day.")]
    )
    assert deletes == []
    count = await gateway.count("kbtest_unit__acme-it-demo__rev-1", {"exact": True})
    assert count == 1


class _QueryOkDocumentFailEmbedder(HashingFakeEmbedder):
    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]:
        if kind == "document":
            raise RuntimeError("document embed failed")
        return super().embed(texts, kind=kind)


@pytest.mark.asyncio
async def test_document_embed_failure_does_not_create_sparse_hybrid_collection(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    gateway = InMemoryQdrantGateway()
    retriever, _ = make_qdrant(gateway=gateway, embedder=_QueryOkDocumentFailEmbedder())
    with pytest.raises(IndexPublishError, match="document embed failed"):
        await retriever.publish(tenant_a, "rev-hybrid", [make_chunk()])
    assert await gateway.get_aliases() == []
    with pytest.raises(GatewayNotFound):
        await gateway.get_collection("kbtest_unit__acme-it-demo__rev-hybrid")


@pytest.mark.asyncio
async def test_publish_dense_into_sparse_collection_raises_without_alias_change(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    sparse, gateway = make_qdrant(embedder=None)
    await sparse.publish(tenant_a, "rev-1", [make_chunk()])
    aliases_before = await gateway.get_aliases()
    hybrid, _ = make_qdrant(gateway=gateway)
    with pytest.raises(IndexPublishError, match="index schema mismatch"):
        await hybrid.publish(tenant_a, "rev-1", [make_chunk()])
    assert await gateway.get_aliases() == aliases_before
    info = await gateway.get_collection("kbtest_unit__acme-it-demo__rev-1")
    assert info["config"]["params"]["vectors"] == {}


@pytest.mark.asyncio
async def test_smoke_failure_leaves_alias_and_deletes_unaliased(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    gateway = InMemoryQdrantGateway()
    gateway.drop_points = True
    retriever, _ = make_qdrant(gateway=gateway)
    with pytest.raises(IndexPublishError):
        await retriever.publish(tenant_a, "rev-1", [make_chunk()])
    aliases = await gateway.get_aliases()
    assert aliases == []
    with pytest.raises(GatewayNotFound):
        await gateway.get_collection("kbtest_unit__acme-it-demo__rev-1")


@pytest.mark.asyncio
async def test_activate_single_alias_call_and_rollback(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    calls: list[list[dict[str, Any]]] = []
    original = gateway.post_aliases

    async def spy(actions: list[dict[str, Any]]) -> None:
        calls.append(actions)
        await original(actions)

    gateway.post_aliases = spy  # type: ignore[method-assign]
    await retriever.publish(tenant_a, "rev-1", [make_chunk(chunk_id="a")])
    await retriever.publish(tenant_a, "rev-2", [make_chunk(chunk_id="b")], activate=False)
    await retriever.activate(tenant_a, "rev-2")
    assert all(len(batch) in {1, 2} for batch in calls)
    await retriever.activate(tenant_a, "rev-1")
    aliases = await gateway.get_aliases()
    assert aliases[0]["collection_name"].endswith("__rev-1")
    with pytest.raises(IndexRevisionNotFound):
        await retriever.activate(tenant_a, "rev-missing")
    with pytest.raises(IndexRevisionNotFound):
        await retriever.activate(tenant_a, "rev-b")


@pytest.mark.asyncio
async def test_gc_keeps_previous_revision_and_deletes_older(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str
) -> None:
    retriever, gateway = make_qdrant()
    await retriever.publish(tenant_a, "rev-1", [make_chunk(chunk_id="a")])
    await retriever.publish(tenant_a, "rev-2", [make_chunk(chunk_id="b")])
    await retriever.publish(tenant_a, "rev-3", [make_chunk(chunk_id="c")])
    names = await gateway.list_collections()
    assert "kbtest_unit__acme-it-demo__rev-1" not in names
    assert "kbtest_unit__acme-it-demo__rev-2" in names
    assert "kbtest_unit__acme-it-demo__rev-3" in names
    await retriever.activate(tenant_a, "rev-2")
    result = await retriever.retrieve(
        "roaming internet price per day",
        tenant_id=tenant_a,
        language="en",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=1000,
    )
    assert result.index_revision == "rev-2"
