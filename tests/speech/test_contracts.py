"""Unit tests for speech contracts and PCM helpers (no model deps required)."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from speech.audio import (
    float32_to_pcm16,
    iter_pcm16_chunks,
    pcm16_duration_ms,
    pcm16_to_float32,
)
from speech.contracts import (
    AudioFrame,
    CancellationToken,
    ErrorCode,
    SpeechError,
    TTSRequest,
)


def test_audio_frame_duration_and_count() -> None:
    frame = AudioFrame(
        session_id="s1",
        seq=0,
        timestamp_ms=0,
        sample_rate=16000,
        pcm_s16le=b"\x00\x00" * 1600,
    )
    assert frame.frame_count == 1600
    assert frame.duration_ms == pytest.approx(100.0)


def test_audio_frame_rejects_negative_timestamp() -> None:
    with pytest.raises(ValidationError):
        AudioFrame(
            session_id="s1", seq=0, timestamp_ms=-1, sample_rate=16000, pcm_s16le=b""
        )


def test_cancellation_token_raises_typed_error() -> None:
    token = CancellationToken()
    token.raise_if_cancelled()
    token.cancel()
    assert token.cancelled
    with pytest.raises(SpeechError) as exc_info:
        token.raise_if_cancelled()
    assert exc_info.value.code is ErrorCode.CANCELLED


def test_error_codes_are_stable_strings() -> None:
    assert ErrorCode.MODEL_UNAVAILABLE.value == "model_unavailable"
    assert ErrorCode.TIMEOUT.value == "timeout"
    assert ErrorCode.INVALID_AUDIO.value == "invalid_audio"
    assert ErrorCode.CANCELLED.value == "cancelled"
    assert ErrorCode.SYNTHESIS_FAILED.value == "synthesis_failed"


def test_tts_request_requires_segments() -> None:
    with pytest.raises(ValidationError):
        TTSRequest(session_id="s1", turn_id="t1", generation_id="g1", segments=[])


def test_pcm_roundtrip_and_odd_bytes() -> None:
    audio = np.array([0.0, 0.5, -0.5], dtype=np.float32)
    pcm = float32_to_pcm16(audio)
    back = pcm16_to_float32(pcm)
    assert np.allclose(back, audio, atol=1e-3)
    with pytest.raises(ValueError):
        pcm16_to_float32(b"\x00")


def test_pcm16_clipping_is_safe() -> None:
    pcm = float32_to_pcm16(np.array([2.0, -2.0], dtype=np.float32))
    assert pcm16_to_float32(pcm).tolist() == pytest.approx([1.0, -1.0], abs=1e-3)


def test_iter_pcm16_chunks_alignment() -> None:
    pcm = b"\x00\x00" * 4800  # 4800 samples
    chunks = list(iter_pcm16_chunks(pcm, sample_rate=24000, chunk_ms=50))
    assert len(chunks) == 4  # 1200 samples per chunk
    assert all(len(chunk) % 2 == 0 for chunk in chunks)


def test_pcm16_duration_ms() -> None:
    assert pcm16_duration_ms(b"\x00\x00" * 1600, 16000) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        pcm16_duration_ms(b"", 0)
