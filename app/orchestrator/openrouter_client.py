import httpx
import asyncio
import json
import os
from typing import AsyncGenerator
from app.orchestrator.state_machine import TurnContext


class OpenRouterAdapter:
    def __init__(self, api_key: str, allowed_models: list[str]):
        self.api_key = api_key
        self.allowed_models = allowed_models
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        # Включаем mock-режим, если ключа нет или он тестовый, как требуется для Этапа 0
        self.is_mock = os.getenv("ENVIRONMENT") == "demo" and (not api_key or api_key == "your_test_key_here")

    async def stream_answer(
            self,
            model_id: str,
            messages: list[dict],
            turn_context: TurnContext
    ) -> AsyncGenerator[str, None]:

        if self.is_mock:
            mock_text = "Это тестовый ответ от mock-провайдера. Система работает штатно."
            for word in mock_text.split():
                if turn_context.is_cancelled:
                    break  # Прерывание при barge-in[cite: 16, 17]
                yield word + " "
                await asyncio.sleep(0.1)  # Имитация TTFT и задержки сети
            return

        if model_id not in self.allowed_models:
            raise ValueError("Model not in allowlist")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model_id,
            "messages": messages,
            "stream": True,
            "provider": {
                "data_collection": "deny",
                "zdr": True
            },
            "temperature": 0.2,
            "max_tokens": 250
        }

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("POST", self.base_url, headers=headers, json=payload, timeout=5.0) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if turn_context.is_cancelled:
                            break  # Прерывание при barge-in[cite: 16, 17]

                        if line.startswith("data: ") and line != "data: [DONE]":
                            data = json.loads(line[6:])
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {}).get("content", "")
                                if delta:
                                    yield delta
            except httpx.HTTPError as e:
                # Нормализация ошибок, скрытие stack trace и ключей[cite: 16, 17]
                raise RuntimeError(f"OpenRouter API error: {e.__class__.__name__}")