import json

import pytest

from app.orchestrator.openrouter_client import OpenRouterAdapter
from app.orchestrator.state_machine import TurnContext

MODEL = "meta-llama/llama-3-8b-instruct"


def _adapter() -> OpenRouterAdapter:
    return OpenRouterAdapter(api_key="", allowed_models=[MODEL])


def _context() -> TurnContext:
    return TurnContext(turn_id="t1", session_id="s1", tenant_id="acme-it-demo")


@pytest.mark.asyncio
async def test_mock_emits_grounded_json_with_cyrillic():
    messages = [
        {
            "role": "system",
            "content": (
                "<EVIDENCE>\n"
                "[acme-hours-1] title=График url=https://www.acme-it.example/help/hours "
                "crawled_at=2026-10-11T00:00:00+00:00 valid_to=\n"
                "content=Офис Acme открыт понедельник.\n"
                "</EVIDENCE>"
            ),
        }
    ]
    blob = ""
    async for chunk in _adapter().stream_answer(MODEL, messages, _context()):
        blob += chunk
    data = json.loads(blob)
    assert data["answer_status"] == "grounded"
    assert data["citation_ids"] == ["acme-hours-1"]
    assert "Офис" in data["answer_text"]
    assert "\\u" not in blob


@pytest.mark.asyncio
async def test_mock_no_evidence_when_block_empty():
    messages = [{"role": "system", "content": "<EVIDENCE>\n\n</EVIDENCE>"}]
    blob = ""
    async for chunk in _adapter().stream_answer(MODEL, messages, _context()):
        blob += chunk
    data = json.loads(blob)
    assert data["answer_status"] == "no_evidence"
    assert data["citation_ids"] == []


@pytest.mark.asyncio
async def test_empty_key_mocks_without_demo_environment(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    adapter = OpenRouterAdapter(api_key="", allowed_models=[MODEL])
    assert adapter.is_mock is True
    messages = [
        {
            "role": "system",
            "content": (
                "<EVIDENCE>\n"
                "[acme-hours-1] title=График url=https://www.acme-it.example/help/hours "
                "crawled_at=2026-10-11T00:00:00+00:00 valid_to=\n"
                "content=Офис Acme открыт понедельник.\n"
                "</EVIDENCE>"
            ),
        }
    ]
    blob = ""
    async for chunk in adapter.stream_answer(MODEL, messages, _context()):
        blob += chunk
    data = json.loads(blob)
    assert data["answer_status"] == "grounded"
    assert data["citation_ids"] == ["acme-hours-1"]


def test_placeholder_key_enables_mock(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    adapter = OpenRouterAdapter(api_key="your_test_key_here", allowed_models=[MODEL])
    assert adapter.is_mock is True


def test_real_key_disables_mock_even_in_demo(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "demo")
    adapter = OpenRouterAdapter(api_key="sk-live-not-a-placeholder", allowed_models=[MODEL])
    assert adapter.is_mock is False


@pytest.mark.asyncio
async def test_mock_stops_on_cancel():
    messages = [
        {
            "role": "system",
            "content": "<EVIDENCE>\n[id-1] title=t url=https://www.acme-it.example/\ncontent=Привет.\n</EVIDENCE>",
        }
    ]
    ctx = _context()
    ctx.cancel()
    chunks = []
    async for chunk in _adapter().stream_answer(MODEL, messages, ctx):
        chunks.append(chunk)
    assert chunks == []
