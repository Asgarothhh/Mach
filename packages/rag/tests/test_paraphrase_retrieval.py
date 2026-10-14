"""Paraphrase robustness for both retrievers (stub and Qdrant sparse-only)."""

from collections.abc import Callable
from typing import Any

import pytest
from mts_contracts.knowledge import (
    ChunkMetadata,
    EvidenceStatus,
    RetrievalFilters,
    RetrievalMode,
)

from mts_rag import InMemoryKnowledgeRetriever
from mts_rag.qdrant import QdrantHybridRetriever
from mts_rag.testing import InMemoryQdrantGateway

ChunkFactory = Callable[..., ChunkMetadata]
MakeQdrant = Callable[..., tuple[QdrantHybridRetriever, InMemoryQdrantGateway]]

TEXT = "Лицензия Acme Professional стоит девяносто девять рублей ежемесячно."
PARAPHRASES = (
    "сколько стоит лицензия",
    "Подскажите, пожалуйста, какая цена лицензии?",
    "почём лицензия professional",
    "стоимость лицензии в месяц",
    "ну а лицензию сколько платить",
)
UNRELATED = ("рецепт борща", "как подключить интернет дома")

_ARGS: dict[str, Any] = {
    "language": "ru",
    "audience": "caller",
    "filters": RetrievalFilters(),
    "index_revision": "active",
    "deadline_ms": 1000,
}


def _chunk(make_chunk: ChunkFactory) -> ChunkMetadata:
    return make_chunk(language="ru", title="Прайс-лист", section_path=["Прайс-лист"], text=TEXT)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", PARAPHRASES)
async def test_stub_paraphrases_sufficient(
    make_chunk: ChunkFactory, tenant_a: str, query: str
) -> None:
    retriever = InMemoryKnowledgeRetriever()
    retriever.publish(tenant_a, "rev-1", [_chunk(make_chunk)])
    result = await retriever.retrieve(query, tenant_id=tenant_a, **_ARGS)
    assert result.evidence_status is EvidenceStatus.SUFFICIENT


@pytest.mark.asyncio
@pytest.mark.parametrize("query", UNRELATED)
async def test_stub_unrelated_not_sufficient(
    make_chunk: ChunkFactory, tenant_a: str, query: str
) -> None:
    retriever = InMemoryKnowledgeRetriever()
    retriever.publish(tenant_a, "rev-1", [_chunk(make_chunk)])
    result = await retriever.retrieve(query, tenant_id=tenant_a, **_ARGS)
    assert result.evidence_status is not EvidenceStatus.SUFFICIENT


@pytest.mark.asyncio
@pytest.mark.parametrize("query", PARAPHRASES)
async def test_qdrant_sparse_only_paraphrases_sufficient(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str, query: str
) -> None:
    retriever, _gateway = make_qdrant(embedder=None)
    await retriever.publish(tenant_a, "rev-1", [_chunk(make_chunk)])
    result = await retriever.retrieve(query, tenant_id=tenant_a, **_ARGS)
    assert result.retrieval_mode is RetrievalMode.SPARSE_ONLY
    assert result.evidence_status is EvidenceStatus.SUFFICIENT


@pytest.mark.asyncio
@pytest.mark.parametrize("query", UNRELATED)
async def test_qdrant_sparse_only_unrelated_not_sufficient(
    make_chunk: ChunkFactory, make_qdrant: MakeQdrant, tenant_a: str, query: str
) -> None:
    retriever, _gateway = make_qdrant(embedder=None)
    await retriever.publish(tenant_a, "rev-1", [_chunk(make_chunk)])
    result = await retriever.retrieve(query, tenant_id=tenant_a, **_ARGS)
    assert result.evidence_status is not EvidenceStatus.SUFFICIENT
