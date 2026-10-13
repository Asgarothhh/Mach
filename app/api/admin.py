import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_admin, verify_transcript_access, AdminUser
from app.models.database import Session, Turn, AuditEvent
from app.schemas.api import SessionResponse, SessionDetailResponse, TurnResponse, TranscriptCorrectionRequest
from app.security.telemetry import get_logger

logger = get_logger("admin_api")
router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


async def log_audit_event(db: AsyncSession, tenant_id: str, actor: str, action: str, details: dict):
    """Асинхронная запись в журнал аудита."""
    audit_event = AuditEvent(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        details=details
    )
    db.add(audit_event)
    await db.commit()


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        db: AsyncSession = Depends(get_db),
        admin: AdminUser = Depends(get_current_admin)
):
    """Фильтрованный список сессий с пагинацией[cite: 16, 17]."""
    # Изоляция тенантов: если админ привязан к конкретному тенанту, форсируем фильтр
    target_tenant = tenant_id if admin.role == "admin" else admin.tenant_id

    query = select(Session).where(Session.tenant_id == target_tenant)
    if status:
        query = query.where(Session.status == status)

    query = query.order_by(Session.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    sessions = result.scalars().all()

    return [
        SessionResponse(
            session_id=s.session_id,
            status=s.status,
            created_at=s.created_at
        ) for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
        session_id: str,
        db: AsyncSession = Depends(get_db),
        admin: AdminUser = Depends(verify_transcript_access)
):
    """Детальная сессия с транскриптами (только для авторизованных)[cite: 17]."""
    # Получаем сессию
    session_result = await db.execute(select(Session).where(Session.session_id == session_id))
    session_obj = session_result.scalar_one_or_none()

    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")

    # Изоляция тенантов[cite: 17]
    if admin.role != "admin" and session_obj.tenant_id != admin.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access denied")

    # Получаем ходы
    turns_result = await db.execute(select(Turn).where(Turn.session_id == session_id).order_by(Turn.started_at))
    turns = turns_result.scalars().all()

    # Запись в аудит факта чтения транскрипта[cite: 16, 17]
    await log_audit_event(
        db=db, tenant_id=session_obj.tenant_id, actor=admin.username,
        action="read_transcript", details={"session_id": session_id}
    )

    logger.info("transcript_accessed", session_id=session_id, actor=admin.username)

    return SessionDetailResponse(
        session_id=session_obj.session_id,
        tenant_id=session_obj.tenant_id,
        status=session_obj.status,
        channel=session_obj.channel,
        created_at=session_obj.created_at,
        turns=[TurnResponse(
            turn_id=t.turn_id, sequence_no=t.sequence_no,
            started_at=t.started_at, redacted_text=t.redacted_text, intent=t.intent
        ) for t in turns]
    )


@router.post("/sessions/{session_id}/transcript-corrections")
async def correct_transcript(
        session_id: str,
        req: TranscriptCorrectionRequest,
        db: AsyncSession = Depends(get_db),
        admin: AdminUser = Depends(verify_transcript_access)
):
    """Ручная коррекция транскрипта с сохранением версии и аудитом[cite: 17]."""
    turn_result = await db.execute(select(Turn).where(Turn.turn_id == req.turn_id, Turn.session_id == session_id))
    turn = turn_result.scalar_one_or_none()

    if not turn:
        raise HTTPException(status_code=404, detail="Turn not found")

    original_text = turn.redacted_text
    turn.redacted_text = req.corrected_text

    # Запись в аудит корректировки (diff и автор)[cite: 17]
    await log_audit_event(
        db=db, tenant_id=admin.tenant_id, actor=admin.username,
        action="correct_transcript",
        details={
            "turn_id": turn.turn_id,
            "original_text": original_text,
            "corrected_text": req.corrected_text,
            "reason": req.reason
        }
    )

    logger.info("transcript_corrected", turn_id=turn.turn_id, actor=admin.username, reason=req.reason)
    return {"status": "success", "message": "Transcript corrected and audited."}