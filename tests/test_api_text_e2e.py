import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.orchestrator.dialog_flow import DialogOrchestrator
from app.orchestrator.openrouter_client import OpenRouterAdapter
from app.orchestrator.state_machine import SessionManager
from app.rag.retriever import KnowledgeRuntime
from tests.conftest import (
    ACME_SUFFICIENT_QUERY,
    LLM_MODEL,
    MTS_SUFFICIENT_QUERY,
    NO_EVIDENCE_QUERY,
    conflict_retriever,
)


def _create_session(client, tenant_id: str) -> str:
    response = client.post(
        "/api/v1/sessions",
        json={"tenant_id": tenant_id, "channel": "text", "language": "ru"},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def test_sufficient_acme(api_client, memory_store):
    session_id = _create_session(api_client, "acme-it-demo")
    response = api_client.post(
        f"/api/v1/sessions/{session_id}/turns/text",
        json={"text": ACME_SUFFICIENT_QUERY},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_status"] == "grounded"
    assert body["citation_ids"]
    assert body["sources"]
    assert all("acme-it.example" in source["canonical_url"] for source in body["sources"])
    assert memory_store.retrieval_events


def test_sufficient_mts(api_client, memory_store):
    session_id = _create_session(api_client, "mts-public-demo")
    response = api_client.post(
        f"/api/v1/sessions/{session_id}/turns/text",
        json={"text": MTS_SUFFICIENT_QUERY},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_status"] == "grounded"
    assert body["sources"]
    assert all("www.mts.by" in source["canonical_url"] for source in body["sources"])


def test_no_evidence_abstention(api_client):
    session_id = _create_session(api_client, "acme-it-demo")
    response = api_client.post(
        f"/api/v1/sessions/{session_id}/turns/text",
        json={"text": NO_EVIDENCE_QUERY},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_status"] == "no_evidence"
    assert body["citation_ids"] == []
    assert body["sources"] == []
    assert body["fallback_reason"] == "no_evidence"


def test_conflict_handoff(memory_store, monkeypatch):
    from app.api import main

    fresh_manager = SessionManager()
    monkeypatch.setattr(main, "session_manager", fresh_manager)
    monkeypatch.setattr(main, "store", memory_store)
    retriever = conflict_retriever()
    runtime = KnowledgeRuntime(retriever=retriever, tenants=frozenset({"acme-it-demo"}))
    monkeypatch.setattr(main, "runtime", runtime)
    orch = DialogOrchestrator(
        fresh_manager, main.llm_adapter, main.guardrails, retriever, memory_store
    )
    monkeypatch.setattr(main, "dialog_orchestrator", orch)
    main.llm_adapter.is_mock = True
    main.limiter.reset()
    with TestClient(main.app) as client:
        session_id = _create_session(client, "acme-it-demo")
        response = client.post(
            f"/api/v1/sessions/{session_id}/turns/text",
            json={"text": ACME_SUFFICIENT_QUERY},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_status"] == "handoff"
    assert body["fallback_reason"] == "evidence_conflict"
    assert body["sources"] == []


def test_unknown_tenant_404(api_client):
    response = api_client.post(
        "/api/v1/sessions",
        json={"tenant_id": "unknown-tenant", "channel": "text"},
    )
    assert response.status_code == 404
    text = response.text
    assert "tenant_not_available" in text
    assert "acme-it-demo" not in text
    assert "mts-public-demo" not in text


def test_tenant_id_in_turn_body_422(api_client):
    session_id = _create_session(api_client, "acme-it-demo")
    response = api_client.post(
        f"/api/v1/sessions/{session_id}/turns/text",
        json={"text": ACME_SUFFICIENT_QUERY, "tenant_id": "mts-public-demo"},
    )
    assert response.status_code == 422


def test_ended_session_text_turn_404(api_client):
    session_id = _create_session(api_client, "acme-it-demo")
    ended = api_client.post(f"/api/v1/sessions/{session_id}/end")
    assert ended.status_code == 200
    response = api_client.post(
        f"/api/v1/sessions/{session_id}/turns/text",
        json={"text": ACME_SUFFICIENT_QUERY},
    )
    assert response.status_code == 404


def test_text_turn_default_adapter_without_forcing_is_mock(memory_store, monkeypatch):
    from app.api import main

    monkeypatch.delenv("ENVIRONMENT", raising=False)
    adapter = OpenRouterAdapter(api_key="", allowed_models=[LLM_MODEL])
    assert adapter.is_mock is True
    fresh_manager = SessionManager()
    monkeypatch.setattr(main, "session_manager", fresh_manager)
    monkeypatch.setattr(main, "store", memory_store)
    orch = DialogOrchestrator(
        fresh_manager, adapter, main.guardrails, main.runtime.retriever, memory_store
    )
    monkeypatch.setattr(main, "dialog_orchestrator", orch)
    main.limiter.reset()
    with TestClient(main.app) as client:
        session_id = _create_session(client, "acme-it-demo")
        response = client.post(
            f"/api/v1/sessions/{session_id}/turns/text",
            json={"text": ACME_SUFFICIENT_QUERY},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_status"] == "grounded"
    assert body["citation_ids"]


def test_ws_invalid_payload_logs_error_class_only(api_client, monkeypatch):
    from app.api import main

    events: list[tuple[str, dict]] = []

    class Recorder:
        def error(self, event, **kwargs):
            events.append((event, kwargs))

        def info(self, event, **kwargs):
            events.append((event, kwargs))

        def warning(self, event, **kwargs):
            events.append((event, kwargs))

    monkeypatch.setattr(main, "logger", Recorder())
    session_id = _create_session(api_client, "acme-it-demo")
    with api_client.websocket_connect(f"/api/v1/ws/sessions/{session_id}") as websocket:
        websocket.send_json(
            {
                "type": "ASREvent",
                "payload": {"text": "+375 29 123-45-67"},
            }
        )
    logged = [item for item in events if item[0] == "ws_validation_error"]
    assert logged
    _, fields = logged[0]
    assert fields.get("error_class")
    assert "error" not in fields
    blob = str(fields)
    assert "+375" not in blob
    assert "123-45-67" not in blob


def test_unknown_session_404(api_client):
    response = api_client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/turns/text",
        json={"text": ACME_SUFFICIENT_QUERY},
    )
    assert response.status_code == 404


def test_ws_bound_session_yields_tts(api_client):
    session_id = _create_session(api_client, "acme-it-demo")
    with api_client.websocket_connect(f"/api/v1/ws/sessions/{session_id}") as websocket:
        websocket.send_json(
            {
                "type": "ASREvent",
                "payload": {
                    "session_id": session_id,
                    "turn_id": str(uuid.uuid4()),
                    "timestamp_ms": 1,
                    "revision": 1,
                    "text": ACME_SUFFICIENT_QUERY,
                    "is_final": True,
                    "language": "ru",
                },
            }
        )
        message = websocket.receive_json()
        assert message["type"] == "TTSChunkEvent"
        assert message["payload"]["is_last_chunk"] is True
        assert message["payload"]["audio_base64"]


def test_ws_unknown_session_closed(api_client):
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        api_client.websocket_connect(f"/api/v1/ws/sessions/{uuid.uuid4()}") as websocket,
    ):
        websocket.receive_text()
    assert exc.value.code == 1008


def test_ready_200_without_openrouter_key(api_client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    response = api_client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["retriever"] == "ok"
    assert "openrouter" not in body["checks"]


def test_ready_503_empty_runtime(api_client, monkeypatch):
    from app.api import main

    empty = KnowledgeRuntime(retriever=main.runtime.retriever, tenants=frozenset())
    monkeypatch.setattr(main, "runtime", empty)
    response = api_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_handoff_endpoints_200(api_client):
    session_id = _create_session(api_client, "acme-it-demo")
    human = api_client.post(f"/api/v1/sessions/{session_id}/handoff/human")
    assert human.status_code == 200
    chat = api_client.post(f"/api/v1/sessions/{session_id}/handoff/chat")
    assert chat.status_code == 200
