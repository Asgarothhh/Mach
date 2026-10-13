"""Pluggable text preprocessors for TTS engines.

Russion-specific stress/homograph handling is model-dependent:

* Silero ``v5_ru``/``v5_4_ru``/``v5_5_ru`` add stress automatically (but are
  CC BY-NC-SA — demo only);
* Silero ``v5_cis_base*`` (MIT) require explicit stress marks such as
  ``к+ошка`` for Slavic languages — :class:`SileroStressPreprocessor` adds them
  with `silero-stress` (MIT, github.com/snakers4/silero-stress).

Preprocessors run **after** normalization and **before** the engine; the clean
(non-marked) text is what ends up in :class:`speech.contracts.TTSChunk.text`
for the UI/text log.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from speech.contracts import ErrorCode, SpeechError

__all__ = ["SileroStressPreprocessor", "TextPreprocessor"]


@runtime_checkable
class TextPreprocessor(Protocol):
    """Callable mapping normalized text to engine-ready text."""

    def __call__(self, text: str) -> str: ...


class SileroStressPreprocessor:
    """Stress/homograph marking for Silero CIS-base voices (silero-stress, MIT).

    ``silero-stress`` covers ~4M Russian word forms with 100% accuracy and
    ~2.2K homographs with F1 0.92, runs on CPU (~0.5 ms/word on one thread) and
    is published under MIT.
    """

    def __init__(self, accentor: Callable[[str], str]) -> None:
        self._accentor = accentor

    @classmethod
    def from_pretrained(cls) -> SileroStressPreprocessor:
        try:
            from silero_stress import load_accentor
        except ImportError as exc:  # pragma: no cover - depends on env
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                "silero-stress is required; install with `pip install silero-stress`",
            ) from exc
        return cls(load_accentor())

    def __call__(self, text: str) -> str:
        try:
            return self._accentor(text)
        except SpeechError:
            raise
        except Exception as exc:  # defensive: model failure must be typed
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE, f"stress model failed: {exc}"
            ) from exc
