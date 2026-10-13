"""Shared streaming loop for phrase-segmented TTS adapters (SSOT §5.7).

Every segment goes through the same pipeline:

    normalize (text_norm) → optional preprocessor (stress) → engine → PCM chunks

Chunk metadata (``segment_id``/``chunk_id``/``generation_id``) and the
cancellation checks between chunks are identical for all engines, so
barge-in/queue-flush logic on the orchestrator side works the same way.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

import numpy as np

from speech.audio import float32_to_pcm16, iter_pcm16_chunks
from speech.contracts import (
    CancellationToken,
    ErrorCode,
    SpeechError,
    TTSChunk,
    TTSRequest,
)
from speech.text_norm import normalize_for_tts
from speech.tts.preprocess import TextPreprocessor

__all__ = ["SegmentEngine", "synthesize_segments"]


@runtime_checkable
class SegmentEngine(Protocol):
    """Synchronous engine producing mono float32 audio in [-1; 1] for one phrase."""

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray: ...


async def synthesize_segments(
    engine: SegmentEngine,
    request: TTSRequest,
    cancel: CancellationToken,
    *,
    max_chunk_ms: int,
    default_speaker: str,
    default_sample_rate: int,
    supports_question_intonation: bool = True,
    preprocessor: TextPreprocessor | None = None,
) -> AsyncIterator[TTSChunk]:
    """Yield transport-sized audio chunks for the phrase segments of a request."""
    speaker = request.speaker or default_speaker
    sample_rate = request.sample_rate or default_sample_rate

    # Prepare all segments first so ``is_last_chunk`` is correct even when the
    # trailing segment is empty or whitespace-only.
    prepared: list[tuple[int, str, str]] = []  # (segment_id, clean text, engine text)
    for segment_id, raw_text in enumerate(request.segments):
        normalized = normalize_for_tts(
            raw_text, supports_question_intonation=supports_question_intonation
        )
        spoken = normalized.spoken
        if not spoken.strip():
            continue
        engine_text = preprocessor(spoken) if preprocessor is not None else spoken
        prepared.append((segment_id, spoken, engine_text))
    if not prepared:
        return

    started = time.perf_counter()
    chunk_id = 0
    first_chunk_ms: float | None = None
    last_segment_id = prepared[-1][0]

    for segment_id, spoken, engine_text in prepared:
        cancel.raise_if_cancelled()
        t0 = time.perf_counter()
        try:
            audio = await asyncio.to_thread(
                engine.synthesize, engine_text, speaker=speaker, sample_rate=sample_rate
            )
        except SpeechError:
            raise
        except Exception as exc:  # defensive: engine failure must be typed
            raise SpeechError(
                ErrorCode.SYNTHESIS_FAILED, f"TTS engine failed: {exc}"
            ) from exc
        synthesis_ms = (time.perf_counter() - t0) * 1000.0

        pcm = float32_to_pcm16(np.asarray(audio, dtype=np.float32).reshape(-1))
        if len(pcm) == 0:
            raise SpeechError(ErrorCode.SYNTHESIS_FAILED, "TTS produced empty audio")

        chunks = list(
            iter_pcm16_chunks(pcm, sample_rate=sample_rate, chunk_ms=max_chunk_ms)
        )
        for index, chunk_pcm in enumerate(chunks):
            # Cancellation is checked between transport chunks; a segment itself
            # is short by design, so barge-in latency stays bounded.
            cancel.raise_if_cancelled()
            is_first = chunk_id == 0
            if is_first:
                first_chunk_ms = (time.perf_counter() - started) * 1000.0
            yield TTSChunk(
                session_id=request.session_id,
                turn_id=request.turn_id,
                generation_id=request.generation_id,
                segment_id=segment_id,
                chunk_id=chunk_id,
                text=spoken,
                pcm_s16le=chunk_pcm,
                sample_rate=sample_rate,
                is_first_chunk=is_first,
                is_last_chunk=(segment_id == last_segment_id and index == len(chunks) - 1),
                first_chunk_ms=first_chunk_ms if is_first else None,
                synthesis_ms=synthesis_ms if index == 0 else None,
            )
            chunk_id += 1
