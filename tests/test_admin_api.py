import pytest
from fastapi.testclient import TestClient

from app.models.database import Turn
from app.orchestrator.dialog_flow import DialogOrchestrator
from app.orchestrator.state_machine import SessionManager, SessionState
from app.rag.demo_fixtures import ACME_TENANT_ID, MTS_TENANT_ID
from tests.conftest import ACME_SUFFICIENT_QUERY
from tests.fakes import InMemoryTurnStore


def _admin_client(memory_store, monkeypatch, environment: str | None = "demo"):
    from app.api import main

    if environment is None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT", environment)
    main.llm_adapter.is_mock = True
    fresh_manager = SessionManager()
    monkeypatch.setattr(main, "session_manager", fresh_manager)
    monkeypatch.setattr(main, "store", memory_store)
    orch = DialogOrchestrator(
        fresh_manager,
        main.llm_adapter,
        main.guardrails,
        main.runtime.retriever,
        memory_store,
    )
    monkeypatch.setattr(main, "dialog_orchestrator", orch)
    main.limiter.reset()
    return TestClient(main.app), fresh_manager


@pytest.mark.asyncio
async def test_admin_requires_demo_environment(memory_store, monkeypatch):
    client, _ = _admin_client(memory_store, monkeypatch, environment=None)
    with client:
        response = client.get("/api/v1/admin/sessions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_lists_only_scoped_tenants(memory_store, monkeypatch):
    client, _ = _admin_client(memory_store, monkeypatch)
    await memory_store.create_session("s-acme", ACME_TENANT_ID, "text", "ru")
    await memory_store.create_session("s-mts", MTS_TENANT_ID, "webrtc", "ru")
    await memory_store.create_session("s-other", "other-tenant", "text", "ru")
    with client:
        response = client.get("/api/v1/admin/sessions")
    assert response.status_code == 200
    body = response.json()
    ids = {item["session_id"] for item in body}
    assert ids == {"s-acme", "s-mts"}
    assert all("tenant_id" in item and "turn_count" in item for item in body)


@pytest.mark.asyncio
async def test_admin_explicit_tenant_outside_scope_403(memory_store, monkeypatch):
    client, _ = _admin_client(memory_store, monkeypatch)
    with client:
        response = client.get("/api/v1/admin/sessions", params={"tenant_id": "other-tenant"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_detail_out_of_scope_is_404(memory_store, monkeypatch):
    client, _ = _admin_client(memory_store, monkeypatch)
    await memory_store.create_session("hidden", "other-tenant", "text", "ru")
    with client:
        missing = client.get("/api/v1/admin/sessions/no-such")
        hidden = client.get("/api/v1/admin/sessions/hidden")
    assert missing.status_code == 404
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_admin_correction_masks_pii_and_audits_session_tenant(memory_store, monkeypatch):
    client, _ = _admin_client(memory_store, monkeypatch)
    await memory_store.create_session("s1", ACME_TENANT_ID, "text", "ru")
    memory_store.turns.append(
        Turn(turn_id="t1", session_id="s1", sequence_no="1", redacted_text="старый текст")
    )
    with client:
        response = client.post(
            "/api/v1/admin/sessions/s1/transcript-corrections",
            json={
                "turn_id": "t1",
                "corrected_text": "звоните +375 29 123-45-67",
                "reason": "ASR_error",
            },
        )
        detail = client.get("/api/v1/admin/sessions/s1")
    assert response.status_code == 200
    assert "[PHONE_REDACTED]" in (memory_store.turns[0].redacted_text or "")
    assert "+375" not in (memory_store.turns[0].redacted_text or "")
    assert "123-45-67" not in (memory_store.turns[0].redacted_text or "")
    actions = [event["action"] for event in memory_store.audit_events]
    assert "correct_transcript" in actions
    assert "read_transcript" in actions
    assert all(event["tenant_id"] == ACME_TENANT_ID for event in memory_store.audit_events)
    assert detail.status_code == 200
    assert detail.json()["tenant_id"] == ACME_TENANT_ID


@pytest.mark.asyncio
async def test_admin_detail_remasks_legacy_unmasked_pii(memory_store, monkeypatch):
    client, _ = _admin_client(memory_store, monkeypatch)
    await memory_store.create_session("s-legacy", ACME_TENANT_ID, "text", "ru")
    memory_store.turns.append(
        Turn(
            turn_id="t-raw",
            session_id="s-legacy",
            sequence_no="1",
            redacted_text="пишите на user@example.com или +375 29 123-45-67",
        )
    )
    with client:
        detail = client.get("/api/v1/admin/sessions/s-legacy")
    assert detail.status_code == 200
    text = detail.json()["turns"][0]["redacted_text"]
    assert "[EMAIL_REDACTED]" in text
    assert "[PHONE_REDACTED]" in text
    assert "user@example.com" not in text
    assert "+375" not in text
    assert "123-45-67" not in text


@pytest.mark.asyncio
async def test_end_orphan_db_session_closes(memory_store, monkeypatch):
    client, manager = _admin_client(memory_store, monkeypatch)
    await memory_store.create_session("orphan", ACME_TENANT_ID, "text", "ru")
    assert "orphan" not in manager.active_sessions
    with client:
        response = client.post("/api/v1/sessions/orphan/end")
    assert response.status_code == 200
    assert memory_store.sessions[0]["status"] is SessionState.CLOSED


def test_text_turn_persists_status(api_client, memory_store):
    created = api_client.post(
        "/api/v1/sessions",
        json={"tenant_id": ACME_TENANT_ID, "channel": "text", "language": "ru"},
    )
    session_id = created.json()["session_id"]
    response = api_client.post(
        f"/api/v1/sessions/{session_id}/turns/text",
        json={"text": ACME_SUFFICIENT_QUERY},
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == ACME_TENANT_ID
    row = next(item for item in memory_store.sessions if item["session_id"] == session_id)
    assert row["status"] is SessionState.LISTENING


def test_handoff_persists_status(api_client, memory_store):
    created = api_client.post(
        "/api/v1/sessions",
        json={"tenant_id": ACME_TENANT_ID, "channel": "text", "language": "ru"},
    )
    session_id = created.json()["session_id"]
    human = api_client.post(f"/api/v1/sessions/{session_id}/handoff/human")
    assert human.status_code == 200
    row = next(item for item in memory_store.sessions if item["session_id"] == session_id)
    assert row["status"] is SessionState.HUMAN_HANDOFF
