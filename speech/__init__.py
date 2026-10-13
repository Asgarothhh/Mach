"""Speech cascade package (ML, track 1): VAD → streaming ASR → streaming TTS.

Normative references:
    * ``docs/SPEC_MTS_VOICE_AGENT_TRACK1.md`` §5.3–5.4, §5.7–5.8, §10, §14;
    * ``docs/DEV_PLAN_TRACK1.md`` §3 "Разработчик 1 — ML".

Design rule: adapters are transport-agnostic and testable without model
weights; heavy optional dependencies (torch, silero) are imported lazily.
"""

from speech.contracts import (
    ASRAdapter,
    ASREvent,
    AudioFrame,
    CancellationToken,
    ErrorCode,
    SpeechError,
    TTSAdapter,
    TTSChunk,
    TTSRequest,
    VADAdapter,
    VADEndReason,
    VADEvent,
    VADEventType,
)

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
