from typing import Protocol

from mts_contracts.knowledge.retrieval import RetrievalFilters, RetrievalResult


class KnowledgeRetriever(Protocol):
    """RAG service contract, SSOT §14.2.

    Implementations:
    - raise InvalidRetrievalRequest, IndexRevisionNotFound, RetrievalUnavailable,
      RetrievalDeadlineExceeded or TenantIsolationError;
    - never raise for an empty or low-relevance result: it is reported via
      RetrievalResult.evidence_status;
    - always let asyncio.CancelledError propagate;
    - return only chunks whose tenant_id equals the requested tenant_id;
    - accept index_revision "active" (ACTIVE_INDEX_REVISION) and report the resolved concrete
      revision in RetrievalResult.index_revision.
    """

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        language: str,
        audience: str,
        filters: RetrievalFilters,
        index_revision: str,
        deadline_ms: int,
    ) -> RetrievalResult: ...
