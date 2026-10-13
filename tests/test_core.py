import pytest
from app.orchestrator.state_machine import SessionManager, SessionState
from app.api.deps import AdminUser
from fastapi import HTTPException


# Тест Машины состояний[cite: 6]
def test_state_machine_transitions():
    manager = SessionManager()
    session_id = "test-123"

    manager.transition(session_id, SessionState.CREATED)
    assert manager.active_sessions[session_id] == SessionState.CREATED

    manager.transition(session_id, SessionState.GENERATING)
    assert manager.active_sessions[session_id] == SessionState.GENERATING

    # Проверка Barge-in[cite: 6, 7]
    manager.active_turns[session_id] = type('obj', (object,), {'cancel': lambda: True})()
    manager.handle_barge_in(session_id)
    assert manager.active_sessions[session_id] == SessionState.INTERRUPTED


# Тест RBAC[cite: 6]
@pytest.mark.asyncio
async def test_rbac_access():
    from app.api.deps import verify_transcript_access

    # Доступ разрешен
    valid_admin = AdminUser(username="admin1", role="support_supervisor", tenant_id="t1")
    result = await verify_transcript_access(valid_admin)
    assert result == valid_admin

    # Доступ запрещен (здесь должна вылететь HTTPException)
    invalid_admin = AdminUser(username="user1", role="viewer", tenant_id="t1")
    with pytest.raises(HTTPException) as exc_info:
        await verify_transcript_access(invalid_admin)
    assert exc_info.value.status_code == 403