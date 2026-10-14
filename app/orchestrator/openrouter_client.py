import asyncio
import json
import os
import re
from collections.abc import AsyncGenerator

import httpx

from app.orchestrator.state_machine import TurnContext
from app.security.telemetry import get_logger

logger = get_logger("openrouter")

GEMMA_MODEL_ID = "google/gemma-4-26b-a4b-it"
STREAM_TIMEOUT_S = 30.0


def build_provider_options(model_id: str) -> dict:
    """Build OpenRouter provider routing.

    Gemma has no ZDR endpoints: forcing zdr=true yields 404 «No endpoints found».
    Attach zdr only when OPENROUTER_REQUIRE_ZDR is true *and* the model is not Gemma.
    """
    provider: dict = {"data_collection": "deny"}
    require_zdr = os.getenv("OPENROUTER_REQUIRE_ZDR", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if require_zdr and model_id != GEMMA_MODEL_ID:
        provider["zdr"] = True
    return provider


class OpenRouterAdapter:
    def __init__(self, api_key: str, allowed_models: list[str]):
        self.api_key = api_key
        self.allowed_models = allowed_models
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        # Mock when the key is missing or a known placeholder. ENVIRONMENT=demo is not required.
        # Live HTTP is used only when a real key is present.
        self.is_mock = not api_key or api_key == "your_test_key_here"

    async def stream_answer(
            self,
            model_id: str,
            messages: list[dict],
            turn_context: TurnContext
    ) -> AsyncGenerator[str, None]:

        if self.is_mock:
            system = next(
                (message.get("content", "") for message in messages if message.get("role") == "system"),
                "",
            )
            evidence_match = re.search(r"<EVIDENCE>(.*?)</EVIDENCE>", system, flags=re.DOTALL)
            evidence = evidence_match.group(1) if evidence_match else ""
            evidence_ids = re.findall(
                r"\[([A-Za-z0-9][A-Za-z0-9._:-]*)\]", evidence
            )
            if evidence_ids:
                content_match = re.search(r"content=(.*)", evidence, flags=re.DOTALL)
                raw_content = content_match.group(1).strip() if content_match else ""
                first_sentence = re.split(r"(?<=[.!?])\s+", raw_content, maxsplit=1)[0].strip()
                payload = {
                    "answer_text": first_sentence or raw_content,
                    "citation_ids": [evidence_ids[0]],
                    "answer_status": "grounded",
                }
            else:
                payload = {
                    "answer_text": "По этому вопросу в базе знаний нет подтверждённых данных.",
                    "citation_ids": [],
                    "answer_status": "no_evidence",
                }
            blob = json.dumps(payload, ensure_ascii=False)
            slice_size = max(1, len(blob) // 3)
            for offset in range(0, len(blob), slice_size):
                if turn_context.is_cancelled:
                    break
                yield blob[offset:offset + slice_size]
                await asyncio.sleep(0)
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
            "provider": build_provider_options(model_id),
            "temperature": 0.2,
            "max_tokens": 250
        }

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST",
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=STREAM_TIMEOUT_S,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if turn_context.is_cancelled:
                            break

                        if line.startswith("data: ") and line != "data: [DONE]":
                            data = json.loads(line[6:])
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {}).get("content", "")
                                if delta:
                                    yield delta
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "openrouter_http_error",
                    error_class=exc.__class__.__name__,
                    status_code=exc.response.status_code,
                )
                raise RuntimeError(
                    f"OpenRouter API error: {exc.__class__.__name__}"
                ) from None
            except httpx.HTTPError as exc:
                logger.error("openrouter_http_error", error_class=exc.__class__.__name__)
                raise RuntimeError(
                    f"OpenRouter API error: {exc.__class__.__name__}"
                ) from None
