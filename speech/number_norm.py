"""Russian number / phone / unit normalization for TTS frontends.

Why this module exists: the Silero packaged models silently DROP every
character outside their symbol set — and their symbol sets contain no digits
at all (verified against ``v5_5_ru`` and ``v5_cis_base_nostress``). Without
normalization the text "Тариф стоит 100 рублей" reaches the model as
"Тариф стоит рублей", and "+375 17 237-98-98" as almost nothing.

The normalizer speaks numbers in words for every engine (words are valid input
for espeak-based Kokoro and Chatterbox as well), so the shared TTS pipeline
behaves the same everywhere:

* plain integers -> Russian cardinals with correct gender ("одна тысяча",
  "две тысячи") and plural agreement for a small set of units
  ("5 минут", "1 минута", "2 часа");
* amounts -> currency agreement ("1 рубль", "2 рубля", "5 рублей",
  "19,90 руб." -> "девятнадцать рублей девяносто копеек");
* decimals without currency -> "три целых пять десятых";
* phone numbers -> group-wise reading ("+375 17 237-98-98" -> "плюс триста
  семьдесят пять, семнадцать, двести тридцать семь, девяносто восемь,
  девяносто восемь");
* short codes with a leading zero -> digit-by-digit ("0890" -> "ноль восемь
  девять ноль");
* USSD/tech codes -> "звёздочка ... решётка".

Dates and ordinals are intentionally out of scope for now (see the TODO in
``speech/README.md``).
"""

from __future__ import annotations

import re

__all__ = ["digits_to_words_ru", "integer_to_words_ru", "normalize_numbers_ru"]

_UNITS_M = ("ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_UNITS_F = ("ноль", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_TEENS = (
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
_TENS = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
_HUNDREDS = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)

_THOUSAND_FORMS = ("тысяча", "тысячи", "тысяч")
_MILLION_FORMS = ("миллион", "миллиона", "миллионов")
_BILLION_FORMS = ("миллиард", "миллиарда", "миллиардов")

_RUB_FORMS = ("рубль", "рубля", "рублей")
_KOP_FORMS = ("копейка", "копейки", "копеек")
_USD_FORMS = ("доллар", "доллара", "долларов")
_CENT_FORMS = ("цент", "цента", "центов")
_EUR_FORMS = ("евро", "евро", "евро")

# word stem → (one, few, many, feminine) for common telephony units
_UNIT_RULES: tuple[tuple[re.Pattern[str], tuple[str, str, str], bool], ...] = (
    (re.compile(r"секунд(?:а|ы|у)?$"), ("секунда", "секунды", "секунд"), True),
    (re.compile(r"минут(?:а|ы|у)?$"), ("минута", "минуты", "минут"), True),
    (re.compile(r"час(?:а|ов)?$"), ("час", "часа", "часов"), False),
    (re.compile(r"день$"), ("день", "дня", "дней"), False),
    (re.compile(r"дн(?:я|ей|и)$"), ("день", "дня", "дней"), False),
    (re.compile(r"недел(?:я|и|ь)?$"), ("неделя", "недели", "недель"), True),
    (re.compile(r"месяц(?:а|ев)?$"), ("месяц", "месяца", "месяцев"), False),
    (re.compile(r"год(?:а)?$"), ("год", "года", "лет"), False),
    (re.compile(r"лет$"), ("год", "года", "лет"), False),
)

_CURRENCY_RULES: tuple[
    tuple[re.Pattern[str], tuple[str, str, str] | None, tuple[str, str, str] | None], ...
] = (
    (re.compile(r"^руб(?:\.|лей|ля|ль)?$", re.IGNORECASE), _RUB_FORMS, _KOP_FORMS),
    (re.compile(r"^₽$"), _RUB_FORMS, _KOP_FORMS),
    (re.compile(r"^коп(?:\.|ейки|ейка|ейку)?$", re.IGNORECASE), None, _KOP_FORMS),
    (re.compile(r"^(?:долл\w*\.?|\$)$", re.IGNORECASE), _USD_FORMS, _CENT_FORMS),
    (re.compile(r"^евро$", re.IGNORECASE), _EUR_FORMS, _CENT_FORMS),
)

_USSD_RE = re.compile(r"(?<![\w])\*[\d*#]+#?")
_PLUS_PHONE_RE = re.compile(r"\+\d(?:[\d\s\u00a0()\-]{4,}\d)")
_DASHED_PHONE_RE = re.compile(r"(?<![\w\-])\d{1,3}(?:-\d{2,3})+(?![\w])")

# number [fraction] [currency|unit] — a single pass so units are consumed too
_CANDIDATE_RE = re.compile(
    r"(?<![\w.,])"
    r"(?P<body>\d+(?:[ \u00a0]\d{3})*)"
    r"(?P<frac>[.,]\d{1,2})?"
    r"(?P<tail>\s*(?:"
    r"руб(?:\.|лей|ля|ль)?|₽|коп(?:\.|ейки|ейка|ейку)?|долл\w*\.?|\$|евро"
    r"|секунд[а-яё]*|минут[а-яё]*|час[а-яё]*|день|дн[яей]+|недел[а-яё]*"
    r"|месяц[а-яё]*|год[а-яё]*|лет"
    r"))?",
    re.IGNORECASE,
)
_END_BOUNDARY_RE = re.compile(r"(?![\d\w])")


def _plural_form(value: int, forms: tuple[str, str, str]) -> str:
    """Choose among (one, few, many) following Russian agreement rules."""
    value = abs(value) % 100
    if 11 <= value <= 14:
        return forms[2]
    value %= 10
    if value == 1:
        return forms[0]
    if 2 <= value <= 4:
        return forms[1]
    return forms[2]


def _triple_to_words(value: int, *, feminine: bool) -> str:
    words: list[str] = []
    hundreds, rest = divmod(value, 100)
    if hundreds:
        words.append(_HUNDREDS[hundreds])
    tens, units = divmod(rest, 10)
    if tens == 1:
        words.append(_TEENS[units])
        return " ".join(words)
    if tens:
        words.append(_TENS[tens])
    if units or not words:
        words.append((_UNITS_F if feminine else _UNITS_M)[units])
    return " ".join(words)


def integer_to_words_ru(value: int) -> str:
    """Cardinal Russian words for a non-negative integer."""
    if value < 0:
        raise ValueError("negative numbers are not supported")
    if value == 0:
        return "ноль"
    parts: list[str] = []
    groups = (
        (1_000_000_000, _BILLION_FORMS, False),
        (1_000_000, _MILLION_FORMS, False),
        (1_000, _THOUSAND_FORMS, True),
    )
    remainder = value
    for scale, forms, feminine in groups:
        if remainder >= scale:
            group, remainder = divmod(remainder, scale)
            parts.append(_triple_to_words(group, feminine=feminine))
            parts.append(_plural_form(group, forms))
    if remainder:
        parts.append(_triple_to_words(remainder, feminine=False))
    return " ".join(parts)


def digits_to_words_ru(digits: str) -> str:
    """Digit-by-digit reading for short codes and phone fragments.

    Uses masculine forms: "один один один", not "одна одна одна".
    """
    return " ".join(_UNITS_M[int(digit)] for digit in digits if digit.isdigit())


def _cardinal_for_agreement(value: int, *, feminine: bool) -> str:
    if value < 1000:
        return _triple_to_words(value, feminine=feminine)
    return integer_to_words_ru(value)


def _decimals_to_words(integer: int, fraction_value: int, fraction_digits: int) -> str:
    unit_forms = (
        ("десятая", "десятых", "десятых")
        if fraction_digits == 1
        else ("сотая", "сотых", "сотых")
    )
    whole_forms = ("целая", "целых", "целых")
    whole = _cardinal_for_agreement(integer, feminine=True)
    fraction = _triple_to_words(fraction_value, feminine=True)
    return (
        f"{whole} {_plural_form(integer, whole_forms)} "
        f"{fraction} {_plural_form(fraction_value, unit_forms)}"
    )


def _amount_to_words(integer: int, major_forms: tuple[str, str, str]) -> str:
    return f"{integer_to_words_ru(integer)} {_plural_form(integer, major_forms)}"


def _number_body_to_words(body: str) -> str:
    """Decide how a digit token itself is read (cardinal / digits / groups)."""
    groups = body.split()
    if not groups:
        return body
    if len(groups) == 1:
        token = groups[0]
        if token.startswith("0") and len(token) >= 2:
            return digits_to_words_ru(token)
        return integer_to_words_ru(int(token))
    # Space-separated groups: thousands ("100 000") or a phone number
    # ("375 17 237 98 98"); thousands have 3-digit groups after the first.
    if all(len(group) == 3 for group in groups[1:]):
        return integer_to_words_ru(int("".join(groups)))
    return ", ".join(
        digits_to_words_ru(group)
        if len(group) == 1 or group.startswith("0")
        else integer_to_words_ru(int(group))
        for group in groups
        if group
    )


def _candidate_repl(match: re.Match[str]) -> str:
    if not _END_BOUNDARY_RE.match(match.string, match.end()):
        return match.group(0)  # e.g. "1000x" — leave unknown constructs alone

    body = match.group("body")
    fraction_text = match.group("frac")
    fraction_text = fraction_text[1:] if fraction_text else None
    tail = (match.group("tail") or "").strip()

    if tail:
        for pattern, major_forms, minor_forms in _CURRENCY_RULES:
            if pattern.match(tail):
                integer = int("".join(body.split()))
                if major_forms is None:  # kopecks only
                    return " ".join(
                        [
                            _cardinal_for_agreement(integer, feminine=True),
                            _plural_form(integer, minor_forms or _KOP_FORMS),
                        ]
                    )
                parts = [_amount_to_words(integer, major_forms)]
                if fraction_text and minor_forms is not None:
                    minor = int(fraction_text)
                    if len(fraction_text) == 1:
                        minor *= 10
                    parts.append(_cardinal_for_agreement(minor, feminine=True))
                    parts.append(_plural_form(minor, minor_forms))
                return " ".join(parts)
        for pattern, forms, feminine in _UNIT_RULES:
            if pattern.match(tail):
                integer = int("".join(body.split()))
                return " ".join(
                    [
                        _cardinal_for_agreement(integer, feminine=feminine),
                        _plural_form(integer, forms),
                    ]
                )
        # The tail matched the loose regex but is not a known word:
        # speak the number and keep the word as-is.
        return f"{_number_body_to_words(body)} {tail}"

    if fraction_text:
        return _decimals_to_words(
            int("".join(body.split())), int(fraction_text), len(fraction_text)
        )
    return _number_body_to_words(body)


def _ussd_repl(match: re.Match[str]) -> str:
    words: list[str] = []
    for char in match.group(0):
        if char == "*":
            words.append("звёздочка")
        elif char == "#":
            words.append("решётка")
        elif char.isdigit():
            words.append(_UNITS_M[int(char)])
    return " ".join(words)


def _phone_groups_to_words(groups: list[str]) -> str:
    spoken: list[str] = []
    for group in groups:
        if not group.isdigit():
            continue
        if len(group) == 1 or group.startswith("0"):
            spoken.append(digits_to_words_ru(group))
        else:
            spoken.append(integer_to_words_ru(int(group)))
    return ", ".join(spoken)


def _plus_phone_repl(match: re.Match[str]) -> str:
    groups = re.split(r"[\s\u00a0()\-]+", match.group(0)[1:])
    return f"плюс {_phone_groups_to_words(groups)}".strip()


def _dashed_phone_repl(match: re.Match[str]) -> str:
    return _phone_groups_to_words(match.group(0).split("-"))


def normalize_numbers_ru(text: str) -> str:
    """Speak out numbers, phone numbers, short codes and USSD for TTS input."""
    if not any(char.isdigit() for char in text):
        return text
    text = _USSD_RE.sub(_ussd_repl, text)
    text = _PLUS_PHONE_RE.sub(_plus_phone_repl, text)
    text = _DASHED_PHONE_RE.sub(_dashed_phone_repl, text)
    return _CANDIDATE_RE.sub(_candidate_repl, text)
