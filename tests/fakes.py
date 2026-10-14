"""List-backed store and retriever fakes for in-process tests. Not used at runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from app.models.database import RetrievalEvent, Turn
from app.models.store import StoredSession, StoredTurn
from app.orchestrator.state_machine import SessionState


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InMemoryTurnStore:
    def __init__(self) -> None:
        self.tenants: list[str] = []
        self.sessions: list[dict] = []
        self.turns: list[Turn] = []
        self.retrieval_events: list[RetrievalEvent] = []
        self.audit_events: list[dict] = []
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
                "status": SessionState.CREATED,
                "created_at": _utcnow(),
                "ended_at": None,
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

    def _find_session(self, session_id: str) -> dict | None:
        for row in self.sessions:
            if row["session_id"] == session_id:
                return row
        return None

    def _turn_count(self, session_id: str) -> int:
        return sum(1 for turn in self.turns if turn.session_id == session_id)

    def _to_stored(self, row: dict) -> StoredSession:
        status = row.get("status", SessionState.CREATED)
        if not isinstance(status, SessionState):
            status = SessionState(str(status))
        return StoredSession(
            session_id=row["session_id"],
            tenant_id=row["tenant_id"],
            status=status,
            channel=row["channel"],
            language=row.get("language") or "ru",
            created_at=row["created_at"],
            ended_at=row.get("ended_at"),
            turn_count=self._turn_count(row["session_id"]),
        )

    async def update_session_status(self, session_id: str, status: SessionState) -> bool:
        row = self._find_session(session_id)
        if row is None:
            return False
        current = row.get("status", SessionState.CREATED)
        if not isinstance(current, SessionState):
            current = SessionState(str(current))
        if current is SessionState.CLOSED and status is not SessionState.CLOSED:
            return False
        row["status"] = status
        if status is SessionState.CLOSED and row.get("ended_at") is None:
            row["ended_at"] = _utcnow()
        return True

    async def get_session(self, session_id: str) -> StoredSession | None:
        row = self._find_session(session_id)
        return None if row is None else self._to_stored(row)

    async def list_sessions(
        self,
        *,
        tenant_ids: Sequence[str],
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[StoredSession]:
        allowed = set(tenant_ids)
        rows = [row for row in self.sessions if row["tenant_id"] in allowed]
        if status:
            rows = [
                row
                for row in rows
                if str(row.get("status", SessionState.CREATED)) == str(status)
            ]
        rows = sorted(rows, key=lambda item: item["created_at"], reverse=True)
        sliced = rows[offset : offset + limit]
        return [self._to_stored(row) for row in sliced]

    async def list_turns(self, session_id: str) -> list[StoredTurn]:
        turns = [turn for turn in self.turns if turn.session_id == session_id]
        turns.sort(key=lambda item: item.started_at or datetime.min.replace(tzinfo=UTC))
        return [
            StoredTurn(
                turn_id=turn.turn_id,
                sequence_no=str(turn.sequence_no),
                started_at=turn.started_at or _utcnow(),
                redacted_text=turn.redacted_text,
                intent=turn.intent,
            )
            for turn in turns
        ]

    async def update_turn_redacted_text(
        self, session_id: str, turn_id: str, redacted_text: str
    ) -> StoredTurn | None:
        for turn in self.turns:
            if turn.turn_id == turn_id and turn.session_id == session_id:
                turn.redacted_text = redacted_text
                return StoredTurn(
                    turn_id=turn.turn_id,
                    sequence_no=str(turn.sequence_no),
                    started_at=turn.started_at,
                    redacted_text=turn.redacted_text,
                    intent=turn.intent,
                )
        return None

    async def record_audit(
        self, *, tenant_id: str, actor: str, action: str, details: dict
    ) -> None:
        self.audit_events.append(
            {
                "tenant_id": tenant_id,
                "actor": actor,
                "action": action,
                "details": details,
                "timestamp": _utcnow(),
            }
        )


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
