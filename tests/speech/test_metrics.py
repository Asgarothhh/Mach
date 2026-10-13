"""Unit tests for the WER/CER metrics (Russian-aware normalization)."""

from __future__ import annotations

from speech.metrics import cer, normalize_text, word_wer


def test_digits_are_expanded_on_both_sides() -> None:
    assert normalize_text("100 рублей") == "сто рублей"
    assert normalize_text("Сто рублей") == "сто рублей"
    assert word_wer("Тариф стоит 100 рублей", "тариф стоит сто рублей") == 0.0
    assert word_wer("Позвоните на 0890", "позвоните на ноль восемь девять ноль") != 0.0


def test_punctuation_and_case_are_ignored() -> None:
    assert normalize_text("Здравствуйте, мир!") == "здравствуйте мир"
    assert word_wer("Ёлка, дом.", "елка дом") == 0.0


def test_wer_and_cer_values() -> None:
    assert word_wer("один два три", "один два") == 1 / 3
    assert 0.0 < cer("привет", "превет") < 0.2


def test_phone_digits_are_expanded() -> None:
    assert normalize_text("+375 17 237-98-98") == (
        "триста семьдесят пять семнадцать двести тридцать семь "
        "девяносто восемь девяносто восемь"
    )
