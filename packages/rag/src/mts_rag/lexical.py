"""Lexical matching used by the stub retriever."""

import re
import unicodedata
from collections.abc import Set

_TOKEN = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    """NFC, casefold, then split on Unicode word characters. Digits are kept; no stemming."""
    return _TOKEN.findall(unicodedata.normalize("NFC", text).casefold())


def lexical_score(query_terms: Set[str], document_terms: Set[str]) -> float:
    """Share of distinct query terms present in the document, in [0, 1]."""
    if not query_terms:
        return 0.0
    return len(query_terms & document_terms) / len(query_terms)
