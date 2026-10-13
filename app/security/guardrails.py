import re
import json
from pydantic import BaseModel


class GuardrailDecision(BaseModel):
    decision: str  # "allow", "mask", "block", "handoff"
    redacted_text: str
    categories: list[str]
    reason_codes: list[str]


class GuardrailsService:
    def __init__(self):
        self.phone_regex = re.compile(r'\+375\s?\(?\d{2}\)?\s?\d{3}\s?-?\s?\d{2}\s?-?\s?\d{2}')
        # Эвристика для отлова базовых инъекций в RAG-контенте
        self.injection_patterns = re.compile(
            r'(ignore\s+previous\s+instructions|забудь\s+инструкции|system\s+prompt|отключи\s+фильтры)',
            re.IGNORECASE
        )

    def check_retrieved_content(self, text: str) -> bool:
        """Проверяет найденный контент на наличие попыток перехвата управления."""
        if self.injection_patterns.search(text):
            return False
        return True

    def process_input(self, text: str) -> GuardrailDecision:
        categories = []
        redacted = text

        if self.phone_regex.search(text):
            redacted = self.phone_regex.sub("[PHONE_REDACTED]", text)
            categories.append("phone_number")

        decision = "allow" if not categories else "mask"

        return GuardrailDecision(
            decision=decision,
            redacted_text=redacted,
            categories=categories,
            reason_codes=["PII_MASKED"] if categories else []
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

        # 3. Валидация разрешенных статусов ответа[cite: 17]
        valid_statuses = {"grounded", "needs_clarification", "no_evidence", "handoff"}
        if generated_json.get("answer_status") not in valid_statuses:
            return False

        return True