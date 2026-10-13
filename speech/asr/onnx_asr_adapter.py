"""ASR adapters on top of the ``onnx-asr`` runtime (MIT, onnxruntime-only).

License-safe models available through onnx-asr:
    * ``t-tech/t-one`` — streaming Conformer for Russian telephony, Apache-2.0;
    * ``gigaam-v3-ctc`` / ``gigaam-v3-rnnt`` (GigaAM v3, MIT);
    * ``alphacep/vosk-model-ru`` / ``vosk-model-small-ru`` (Apache-2.0);
    * Whisper ONNX exports.

This module implements the SSOT §5.4 ``ASRAdapter`` contract in segment mode:
the orchestrator's VAD closes a turn, the adapter recognizes the finished
segment and emits the final event. T-one's native 300 ms chunk-by-chunk
streaming API (the ``tone`` package) can replace the recognizer later without
changing the contract.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel, Field

from speech.audio import pcm16_to_float32
from speech.contracts import ASREvent, AudioFrame, ErrorCode, SpeechError

__all__ = ["OnnxAsrAdapter", "OnnxAsrConfig", "OnnxAsrRecognizer", "Recognizer"]


@runtime_checkable
class Recognizer(Protocol):
    """Synchronous recognizer: mono float32 in [-1; 1] -> text."""

    def recognize(self, samples: np.ndarray, sample_rate: int) -> str: ...


class OnnxAsrConfig(BaseModel):
    """Adapter configuration."""

    model: str = Field(default="t-tech/t-one", description="onnx-asr model name")
    quantization: str | None = None
    sample_rate: int = Field(default=16000, gt=0)
    max_segment_seconds: float = Field(
        default=20.0,
        gt=0,
        description="Hard cap; a longer turn is force-closed with a final event",
    )


class OnnxAsrRecognizer:
    """Thin wrapper around ``onnx_asr.load_model`` (lazy import)."""

    def __init__(self, model: str, quantization: str | None = None) -> None:
        try:
            import onnx_asr
        except ImportError as exc:  # pragma: no cover - depends on env
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                "onnx-asr is required; install with `pip install onnx-asr[cpu,hub]`",
            ) from exc
        self._model = onnx_asr.load_model(model, quantization=quantization)

    def recognize(self, samples: np.ndarray, sample_rate: int) -> str:
        result = self._model.recognize(samples, sample_rate=sample_rate)
        if isinstance(result, str):
            return result
        if isinstance(result, (list, tuple)):
            return " ".join(str(item) for item in result)
        return str(result)


class OnnxAsrAdapter:
    """Segment-mode ASR adapter: one final event per VAD-closed turn."""

    def __init__(self, recognizer: Recognizer, config: OnnxAsrConfig | None = None) -> None:
        self._recognizer = recognizer
        self.config = config or OnnxAsrConfig()

    @classmethod
    def from_pretrained(cls, config: OnnxAsrConfig | None = None) -> OnnxAsrAdapter:
        cfg = config or OnnxAsrConfig()
        return cls(OnnxAsrRecognizer(cfg.model, cfg.quantization), cfg)

    async def stream(self, audio_frames: AsyncIterator[AudioFrame]) -> AsyncIterator[ASREvent]:
        cfg = self.config
        max_bytes = int(cfg.sample_rate * cfg.max_segment_seconds) * 2

        turn_id: str | None = None
        session_id = ""
        start_ms = 0
        end_ms: int | None = None
        buffer = bytearray()

        async for frame in audio_frames:
            if frame.sample_rate != cfg.sample_rate or frame.channels != 1:
                raise SpeechError(
                    ErrorCode.INVALID_AUDIO,
                    "ASR expects "
                    f"{cfg.sample_rate} Hz mono PCM16, got "
                    f"{frame.sample_rate} Hz / {frame.channels} ch",
                )
            if frame.turn_id is None:
                raise SpeechError(ErrorCode.INVALID_AUDIO, "frames must carry turn_id")

            if turn_id is not None and frame.turn_id != turn_id:
                event = await self._finalize(session_id, turn_id, buffer, start_ms, end_ms)
                if event is not None:
                    yield event
                buffer = bytearray()
                turn_id = None

            if turn_id is None:
                turn_id = frame.turn_id
                session_id = frame.session_id
                start_ms = frame.timestamp_ms
            buffer.extend(frame.pcm_s16le)
            end_ms = frame.timestamp_ms + int(round(frame.duration_ms))

            if len(buffer) >= max_bytes:
                # Hard cap: force-close the turn instead of growing unbounded.
                event = await self._finalize(session_id, turn_id, buffer, start_ms, end_ms)
                if event is not None:
                    yield event
                buffer = bytearray()
                turn_id = None

        if turn_id is not None and buffer:
            event = await self._finalize(session_id, turn_id, buffer, start_ms, end_ms)
            if event is not None:
                yield event

    async def _finalize(
        self,
        session_id: str,
        turn_id: str,
        pcm_s16le: bytearray,
        start_ms: int,
        end_ms: int | None,
    ) -> ASREvent | None:
        if not pcm_s16le:
            return None
        samples = pcm16_to_float32(bytes(pcm_s16le))
        if samples.size == 0:
            return None
        try:
            text = await asyncio.to_thread(
                self._recognizer.recognize, samples, self.config.sample_rate
            )
        except SpeechError:
            raise
        except Exception as exc:  # defensive: engine failure must be typed
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE, f"ASR recognition failed: {exc}"
            ) from exc
        return ASREvent(
            session_id=session_id,
            turn_id=turn_id,
            revision=0,
            text=text.strip(),
            is_final=True,
            language="ru",
            start_ms=start_ms,
            end_ms=end_ms,
        )
