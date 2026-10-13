"""Text-quality metrics for ASR/TTS evaluation (WER/CER), Russian-aware.

Used by the TTS A/B harness (whisper round-trip WER) and the ASR benchmark.
Numbers are compared token-wise: datasets usually spell them out while ASR
outputs digits (or vice versa), so ``digits_to_words_ru`` from
:mod:`speech.number_norm` can be applied to both sides before scoring when a
word-level comparison is desired.
"""

from __future__ import annotations

import re

__all__ = [
    "cer",
    "char_edit_units",
    "normalize_text",
    "word_edit_units",
    "word_wer",
]

_NON_WORD_RE = re.compile(r"[^а-яa-zё0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Lowercase, ё→е, strip punctuation, collapse whitespace."""
    text = text.lower().replace("ё", "е")
    text = _NON_WORD_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, start=1):
        current = [i]
        for j, hyp_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ref_item != hyp_item),
                )
            )
        previous = current
    return previous[-1]


def word_edit_units(reference: str, hypothesis: str) -> tuple[int, int]:
    """Word-level (edit distance, reference length) for corpus-level WER."""
    ref = normalize_text(reference).split()
    hyp = normalize_text(hypothesis).split()
    return _edit_distance(ref, hyp), len(ref)


def char_edit_units(reference: str, hypothesis: str) -> tuple[int, int]:
    """Character-level (edit distance, reference length) for corpus-level CER."""
    ref = list(normalize_text(reference).replace(" ", ""))
    hyp = list(normalize_text(hypothesis).replace(" ", ""))
    return _edit_distance(ref, hyp), len(ref)


def word_wer(reference: str, hypothesis: str) -> float:
    """Word error rate with Russian-aware normalization."""
    distance, length = word_edit_units(reference, hypothesis)
    return distance / max(1, length)


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate (characters, punctuation stripped)."""
    distance, length = char_edit_units(reference, hypothesis)
    return distance / max(1, length)
