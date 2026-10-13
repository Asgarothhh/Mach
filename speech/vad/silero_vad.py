"""Streaming VAD adapter on top of Silero VAD (MIT) with configurable endpointing.

Design notes:
    * the Silero model is used as a per-frame speech-probability function; the
      streaming state machine (min speech, min silence, max utterance,
      hysteresis, prefix padding) is ours and is unit-testable without torch;
    * 512 samples @ 16 kHz is the required Silero v5/v6 window; the adapter
      re-frames arbitrary incoming PCM internally;
    * SSOT §5.3 starting points: barge-in confirmation after 150–250 ms of
      speech, endpoint silence 250–450 ms — both are config values here, to be
      tuned on recorded test calls, not constants of the standard.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, Field

from speech.audio import pcm16_to_float32
from speech.contracts import (
    AudioFrame,
    ErrorCode,
    SpeechError,
    VADEndReason,
    VADEvent,
    VADEventType,
)

__all__ = ["SpeechProbabilityFn", "SileroVADAdapter", "VADConfig"]

#: Callable returning speech probability in [0; 1] for one fixed-size window.
SpeechProbabilityFn = Callable[[np.ndarray, int], float]


class VADConfig(BaseModel):
    """Endpointing configuration (SSOT §5.3). Values are tuning starts."""

    sample_rate: int = Field(default=16000, gt=0)
    frame_samples: int = Field(default=512, gt=0, description="Silero window @16 kHz")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    neg_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Hysteresis end threshold"
    )
    min_speech_duration_ms: int = Field(default=160, ge=0)
    min_silence_duration_ms: int = Field(default=320, ge=0)
    prefix_padding_ms: int = Field(default=96, ge=0)
    max_utterance_duration_ms: int = Field(default=30000, gt=0)

    def end_threshold(self) -> float:
        if self.neg_threshold is not None:
            return self.neg_threshold
        return max(0.0, self.threshold - 0.15)


@dataclass
class _SegmentState:
    in_speech: bool = False
    start_ts_ms: float = 0.0
    end_ts_ms: float = 0.0
    speech_run_ms: float = 0.0
    silence_run_ms: float = 0.0
    prob_sum: float = 0.0
    prob_count: int = 0


class _VADStateMachine:
    """Pure endpointing logic; one instance per stream."""

    def __init__(self, config: VADConfig, session_id: str) -> None:
        self.config = config
        self.session_id = session_id
        self._state = _SegmentState()
        self._seq = 0

    def push(self, prob: float, window_end_ms: float, window_ms: float) -> VADEvent | None:
        cfg = self.config
        st = self._state

        if not st.in_speech:
            if prob >= cfg.threshold:
                st.speech_run_ms += window_ms
            elif prob < cfg.end_threshold():
                st.speech_run_ms = 0.0
            # Between end_threshold and threshold: hold the run (hysteresis).

            if st.speech_run_ms > 0 and st.speech_run_ms >= cfg.min_speech_duration_ms:
                st.in_speech = True
                st.start_ts_ms = max(
                    0.0, window_end_ms - st.speech_run_ms - cfg.prefix_padding_ms
                )
                st.end_ts_ms = window_end_ms
                st.silence_run_ms = 0.0
                st.prob_sum = prob
                st.prob_count = 1
                st.speech_run_ms = 0.0
                return self._event(
                    VADEventType.SPEECH_START, st.start_ts_ms, confidence=prob
                )
            return None

        st.end_ts_ms = window_end_ms
        if prob >= cfg.end_threshold():
            st.silence_run_ms = 0.0
            st.prob_sum += prob
            st.prob_count += 1
        else:
            st.silence_run_ms += window_ms

        duration_ms = st.end_ts_ms - st.start_ts_ms
        if st.silence_run_ms >= cfg.min_silence_duration_ms:
            return self._end_segment(VADEndReason.SILENCE)
        if duration_ms >= cfg.max_utterance_duration_ms:
            return self._end_segment(VADEndReason.MAX_UTTERANCE)
        return None

    def flush(self, stream_end_ms: float) -> VADEvent | None:
        """Finalize an unfinished segment when the audio stream ends."""
        if not self._state.in_speech:
            return None
        self._state.end_ts_ms = max(self._state.end_ts_ms, stream_end_ms)
        return self._end_segment(VADEndReason.STREAM_END)

    def _end_segment(self, reason: VADEndReason) -> VADEvent:
        st = self._state
        if reason is VADEndReason.SILENCE:
            last_speech_ts = st.end_ts_ms - st.silence_run_ms
        else:
            last_speech_ts = st.end_ts_ms
        confidence = st.prob_sum / st.prob_count if st.prob_count else None
        event = self._event(
            VADEventType.SPEECH_END,
            last_speech_ts,
            duration_ms=int(round(last_speech_ts - st.start_ts_ms)),
            confidence=confidence,
            reason=reason,
        )
        self._state = _SegmentState()
        return event

    def _event(
        self,
        event_type: VADEventType,
        timestamp_ms: float,
        *,
        duration_ms: int | None = None,
        confidence: float | None = None,
        reason: VADEndReason | None = None,
    ) -> VADEvent:
        event = VADEvent(
            session_id=self.session_id,
            seq=self._seq,
            type=event_type,
            timestamp_ms=int(round(timestamp_ms)),
            duration_ms=duration_ms,
            confidence=confidence,
            reason=reason,
        )
        self._seq += 1
        return event


class SileroVADAdapter:
    """Streaming VAD: ``AudioFrame`` iterator in, ``VADEvent`` iterator out."""

    def __init__(
        self,
        speech_probability: SpeechProbabilityFn,
        config: VADConfig | None = None,
    ) -> None:
        self._speech_probability = speech_probability
        self.config = config or VADConfig()

    @classmethod
    def from_pretrained(cls, config: VADConfig | None = None) -> SileroVADAdapter:
        """Load Silero VAD v6 (MIT). Requires the ``[vad]`` optional deps."""
        cfg = config or VADConfig()
        try:
            import torch  # noqa: F401
            from silero_vad import load_silero_vad
        except ImportError as exc:
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                "silero-vad and torch are required; install with `pip install -e .[vad]`",
            ) from exc

        model = load_silero_vad(onnx=False)
        reset_states = getattr(model, "reset_states", None)

        def probability(frame: np.ndarray, sample_rate: int) -> float:
            import torch

            with torch.no_grad():
                value = model(torch.from_numpy(frame.astype(np.float32)), sample_rate)
            return float(value)

        adapter = cls(probability, cfg)
        adapter._reset_callback = reset_states  # type: ignore[attr-defined]
        return adapter

    async def stream(self, audio_frames: AsyncIterator[AudioFrame]) -> AsyncIterator[VADEvent]:
        cfg = self.config
        frame_bytes = cfg.frame_samples * 2  # mono s16le
        frame_ms = 1000.0 * cfg.frame_samples / cfg.sample_rate

        reset = getattr(self, "_reset_callback", None)
        if reset is not None:
            reset()

        machine: _VADStateMachine | None = None
        buffer = bytearray()
        buffer_ts_ms: float | None = None

        async for frame in audio_frames:
            if frame.sample_rate != cfg.sample_rate or frame.channels != 1:
                raise SpeechError(
                    ErrorCode.INVALID_AUDIO,
                    "VAD expects "
                    f"{cfg.sample_rate} Hz mono PCM16, got "
                    f"{frame.sample_rate} Hz / {frame.channels} ch",
                )
            if machine is None:
                machine = _VADStateMachine(cfg, frame.session_id)
            elif frame.session_id != machine.session_id:
                raise SpeechError(
                    ErrorCode.INVALID_AUDIO, "one VAD stream must serve one session"
                )

            if buffer_ts_ms is None:
                buffer_ts_ms = float(frame.timestamp_ms)
            buffer.extend(frame.pcm_s16le)

            while len(buffer) >= frame_bytes:
                window = bytes(buffer[:frame_bytes])
                del buffer[:frame_bytes]
                assert buffer_ts_ms is not None
                window_end_ms = buffer_ts_ms + frame_ms
                np_window = pcm16_to_float32(window)
                try:
                    prob = await asyncio.to_thread(
                        self._speech_probability, np_window, cfg.sample_rate
                    )
                except SpeechError:
                    raise
                except Exception as exc:  # defensive: model failure must be typed
                    raise SpeechError(
                        ErrorCode.MODEL_UNAVAILABLE, f"VAD inference failed: {exc}"
                    ) from exc
                buffer_ts_ms = window_end_ms

                event = machine.push(min(max(float(prob), 0.0), 1.0), window_end_ms, frame_ms)
                if event is not None:
                    yield event

        if machine is not None:
            event = machine.flush(buffer_ts_ms if buffer_ts_ms is not None else 0.0)
            if event is not None:
                yield event
