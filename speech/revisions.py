"""Transcript revision guard: interim hypotheses never override finals.

SSOT §5.4/§11.1 and the frontend integration contract require that late
partial revisions are ignored after the final transcript of a turn arrives and
that duplicates do not create extra turns. The orchestrator feeds every
``ASREvent`` through :meth:`TranscriptRevisionTracker.apply` and only reacts to
events that are returned (``None`` means "drop").
"""

from __future__ import annotations

from dataclasses import dataclass

from speech.contracts import ASREvent

__all__ = ["TranscriptRevisionTracker"]


@dataclass
class _TurnState:
    last_interim_revision: int | None = None
    interim_text: str = ""
    final_text: str | None = None


class TranscriptRevisionTracker:
    """Accept only monotonic ASR events per ``(session_id, turn_id)``."""

    def __init__(self) -> None:
        self._turns: dict[tuple[str, str], _TurnState] = {}

    def apply(self, event: ASREvent) -> ASREvent | None:
        """Return the event if it must be applied, else ``None``."""
        state = self._turns.setdefault((event.session_id, event.turn_id), _TurnState())

        if state.final_text is not None:
            # The turn is finalized: late partials and duplicate finals are dropped.
            return None

        if event.is_final:
            state.final_text = event.text
            return event

        if (
            state.last_interim_revision is not None
            and event.revision <= state.last_interim_revision
        ):
            # Stale or duplicated interim revision.
            return None

        state.last_interim_revision = event.revision
        state.interim_text = event.text
        return event

    def interim_text(self, session_id: str, turn_id: str) -> str | None:
        state = self._turns.get((session_id, turn_id))
        return state.interim_text if state and state.interim_text else None

    def final_text(self, session_id: str, turn_id: str) -> str | None:
        state = self._turns.get((session_id, turn_id))
        return state.final_text if state else None

    def forget(self, session_id: str, turn_id: str) -> None:
        """Drop state of a finished turn (caller decides retention)."""
        self._turns.pop((session_id, turn_id), None)
