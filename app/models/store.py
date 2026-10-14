"""Turn persistence. SQLAlchemy implementation; list-backed fake lives in tests/."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select, text

from app.models.database import AuditEvent, RetrievalEvent, Session, Tenant, Turn
from app.orchestrator.state_machine import SessionState


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class StoredSession:
    session_id: str
    tenant_id: str
    status: SessionState
    channel: str
    language: str
    created_at: datetime
    ended_at: datetime | None
    turn_count: int = 0


@dataclass(frozen=True)
class StoredTurn:
    turn_id: str
    sequence_no: str
    started_at: datetime
    redacted_text: str | None
    intent: str | None


def _as_state(value: object) -> SessionState:
    if isinstance(value, SessionState):
        return value
    return SessionState(str(value))


class TurnStore(Protocol):
    async def ensure_tenants(self, ids: Iterable[str]) -> None: ...

    async def create_session(
        self, session_id: str, tenant_id: str, channel: str, language: str
    ) -> None: ...

    async def record_turn(
        self, turn: Turn, retrieval_event: RetrievalEvent | None
    ) -> None: ...

    async def ping(self) -> bool: ...

    async def update_session_status(self, session_id: str, status: SessionState) -> bool: ...

    async def get_session(self, session_id: str) -> StoredSession | None: ...

    async def list_sessions(
        self,
        *,
        tenant_ids: Sequence[str],
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[StoredSession]: ...

    async def list_turns(self, session_id: str) -> list[StoredTurn]: ...

    async def update_turn_redacted_text(
        self, session_id: str, turn_id: str, redacted_text: str
    ) -> StoredTurn | None: ...

    async def record_audit(
        self, *, tenant_id: str, actor: str, action: str, details: dict
    ) -> None: ...


class SqlAlchemyTurnStore:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def ensure_tenants(self, ids: Iterable[str]) -> None:
        async with self._session_factory() as session:
            for tenant_id in ids:
                existing = await session.get(Tenant, tenant_id)
                if existing is None:
                    session.add(Tenant(tenant_id=tenant_id, display_name=tenant_id))
            await session.commit()

    async def create_session(
        self, session_id: str, tenant_id: str, channel: str, language: str
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                Session(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    channel=channel,
                    language=language,
                    status=SessionState.CREATED,
                )
            )
            await session.commit()

    async def record_turn(
        self, turn: Turn, retrieval_event: RetrievalEvent | None
    ) -> None:
        async with self._session_factory() as session:
            session.add(turn)
            if retrieval_event is not None:
                session.add(retrieval_event)
            await session.commit()

    async def ping(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - ping reports availability, must not raise
            return False

    async def update_session_status(self, session_id: str, status: SessionState) -> bool:
        async with self._session_factory() as session:
            row = await session.get(Session, session_id)
            if row is None:
                return False
            current = _as_state(row.status)
            if current is SessionState.CLOSED and status is not SessionState.CLOSED:
                return False
            row.status = status
            if status is SessionState.CLOSED and row.ended_at is None:
                row.ended_at = _utcnow()
            await session.commit()
            return True

    async def get_session(self, session_id: str) -> StoredSession | None:
        async with self._session_factory() as session:
            row = await session.get(Session, session_id)
            if row is None:
                return None
            count = await session.scalar(
                select(func.count()).select_from(Turn).where(Turn.session_id == session_id)
            )
            return _row_to_stored(row, int(count or 0))

    async def list_sessions(
        self,
        *,
        tenant_ids: Sequence[str],
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[StoredSession]:
        async with self._session_factory() as session:
            query = select(Session).where(Session.tenant_id.in_(list(tenant_ids)))
            if status:
                query = query.where(Session.status == status)
            query = query.order_by(Session.created_at.desc()).offset(offset).limit(limit)
            rows = (await session.execute(query)).scalars().all()
            out: list[StoredSession] = []
            for row in rows:
                count = await session.scalar(
                    select(func.count())
                    .select_from(Turn)
                    .where(Turn.session_id == row.session_id)
                )
                out.append(_row_to_stored(row, int(count or 0)))
            return out

    async def list_turns(self, session_id: str) -> list[StoredTurn]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Turn).where(Turn.session_id == session_id).order_by(Turn.started_at)
            )
            return [_turn_to_stored(turn) for turn in result.scalars().all()]

    async def update_turn_redacted_text(
        self, session_id: str, turn_id: str, redacted_text: str
    ) -> StoredTurn | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Turn).where(Turn.turn_id == turn_id, Turn.session_id == session_id)
            )
            turn = result.scalar_one_or_none()
            if turn is None:
                return None
            turn.redacted_text = redacted_text
            await session.commit()
            return _turn_to_stored(turn)

    async def record_audit(
        self, *, tenant_id: str, actor: str, action: str, details: dict
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    actor=actor,
                    action=action,
                    details=details,
                )
            )
            await session.commit()


def _row_to_stored(row: Session, turn_count: int) -> StoredSession:
    return StoredSession(
        session_id=row.session_id,
        tenant_id=row.tenant_id,
        status=_as_state(row.status),
        channel=row.channel,
        language=row.language or "ru",
        created_at=row.created_at,
        ended_at=row.ended_at,
        turn_count=turn_count,
    )


def _turn_to_stored(turn: Turn) -> StoredTurn:
    return StoredTurn(
        turn_id=turn.turn_id,
        sequence_no=str(turn.sequence_no),
        started_at=turn.started_at,
        redacted_text=turn.redacted_text,
        intent=turn.intent,
    )
