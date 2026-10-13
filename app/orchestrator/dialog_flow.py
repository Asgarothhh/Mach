import asyncio
from typing import Optional
from app.orchestrator.state_machine import SessionManager, SessionState, TurnContext
from app.orchestrator.openrouter_client import OpenRouterAdapter
from app.security.guardrails import GuardrailsService
from app.security.telemetry import get_logger

logger = get_logger("dialog_flow")


class DialogOrchestrator:
    def __init__(
            self,
            session_manager: SessionManager,
            llm_adapter: OpenRouterAdapter,
            guardrails: GuardrailsService
    ):
        self.session_manager = session_manager
        self.llm = llm_adapter
        self.guardrails = guardrails

    async def handle_final_asr(self, session_id: str, asr_text: str, tenant_id: str):
        """Обработка подтвержденной реплики пользователя и запуск LLM."""
        self.session_manager.transition(session_id, SessionState.GENERATING)

        # Создаем новый контекст хода с токеном отмены[cite: 3]
        import uuid
        turn_id = str(uuid.uuid4())
        turn_context = TurnContext(turn_id=turn_id, session_id=session_id, tenant_id=tenant_id)
        self.session_manager.active_turns[session_id] = turn_context

        # 1. Guardrails: маскирование PII перед отправкой во внешний LLM[cite: 3, 4]
        guardrail_result = self.guardrails.process_input(asr_text)
        if guardrail_result.decision == "block":
            self.session_manager.transition(session_id, SessionState.HANDOFF)
            return "Извините, этот запрос нарушает политику безопасности."

        messages = [{"role": "user", "content": guardrail_result.redacted_text}]

        # 2. Вызов OpenRouter с проверкой на отмену[cite: 3]
        try:
            response_chunks = []
            async for chunk in self.llm.stream_answer(
                    model_id="meta-llama/llama-3-8b-instruct",
                    messages=messages,
                    turn_context=turn_context
            ):
                if turn_context.is_cancelled:
                    logger.info("llm_generation_cancelled", turn_id=turn_id)
                    break
                response_chunks.append(chunk)
                # TODO: Отправка чанков в TTS адаптер

            return "".join(response_chunks)
        except Exception as e:
            logger.error("llm_generation_failed", error=str(e), turn_id=turn_id)
            self.session_manager.transition(session_id, SessionState.DEGRADED)
            return "Извините, произошла техническая ошибка."

    def handle_barge_in(self, session_id: str):
        """Немедленная отмена генерации и очистка состояния при перебивании[cite: 3, 4]."""
        self.session_manager.handle_barge_in(session_id)
        logger.info("barge_in_processed", session_id=session_id)