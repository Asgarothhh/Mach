"""Unit tests for the transcript revision guard (SSOT §5.4 / §11.1)."""

from __future__ import annotations

from speech.contracts import ASREvent
from speech.revisions import TranscriptRevisionTracker


def event(revision: int, text: str, *, final: bool = False, turn: str = "t1") -> ASREvent:
    return ASREvent(
        session_id="s1", turn_id=turn, revision=revision, text=text, is_final=final
    )


def test_late_partial_after_final_is_dropped() -> None:
    tracker = TranscriptRevisionTracker()
    assert tracker.apply(event(0, "привет")) is not None
    assert tracker.apply(event(1, "привет, это тест", final=True)) is not None
    assert tracker.apply(event(2, "привет, это тест, я", final=False)) is None
    assert tracker.final_text("s1", "t1") == "привет, это тест"


def test_stale_and_duplicate_interim_revisions_dropped() -> None:
    tracker = TranscriptRevisionTracker()
    assert tracker.apply(event(0, "первый")) is not None
    assert tracker.apply(event(0, "дубликат")) is None
    assert tracker.apply(event(1, "второй")) is not None
    assert tracker.apply(event(0, "устаревший")) is None
    assert tracker.interim_text("s1", "t1") == "второй"


def test_duplicate_final_is_dropped() -> None:
    tracker = TranscriptRevisionTracker()
    assert tracker.apply(event(0, "итог", final=True)) is not None
    assert tracker.apply(event(1, "итог ещё раз", final=True)) is None
    assert tracker.final_text("s1", "t1") == "итог"


def test_turns_and_sessions_are_isolated() -> None:
    tracker = TranscriptRevisionTracker()
    assert tracker.apply(event(0, "ход 1")) is not None
    assert tracker.apply(event(0, "ход 2", turn="t2")) is not None
    assert tracker.apply(event(1, "ход 1 продолжение")) is not None
    assert tracker.final_text("s1", "t2") is None
    other = ASREvent(
        session_id="s2", turn_id="t1", revision=0, text="другая сессия", is_final=False
    )
    assert tracker.apply(other) is not None


def test_forget_clears_turn_state() -> None:
    tracker = TranscriptRevisionTracker()
    tracker.apply(event(0, "текст", final=True))
    tracker.forget("s1", "t1")
    assert tracker.final_text("s1", "t1") is None
    # After forget a new turn with the same key starts from scratch.
    assert tracker.apply(event(0, "заново")) is not None
