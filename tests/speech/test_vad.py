"""Unit tests for the streaming VAD state machine (SSOT §5.3)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np
import pytest

from speech.contracts import (
    AudioFrame,
    ErrorCode,
    SpeechError,
    VADEndReason,
    VADEvent,
    VADEventType,
)
from speech.vad.silero_vad import SileroVADAdapter, VADConfig

FRAME_MS = 32  # 512 samples @ 16 kHz


async def _agen(items: list[AudioFrame]) -> AsyncIterator[AudioFrame]:
    for item in items:
        yield item


async def _collect(stream: AsyncIterator[VADEvent]) -> list[VADEvent]:
    return [event async for event in stream]


def make_frames(count: int, *, sample_rate: int = 16000, samples: int = 512) -> list[AudioFrame]:
    return [
        AudioFrame(
            session_id="s1",
            turn_id="t1",
            seq=index,
            timestamp_ms=index * FRAME_MS,
            sample_rate=sample_rate,
            pcm_s16le=b"\x00\x00" * samples,
        )
        for index in range(count)
    ]


def make_adapter(probs: list[float], **cfg_overrides: int) -> SileroVADAdapter:
    iterator = iter(probs)

    def probability(frame: np.ndarray, sample_rate: int) -> float:
        return next(iterator)

    config = VADConfig(
        min_speech_duration_ms=cfg_overrides.get("min_speech_duration_ms", 64),
        min_silence_duration_ms=cfg_overrides.get("min_silence_duration_ms", 64),
        prefix_padding_ms=cfg_overrides.get("prefix_padding_ms", 0),
        max_utterance_duration_ms=cfg_overrides.get("max_utterance_duration_ms", 30000),
    )
    return SileroVADAdapter(probability, config)


def run_stream(
    adapter: SileroVADAdapter, probs: list[float], **frame_kwargs: int
) -> list[VADEvent]:
    frames = make_frames(len(probs), **frame_kwargs)
    return asyncio.run(_collect(adapter.stream(_agen(frames))))


def test_speech_segment_start_and_end() -> None:
    probs = [0.1] * 3 + [0.9] * 5 + [0.1] * 4
    events = run_stream(make_adapter(probs), probs)

    assert [event.type for event in events] == [
        VADEventType.SPEECH_START,
        VADEventType.SPEECH_END,
    ]
    start, end = events
    assert start.timestamp_ms == 96  # speech actually began at 96 ms
    assert end.timestamp_ms == 256  # last speech frame, not the silence tail
    assert end.duration_ms == 160
    assert end.reason is VADEndReason.SILENCE
    assert end.confidence == pytest.approx(0.9)


def test_max_utterance_forces_end() -> None:
    probs = [0.9] * 10
    events = run_stream(make_adapter(probs, max_utterance_duration_ms=96), probs)

    ends = [event for event in events if event.type is VADEventType.SPEECH_END]
    assert ends, "expected a forced segment end"
    assert ends[0].reason is VADEndReason.MAX_UTTERANCE
    assert ends[0].duration_ms == 96


def test_stream_end_flushes_active_segment() -> None:
    probs = [0.1, 0.1, 0.9, 0.9, 0.9, 0.9]
    events = run_stream(make_adapter(probs), probs)

    assert events[-1].type is VADEventType.SPEECH_END
    assert events[-1].reason is VADEndReason.STREAM_END
    assert events[-1].timestamp_ms == 192


def test_short_pause_does_not_end_turn() -> None:
    # A brief dip below the start threshold (0.4) must not close the turn.
    probs = [0.9, 0.9, 0.4, 0.4, 0.0, 0.0]
    events = run_stream(make_adapter(probs), probs)

    assert [event.type for event in events] == [
        VADEventType.SPEECH_START,
        VADEventType.SPEECH_END,
    ]
    assert events[1].timestamp_ms == 128


def test_no_speech_yields_no_events() -> None:
    probs = [0.3] * 6
    assert run_stream(make_adapter(probs), probs) == []


def test_uncertain_band_alone_does_not_start_speech() -> None:
    # Probabilities between end- and start-threshold are not speech on their own.
    probs = [0.4] * 6
    assert run_stream(make_adapter(probs), probs) == []


def test_wrong_sample_rate_is_typed_error() -> None:
    probs = [0.9] * 4
    adapter = make_adapter(probs)
    frames = make_frames(len(probs), sample_rate=48000)
    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(_collect(adapter.stream(_agen(frames))))
    assert exc_info.value.code is ErrorCode.INVALID_AUDIO


def test_probability_failure_is_typed_error() -> None:
    def probability(frame: np.ndarray, sample_rate: int) -> float:
        raise RuntimeError("model exploded")

    adapter = SileroVADAdapter(
        probability,
        VADConfig(min_speech_duration_ms=64, min_silence_duration_ms=64, prefix_padding_ms=0),
    )
    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(_collect(adapter.stream(_agen(make_frames(2)))))
    assert exc_info.value.code is ErrorCode.MODEL_UNAVAILABLE
