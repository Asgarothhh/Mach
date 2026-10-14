from pydantic import BaseModel
from typing import Optional

from app.schemas.api import SourceRef

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
    """Фрагмент синтезированного аудио[cite: 3].

    Stage-1 additions (audio pipeline): ``generation_id`` ties chunks to a
    turn so cancelled generations can be dropped client-side, ``sample_rate``
    tells the player how to decode ``audio_base64`` (PCM16-LE mono), and
    ``fallback_text`` carries the answer when TTS is unavailable (text-mode
    degradation per SSOT §10) instead of pretending to send audio.
    """
    chunk_id: str
    audio_base64: str
    is_last_chunk: bool
    generation_id: Optional[str] = None
    sample_rate: Optional[int] = None
    first_chunk_ms: Optional[float] = None
    fallback_text: Optional[str] = None
    text: Optional[str] = None

class InterruptionEvent(BaseModel):
    """Событие barge-in от пользователя (перебивание)[cite: 3, 4]."""
    session_id: str
    interrupted_turn_id: str
    timestamp_ms: int


class AnswerEvent(BaseEvent):
    """Grounded/fallback answer text, sent over WS before TTS starts."""
    answer_text: str
    answer_status: str
    citation_ids: list[str] = []
    sources: list[SourceRef] = []