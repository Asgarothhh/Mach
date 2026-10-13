"""Unit tests for the voice-agent speech cascade (junction: PCM -> VAD -> ASR)."""

from __future__ import annotations

import asyncio
import time

import numpy as np
import pytest

from app.voice_agent.speech_cascade import SAMPLE_RATE, SpeechCascade
from speech.contracts import ErrorCode, SpeechError, VADEvent
from speech.vad.silero_vad import SileroVADAdapter, VADConfig

CHUNK_SAMPLES = 512  # one VAD window = 32 ms @16 kHz
CHUNK_BYTES = CHUNK_SAMPLES * 2


def marker_chunk(value: int, samples: int = CHUNK_SAMPLES) -> bytes:
    """A chunk whose every sample equals ``value`` (identifies its position)."""
    return np.full(samples, value, dtype="<i2").tobytes()


def make_vad(probs: list[float], **overrides: int) -> SileroVADAdapter:
    iterator = iter(probs)

    def probability(frame: np.ndarray, sample_rate: int) -> float:
        try:
            return next(iterator)
        except StopIteration:
            return 0.1

    config = VADConfig(
        min_speech_duration_ms=overrides.get("min_speech_duration_ms", 64),
        min_silence_duration_ms=overrides.get("min_silence_duration_ms", 64),
        prefix_padding_ms=overrides.get("prefix_padding_ms", 64),
        max_utterance_duration_ms=overrides.get("max_utterance_duration_ms", 30000),
    )
    return SileroVADAdapter(probability, config)


class FakeRecognizer:
    """Records the segments it is asked to recognize."""

    def __init__(self, text: str = "тест") -> None:
        self.text = text
        self.segments: list[np.ndarray] = []

    def recognize(self, samples: np.ndarray, sample_rate: int) -> str:
        self.segments.append(np.asarray(samples))
        return self.text


async def feed_chunks(cascade: SpeechCascade, chunks: list[bytes], *, settle: float = 0.01) -> None:
    for chunk in chunks:
        await cascade.feed(chunk)
        await asyncio.sleep(settle)  # let the VAD task keep up (keeps capture deterministic)


def test_segment_becomes_final_asr_event_with_retroactive_capture() -> None:
    probs = [0.1] * 3 + [0.9] * 8 + [0.1] * 4
    vad = make_vad(probs, prefix_padding_ms=64)
    recognizer = FakeRecognizer("привет")
    vad_events: list[VADEvent] = []
    asr_events = []

    async def main() -> None:
        cascade = SpeechCascade(
            "s1",
            on_vad=lambda event: _record(vad_events, event),
            on_asr=lambda event: _record(asr_events, event),
            vad_adapter=vad,
            recognizer=recognizer,
        )
        chunks = [marker_chunk(index) for index in range(len(probs))]
        await feed_chunks(cascade, chunks)
        await cascade.close()

    asyncio.run(main())

    assert [event.type.value for event in vad_events] == ["speech_start", "speech_end"]
    assert len(asr_events) == 1
    event = asr_events[0]
    assert event.text == "привет"
    assert event.is_final is True
    assert event.revision == 0
    assert event.turn_id == "s1:t1"
    assert event.end_ms == 352  # last speech frame, silence tail excluded

    # Retroactive capture: speech starts at chunk 3, but the segment must begin
    # with lookbehind (prefix padding) — chunk 1, not chunk 3.
    assert len(recognizer.segments) == 1
    samples = recognizer.segments[0]
    first_marker = int(round(float(samples[0]) * 32768))
    assert first_marker == 1
    assert len(samples) >= int(0.32 * SAMPLE_RATE)  # >= 320 ms of speech captured


def test_capture_starts_at_padding_when_frames_arrive_while_vad_lags() -> None:
    """All frames fed before the VAD handles SPEECH_START are available (no gaps)."""
    probs = [0.1] * 3 + [0.9] * 8 + [0.1] * 4
    vad = make_vad(probs, prefix_padding_ms=64)
    recognizer = FakeRecognizer("ok")

    async def main() -> None:
        cascade = SpeechCascade(
            "s2",
            on_vad=lambda event: asyncio.sleep(0),
            on_asr=lambda event: asyncio.sleep(0),
            vad_adapter=vad,
            recognizer=recognizer,
        )
        # Feed everything without yielding: the VAD task processes the whole
        # backlog afterwards; the capture must still contain the segment start.
        for index in range(len(probs)):
            await cascade.feed(marker_chunk(index))
        await cascade.close()

    asyncio.run(main())

    assert recognizer.segments, "segment was not recognized"
    first_marker = int(round(float(recognizer.segments[0][0]) * 32768))
    assert first_marker == 1  # no dropped chunks between feed() and VAD handling


def test_silence_watchdog_closes_an_open_segment_without_trailing_audio() -> None:
    """If the stream stops mid-utterance, the watchdog endpoints the turn."""

    async def main() -> None:
        # Speech starts and then the channel goes silent (no further feed calls).
        probs = [0.1] * 3 + [0.9] * 8
        vad = make_vad(probs, prefix_padding_ms=64)
        recognizer = FakeRecognizer("watchdog")
        asr_events: list = []

        async def on_asr(event) -> None:
            asr_events.append(event)

        cascade = SpeechCascade(
            "s3",
            on_vad=lambda event: asyncio.sleep(0),
            on_asr=on_asr,
            vad_adapter=vad,
            recognizer=recognizer,
        )
        for index in range(len(probs)):
            await cascade.feed(marker_chunk(index))

        deadline = time.monotonic() + 5.0
        while not asr_events and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        closed_by_watchdog = bool(asr_events)
        await cascade.close()
        assert closed_by_watchdog, "watchdog did not endpoint the open segment"
        assert asr_events[0].text == "watchdog"

    asyncio.run(main())


def test_feed_validates_payload_and_rejects_closed_cascade() -> None:
    async def main() -> None:
        cascade = SpeechCascade(
            "s4",
            on_vad=lambda event: asyncio.sleep(0),
            on_asr=lambda event: asyncio.sleep(0),
            vad_adapter=make_vad([0.1] * 4),
            recognizer=FakeRecognizer(),
        )
        with pytest.raises(SpeechError) as excinfo:
            await cascade.feed(b"\x01\x02\x03")  # odd length
        assert excinfo.value.code is ErrorCode.INVALID_AUDIO
        with pytest.raises(SpeechError):
            await cascade.feed(b"")
        await cascade.close()
        with pytest.raises(SpeechError):
            await cascade.feed(marker_chunk(0))

    asyncio.run(main())


async def _record(sink: list, event) -> None:
    sink.append(event)
