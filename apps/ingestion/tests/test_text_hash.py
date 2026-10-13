from mts_ingestion import TEXT_NORMALIZATION_VERSION, content_hash, normalize_text


def test_hash_ignores_whitespace_noise() -> None:
    noisy = "  Цена:   5 BYN\t в день  \n\n\n\n  Итого  \n"
    clean = "Цена: 5 BYN в день\n\nИтого"
    assert normalize_text(noisy) == clean
    assert content_hash(noisy) == content_hash(clean)


def test_hash_ignores_nbsp_zero_width_crlf() -> None:
    noisy = "5\u00a0BYN\u200b\r\nв\u202fдень\ufeff\rконец\u3000!"
    assert normalize_text(noisy) == "5 BYN\nв день\nконец !"
    assert content_hash(noisy) == content_hash("5 BYN\nв день\nконец !")


def test_hash_sensitive_to_digits_and_case() -> None:
    base = content_hash("Роуминг 5 BYN")
    assert base != content_hash("Роуминг 6 BYN")
    assert base != content_hash("роуминг 5 BYN")
    assert base != content_hash("Роуминг 5 BYN.")


def test_nfc_not_nfkc() -> None:
    assert normalize_text("e\u0301") == "\u00e9"
    assert content_hash("e\u0301") == content_hash("\u00e9")
    for text in ("№ 5", "½ цены", "x²", "ﬁ"):
        assert normalize_text(text) == text


def test_normalization_is_idempotent_and_versioned() -> None:
    text = " a \u200d\u0301 \n\n\n b\r\n"
    assert normalize_text(normalize_text(text)) == normalize_text(text)
    assert TEXT_NORMALIZATION_VERSION == 1
