"""Unit tests for the streaming TTS adapter contract (SSOT §5.7)."""

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
from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig


class FakeEngine:
    """Deterministic engine: constant-value audio of a fixed duration."""

    def __init__(
        self,
        *,
        duration_ms: int = 240,
        fill: float = 0.5,
        empty: bool = False,
        fail_on_call: int | None = None,
    ) -> None:
        self.duration_ms = duration_ms
        self.fill = fill
        self.empty = empty
        self.fail_on_call = fail_on_call
        self.calls: list[tuple[str, str, int]] = []

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray:
        self.calls.append((text, speaker, sample_rate))
        if self.fail_on_call is not None and len(self.calls) >= self.fail_on_call:
            raise RuntimeError("engine boom")
        if self.empty:
            return np.zeros(0, dtype=np.float32)
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


async def _collect_chunks(
    adapter: SileroTTSAdapter, req: TTSRequest, token: CancellationToken | None = None
) -> list[TTSChunk]:
    token = token or CancellationToken()
    return [chunk async for chunk in adapter.synthesize(req, token)]


def test_chunks_carry_ids_and_split_by_segments() -> None:
    engine = FakeEngine()
    adapter = SileroTTSAdapter(engine, SileroTTSConfig(sample_rate=24000, max_chunk_ms=120))
    chunks = asyncio.run(_collect_chunks(adapter, request("Первая фраза.", "Вторая фраза.")))

    assert [chunk.segment_id for chunk in chunks] == [0, 0, 1, 1]
    assert [chunk.chunk_id for chunk in chunks] == [0, 1, 2, 3]
    assert all(chunk.generation_id == "gen-1" for chunk in chunks)
    assert chunks[0].is_first_chunk
    assert chunks[0].first_chunk_ms is not None
    assert chunks[1].first_chunk_ms is None
    assert not chunks[0].is_last_chunk
    assert chunks[-1].is_last_chunk
    assert all(chunk.pcm_s16le for chunk in chunks)


def test_cancellation_stops_stream_and_raises() -> None:
    adapter = SileroTTSAdapter(FakeEngine(), SileroTTSConfig(sample_rate=24000))
    token = CancellationToken()

    async def consume_and_cancel() -> int:
        seen = 0
        async for _ in adapter.synthesize(request("Фраза."), token):
            seen += 1
            token.cancel()
        return seen

    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(consume_and_cancel())
    assert exc_info.value.code is ErrorCode.CANCELLED


def test_question_markers_follow_config() -> None:
    engine = FakeEngine()
    adapter = SileroTTSAdapter(engine, SileroTTSConfig(supports_question_intonation=True))
    asyncio.run(_collect_chunks(adapter, request("*Вы* звоните?")))
    assert engine.calls[-1][0] == "*Вы* звоните?"

    engine_plain = FakeEngine()
    adapter_plain = SileroTTSAdapter(
        engine_plain, SileroTTSConfig(supports_question_intonation=False)
    )
    asyncio.run(_collect_chunks(adapter_plain, request("*Вы* звоните?")))
    assert "*" not in engine_plain.calls[-1][0]


def test_text_normalization_reaches_engine_and_chunk_log() -> None:
    engine = FakeEngine()
    adapter = SileroTTSAdapter(engine)
    chunks = asyncio.run(_collect_chunks(adapter, request("Стоимость 10 руб.")))

    assert engine.calls[0][0] == "Стоимость 10 рублей"
    assert chunks[0].text == "Стоимость 10 рублей"


def test_empty_engine_output_is_typed_error() -> None:
    adapter = SileroTTSAdapter(FakeEngine(empty=True))
    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(_collect_chunks(adapter, request("Фраза.")))
    assert exc_info.value.code is ErrorCode.SYNTHESIS_FAILED


def test_engine_failure_is_typed() -> None:
    adapter = SileroTTSAdapter(FakeEngine(fail_on_call=1))
    with pytest.raises(SpeechError) as exc_info:
        asyncio.run(_collect_chunks(adapter, request("Фраза.")))
    assert exc_info.value.code is ErrorCode.SYNTHESIS_FAILED


def test_request_sample_rate_and_speaker_override_config() -> None:
    engine = FakeEngine()
    adapter = SileroTTSAdapter(engine, SileroTTSConfig(sample_rate=24000, speaker="xenia"))
    chunks = asyncio.run(
        _collect_chunks(adapter, request("Фраза.", sample_rate=8000, speaker="aidar"))
    )

    assert engine.calls[0][2] == 8000
    assert engine.calls[0][1] == "aidar"
    assert all(chunk.sample_rate == 8000 for chunk in chunks)


def test_empty_segment_is_skipped() -> None:
    engine = FakeEngine()
    adapter = SileroTTSAdapter(engine)
    chunks = asyncio.run(_collect_chunks(adapter, request("   ", "Нормальная фраза.")))

    assert engine.calls == [("Нормальная фраза.", "xenia", 24000)]
    assert all(chunk.segment_id == 1 for chunk in chunks)
