"""Sentence-segmented streaming TTS for the orchestrator (ML side of the junction).

* collects LLM answer deltas, flushes complete sentences to the ML TTS
  adapter (Silero CIS-base MIT + silero-stress, voice ``ru_bogdan`` by
  default) — phrase-sized segments per SSOT §5.7;
* every transport chunk carries ``generation_id == turn_id`` so the client
  can drop chunks of cancelled generations;
* a final marker event (``is_last_chunk=True``, empty audio) always closes
  the stream, so a consumer can simply play until it sees the marker;
* cancellation: checks ``TurnContext.is_cancelled`` between chunks and
  cancels the TTS token, so a barge-in stops the audio immediately;
* fallback: if the model is unavailable, emits ``fallback_text`` instead of
  audio (text-mode degradation, SSOT §10).
"""

from __future__ import annotations

import asyncio
import base64
import re
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.schemas.events import TTSChunkEvent
from speech.contracts import CancellationToken, ErrorCode, SpeechError, TTSRequest

if TYPE_CHECKING:  # pragma: no cover
    from app.orchestrator.state_machine import TurnContext

__all__ = ["TTSSentenceStreamer"]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")

DEFAULT_SAMPLE_RATE = 24000


class TTSSentenceStreamer:
    """Turns a stream of answer-text deltas into a stream of audio events."""

    def __init__(self, session_id: str, turn_id: str, turn_context: TurnContext) -> None:
        self._session_id = session_id
        self._turn_id = turn_id
        self._turn_context = turn_context
        self._buffer = ""
        self._counter = 0

    # -- public API --------------------------------------------------------

    async def feed_text(self, delta: str) -> AsyncIterator[TTSChunkEvent]:
        """Append an LLM delta; synthesize any sentences that are complete."""
        self._buffer += delta
        while True:
            match = _SENTENCE_SPLIT.search(self._buffer)
            if match is None:
                return
            segment = self._buffer[: match.end()].strip()
            self._buffer = self._buffer[match.end():]
            if segment:
                async for event in self._synthesize(segment):
                    yield event
    async def finish(self) -> AsyncIterator[TTSChunkEvent]:
        """Flush the tail of the answer and emit the closing marker."""
        remainder = self._buffer.strip()
        self._buffer = ""
        if remainder and not self._turn_context.is_cancelled:
            async for event in self._synthesize(remainder):
                yield event
        if not self._turn_context.is_cancelled:
            yield self._event(pcm=b"", is_last=True)

    # -- internals ---------------------------------------------------------

    async def _synthesize(self, text: str) -> AsyncIterator[TTSChunkEvent]:
        if self._turn_context.is_cancelled:
            return
        try:
            from app.voice_agent.factory import get_tts_adapter_for_mode

            adapter = await asyncio.to_thread(get_tts_adapter_for_mode)
        except SpeechError:
            # Text-mode degradation: the caller shows fallback_text.
            yield self._event(pcm=b"", is_last=False, fallback_text=text, text=text)
            return

        token = CancellationToken()
        request = TTSRequest(
            session_id=self._session_id,
            turn_id=self._turn_id,
            generation_id=self._turn_id,
            segments=[text],
        )
        try:
            async for chunk in adapter.synthesize(request, token):
                if self._turn_context.is_cancelled:
                    token.cancel()
                    return
                yield self._event(
                    pcm=chunk.pcm_s16le,
                    is_last=False,
                    sample_rate=chunk.sample_rate,
                    first_chunk_ms=chunk.first_chunk_ms if chunk.is_first_chunk else None,
                    text=text,
                )
        except SpeechError as exc:
            if exc.code is ErrorCode.CANCELLED:
                return  # barge-in cancelled this generation — send nothing
            yield self._event(pcm=b"", is_last=False, fallback_text=text, text=text)

    def _event(
        self,
        *,
        pcm: bytes,
        is_last: bool,
        sample_rate: int | None = None,
        first_chunk_ms: float | None = None,
        fallback_text: str | None = None,
        text: str | None = None,
    ) -> TTSChunkEvent:
        self._counter += 1
        return TTSChunkEvent(
            session_id=self._session_id,
            turn_id=self._turn_id,
            timestamp_ms=int(time.time() * 1000),
            chunk_id=f"{self._turn_id}-{self._counter}",
            audio_base64=base64.b64encode(pcm).decode("ascii"),
            is_last_chunk=is_last,
            generation_id=self._turn_id,
            sample_rate=sample_rate or DEFAULT_SAMPLE_RATE,
            first_chunk_ms=first_chunk_ms,
            fallback_text=fallback_text,
            text=text,
        )
