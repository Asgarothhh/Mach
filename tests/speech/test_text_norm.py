"""Unit tests for conservative TTS text normalization (SSOT §5.7)."""

from __future__ import annotations

from speech.text_norm import normalize_for_tts


def test_markers_kept_for_question_voice() -> None:
    text = "*Вы* звоните по поводу тарифа?"
    result = normalize_for_tts(text)
    assert result.spoken == text
    assert result.original == text


def test_markers_stripped_for_plain_voice() -> None:
    result = normalize_for_tts("*Вы* звоните?", supports_question_intonation=False)
    assert "*" not in result.spoken
    assert result.spoken == "Вы звоните?"


def test_unpaired_marker_is_dropped() -> None:
    result = normalize_for_tts("Здравствуйте, *коллеги")
    assert "*" not in result.spoken


def test_abbreviations_and_whitespace() -> None:
    result = normalize_for_tts("Стоимость 10 руб.  т.е.  недорого")
    assert "рублей" in result.spoken
    assert "то есть" in result.spoken
    assert "  " not in result.spoken


def test_numbers_and_phones_are_spoken() -> None:
    text = "Позвоните на 0890 или +375 17 237-98-98, стоимость 100 рублей"
    result = normalize_for_tts(text)

    assert result.original == text
    assert "ноль восемь девять ноль" in result.spoken
    assert (
        "плюс триста семьдесят пять, семнадцать, двести тридцать семь, "
        "девяносто восемь, девяносто восемь" in result.spoken
    )
    assert "сто рублей" in result.spoken


def test_control_characters_removed() -> None:
    result = normalize_for_tts("Привет\x00\x07 мир")
    assert "\x00" not in result.spoken
    assert "\x07" not in result.spoken
    assert result.spoken == "Привет мир"


def test_ussd_survives_plain_voice_marker_stripping() -> None:
    result = normalize_for_tts("Наберите *111*4#.", supports_question_intonation=False)
    assert "звёздочка один один один звёздочка четыре решётка" in result.spoken
    assert "*" not in result.spoken and "#" not in result.spoken
