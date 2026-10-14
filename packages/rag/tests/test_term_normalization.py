import pytest

from mts_rag.lexical import (
    document_terms,
    index_terms,
    query_terms,
    stem,
    term_coverage,
    tokenize,
)
from mts_rag.sparse import SPARSE_VECTOR_NAME, Bm25HashSparseEncoder


@pytest.mark.parametrize(
    ("forms"),
    [
        ("лицензия", "лицензии", "лицензию", "лицензией"),
        ("поддержка", "поддержки", "поддержкой"),
        ("турция", "турции", "турцию"),
        ("звонки", "звонков", "звонкам"),
        ("баланс", "баланса", "балансе"),
    ],
)
def test_stem_merges_inflections(forms: tuple[str, ...]) -> None:
    assert len({stem(form) for form in forms}) == 1


def test_stem_keeps_digits_and_latin() -> None:
    assert stem("100") == "100"
    assert stem("ussd") == "ussd"
    assert stem("ёлка") == stem("елка")


def test_query_terms_drop_politeness_and_question_words() -> None:
    terms = query_terms("Подскажите, пожалуйста, какой у вас график работы")
    assert terms == query_terms("график работы")
    assert query_terms("с какого по какое время, только в будни") == query_terms("время будни")


def test_query_terms_keep_entities_numbers_and_places() -> None:
    terms = query_terms("сколько стоит роуминг в египте 2026 года")
    assert stem("египте") in terms
    assert "2026" in terms
    assert stem("роуминг") in terms


def test_negation_is_not_dropped_from_text_but_not_counted() -> None:
    assert "не" in tokenize("вы не работаете в субботу")
    assert "не" not in query_terms("вы не работаете в субботу")
    assert query_terms("без интернета") == query_terms("интернета")


@pytest.mark.parametrize(
    ("query", "document"),
    [
        ("какая цена лицензии", "Лицензия стоит 99 рублей"),
        ("почём лицензия", "Лицензия стоит 99 рублей"),
        ("какая почта поддержки", "Поддержка доступна через email"),
        ("до скольки работаете", "График работы: открыт с девяти"),
        ("сколько денег на счету", "Баланс проверяется командой"),
    ],
)
def test_concepts_match_paraphrases(query: str, document: str) -> None:
    assert term_coverage(query_terms(query), document_terms(document)) >= 0.5


def test_stem_prefix_bridges_verb_and_noun_forms() -> None:
    assert term_coverage(query_terms("открыты"), document_terms("офис открыт")) == 1.0


@pytest.mark.parametrize(
    ("query", "document"),
    [
        ("рецепт борща", "Лицензия стоит 99 рублей"),
        ("как подключить интернет дома", "Входящие звонки в Турции"),
        ("погода завтра", "График работы офиса"),
    ],
)
def test_unrelated_queries_stay_below_threshold(query: str, document: str) -> None:
    assert term_coverage(query_terms(query), document_terms(document)) < 0.5


@pytest.mark.parametrize(
    ("query", "document"),
    [
        ("нет связи", "Поддержка Acme доступна через почту support@acme-it.example."),
        ("e-sim", "Поддержка Acme доступна через почту support@acme-it.example."),
        ("сменить оператора", "Поддержка Acme доступна через почту support@acme-it.example."),
    ],
)
def test_ambiguous_telecom_words_are_not_contact_concepts(query: str, document: str) -> None:
    assert term_coverage(query_terms(query), document_terms(document)) == 0.0


def test_prefix_bridges_endings_but_not_new_words() -> None:
    assert term_coverage(query_terms("банк"), document_terms("банкомат рядом")) == 0.0
    assert term_coverage(query_terms("кредит"), document_terms("кредитный лимит")) == 0.0
    assert term_coverage(query_terms("лицензии"), document_terms("лицензия")) == 1.0


def test_short_stems_need_exact_match() -> None:
    # "сто" (hundred) must not be confused with "стоит" (price concept).
    assert "#price" in query_terms("стоит")
    assert term_coverage(query_terms("стоит"), document_terms("звёздочка сто решётка")) == 0.0


def test_empty_query_terms_score_zero() -> None:
    assert (
        term_coverage(query_terms("ну подскажите пожалуйста"), document_terms("что угодно")) == 0.0
    )


def test_sparse_v2_shares_ids_across_inflections() -> None:
    encoder = Bm25HashSparseEncoder()
    assert SPARSE_VECTOR_NAME == "sparse_bm25h_v2"
    assert (
        encoder.encode_query(index_terms("лицензии")).indices
        == encoder.encode_query(index_terms("лицензия")).indices
    )
    assert "не" in index_terms("не работает")
