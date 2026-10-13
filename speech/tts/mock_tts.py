"""Deterministic PCM TTS adapter for tests and the CPU demo stand.

Yields a short 440 Hz tone sized to the phrase so barge-in has a real
playback window. This is not a voice model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np

from speech.audio import float32_to_pcm16, iter_pcm16_chunks
from speech.contracts import CancellationToken, TTSChunk, TTSRequest

__all__ = ["MockTTSAdapter", "DEFAULT_SAMPLE_RATE"]

DEFAULT_SAMPLE_RATE = 24000
_CHUNK_MS = 40


class MockTTSAdapter:
    """Tone-generator TTS that honours ``CancellationToken`` between chunks."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate

    async def synthesize(
        self, request: TTSRequest, cancel: CancellationToken
    ) -> AsyncIterator[TTSChunk]:
        first = True
        for segment_id, text in enumerate(request.segments):
            cancel.raise_if_cancelled()
            duration_s = min(0.08 + 0.01 * min(len(text), 20), 0.4)
            n_samples = max(1, int(self.sample_rate * duration_s))
            t = np.arange(n_samples, dtype=np.float32) / self.sample_rate
            audio = (0.1 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
            pcm = float32_to_pcm16(audio)
            pieces = list(
                iter_pcm16_chunks(pcm, sample_rate=self.sample_rate, chunk_ms=_CHUNK_MS)
            ) or [pcm]
            for chunk_id, piece in enumerate(pieces):
                cancel.raise_if_cancelled()
                yield TTSChunk(
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    generation_id=request.generation_id,
                    segment_id=segment_id,
                    chunk_id=chunk_id,
                    text=text,
                    pcm_s16le=piece,
                    sample_rate=self.sample_rate,
                    is_first_chunk=first,
                    is_last_chunk=False,
                )
                first = False
