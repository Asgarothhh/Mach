"""Unit tests for Russian number/phone normalization (TTS text frontend)."""

from __future__ import annotations

import pytest

from speech.number_norm import (
    digits_to_words_ru,
    integer_to_words_ru,
    normalize_numbers_ru,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "ноль"),
        (1, "один"),
        (2, "два"),
        (11, "одиннадцать"),
        (21, "двадцать один"),
        (100, "сто"),
        (101, "сто один"),
        (1000, "одна тысяча"),
        (2000, "две тысячи"),
        (5000, "пять тысяч"),
        (21000, "двадцать одна тысяча"),
        (100000, "сто тысяч"),
        (1000000, "один миллион"),
        (2000000, "два миллиона"),
        (5000000, "пять миллионов"),
        (2026, "две тысячи двадцать шесть"),
        (1234567, "один миллион двести тридцать четыре тысячи пятьсот шестьдесят семь"),
    ],
)
def test_integer_to_words(value: int, expected: str) -> None:
    assert integer_to_words_ru(value) == expected


def test_digits_to_words() -> None:
    assert digits_to_words_ru("0890") == "ноль восемь девять ноль"


def test_currency_agreement() -> None:
    assert normalize_numbers_ru("1 руб.") == "один рубль"
    assert normalize_numbers_ru("2 руб.") == "два рубля"
    assert normalize_numbers_ru("5 руб.") == "пять рублей"
    assert normalize_numbers_ru("100 рублей") == "сто рублей"
    assert normalize_numbers_ru("1 коп.") == "одна копейка"
    assert normalize_numbers_ru("22 коп.") == "двадцать две копейки"
    assert normalize_numbers_ru("19,90 руб.") == "девятнадцать рублей девяносто копеек"
    assert normalize_numbers_ru("19,9 руб.") == "девятнадцать рублей девяносто копеек"


def test_units_and_gender_agreement() -> None:
    assert normalize_numbers_ru("1 минута") == "одна минута"
    assert normalize_numbers_ru("2 минуты") == "две минуты"
    assert normalize_numbers_ru("5 минут") == "пять минут"
    assert normalize_numbers_ru("2 часа") == "два часа"
    assert normalize_numbers_ru("5 часов") == "пять часов"
    assert normalize_numbers_ru("3 дня") == "три дня"
    assert normalize_numbers_ru("21 год") == "двадцать один год"
    assert normalize_numbers_ru("5 лет") == "пять лет"


def test_phone_numbers_and_codes() -> None:
    assert normalize_numbers_ru("+375 17 237-98-98") == (
        "плюс триста семьдесят пять, семнадцать, двести тридцать семь, "
        "девяносто восемь, девяносто восемь"
    )
    assert normalize_numbers_ru("8-800-555-35-35") == (
        "восемь, восемьсот, пятьсот пятьдесят пять, тридцать пять, тридцать пять"
    )
    assert normalize_numbers_ru("0890") == "ноль восемь девять ноль"
    assert normalize_numbers_ru("*111*4#") == (
        "звёздочка один один один звёздочка четыре решётка"
    )


def test_decimals_and_thousands() -> None:
    assert normalize_numbers_ru("3,5") == "три целых пять десятых"
    assert normalize_numbers_ru("2,25") == "две целых двадцать пять сотых"
    assert normalize_numbers_ru("10 000") == "десять тысяч"
    assert normalize_numbers_ru("1 000 000") == "один миллион"


def test_unknown_constructs_are_left_alone() -> None:
    assert normalize_numbers_ru("1000x") == "1000x"
    assert normalize_numbers_ru("без цифр") == "без цифр"


def test_text_with_numbers_in_sentences() -> None:
    result = normalize_numbers_ru(
        "Тариф стоит 100 рублей в месяц, подключение бесплатное."
    )
    assert result == "Тариф стоит сто рублей в месяц, подключение бесплатное."
