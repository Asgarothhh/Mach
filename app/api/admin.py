from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import AdminUser, get_current_admin, get_turn_store, verify_transcript_access
from app.models.store import TurnStore
from app.schemas.api import (
    AdminSessionSummary,
    SessionDetailResponse,
    TranscriptCorrectionRequest,
    TurnResponse,
)
from app.security.guardrails import GuardrailsService
from app.security.telemetry import get_logger

logger = get_logger("admin_api")
router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])
_guardrails = GuardrailsService()


def _in_scope(admin: AdminUser, tenant_id: str) -> bool:
    return tenant_id in admin.tenant_scope


@router.get("/sessions", response_model=List[AdminSessionSummary])
async def list_sessions(
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        admin: AdminUser = Depends(get_current_admin),
        store: TurnStore = Depends(get_turn_store),
):
    """Filtered session list, restricted to the admin's tenant_scope."""
    if tenant_id is not None and not _in_scope(admin, tenant_id):
        raise HTTPException(status_code=403, detail="Tenant access denied")
    scoped = [tenant_id] if tenant_id else list(admin.tenant_scope)
    sessions = await store.list_sessions(
        tenant_ids=scoped, status=status, limit=limit, offset=offset
    )
    return [
        AdminSessionSummary(
            session_id=item.session_id,
            tenant_id=item.tenant_id,
            status=item.status,
            channel=item.channel,
            language=item.language,
            created_at=item.created_at,
            ended_at=item.ended_at,
            turn_count=item.turn_count,
        )
        for item in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
        session_id: str,
        admin: AdminUser = Depends(verify_transcript_access),
        store: TurnStore = Depends(get_turn_store),
):
    """Детальная сессия с транскриптами (только для авторизованных)[cite: 17]."""
    session_obj = await store.get_session(session_id)
    if session_obj is None or not _in_scope(admin, session_obj.tenant_id):
        raise HTTPException(status_code=404, detail="Session not found")

    turns = await store.list_turns(session_id)
    await store.record_audit(
        tenant_id=session_obj.tenant_id,
        actor=admin.username,
        action="read_transcript",
        details={"session_id": session_id},
    )
    logger.info("transcript_accessed", session_id=session_id, actor=admin.username)

    return SessionDetailResponse(
        session_id=session_obj.session_id,
        tenant_id=session_obj.tenant_id,
        status=session_obj.status,
        channel=session_obj.channel,
        language=session_obj.language,
        created_at=session_obj.created_at,
        ended_at=session_obj.ended_at,
        turn_count=session_obj.turn_count,
        turns=[
            TurnResponse(
                turn_id=turn.turn_id,
                sequence_no=turn.sequence_no,
                started_at=turn.started_at,
                redacted_text=(
                    _guardrails.process_input(turn.redacted_text).redacted_text
                    if turn.redacted_text
                    else turn.redacted_text
                ),
                intent=turn.intent,
            )
            for turn in turns
        ],
    )


@router.post("/sessions/{session_id}/transcript-corrections")
async def correct_transcript(
        session_id: str,
        req: TranscriptCorrectionRequest,
        admin: AdminUser = Depends(verify_transcript_access),
        store: TurnStore = Depends(get_turn_store),
):
    """Ручная коррекция транскрипта с сохранением версии и аудитом[cite: 17]."""
    session_obj = await store.get_session(session_id)
    if session_obj is None or not _in_scope(admin, session_obj.tenant_id):
        raise HTTPException(status_code=404, detail="Session not found")

    masked = _guardrails.process_input(req.corrected_text)
    updated = await store.update_turn_redacted_text(
        session_id, req.turn_id, masked.redacted_text
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Turn not found")

    await store.record_audit(
        tenant_id=session_obj.tenant_id,
        actor=admin.username,
        action="correct_transcript",
        details={
            "turn_id": updated.turn_id,
            "corrected_text": masked.redacted_text,
            "reason": req.reason,
        },
    )
    logger.info("transcript_corrected", turn_id=updated.turn_id, actor=admin.username, reason=req.reason)
    return {"status": "success", "message": "Transcript corrected and audited."}
