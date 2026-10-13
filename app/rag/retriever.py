from typing import Protocol, List
from pydantic import BaseModel

class RetrievalFilters(BaseModel):
    # Фильтры для базы знаний
    service: str | None = None
    topic: str | None = None

class SourceChunk(BaseModel):
    chunk_id: str
    title: str
    url: str
    content: str
    valid_to: str | None = None

class RetrievalResult(BaseModel):
    chunks: List[SourceChunk]
    index_revision: str
    stale_conflict: bool = False

class KnowledgeRetriever(Protocol):
    async def retrieve(
        self, query: str, *, tenant_id: str, language: str, audience: str,
        filters: RetrievalFilters, index_revision: str, deadline_ms: int
    ) -> RetrievalResult: ...

class MockKnowledgeRetriever:
    """Заглушка для Этапа 1/2 до готовности реального поиска Qdrant."""
    async def retrieve(
        self, query: str, *, tenant_id: str, language: str, audience: str,
        filters: RetrievalFilters, index_revision: str, deadline_ms: int
    ) -> RetrievalResult:
        return RetrievalResult(
            chunks=[
                SourceChunk(
                    chunk_id="S1",
                    title="Тарифы в роуминге",
                    url="https://mts.by/roaming",
                    content="Входящие звонки в Турции стоят 1.5 BYN за минуту. Исходящие 3 BYN."
                )
            ],
            index_revision="v1.0",
            stale_conflict=False
        )