import re
import unicodedata

from pydantic import BaseModel

_CONTROL_CATEGORIES = frozenset({"Cc", "Cf"})

EMAIL_PLACEHOLDER = "[EMAIL_REDACTED]"
CARD_PLACEHOLDER = "[CARD_REDACTED]"
ID_PLACEHOLDER = "[ID_REDACTED]"
PASSPORT_PLACEHOLDER = "[PASSPORT_REDACTED]"
PHONE_PLACEHOLDER = "[PHONE_REDACTED]"

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+-])"
)
_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ \-]*){13,19}(?!\d)")
_BY_PERSONAL_ID_RE = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё0-9])\d{7}[A-Za-zА-Яа-яЁё]\d{3}[A-Za-zА-Яа-яЁё]{2}\d(?![A-Za-zА-Яа-яЁё0-9])"
)
_BY_PASSPORT_RE = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё0-9])[A-Za-zА-Яа-яЁё]{2}\d{7}(?![A-Za-zА-Яа-яЁё0-9])"
)
_RU_PASSPORT_RE = re.compile(
    r"(?iu)(паспорт[а-яё]*\s+)(\d{2}\s?\d{2}\s?\d{6}|\d{4}\s?\d{6}|\d{10})(?!\d)"
)
_PHONE_CANDIDATE_RE = re.compile(r"(?<![\dA-Za-z*])(\+?\d(?:[\s().-]*\d){7,17})(?!\d)")
_NON_DIGIT_RE = re.compile(r"\D")


def _strip_controls(text: str) -> str:
    nfkc = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in nfkc if unicodedata.category(ch) not in _CONTROL_CATEGORIES)


def _luhn_ok(digits: str) -> bool:
    total = 0
    alt = False
    for char in reversed(digits):
        n = ord(char) - 48
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def _mask_cards(text: str) -> tuple[str, bool]:
    hit = False

    def repl(match: re.Match[str]) -> str:
        nonlocal hit
        digits = _NON_DIGIT_RE.sub("", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            hit = True
            return CARD_PLACEHOLDER
        return match.group(0)

    return _CARD_CANDIDATE_RE.sub(repl, text), hit


def _is_by_phone(digits: str, had_plus: bool) -> bool:
    if had_plus and digits.startswith("375") and len(digits) >= 12:
        return True
    return len(digits) == 11 and digits.startswith("80")


def _is_ru_kz_phone(digits: str, had_plus: bool) -> bool:
    if had_plus and digits.startswith("7") and not digits.startswith("375") and len(digits) >= 11:
        return True
    return len(digits) == 11 and digits.startswith("8") and not digits.startswith("80")


def _is_generic_plus_phone(digits: str, had_plus: bool) -> bool:
    return had_plus and 8 <= len(digits) <= 15


def _mask_phones(text: str) -> tuple[str, bool]:
    hit = False

    def repl(match: re.Match[str]) -> str:
        nonlocal hit
        raw = match.group(0)
        had_plus = raw.strip().startswith("+")
        digits = _NON_DIGIT_RE.sub("", raw)
        if (
            _is_by_phone(digits, had_plus)
            or _is_ru_kz_phone(digits, had_plus)
            or _is_generic_plus_phone(digits, had_plus)
        ):
            hit = True
            return PHONE_PLACEHOLDER
        return raw

    return _PHONE_CANDIDATE_RE.sub(repl, text), hit


class GuardrailDecision(BaseModel):
    decision: str  # "allow", "mask", "block", "handoff"
    redacted_text: str
    categories: list[str]
    reason_codes: list[str]


class GuardrailsService:
    def __init__(self):
        self.injection_patterns = re.compile(
            r"(ignore\s+previous\s+instructions|забудь\s+инструкции|system\s+prompt|отключи\s+фильтры)",
            re.IGNORECASE,
        )

    def check_retrieved_content(self, text: str) -> bool:
        """Проверяет найденный контент на наличие попыток перехвата управления."""
        return not self.injection_patterns.search(text)

    def process_input(self, text: str) -> GuardrailDecision:
        categories: list[str] = []
        redacted = _strip_controls(text)

        redacted, emails = _EMAIL_RE.subn(EMAIL_PLACEHOLDER, redacted)
        if emails:
            categories.append("email")

        redacted, cards = _mask_cards(redacted)
        if cards:
            categories.append("payment_card")

        redacted, ids = _BY_PERSONAL_ID_RE.subn(ID_PLACEHOLDER, redacted)
        if ids:
            categories.append("personal_id")

        redacted, by_passports = _BY_PASSPORT_RE.subn(PASSPORT_PLACEHOLDER, redacted)
        if by_passports:
            categories.append("passport")

        def ru_passport_repl(match: re.Match[str]) -> str:
            return f"{match.group(1)}{PASSPORT_PLACEHOLDER}"

        redacted, ru_passports = _RU_PASSPORT_RE.subn(ru_passport_repl, redacted)
        if ru_passports and "passport" not in categories:
            categories.append("passport")
        elif ru_passports:
            pass

        redacted, phones = _mask_phones(redacted)
        if phones:
            categories.append("phone_number")

        decision = "allow" if not categories else "mask"
        return GuardrailDecision(
            decision=decision,
            redacted_text=redacted,
            categories=categories,
            reason_codes=["PII_MASKED"] if categories else [],
        )

    def validate_output(self, generated_json: dict, valid_source_ids: list[str]) -> bool:
        """Проверка выходного контракта и галлюцинаций ссылок."""
        # 1. Проверка утечки системного промпта
        answer_text = generated_json.get("answer_text", "")
        if "<TRUSTED_POLICY>" in answer_text:
            return False

        # 2. Проверка, что модель не выдумала citation_ids[cite: 17]
        citation_ids = generated_json.get("citation_ids", [])
        for c_id in citation_ids:
            if c_id not in valid_source_ids:
                return False  # Обнаружена выдуманная ссылка
        if generated_json.get("answer_status") == "grounded" and not citation_ids:
            return False

        # 3. Валидация разрешенных статусов ответа[cite: 17]
        valid_statuses = {"grounded", "needs_clarification", "no_evidence", "handoff"}
        return generated_json.get("answer_status") in valid_statuses
