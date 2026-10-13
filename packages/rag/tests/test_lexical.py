import unicodedata

from mts_rag.lexical import lexical_score, tokenize


def test_tokenize_casefolds_and_splits_punctuation() -> None:
    assert tokenize("Роуминг: ИНТЕРНЕТ, 5 BYN/день!") == ["роуминг", "интернет", "5", "byn", "день"]


def test_tokenize_keeps_digits_without_stemming() -> None:
    assert tokenize("Tariffs 2026 tariff") == ["tariffs", "2026", "tariff"]


def test_tokenize_nfc_equivalence() -> None:
    composed = "Мой"
    decomposed = unicodedata.normalize("NFD", composed)
    assert decomposed != composed
    assert tokenize(decomposed) == tokenize(composed) == ["мой"]


def test_lexical_score_fraction_of_query_terms() -> None:
    query = frozenset({"roaming", "price", "day", "zone"})
    document = frozenset({"roaming", "day", "internet"})
    assert lexical_score(query, document) == 0.5
    assert lexical_score(query, query | document) == 1.0
    assert lexical_score(query, frozenset()) == 0.0


def test_lexical_score_empty_query_is_zero() -> None:
    assert lexical_score(frozenset(), frozenset({"roaming"})) == 0.0
