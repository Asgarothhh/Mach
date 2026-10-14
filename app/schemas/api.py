from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.orchestrator.state_machine import SessionState


class TenantCreate(BaseModel):
    display_name: str
    settings_revision: str | None = None

class TenantResponse(BaseModel):
    tenant_id: str
    display_name: str
    created_at: datetime

class SessionCreateRequest(BaseModel):
    tenant_id: str
    channel: str = Field(default="webrtc", description="Канал связи, например, sip, webrtc или mock")
    language: str = Field(default="ru", pattern=r"^[a-z]{2,3}$")

class SessionResponse(BaseModel):
    session_id: str
    status: SessionState
    created_at: datetime


class AdminSessionSummary(BaseModel):
    session_id: str
    tenant_id: str
    status: SessionState
    channel: str
    language: str
    created_at: datetime
    ended_at: datetime | None = None
    turn_count: int = 0

class ErrorResponse(BaseModel):
    detail: str
    error_code: str

class TurnResponse(BaseModel):
    turn_id: str
    sequence_no: str
    started_at: datetime
    redacted_text: str | None = None
    intent: str | None = None

class SessionDetailResponse(BaseModel):
    session_id: str
    tenant_id: str
    status: SessionState
    channel: str
    language: str = "ru"
    created_at: datetime
    ended_at: datetime | None = None
    turn_count: int = 0
    turns: list[TurnResponse] = []

class TranscriptCorrectionRequest(BaseModel):
    turn_id: str
    corrected_text: str
    reason: str = Field(..., description="Причина корректировки, например: 'ASR_error'")

class HandoffResponse(BaseModel):
    session_id: str
    status: str
    handoff_type: str  # "human" или "chat"
    chat_link: str | None = None
    message: str


class SourceRef(BaseModel):
    chunk_id: str
    title: str
    canonical_url: str
    crawled_at: datetime | None = None
    valid_to: datetime | None = None


class TextTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)


class TextTurnResponse(BaseModel):
    session_id: str
    tenant_id: str | None = None
    turn_id: str
    answer_text: str
    answer_status: str
    citation_ids: list[str]
    sources: list[SourceRef]
    fallback_reason: str | None = None
    evidence_status: str | None = None
    index_revision: str | None = None