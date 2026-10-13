from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.orchestrator.state_machine import SessionState

class TenantCreate(BaseModel):
    display_name: str
    settings_revision: Optional[str] = None

class TenantResponse(BaseModel):
    tenant_id: str
    display_name: str
    created_at: datetime

class SessionCreateRequest(BaseModel):
    tenant_id: str
    channel: str = Field(default="webrtc", description="Канал связи, например, sip, webrtc или mock")
    language: str = Field(default="ru")

class SessionResponse(BaseModel):
    session_id: str
    status: SessionState
    created_at: datetime

class ErrorResponse(BaseModel):
    detail: str
    error_code: str

class TurnResponse(BaseModel):
    turn_id: str
    sequence_no: str
    started_at: datetime
    redacted_text: Optional[str] = None
    intent: Optional[str] = None

class SessionDetailResponse(BaseModel):
    session_id: str
    tenant_id: str
    status: SessionState
    channel: str
    created_at: datetime
    turns: List[TurnResponse] = []

class TranscriptCorrectionRequest(BaseModel):
    turn_id: str
    corrected_text: str
    reason: str = Field(..., description="Причина корректировки, например: 'ASR_error'")