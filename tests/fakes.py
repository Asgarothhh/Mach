"""List-backed store and retriever fakes for in-process tests. Not used at runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from app.models.database import RetrievalEvent, Turn


class InMemoryTurnStore:
    def __init__(self) -> None:
        self.tenants: list[str] = []
        self.sessions: list[dict] = []
        self.turns: list[Turn] = []
        self.retrieval_events: list[RetrievalEvent] = []
        self.fail_record = False
        self.fail_ping = False

    async def ensure_tenants(self, ids: Iterable[str]) -> None:
        for tenant_id in ids:
            if tenant_id not in self.tenants:
                self.tenants.append(tenant_id)

    async def create_session(
        self, session_id: str, tenant_id: str, channel: str, language: str
    ) -> None:
        self.sessions.append(
            {
                "session_id": session_id,
                "tenant_id": tenant_id,
                "channel": channel,
                "language": language,
            }
        )

    async def record_turn(
        self, turn: Turn, retrieval_event: RetrievalEvent | None
    ) -> None:
        if self.fail_record:
            raise RuntimeError("store unavailable")
        self.turns.append(turn)
        if retrieval_event is not None:
            self.retrieval_events.append(retrieval_event)

    async def ping(self) -> bool:
        return not self.fail_ping


class SpyRetriever:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls: list[dict] = []

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        language: str,
        audience: str,
        filters,
        index_revision: str,
        deadline_ms: int,
    ):
        self.calls.append(
            {
                "query": query,
                "tenant_id": tenant_id,
                "language": language,
                "audience": audience,
                "filters": filters,
                "index_revision": index_revision,
                "deadline_ms": deadline_ms,
            }
        )
        return await self.inner.retrieve(
            query,
            tenant_id=tenant_id,
            language=language,
            audience=audience,
            filters=filters,
            index_revision=index_revision,
            deadline_ms=deadline_ms,
        )


class HangingRetriever:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        language: str,
        audience: str,
        filters,
        index_revision: str,
        deadline_ms: int,
    ):
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("hanging retriever should have been cancelled")


class RaisingRetriever:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        language: str,
        audience: str,
        filters,
        index_revision: str,
        deadline_ms: int,
    ):
        raise self.exc


class CountingLLM:
    def __init__(self, inner=None, chunks: list[str] | None = None) -> None:
        self.inner = inner
        self.chunks = chunks
        self.calls = 0
        self.is_mock = True

    async def stream_answer(self, model_id, messages, turn_context):
        self.calls += 1
        if self.chunks is not None:
            for chunk in self.chunks:
                if turn_context.is_cancelled:
                    return
                yield chunk
            return
        assert self.inner is not None
        async for chunk in self.inner.stream_answer(model_id, messages, turn_context):
            yield chunk
