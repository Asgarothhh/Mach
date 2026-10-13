"""Unit tests for the Chatterbox adapter contract (no model deps)."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from speech.contracts import (
    CancellationToken,
    ErrorCode,
    SpeechError,
    TTSChunk,
    TTSRequest,
)
from speech.tts.chatterbox_tts import ChatterboxTTSAdapter, ChatterboxTTSConfig


class FakeEngine:
    def __init__(self, *, duration_ms: int = 240, fill: float = 0.3) -> None:
        self.duration_ms = duration_ms
        self.fill = fill
        self.calls: list[tuple[str, str, int]] = []

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray:
        self.calls.append((text, speaker, sample_rate))
        samples = int(sample_rate * self.duration_ms / 1000)
        return np.full(samples, self.fill, dtype=np.float32)


def request(*segments: str, **kwargs: object) -> TTSRequest:
    return TTSRequest(
        session_id="s1",
        turn_id="t1",
        generation_id="gen-1",
        segments=list(segments),
        **kwargs,
    )


async def _collect(adapter: ChatterboxTTSAdapter, req: TTSRequest) -> list[TTSChunk]:
    return [chunk async for chunk in adapter.synthesize(req, CancellationToken())]


def test_chatterbox_streams_native_rate_chunks() -> None:
    engine = FakeEngine()
    adapter = ChatterboxTTSAdapter(engine, ChatterboxTTSConfig())
    chunks = asyncio.run(_collect(adapter, request("Здравствуйте! Как ваши дела?")))

    assert engine.calls[0][0] == "Здравствуйте! Как ваши дела?"
    assert engine.calls[0][2] == 24000
    assert all(chunk.sample_rate == 24000 for chunk in chunks)
    assert chunks[0].is_first_chunk and chunks[-1].is_last_chunk


def test_chatterbox_rejects_unsupported_sample_rate() -> None:
    adapter = ChatterboxTTSAdapter(FakeEngine(), ChatterboxTTSConfig())
    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(_collect(adapter, request("Фраза.", sample_rate=8000)))
    assert exc_info.value.code is ErrorCode.INVALID_AUDIO


def test_chatterbox_keeps_generation_ids() -> None:
    adapter = ChatterboxTTSAdapter(FakeEngine(), ChatterboxTTSConfig())
    chunks = asyncio.run(_collect(adapter, request("Первая фраза.", "Вторая фраза.")))
    assert all(chunk.generation_id == "gen-1" for chunk in chunks)
    assert [chunk.segment_id for chunk in chunks] == [0, 0, 1, 1]
