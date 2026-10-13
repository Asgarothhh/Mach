"""Segment recognizer used by ``SpeechCascade`` in mock mode.

``MockASRAdapter`` is a streaming ``ASRAdapter`` and expects ``frame.turn_id``.
The cascade calls ``recognize(samples, sample_rate) -> str`` after VAD closes
a segment, so the live junction needs this narrower helper.
"""

from __future__ import annotations

import os

import numpy as np

__all__ = ["ScriptedRecognizer", "DEFAULT_MOCK_ASR_TEXT"]

DEFAULT_MOCK_ASR_TEXT = "график работы офис acme"


class ScriptedRecognizer:
    """Return a fixed transcript for any PCM segment."""

    def __init__(self, text: str | None = None) -> None:
        self.text = text if text is not None else os.getenv(
            "VOICE_MOCK_ASR_TEXT", DEFAULT_MOCK_ASR_TEXT
        )

    def recognize(self, samples: np.ndarray, sample_rate: int) -> str:
        del samples, sample_rate
        return self.text
