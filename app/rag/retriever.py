"""Demo knowledge runtime: publishes isolated tenant indexes, no retrieve wrapper."""

from __future__ import annotations

from dataclasses import dataclass

from mts_contracts.knowledge import (
    ACTIVE_INDEX_REVISION,
    KnowledgeRetriever,
    RetrievalFilters,
)
from mts_rag import InMemoryKnowledgeRetriever

from app.rag.demo_fixtures import (
    ACME_TENANT_ID,
    DEMO_INDEX_REVISION,
    MTS_TENANT_ID,
    acme_chunks,
    mts_chunks,
)

_PROBE_QUERY = "probe"
_PROBE_DEADLINE_MS = 50


@dataclass(frozen=True)
class KnowledgeRuntime:
    retriever: KnowledgeRetriever
    tenants: frozenset[str]

    async def probe(self) -> dict[str, str]:
        """Resolve the active revision for each demo tenant. Errors map to unavailable."""
        statuses: dict[str, str] = {}
        for tenant_id in sorted(self.tenants):
            try:
                await self.retriever.retrieve(
                    _PROBE_QUERY,
                    tenant_id=tenant_id,
                    language="ru",
                    audience="caller",
                    filters=RetrievalFilters(),
                    index_revision=ACTIVE_INDEX_REVISION,
                    deadline_ms=_PROBE_DEADLINE_MS,
                )
            except Exception:  # noqa: BLE001 - probe maps any retrieve failure to unavailable
                statuses[tenant_id] = "unavailable"
            else:
                statuses[tenant_id] = "ok"
        return statuses


def build_demo_runtime() -> KnowledgeRuntime:
    retriever = InMemoryKnowledgeRetriever()
    retriever.publish(
        ACME_TENANT_ID, DEMO_INDEX_REVISION, acme_chunks(), activate=True
    )
    retriever.publish(
        MTS_TENANT_ID, DEMO_INDEX_REVISION, mts_chunks(), activate=True
    )
    return KnowledgeRuntime(
        retriever=retriever,
        tenants=frozenset({ACME_TENANT_ID, MTS_TENANT_ID}),
    )
