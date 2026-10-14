import math

from mts_rag.lexical import tokenize
from mts_rag.sparse import Bm25HashSparseEncoder, token_id


def test_token_id_is_uint32_and_deterministic() -> None:
    first = token_id("роуминг")
    assert first == token_id("роуминг")
    assert 0 <= first <= 0xFFFFFFFF
    assert token_id("роуминг") != token_id("интернет")


def test_query_unique_terms_value_one() -> None:
    encoder = Bm25HashSparseEncoder()
    vector = encoder.encode_query(tokenize("roaming roaming internet"))
    assert vector.values == [1.0] * len(vector.indices)
    assert vector.indices == sorted(vector.indices)
    assert len(vector.indices) == len(set(vector.indices))


def test_document_weights_positive_and_idf_differs_by_corpus() -> None:
    encoder = Bm25HashSparseEncoder()
    docs_a = [tokenize("roaming internet price"), tokenize("office hours monday")]
    docs_b = [tokenize("roaming internet price"), tokenize("roaming internet")]
    stats_a = encoder.fit(docs_a)
    stats_b = encoder.fit(docs_b)
    vec_a = encoder.encode_document(docs_a[0], stats_a)
    vec_b = encoder.encode_document(docs_b[0], stats_b)
    assert vec_a.values and all(value > 0.0 for value in vec_a.values)
    roaming_id = token_id("roaming")
    weight_a = dict(zip(vec_a.indices, vec_a.values, strict=True))[roaming_id]
    weight_b = dict(zip(vec_b.indices, vec_b.values, strict=True))[roaming_id]
    assert not math.isclose(weight_a, weight_b)


def test_numbers_and_negations_kept() -> None:
    encoder = Bm25HashSparseEncoder()
    tokens = tokenize("нет 100 без roaming")
    assert "нет" in tokens
    assert "100" in tokens
    assert "без" in tokens
    vector = encoder.encode_query(tokens)
    assert vector.indices
