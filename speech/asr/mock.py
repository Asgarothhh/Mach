"""Deterministic scripted ASR adapter for tests and stage-0 E2E.

This is not a quality model: it exists so the orchestrator, API and UI can be
built and tested before the real streaming ASR (sherpa-onnx / faster-whisper
candidates, SSOT §5.4) lands. It emits interim revisions and one final event
per turn, in the exact ``ASREvent`` shape the real adapter will use.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

from speech.contracts import ASREvent, AudioFrame

__all__ = ["MockASRAdapter"]


class MockASRAdapter:
    """Emit scripted interim/final transcripts per turn.

    ``transcripts`` maps ``turn_id`` → final text. Interim events show growing
    word prefixes; the final event is emitted when the frame's ``turn_id``
    changes or when the stream ends.
    """

    def __init__(
        self,
        transcripts: Mapping[str, str] | None = None,
        *,
        interim_revisions: int = 2,
        frames_per_revision: int = 4,
        default_text: str = "тестовая реплика",
    ) -> None:
        if interim_revisions < 0 or frames_per_revision <= 0:
            raise ValueError("interim_revisions must be >= 0 and frames_per_revision > 0")
        self._transcripts = dict(transcripts or {})
        self._interim_revisions = interim_revisions
        self._frames_per_revision = frames_per_revision
        self._default_text = default_text

    async def stream(self, audio_frames: AsyncIterator[AudioFrame]) -> AsyncIterator[ASREvent]:
        turn_id: str | None = None
        session_id = ""
        revision = 0
        interim_emitted = 0
        frames = 0

        async for frame in audio_frames:
            if frame.turn_id is None:
                raise ValueError("MockASRAdapter requires frames with turn_id")
            if turn_id is not None and frame.turn_id != turn_id:
                yield self._final(turn_id, session_id, revision)
                revision = 0
                interim_emitted = 0
                frames = 0

            turn_id = frame.turn_id
            session_id = frame.session_id
            frames += 1

            if (
                interim_emitted < self._interim_revisions
                and frames % self._frames_per_revision == 0
            ):
                text = self._text(turn_id)
                yield ASREvent(
                    session_id=session_id,
                    turn_id=turn_id,
                    revision=revision,
                    text=self._interim(text, interim_emitted),
                    is_final=False,
                )
                revision += 1
                interim_emitted += 1

        if turn_id is not None:
            yield self._final(turn_id, session_id, revision)

    def _text(self, turn_id: str) -> str:
        return self._transcripts.get(turn_id, self._default_text)

    @staticmethod
    def _interim(text: str, index: int) -> str:
        words = text.split()
        return " ".join(words[: max(1, (index + 1) * 2)])

    def _final(self, turn_id: str, session_id: str, revision: int) -> ASREvent:
        return ASREvent(
            session_id=session_id,
            turn_id=turn_id,
            revision=revision,
            text=self._text(turn_id),
            is_final=True,
            confidence=0.99,
        )
