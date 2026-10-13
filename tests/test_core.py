import pytest
from fastapi import HTTPException

from app.api.deps import AdminUser
from app.orchestrator.state_machine import SessionBinding, SessionManager, SessionState


def test_state_machine_transitions():
    manager = SessionManager()
    session_id = "test-123"

    manager.transition(session_id, SessionState.CREATED)
    assert manager.active_sessions[session_id] == SessionState.CREATED

    manager.transition(session_id, SessionState.GENERATING)
    assert manager.active_sessions[session_id] == SessionState.GENERATING

    # Исправление: добавляем self в аргументы lambda-функции
    manager.active_turns[session_id] = type('obj', (object,), {'cancel': lambda self: True})()
    manager.handle_barge_in(session_id)
    assert manager.active_sessions[session_id] == SessionState.INTERRUPTED


@pytest.mark.asyncio
async def test_rbac_access():
    from app.api.deps import verify_transcript_access

    valid_admin = AdminUser(username="admin1", role="support_supervisor", tenant_id="t1")
    result = await verify_transcript_access(valid_admin)
    assert result == valid_admin

    invalid_admin = AdminUser(username="user1", role="viewer", tenant_id="t1")
    with pytest.raises(HTTPException) as exc_info:
        await verify_transcript_access(invalid_admin)
    assert exc_info.value.status_code == 403


def test_session_binding_set_once():
    manager = SessionManager()
    binding = SessionBinding(tenant_id="acme-it-demo", language="ru", channel="webrtc")
    manager.bind("s1", binding)
    assert manager.get_binding("s1") == binding
    assert manager.get_binding("missing") is None
    later = SessionBinding(tenant_id="mts-public-demo", language="be", channel="sip")
    manager.bind("s1", later)
    assert manager.get_binding("s1").tenant_id == "mts-public-demo"
    manager.unbind("s1")
    assert manager.get_binding("s1") is None
