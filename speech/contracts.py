"""Typed contracts of the speech cascade (VAD → ASR → orchestrator → TTS).

This module is the single place where the ML side (``speech/``) defines the
interfaces consumed by the orchestrator, telephony adapters and UI.

Normative references:
    * ``docs/SPEC_MTS_VOICE_AGENT_TRACK1.md`` §5.4 (streaming ASR interface),
      §5.7 (streaming TTS), §14.1 (orchestrator), §10 (timeouts/cancellation);
    * ``docs/DEV_PLAN_TRACK1.md`` §3 "Адаптеры и потоковые события".

Rules kept here on purpose:
    * interim revisions and final transcripts are separate events;
    * every TTS audio chunk carries session/turn/generation identifiers so the
      orchestrator can drop chunks of cancelled generations;
    * all errors are typed (``model_unavailable`` / ``timeout`` /
      ``invalid_audio`` / ``cancelled`` / ``synthesis_failed``).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

__all__ = [
    "ASRAdapter",
    "ASREvent",
    "AudioFrame",
    "CancellationToken",
    "ErrorCode",
    "SpeechError",
    "TTSAdapter",
    "TTSChunk",
    "TTSRequest",
    "VADAdapter",
    "VADEndReason",
    "VADEvent",
    "VADEventType",
]


class ErrorCode(StrEnum):
    """Typed error taxonomy required by the track-1 plan (ML section)."""

    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"
    INVALID_AUDIO = "invalid_audio"
    CANCELLED = "cancelled"
    SYNTHESIS_FAILED = "synthesis_failed"


class SpeechError(Exception):
    """Typed speech-pipeline error; never leaks model internals to the caller."""

    def __init__(self, code: ErrorCode, message: str = "", *, retryable: bool = False) -> None:
        super().__init__(f"{code.value}: {message}" if message else code.value)
        self.code = code
        self.message = message
        self.retryable = retryable


class AudioFrame(BaseModel):
    """PCM16-LE audio frame.

    ``timestamp_ms`` is the caller-provided time of the first sample relative
    to call start. Frames of one stream are expected to be contiguous; gaps are
    a telephony-adapter concern, not an ML one.
    """

    session_id: str
    turn_id: str | None = None
    seq: int = Field(ge=0, description="Monotonic frame counter within the stream")
    timestamp_ms: int = Field(ge=0)
    sample_rate: int = Field(gt=0, description="Hz, e.g. 16000 for VAD")
    channels: int = Field(default=1, ge=1, le=2)
    pcm_s16le: bytes

    @property
    def frame_count(self) -> int:
        """Number of audio frames (samples per channel) in the payload."""
        return len(self.pcm_s16le) // (2 * self.channels)

    @property
    def duration_ms(self) -> float:
        samples = len(self.pcm_s16le) / (2 * self.channels)
        return samples / self.sample_rate * 1000.0


class VADEventType(StrEnum):
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"


class VADEndReason(StrEnum):
    SILENCE = "silence"
    MAX_UTTERANCE = "max_utterance"
    STREAM_END = "stream_end"


class VADEvent(BaseModel):
    """Voice-activity event with timestamps and confidence (SSOT §5.3)."""

    session_id: str
    seq: int = Field(ge=0)
    type: VADEventType
    timestamp_ms: int = Field(ge=0, description="Call-relative time of the event")
    duration_ms: int | None = Field(default=None, description="Speech duration for SPEECH_END")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: VADEndReason | None = None


class ASREvent(BaseModel):
    """ASR interim/final hypothesis (SSOT §5.4 interface, kept unchanged)."""

    session_id: str
    turn_id: str
    revision: int = Field(ge=0)
    text: str
    is_final: bool
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class TTSRequest(BaseModel):
    """Phrase-sized segments to synthesize.

    ``segments`` are semantic phrase chunks produced by the answer validator;
    the adapter may split the *audio* into transport chunks but must not change
    the segment semantics.
    """

    session_id: str
    turn_id: str
    generation_id: str
    segments: list[str] = Field(min_length=1)
    language: str = "ru"
    speaker: str | None = None
    sample_rate: int | None = Field(default=None, gt=0)


class TTSChunk(BaseModel):
    """Audio chunk plus identifiers so stale generations can be dropped (§5.7)."""

    session_id: str
    turn_id: str
    generation_id: str
    segment_id: int = Field(ge=0)
    chunk_id: int = Field(ge=0)
    text: str
    pcm_s16le: bytes
    sample_rate: int = Field(gt=0)
    is_first_chunk: bool = False
    is_last_chunk: bool = False
    first_chunk_ms: float | None = Field(default=None, ge=0.0)
    synthesis_ms: float | None = Field(default=None, ge=0.0)


class CancellationToken:
    """Cooperative cancellation token propagated through ASR/LLM/TTS (§4.1)."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise SpeechError(ErrorCode.CANCELLED)


@runtime_checkable
class VADAdapter(Protocol):
    """Streaming VAD: audio frames in, speech start/end events out."""

    def stream(self, audio_frames: AsyncIterator[AudioFrame]) -> AsyncIterator[VADEvent]: ...


@runtime_checkable
class ASRAdapter(Protocol):
    """Streaming ASR: audio frames in, interim/final hypotheses out (§5.4)."""

    def stream(self, audio_frames: AsyncIterator[AudioFrame]) -> AsyncIterator[ASREvent]: ...


@runtime_checkable
class TTSAdapter(Protocol):
    """Streaming TTS: phrase segments in, audio chunks out (§5.7)."""

    def synthesize(
        self, request: TTSRequest, cancel: CancellationToken
    ) -> AsyncIterator[TTSChunk]: ...
