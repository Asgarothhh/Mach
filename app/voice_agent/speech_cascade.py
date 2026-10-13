"""Per-session speech cascade for the test channel: PCM -> VAD -> ASR (T-one).

Contract (fixed in ``docs/STAGE1_SPEECH_E2E.md``): WebSocket binary frames are
PCM16-LE mono at 16 kHz. The cascade

* runs the ML Silero VAD (MIT) over the stream and reports speech start/end;
* captures the audio of each speech segment — retroactively from the VAD
  start timestamp thanks to a rolling buffer — and recognizes it with T-one
  (Apache-2.0) via the onnx-asr runtime;
* emits one final ``ASREvent`` per segment (interim hypotheses are the
  follow-up: native T-one 300 ms chunks, not required by the Stage-1 gate).

Barge-in is only *detected* here (SPEECH_START while a segment is open while
the endpoint knows the agent is speaking); the cancel policy lives in the WS
endpoint which owns the orchestrator and the generation task.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable

from app.voice_agent.asr import get_recognizer
from speech.audio import pcm16_to_float32
from speech.contracts import (
    ASREvent,
    AudioFrame,
    ErrorCode,
    SpeechError,
    VADEvent,
    VADEventType,
)
from speech.vad import SileroVADAdapter, VADConfig

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
_MAX_BUFFER_MS = 40_000  # rolling capture window for retroactive segment start
_SILENCE_IDLE_MS = 700  # no audio while a segment is open -> feed silence

VADCallback = Callable[[VADEvent], Awaitable[None]]
ASRCallback = Callable[[ASREvent], Awaitable[None]]


class SpeechCascade:
    """Feeds PCM into VAD and turns finished speech segments into ASR events."""

    def __init__(
        self,
        session_id: str,
        *,
        on_vad: VADCallback,
        on_asr: ASRCallback,
        vad_adapter: SileroVADAdapter | None = None,
        recognizer: object | None = None,
    ) -> None:
        self.session_id = session_id
        self._on_vad = on_vad
        self._on_asr = on_asr
        self._vad = vad_adapter or SileroVADAdapter.from_pretrained(
            # 400 ms of left context: VAD onset lags on plosive/fricative word
            # starts ("Подс-") — the ASR needs the full word, and every ms missed
            # at the start costs accuracy (measured on synth_01: 96 ms padding
            # -> "кдите", 400 ms -> "подскажите").
            VADConfig(sample_rate=SAMPLE_RATE, prefix_padding_ms=400)
        )
        self._recognizer = recognizer
        self._queue: asyncio.Queue[AudioFrame | None] = asyncio.Queue()
        self._task = asyncio.create_task(self._run())
        self._frames: deque[tuple[int, bytes]] = deque()
        self._segment: bytearray | None = None
        self._next_ts_ms = 0
        self._seq = 0
        self.turn_counter = 0
        self.current_turn_id: str | None = None
        self._closed = False
        self._last_audio_at = 0.0
        self._watchdog_task = asyncio.create_task(self._silence_watchdog())

    # -- public API --------------------------------------------------------

    async def feed(self, pcm_s16le: bytes) -> None:
        """Feed one chunk of PCM16-LE mono @16 kHz from the transport."""
        if not pcm_s16le or len(pcm_s16le) % 2 != 0:
            raise SpeechError(
                ErrorCode.INVALID_AUDIO, "PCM16 payload must be non-empty and even"
            )
        self._last_audio_at = time.monotonic()
        await self._enqueue(pcm_s16le)

    @property
    def speaking(self) -> bool:
        """True while a speech segment is being captured."""
        return self._segment is not None

    async def close(self) -> None:
        """Finish processing (flushes an unfinished segment) and stop."""
        if self._closed:
            return
        self._closed = True
        self._watchdog_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._watchdog_task
        await self._queue.put(None)
        try:
            await asyncio.wait_for(self._task, timeout=15)
        except TimeoutError:  # pragma: no cover - defensive
            self._task.cancel()

    # -- internals ---------------------------------------------------------

    async def _enqueue(self, pcm_s16le: bytes) -> None:
        if self._closed:
            raise SpeechError(ErrorCode.INVALID_AUDIO, "cascade is closed")
        frame = AudioFrame(
            session_id=self.session_id,
            seq=self._seq,
            timestamp_ms=self._next_ts_ms,
            sample_rate=SAMPLE_RATE,
            pcm_s16le=pcm_s16le,
        )
        self._seq += 1
        self._frames.append((self._next_ts_ms, pcm_s16le))
        if self._segment is not None:
            self._segment.extend(pcm_s16le)
        self._next_ts_ms += int(round(len(pcm_s16le) / 2 / SAMPLE_RATE * 1000))
        self._trim_frames()
        await self._queue.put(frame)

    async def _silence_watchdog(self) -> None:
        """Streaming channels normally send silence continuously.

        If the audio stops while a segment is open (paused stream, dropped
        packets, caller on hold), feed synthetic silence so endpointing can
        close the turn instead of hanging until the channel actually resumes.
        """
        step_bytes = SAMPLE_RATE * 2 * 100 // 1000  # 100 ms of silence
        try:
            while not self._closed:
                await asyncio.sleep(0.2)
                if self._segment is None:
                    continue
                if time.monotonic() - self._last_audio_at < _SILENCE_IDLE_MS / 1000:
                    continue
                for _ in range(10):  # 1 s > min_silence_duration with margin
                    if self._closed or self._segment is None:
                        break
                    await self._enqueue(bytes(step_bytes))
                self._last_audio_at = time.monotonic()
        except asyncio.CancelledError:
            raise

    def _trim_frames(self) -> None:
        cutoff = self._next_ts_ms - _MAX_BUFFER_MS
        while self._frames and self._frames[0][0] < cutoff:
            self._frames.popleft()

    async def _run(self) -> None:
        async def frames() -> AsyncIterator[AudioFrame]:
            while True:
                item = await self._queue.get()
                if item is None:
                    return
                yield item

        try:
            async for event in self._vad.stream(frames()):
                await self._handle_vad(event)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a broken cascade must not kill the call
            logger.exception("speech_cascade_failed session_id=%s", self.session_id)
            self._closed = True

    async def _handle_vad(self, event: VADEvent) -> None:
        segment: bytes | None = None
        if event.type is VADEventType.SPEECH_START:
            self.turn_counter += 1
            self.current_turn_id = f"{self.session_id}:t{self.turn_counter}"
            capture = bytearray()
            for timestamp_ms, pcm in self._frames:
                frame_end = timestamp_ms + int(
                    round(len(pcm) / 2 / SAMPLE_RATE * 1000)
                )
                if frame_end > event.timestamp_ms:
                    capture.extend(pcm)
            self._segment = capture
        elif event.type is VADEventType.SPEECH_END:
            if self._segment is not None:
                segment = bytes(self._segment)
            self._segment = None

        await self._on_vad(event)

        if segment:
            await self._recognize(segment, end_ms=event.timestamp_ms)

    async def _recognize(self, segment: bytes, *, end_ms: int) -> None:
        recognizer = self._recognizer or get_recognizer()
        samples = pcm16_to_float32(segment)
        try:
            text = await asyncio.to_thread(
                recognizer.recognize, samples, SAMPLE_RATE  # type: ignore[attr-defined]
            )
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("asr_failed session_id=%s", self.session_id)
            raise SpeechError(ErrorCode.MODEL_UNAVAILABLE, f"ASR failed: {exc}") from exc

        event = ASREvent(
            session_id=self.session_id,
            turn_id=self.current_turn_id or f"{self.session_id}:t{self.turn_counter}",
            revision=0,
            text=text.strip(),
            is_final=True,
            language="ru",
            end_ms=end_ms,
        )
        logger.info(
            "asr_final session_id=%s turn_id=%s chars=%d",
            self.session_id,
            event.turn_id,
            len(event.text),
        )
        await self._on_asr(event)
