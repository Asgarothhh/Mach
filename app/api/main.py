import json
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from app.schemas.api import SessionCreateRequest, SessionResponse, ErrorResponse
from app.schemas.events import ASREvent, VADEvent, InterruptionEvent
from app.orchestrator.state_machine import SessionManager, SessionState
from app.security.guardrails import GuardrailsService
from app.security.telemetry import get_logger
from app.api.admin import router as admin_router

logger = get_logger("api_main")
app = FastAPI(title="MTS Voice Agent API", version="1.0")

# Настройка CORS для Frontend[cite: 16, 17]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_manager = SessionManager()
guardrails = GuardrailsService()

app.include_router(admin_router)


@app.get("/health/live", tags=["Health"])
async def liveness():
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
async def readiness():
    return {"status": "ready"}


@app.post("/api/v1/sessions", response_model=SessionResponse, tags=["Sessions"])
async def create_session(req: SessionCreateRequest):
    import uuid
    session_id = str(uuid.uuid4())
    session_manager.transition(session_id, SessionState.CREATED)

    logger.info("session_created", session_id=session_id, tenant_id=req.tenant_id)

    return SessionResponse(
        session_id=session_id,
        status=SessionState.CREATED,
        created_at=datetime.now(timezone.utc)
    )


@app.post("/api/v1/sessions/{session_id}/end", tags=["Sessions"])
async def end_session(session_id: str):
    if session_id not in session_manager.active_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session_manager.transition(session_id, SessionState.CLOSED)
    if session_id in session_manager.active_turns:
        session_manager.active_turns[session_id].cancel()

    logger.info("session_ended", session_id=session_id)
    return {"message": "Session terminated"}


@app.websocket("/api/v1/ws/sessions/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Точка входа для потокового аудио и событий[cite: 16, 17].
    """
    await websocket.accept()
    session_manager.transition(session_id, SessionState.CONNECTING)

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
                event_type = data.get("type")

                # Маршрутизация событий[cite: 16, 17]
                if event_type == "ASREvent":
                    asr_event = ASREvent(**data["payload"])
                    if asr_event.is_final:
                        session_manager.transition(session_id, SessionState.TRANSCRIBING_FINAL)
                        logger.info("asr_final_received", session_id=session_id, turn_id=asr_event.turn_id)
                        # В будущем здесь будет вызов DialogOrchestrator.handle_final_asr

                elif event_type == "VADEvent":
                    vad_event = VADEvent(**data["payload"])
                    new_state = SessionState.LISTENING if vad_event.is_speech else SessionState.ENDPOINT_PENDING
                    session_manager.transition(session_id, new_state)

                elif event_type == "InterruptionEvent":
                    interruption = InterruptionEvent(**data["payload"])
                    session_manager.handle_barge_in(session_id)
                    logger.info("barge_in_triggered", session_id=session_id)

                else:
                    logger.debug("ws_unhandled_event", session_id=session_id, event_type=event_type)

            except json.JSONDecodeError:
                logger.warning("invalid_json_received", session_id=session_id)
            except Exception as e:
                logger.error("ws_validation_error", session_id=session_id, error=str(e))

    except WebSocketDisconnect:
        session_manager.transition(session_id, SessionState.CLOSED)
        logger.info("ws_disconnected", session_id=session_id)