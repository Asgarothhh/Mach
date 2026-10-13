"""Normalised-text checksum (SSOT §6.2.5): unchanged content must not create a new revision.

Changing any rule here changes `content_hash` for existing documents: bump
`TEXT_NORMALIZATION_VERSION`.
"""

import hashlib
import re
import unicodedata

TEXT_NORMALIZATION_VERSION = 1

_UNICODE_SPACES = "\u00a0" + "".join(chr(c) for c in range(0x2000, 0x200B)) + "\u202f\u205f\u3000"
_ZERO_WIDTH = "\u200b\u200c\u200d\ufeff"
_TRANSLATION: dict[int, str | None] = {ord(c): " " for c in _UNICODE_SPACES} | {
    ord(c): None for c in _ZERO_WIDTH
}
_HORIZONTAL_RUN = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Whitespace-insensitive, otherwise lossless normal form.

    NFC rather than NFKC: NFKC rewrites `№`, `½` and superscripts and could alter prices.
    Case, digits and punctuation are never changed.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").translate(_TRANSLATION)
    normalized = unicodedata.normalize("NFC", normalized)
    normalized = _HORIZONTAL_RUN.sub(" ", normalized)
    normalized = "\n".join(line.strip(" ") for line in normalized.split("\n"))
    return _BLANK_LINES.sub("\n\n", normalized).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
