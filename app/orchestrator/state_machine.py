import asyncio
from enum import Enum

from pydantic import BaseModel, Field


class SessionState(str, Enum):
    CREATED = "CREATED"
    CONNECTING = "CONNECTING"
    NOTICE_PENDING = "NOTICE_PENDING"
    LISTENING = "LISTENING"
    ENDPOINT_PENDING = "ENDPOINT_PENDING"
    TRANSCRIBING_FINAL = "TRANSCRIBING_FINAL"
    ROUTING = "ROUTING"
    RETRIEVING = "RETRIEVING"
    GENERATING = "GENERATING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    DEGRADED = "DEGRADED"
    CHAT_HANDOFF = "CHAT_HANDOFF"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    CLOSED = "CLOSED"


class SessionBinding(BaseModel):
    tenant_id: str
    language: str
    channel: str

    class Config:
        frozen = True


class TurnContext(BaseModel):
    turn_id: str
    session_id: str
    tenant_id: str
    cancel_event: asyncio.Event = Field(default_factory=asyncio.Event)

    class Config:
        arbitrary_types_allowed = True

    def cancel(self):
        self.cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()


class SessionManager:
    def __init__(self):
        self.active_sessions: dict[str, SessionState] = {}
        self.active_turns: dict[str, TurnContext] = {}
        self.bindings: dict[str, SessionBinding] = {}

    def bind(self, session_id: str, binding: SessionBinding) -> None:
        self.bindings[session_id] = binding

    def get_binding(self, session_id: str) -> SessionBinding | None:
        return self.bindings.get(session_id)

    def unbind(self, session_id: str) -> None:
        self.bindings.pop(session_id, None)

    def transition(self, session_id: str, new_state: SessionState):
        # Здесь можно добавить валидацию допустимых переходов
        self.active_sessions[session_id] = new_state

    def handle_barge_in(self, session_id: str):
        self.transition(session_id, SessionState.INTERRUPTED)
        if session_id in self.active_turns:
            self.active_turns[session_id].cancel()