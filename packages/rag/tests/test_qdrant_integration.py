import os
import uuid
from collections.abc import Callable

import pytest
from mts_contracts.knowledge import ChunkMetadata, RetrievalFilters

from mts_rag.qdrant import QdrantHybridRetriever, QdrantRetrieverSettings
from mts_rag.qdrant_http import HttpQdrantGateway
from mts_rag.testing import HashingFakeEmbedder

pytestmark = pytest.mark.integration

_URL = os.environ.get("QDRANT_TEST_URL", "").strip()


@pytest.mark.skipif(not _URL, reason="QDRANT_TEST_URL is not set")
@pytest.mark.asyncio
async def test_real_qdrant_publish_and_hybrid_retrieve(
    make_chunk: Callable[..., ChunkMetadata], tenant_a: str
) -> None:
    prefix = f"kbtest_{uuid.uuid4().hex[:8]}"
    gateway = HttpQdrantGateway(_URL)
    retriever = QdrantHybridRetriever(
        gateway,
        embedder=HashingFakeEmbedder(),
        settings=QdrantRetrieverSettings(collection_prefix=prefix),
    )
    try:
        await retriever.publish(tenant_a, "rev-1", [make_chunk()])
        result = await retriever.retrieve(
            "roaming internet price per day",
            tenant_id=tenant_a,
            language="en",
            audience="caller",
            filters=RetrievalFilters(),
            index_revision="active",
            deadline_ms=2000,
        )
        assert result.index_revision == "rev-1"
        assert result.chunks
    finally:
        aliases = await gateway.get_aliases()
        for item in aliases:
            if item["alias_name"].startswith(f"{prefix}__"):
                await gateway.post_aliases([{"delete_alias": {"alias_name": item["alias_name"]}}])
        info_failed = False
        try:
            collections = [f"{prefix}__{tenant_a}__rev-1"]
            for name in collections:
                await gateway.delete_collection(name)
        except Exception:
            info_failed = True
        del info_failed
        await retriever.aclose()
