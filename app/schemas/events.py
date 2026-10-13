from pydantic import BaseModel
from typing import Optional

class BaseEvent(BaseModel):
    session_id: str
    turn_id: str
    timestamp_ms: int

class ASREvent(BaseEvent):
    """Событие от потокового ASR адаптера[cite: 3]."""
    revision: int
    text: str
    is_final: bool
    language: Optional[str] = None
    confidence: Optional[float] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None

class VADEvent(BaseEvent):
    """Событие активности голоса[cite: 3]."""
    is_speech: bool
    confidence: float

class TTSChunkEvent(BaseEvent):
    """Фрагмент синтезированного аудио[cite: 3]."""
    chunk_id: str
    audio_base64: str
    is_last_chunk: bool

class InterruptionEvent(BaseModel):
    """Событие barge-in от пользователя (перебивание)[cite: 3, 4]."""
    session_id: str
    interrupted_turn_id: str
    timestamp_ms: int