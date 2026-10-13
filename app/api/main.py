import os
import json
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Импорт схем и моделей
from app.schemas.api import SessionCreateRequest, SessionResponse, ErrorResponse
from app.schemas.events import ASREvent, VADEvent, InterruptionEvent
from app.models.database import Turn

# Импорт доменных модулей и оркестратора
from app.orchestrator.state_machine import SessionManager, SessionState
from app.orchestrator.openrouter_client import OpenRouterAdapter
from app.orchestrator.dialog_flow import DialogOrchestrator
from app.security.guardrails import GuardrailsService
from app.security.telemetry import get_logger
from app.rag.retriever import MockKnowledgeRetriever

# Импорт зависимостей базы данных и роутеров
from app.api.deps import AsyncSessionLocal
from app.api.admin import router as admin_router

logger = get_logger("api_main")

# Инициализация FastAPI
app = FastAPI(title="MTS Voice Agent API", version="1.0")

# Настройка CORS для Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Заменить на APP_PUBLIC_ORIGIN из .env для продакшена
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение административных эндпоинтов
app.include_router(admin_router)

# Инициализация синглтонов сервисов
session_manager = SessionManager()
guardrails = GuardrailsService()
retriever = MockKnowledgeRetriever() # ИСПРАВЛЕНИЕ: инициализируем ретривер

# LLM-адаптер с автоматическим переходом в mock-режим, если ключа нет
llm_adapter = OpenRouterAdapter(
    api_key=os.getenv("OPENROUTER_API_KEY", ""),
    allowed_models=["meta-llama/llama-3-8b-instruct"]
)

# ИСПРАВЛЕНИЕ: передаем retriever 4-ым аргументом[cite: 16, 17]
dialog_orchestrator = DialogOrchestrator(session_manager, llm_adapter, guardrails, retriever)


@app.get("/health/live", tags=["Health"])
async def liveness():
    """Проверка доступности процесса."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
async def readiness():
    """Проверка готовности к обслуживанию трафика (зависимости)."""
    # TODO: Добавить проверку соединения с PostgreSQL и Redis
    return {"status": "ready"}


@app.post("/api/v1/sessions", response_model=SessionResponse, tags=["Sessions"])
async def create_session(req: SessionCreateRequest):
    """Инициализация новой сессии вызова."""
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
    """Принудительное завершение сессии и отмена активных задач."""
    # TODO: Добавить проверку токена авторизации
    if session_id not in session_manager.active_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session_manager.transition(session_id, SessionState.CLOSED)
    if session_id in session_manager.active_turns:
        session_manager.active_turns[session_id].cancel()

    logger.info("session_ended", session_id=session_id)
    return {"message": "Session terminated"}


async def send_tts_stream(websocket: WebSocket, session_id: str, asr_text: str):
    """Фоновая задача потоковой отправки аудиочанков в сокет."""
    # Хардкод tenant_id для демо Этапа 1. В реальности извлекается из сессии БД.
    tenant_id = "demo-tenant-1"
    try:
        async with AsyncSessionLocal() as db:
            async for tts_event in dialog_orchestrator.stream_final_asr(session_id, asr_text, tenant_id, db):
                await websocket.send_json({
                    "type": "TTSChunkEvent",
                    "payload": tts_event.model_dump()
                })
    except asyncio.CancelledError:
        logger.info("tts_stream_task_cancelled", session_id=session_id)
    except Exception as e:
        logger.error("tts_stream_error", error=str(e), session_id=session_id)


@app.websocket("/api/v1/ws/sessions/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Точка входа для потокового аудио и событий[cite: 16, 17].
    """
    # TODO: Проверка media token перед accept
    await websocket.accept()
    session_manager.transition(session_id, SessionState.CONNECTING)

    generation_task = None

    try:
        while True:
            # Читаем как текст, чтобы избежать падений на бинарных данных до реализации их обработки
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
                event_type = data.get("type")

                # Маршрутизация событий
                if event_type == "ASREvent":
                    asr_event = ASREvent(**data["payload"])
                    if asr_event.is_final:
                        session_manager.transition(session_id, SessionState.TRANSCRIBING_FINAL)
                        logger.info("asr_final_received", session_id=session_id, turn_id=asr_event.turn_id)

                        # Запускаем генерацию и отправку в фоне, не блокируя цикл приема
                        generation_task = asyncio.create_task(
                            send_tts_stream(websocket, session_id, asr_event.text)
                        )

                elif event_type == "VADEvent":
                    vad_event = VADEvent(**data["payload"])
                    new_state = SessionState.LISTENING if vad_event.is_speech else SessionState.ENDPOINT_PENDING
                    session_manager.transition(session_id, new_state)

                elif event_type == "InterruptionEvent":
                    # Пользователь перебил бота: отменяем токен генерации[cite: 16, 17]
                    session_manager.handle_barge_in(session_id)
                    logger.info("barge_in_triggered", session_id=session_id)

            except json.JSONDecodeError:
                logger.warning("invalid_json_received", session_id=session_id)
            except Exception as e:
                logger.error("ws_validation_error", session_id=session_id, error=str(e))

    except WebSocketDisconnect:
        session_manager.transition(session_id, SessionState.CLOSED)
        if generation_task:
            generation_task.cancel()
        logger.info("ws_disconnected", session_id=session_id)