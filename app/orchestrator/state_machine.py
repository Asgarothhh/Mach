import asyncio
from collections import deque
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field

HISTORY_EXCHANGES = 3


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


@dataclass(frozen=True)
class Exchange:
    """One finished turn kept in short-lived session memory (redacted text only)."""

    user_text: str
    query: str
    answer_text: str
    kind: str


class SessionManager:
    def __init__(self):
        self.active_sessions: dict[str, SessionState] = {}
        self.active_turns: dict[str, TurnContext] = {}
        self.bindings: dict[str, SessionBinding] = {}
        self.history: dict[str, deque[Exchange]] = {}
        self.turn_counts: dict[str, int] = {}

    def bind(self, session_id: str, binding: SessionBinding) -> None:
        self.bindings[session_id] = binding

    def get_binding(self, session_id: str) -> SessionBinding | None:
        return self.bindings.get(session_id)

    def unbind(self, session_id: str) -> None:
        self.bindings.pop(session_id, None)
        self.history.pop(session_id, None)
        self.turn_counts.pop(session_id, None)

    def next_sequence_no(self, session_id: str) -> int:
        self.turn_counts[session_id] = self.turn_counts.get(session_id, 0) + 1
        return self.turn_counts[session_id]

    def record_exchange(self, session_id: str, exchange: Exchange) -> None:
        if session_id not in self.history:
            self.history[session_id] = deque(maxlen=HISTORY_EXCHANGES)
        self.history[session_id].append(exchange)

    def recent_exchanges(self, session_id: str) -> tuple[Exchange, ...]:
        return tuple(self.history.get(session_id, ()))

    def transition(self, session_id: str, new_state: SessionState):
        current = self.active_sessions.get(session_id)
        if current is SessionState.CLOSED and new_state is not SessionState.CLOSED:
            return
        self.active_sessions[session_id] = new_state
        if new_state is SessionState.CLOSED:
            self.history.pop(session_id, None)

    def handle_barge_in(self, session_id: str):
        self.transition(session_id, SessionState.INTERRUPTED)
        if session_id in self.active_turns:
            self.active_turns[session_id].cancel()