import re
from pydantic import BaseModel


class GuardrailDecision(BaseModel):
    decision: str  # "allow", "mask", "block", "handoff"
    redacted_text: str
    categories: list[str]
    reason_codes: list[str]


class GuardrailsService:
    def __init__(self):
        # В реальной системе здесь инициализируется Microsoft Presidio
        self.phone_regex = re.compile(r'\+375\s?\(?\d{2}\)?\s?\d{3}\s?-?\s?\d{2}\s?-?\s?\d{2}')

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

    def validate_output(self, generated_text: str, source_ids: list[str]) -> bool:
        # Проверка, что LLM не придумал citation_ids, которых нет в RAG
        # Проверка отсутствия утечек system prompt
        if "<TRUSTED_POLICY>" in generated_text:
            return False
        return True