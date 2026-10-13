"""Unit tests for text preprocessors (stress marking pipeline)."""

from __future__ import annotations

import pytest

from speech.contracts import ErrorCode, SpeechError
from speech.tts.preprocess import SileroStressPreprocessor


def test_preprocessor_marks_text_via_accentor() -> None:
    preprocessor = SileroStressPreprocessor(lambda text: text.replace("замок", "з+амок"))
    assert preprocessor("Это замок") == "Это з+амок"


def test_accentor_failure_is_typed() -> None:
    def broken(text: str) -> str:
        raise RuntimeError("model exploded")

    preprocessor = SileroStressPreprocessor(broken)
    with pytest.raises(SpeechError) as exc_info:
        preprocessor("текст")
    assert exc_info.value.code is ErrorCode.MODEL_UNAVAILABLE
