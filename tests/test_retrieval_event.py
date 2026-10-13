import json

import pytest

from app.orchestrator.grounding import RETRIEVAL_EVENT_KEYS, query_sha256
from tests.conftest import bind_session, make_orchestrator
from tests.fakes import SpyRetriever


class LoggerRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def info(self, event, **kwargs):
        self.events.append((event, kwargs))

    def error(self, event, **kwargs):
        self.events.append((event, kwargs))

    def warning(self, event, **kwargs):
        self.events.append((event, kwargs))


@pytest.mark.asyncio
async def test_event_allowlist_and_redacted_hash(demo_runtime, counting_llm, monkeypatch):
    from app.orchestrator import dialog_flow

    recorder = LoggerRecorder()
    monkeypatch.setattr(dialog_flow, "logger", recorder)

    spy = SpyRetriever(demo_runtime.retriever)
    orch, manager, store, _ = make_orchestrator(spy, llm=counting_llm)
    bind_session(manager)
    phone_query = "график работы офис acme +375 29 123-45-67"
    outcome = await orch.run_turn("s1", phone_query, channel="text")
    assert outcome.answer_status == "grounded"

    event = store.retrieval_events[0]
    payload = {
        key: getattr(event, key)
        for key in RETRIEVAL_EVENT_KEYS
    }
    assert set(payload) == RETRIEVAL_EVENT_KEYS
    redacted = "график работы офис acme [PHONE_REDACTED]"
    assert spy.calls[0]["query"] == redacted
    assert event.query_sha256 == query_sha256(redacted)
    assert event.query_chars == len(redacted)

    dumped = json.dumps(payload, default=str)
    assert "query_variants" not in dumped
    assert "+375" not in dumped
    assert "123-45-67" not in dumped
    assert "query_variants" not in payload

    for event_name, fields in recorder.events:
        blob = json.dumps({"event": event_name, **fields}, default=str)
        assert "query_variants" not in blob
        assert "+375" not in blob
        assert phone_query not in blob
        assert "query" not in fields
