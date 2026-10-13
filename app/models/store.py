"""Turn persistence. SQLAlchemy implementation; list-backed fake lives in tests/."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from sqlalchemy import text

from app.models.database import RetrievalEvent, Session, Tenant, Turn
from app.orchestrator.state_machine import SessionState


class TurnStore(Protocol):
    async def ensure_tenants(self, ids: Iterable[str]) -> None: ...

    async def create_session(
        self, session_id: str, tenant_id: str, channel: str, language: str
    ) -> None: ...

    async def record_turn(
        self, turn: Turn, retrieval_event: RetrievalEvent | None
    ) -> None: ...

    async def ping(self) -> bool: ...


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
