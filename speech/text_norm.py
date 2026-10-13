"""Conservative text normalization for TTS (SSOT §5.7).

The rule of this module: normalization must never change facts. It expands a
small set of safe abbreviations, cleans whitespace/control characters,
manages question-intonation markers (``*слово*`` for Silero v5.4+/v5.5+) and
speaks out numbers via :mod:`speech.number_norm`.

Why numbers must become words: the Silero packaged models have NO digits in
their symbol sets and silently DROP everything outside it — "100 рублей"
reaches the model as "рублей", "+375 17 237-98-98" as almost nothing. See
``speech/number_norm.py`` for phones, short codes, USSD, currency and unit
agreement. The original text is preserved for the protected log.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from speech.number_norm import normalize_numbers_ru

__all__ = ["NormalizedText", "normalize_for_tts"]

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")

# Safe expansions only; anything ambiguous stays as-is (see module docstring).
_ABBREVIATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bт\.\s*е\.", re.IGNORECASE), "то есть"),
    (re.compile(r"\bт\.\s*к\.", re.IGNORECASE), "так как"),
    (re.compile(r"\bт\.\s*д\.", re.IGNORECASE), "так далее"),
    (re.compile(r"\bт\.\s*п\.", re.IGNORECASE), "тому подобное"),
    (re.compile(r"\bруб\.", re.IGNORECASE), "рублей"),
    (re.compile(r"\bкоп\.", re.IGNORECASE), "копеек"),
)


@dataclass(frozen=True)
class NormalizedText:
    """``spoken`` goes to TTS; ``original`` stays in the protected text log."""

    original: str
    spoken: str


def normalize_for_tts(
    text: str, *, supports_question_intonation: bool = True
) -> NormalizedText:
    """Return TTS-ready text without changing facts.

    ``*word*`` marks the intonation center of a general question for Silero
    v5.4+/v5.5+ (habr.com/ru/articles/1015942). Unpaired markers would confuse
    the model, so they are dropped; the same happens when the configured voice
    does not support question intonation.
    """
    cleaned = unicodedata.normalize("NFC", text)
    cleaned = _CONTROL_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split())

    if not supports_question_intonation or cleaned.count("*") % 2 != 0:
        cleaned = cleaned.replace("*", "")
        cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()

    for pattern, replacement in _ABBREVIATIONS:
        cleaned = pattern.sub(replacement, cleaned)

    cleaned = normalize_numbers_ru(cleaned)

    return NormalizedText(original=text, spoken=cleaned)
