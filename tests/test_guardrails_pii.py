import json

import pytest

from app.security.guardrails import GuardrailsService
from tests.conftest import bind_session, make_orchestrator
from tests.fakes import SpyRetriever
from tests.test_conversation import RecordingLLM

VISA = "4111111111111111"
VISA_INVALID = "4111111111111112"


def _mask(text: str):
    return GuardrailsService().process_input(text)


def test_nfkc_and_control_chars_stripped():
    result = _mask("график\x00 работы\u200b")
    assert "\x00" not in result.redacted_text
    assert "\u200b" not in result.redacted_text
    assert "график" in result.redacted_text


def test_email_is_masked():
    result = _mask("напишите на user@example.com пожалуйста")
    assert "[EMAIL_REDACTED]" in result.redacted_text
    assert "user@example.com" not in result.redacted_text
    assert "email" in result.categories
    assert result.decision == "mask"


@pytest.mark.parametrize(
    "number",
    [
        "+375 29 123-45-67",
        "+375291234567",
        "80 29 123 45 67",
        "80291234567",
        "8 029 123-45-67",
        "+7 900 123-45-67",
        "8 900 123 45 67",
        "+441234567890",
    ],
)
def test_phones_are_masked(number: str):
    result = _mask(f"перезвоните {number} утром")
    assert "[PHONE_REDACTED]" in result.redacted_text
    assert "123" not in result.redacted_text or "[PHONE_REDACTED]" in result.redacted_text
    digits = "".join(ch for ch in number if ch.isdigit())
    assert digits not in result.redacted_text.replace("[PHONE_REDACTED]", "")
    assert "phone_number" in result.categories


def test_legacy_formatted_by_phone():
    result = _mask("+375 29 123-45-67")
    assert result.redacted_text == "[PHONE_REDACTED]"


def test_luhn_card_is_masked():
    result = _mask(f"карта {VISA} к оплате")
    assert "[CARD_REDACTED]" in result.redacted_text
    assert VISA not in result.redacted_text
    assert "payment_card" in result.categories


def test_luhn_invalid_16_digit_is_not_a_card():
    result = _mask(f"номер {VISA_INVALID} не карта")
    assert "[CARD_REDACTED]" not in result.redacted_text
    assert VISA_INVALID in result.redacted_text


def test_by_personal_number_and_passport():
    result = _mask("личный номер 1234567A123AB1 паспорт MP1234567")
    assert "[ID_REDACTED]" in result.redacted_text
    assert "[PASSPORT_REDACTED]" in result.redacted_text
    assert "1234567A123AB1" not in result.redacted_text
    assert "MP1234567" not in result.redacted_text


def test_ru_passport_near_keyword():
    result = _mask("паспорт 4510 123456 лежит дома")
    assert "[PASSPORT_REDACTED]" in result.redacted_text
    assert "123456" not in result.redacted_text
    assert "паспорт" in result.redacted_text.lower()


def test_ru_passport_digits_without_keyword_stay():
    result = _mask("код 4510123456 для входа")
    assert "[PASSPORT_REDACTED]" not in result.redacted_text


@pytest.mark.parametrize(
    "text",
    [
        "наберите *100# для баланса",
        "короткий номер 0890",
        "билет стоит 15.99",
        "офис до 18:00",
        "встреча в 9:00",
        "стоит 100 рублей",
    ],
)
def test_public_numbers_are_not_masked(text: str):
    result = _mask(text)
    assert result.decision == "allow"
    assert result.categories == []
    assert "REDACTED" not in result.redacted_text
    assert "*100#" in text or "0890" in result.redacted_text or "15.99" in result.redacted_text or "18:00" in result.redacted_text or "9:00" in result.redacted_text or "100" in result.redacted_text


@pytest.mark.asyncio
async def test_retriever_and_llm_never_see_raw_pii(demo_runtime):
    spy = SpyRetriever(demo_runtime.retriever)
    llm = RecordingLLM(inner=make_orchestrator(demo_runtime.retriever)[3])
    orch, manager, _, _ = make_orchestrator(spy, llm=llm)
    bind_session(manager)
    raw = "график работы офис acme +375 29 123-45-67 user@example.com"
    await orch.run_turn("s1", raw, channel="text")
    blob = str(spy.calls) + json.dumps(llm.messages, ensure_ascii=False)
    assert "+375" not in blob
    assert "123-45-67" not in blob
    assert "user@example.com" not in blob
    assert "[PHONE_REDACTED]" in blob
    assert "[EMAIL_REDACTED]" in blob
