from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.api.deps import get_db
from app.models.database import Session, Turn
from app.schemas.api import SessionResponse

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


# В реальном приложении здесь должен быть Depends(verify_admin_token)[cite: 4]
@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
        tenant_id: str = None,
        limit: int = 50,
        db: AsyncSession = Depends(get_db)
):
    """Фильтрованный список сессий для админ-панели[cite: 3, 4]."""
    query = select(Session)
    if tenant_id:
        query = query.where(Session.tenant_id == tenant_id)
    query = query.limit(limit)

    result = await db.execute(query)
    sessions = result.scalars().all()

    return [
        SessionResponse(
            session_id=s.session_id,
            status=s.status,
            created_at=s.created_at
        ) for s in sessions
    ]


@router.get("/sessions/{session_id}/turns")
async def get_session_turns(
        session_id: str,
        db: AsyncSession = Depends(get_db)
):
    """Детальная сессия: транскрипт и latency breakdown[cite: 3]."""
    query = select(Turn).where(Turn.session_id == session_id).order_by(Turn.started_at)
    result = await db.execute(query)
    turns = result.scalars().all()

    if not turns:
        raise HTTPException(status_code=404, detail="Turns not found")

    return [{
        "turn_id": t.turn_id,
        "sequence_no": t.sequence_no,
        "redacted_text": t.redacted_text,
        "intent": t.intent
    } for t in turns]