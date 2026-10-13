from pydantic import BaseModel, Field
from typing import Optional
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