from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from mts_contracts.knowledge import ChunkMetadata

from mts_rag import InMemoryKnowledgeRetriever, LexicalStubSettings
from mts_rag.qdrant import QdrantHybridRetriever, QdrantRetrieverSettings
from mts_rag.testing import HashingFakeEmbedder, InMemoryQdrantGateway

TENANT_A = "acme-it-demo"
FIXED_NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def now() -> datetime:
    return FIXED_NOW


@pytest.fixture
def tenant_a() -> str:
    return TENANT_A


@pytest.fixture
def make_chunk() -> Callable[..., ChunkMetadata]:
    def factory(**overrides: Any) -> ChunkMetadata:
        data: dict[str, Any] = {
            "chunk_id": "chunk-1",
            "document_id": "a" * 64,
            "revision_id": "rev-1",
            "source_url": "https://www.acme-it.example/help/roaming?utm_source=x",
            "canonical_url": "https://www.acme-it.example/help/roaming",
            "title": "Roaming",
            "section_path": ["Help", "Roaming"],
            "tenant_id": TENANT_A,
            "service": "roaming",
            "topic": "pricing",
            "audience": "caller",
            "language": "en",
            "content_hash": "b" * 64,
            "crawled_at": "2026-10-11T00:00:00Z",
            "published_at": None,
            "valid_from": None,
            "valid_to": None,
            "effective_status": "active",
            "source_type": "html",
            "trust_level": "tenant_approved_source",
            "text": "Roaming internet costs 5 BYN per day.",
        }
        data.update(overrides)
        return ChunkMetadata.model_validate(data)

    return factory


@pytest.fixture
def make_retriever() -> Callable[..., InMemoryKnowledgeRetriever]:
    def factory(
        settings: LexicalStubSettings | None = None,
        *,
        clock: Callable[[], float] = lambda: 100.0,
        now: Callable[[], datetime] = lambda: FIXED_NOW,
    ) -> InMemoryKnowledgeRetriever:
        return InMemoryKnowledgeRetriever(settings, clock=clock, now=now)

    return factory


@pytest.fixture
def make_qdrant() -> Callable[..., tuple[QdrantHybridRetriever, InMemoryQdrantGateway]]:
    def factory(
        *,
        embedder: Any = ...,
        reranker: Any = None,
        settings: QdrantRetrieverSettings | None = None,
        clock: Callable[[], float] = lambda: 100.0,
        now: Callable[[], datetime] = lambda: FIXED_NOW,
        gateway: InMemoryQdrantGateway | None = None,
    ) -> tuple[QdrantHybridRetriever, InMemoryQdrantGateway]:
        store = gateway if gateway is not None else InMemoryQdrantGateway()
        dense = HashingFakeEmbedder() if embedder is ... else embedder
        retriever = QdrantHybridRetriever(
            store,
            embedder=dense,
            reranker=reranker,
            settings=settings or QdrantRetrieverSettings(collection_prefix="kbtest_unit"),
            clock=clock,
            now=now,
        )
        return retriever, store

    return factory
