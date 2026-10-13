"""Unit tests for the onnx-asr segment-mode adapter (no model deps)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np
import pytest

from speech.asr.onnx_asr_adapter import OnnxAsrAdapter, OnnxAsrConfig
from speech.contracts import ASREvent, AudioFrame, ErrorCode, SpeechError


class FakeRecognizer:
    def __init__(self, text: str = "тестовая реплика", fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.calls: list[float] = []

    def recognize(self, samples: np.ndarray, sample_rate: int) -> str:
        self.calls.append(samples.size / sample_rate)
        if self.fail:
            raise RuntimeError("engine exploded")
        return self.text


async def _agen(frames: list[AudioFrame]) -> AsyncIterator[AudioFrame]:
    for frame in frames:
        yield frame


async def _collect(stream: AsyncIterator[ASREvent]) -> list[ASREvent]:
    return [event async for event in stream]


def make_frames(
    turn_id: str, seconds: float, *, sample_rate: int = 16000, start_ms: int = 0
) -> list[AudioFrame]:
    frames = []
    samples = int(sample_rate * seconds)
    for index in range(0, samples, 1600):  # 100 ms frames
        chunk = min(1600, samples - index)
        frames.append(
            AudioFrame(
                session_id="s1",
                turn_id=turn_id,
                seq=len(frames),
                timestamp_ms=start_ms + index * 1000 // sample_rate,
                sample_rate=sample_rate,
                pcm_s16le=b"\x00\x00" * chunk,
            )
        )
    return frames


def test_single_turn_produces_final_event() -> None:
    recognizer = FakeRecognizer("привет мир")
    adapter = OnnxAsrAdapter(recognizer, OnnxAsrConfig())
    events = asyncio.run(_collect(adapter.stream(_agen(make_frames("t1", 1.0)))))

    assert len(events) == 1
    event = events[0]
    assert event.is_final and event.turn_id == "t1"
    assert event.text == "привет мир"
    assert event.start_ms == 0 and event.end_ms is not None
    assert recognizer.calls == [pytest.approx(1.0, abs=0.01)]


def test_two_turns_produce_two_finals() -> None:
    adapter = OnnxAsrAdapter(FakeRecognizer("раз"), OnnxAsrConfig())
    frames = make_frames("t1", 0.5) + make_frames("t2", 0.5, start_ms=1000)
    events = asyncio.run(_collect(adapter.stream(_agen(frames))))

    assert [event.turn_id for event in events] == ["t1", "t2"]


def test_max_segment_force_closes_turn() -> None:
    recognizer = FakeRecognizer("длинная")
    adapter = OnnxAsrAdapter(recognizer, OnnxAsrConfig(max_segment_seconds=0.5))
    events = asyncio.run(_collect(adapter.stream(_agen(make_frames("t1", 1.5)))))

    assert len(events) == 3  # 0.5 s cap -> three finals
    assert all(event.turn_id == "t1" for event in events)


def test_wrong_sample_rate_is_typed_error() -> None:
    adapter = OnnxAsrAdapter(FakeRecognizer(), OnnxAsrConfig())
    frames = make_frames("t1", 0.5, sample_rate=48000)
    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(_collect(adapter.stream(_agen(frames))))
    assert exc_info.value.code is ErrorCode.INVALID_AUDIO


def test_missing_turn_id_is_typed_error() -> None:
    adapter = OnnxAsrAdapter(FakeRecognizer(), OnnxAsrConfig())
    frame = AudioFrame(
        session_id="s1",
        seq=0,
        timestamp_ms=0,
        sample_rate=16000,
        pcm_s16le=b"\x00\x00" * 100,
    )
    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(_collect(adapter.stream(_agen([frame]))))
    assert exc_info.value.code is ErrorCode.INVALID_AUDIO


def test_recognizer_failure_is_typed() -> None:
    adapter = OnnxAsrAdapter(FakeRecognizer(fail=True), OnnxAsrConfig())
    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(_collect(adapter.stream(_agen(make_frames("t1", 0.3)))))
    assert exc_info.value.code is ErrorCode.MODEL_UNAVAILABLE
