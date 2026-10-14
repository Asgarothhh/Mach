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

import re
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from speech.contracts import ErrorCode, SpeechError

__all__ = ["RuAccentStressPreprocessor", "SileroStressPreprocessor", "TextPreprocessor"]

_ACUTE = "\u0301"
_PLUS_VOWEL_RE = re.compile(r"\+([аеёиоуыэюяАЕЁИОУЫЭЮЯ])")


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


class RuAccentStressPreprocessor:
    """Acute stress marking for engines that expect it inside the text.

    The official Chatterbox pipeline stresses Russian through
    ``russian_text_stresser``; that package is not installable here (its
    dependency pin conflicts with the environment), while RUAccent (MIT) already
    powers the Kokoro G2P stack and produces the same combining-acute format
    (``замо́к``). Missing stress marks are the known cause of wrong word stress
    and an "English accent" in Russian Chatterbox output.
    """

    def __init__(self, accentor: Callable[[str], str]) -> None:
        self._accentor = accentor

    @classmethod
    def from_pretrained(cls, omograph_model_size: str = "turbo") -> RuAccentStressPreprocessor:
        try:
            from ruaccent import RUAccent
        except ImportError as exc:  # pragma: no cover - depends on env
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                "ruaccent is required; install with `pip install ruaccent`",
            ) from exc
        accentor = RUAccent()
        accentor.load(omograph_model_size=omograph_model_size, use_dictionary=True)
        return cls(accentor.process_all)

    def __call__(self, text: str) -> str:
        try:
            marked = self._accentor(text)
        except SpeechError:
            raise
        except Exception as exc:  # defensive: model failure must be typed
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE, f"stress model failed: {exc}"
            ) from exc
        # RUAccent marks stress as '+' before the vowel; the engines expect
        # a combining acute after it (same convention as ru_g2p).
        return _PLUS_VOWEL_RE.sub("\\1" + _ACUTE, marked)
