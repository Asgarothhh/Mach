import os
import json
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware

# Импорт схем и моделей
from app.schemas.api import HandoffResponse, SessionCreateRequest, SessionResponse, ErrorResponse
from app.schemas.events import ASREvent, VADEvent, InterruptionEvent
from app.models.database import Turn

# Импорт доменных модулей и оркестратора
from app.orchestrator.state_machine import SessionManager, SessionState
from app.orchestrator.openrouter_client import OpenRouterAdapter
from app.orchestrator.dialog_flow import DialogOrchestrator
from app.security.guardrails import GuardrailsService
from app.security.telemetry import get_logger
from app.rag.retriever import MockKnowledgeRetriever

from prometheus_client import make_asgi_app

# Импорт зависимостей базы данных и роутеров
from app.api.deps import AsyncSessionLocal
from app.api.admin import router as admin_router
from app.voice_agent.speech_cascade import SpeechCascade
from speech.contracts import (
    ASREvent as SpeechASREvent,
    SpeechError as SpeechPipelineError,
    VADEvent as SpeechVADEvent,
    VADEventType as SpeechVADEventType,
)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = get_logger("api_main")

# Инициализация FastAPI
app = FastAPI(title="MTS Voice Agent API", version="1.0")

# Настройка Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

# Экспорт метрик Prometheus
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Инициализация синглтонов сервисов (Убрано дублирование)
session_manager = SessionManager()
guardrails = GuardrailsService()
retriever = MockKnowledgeRetriever()

# LLM-адаптер с автоматическим переходом в mock-режим, если ключа нет
llm_adapter = OpenRouterAdapter(
    api_key=os.getenv("OPENROUTER_API_KEY", ""),
    allowed_models=["meta-llama/llama-3-8b-instruct"]
)

# Передаем retriever 4-ым аргументом[cite: 6, 7]
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
@limiter.limit("5/minute")
async def create_session(request: Request, req: SessionCreateRequest):
    """Инициализация новой сессии вызова с ограничением частоты[cite: 6]."""
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
    """Фоновая задача потоковой отправки аудиочанков в сокет.

    Чанки пейсятся по темпу воспроизведения (как это делает реальный
    медиамост): иначе тестовый канал получает весь ответ мгновенно, и
    перебивание физически не может попасть в момент речи агента.
    При отмене задачи (barge-in) отправка прекращается на ближайшем await.
    """
    # Хардкод tenant_id для демо Этапа 1. В реальности извлекается из сессии БД.
    tenant_id = "demo-tenant-1"
    try:
        async with AsyncSessionLocal() as db:
            stream = dialog_orchestrator.stream_final_asr(session_id, asr_text, tenant_id, db)
            try:
                async for tts_event in stream:
                    await websocket.send_json({
                        "type": "TTSChunkEvent",
                        "payload": tts_event.model_dump()
                    })
                    if tts_event.audio_base64:
                        pcm_bytes = len(tts_event.audio_base64) * 3 // 4
                        sample_rate = tts_event.sample_rate or 24000
                        audio_seconds = pcm_bytes / 2 / sample_rate
                        await asyncio.sleep(max(0.0, min(audio_seconds, 2.0)))
            finally:
                # Явно закрываем генератор в этом же контексте: при отмене
                # (barge-in) сборщик мусора иначе финализирует его в чужом
                # контексте и OTel-трейсинг сыплет "Failed to detach context".
                await stream.aclose()
    except asyncio.CancelledError:
        logger.info("tts_stream_task_cancelled", session_id=session_id)
    except Exception as e:
        logger.error("tts_stream_error", error=str(e), session_id=session_id)


async def _safe_send_json(websocket: WebSocket, payload: dict) -> None:
    """Send a JSON event unless the socket is already gone."""
    try:
        await websocket.send_json(payload)
    except (RuntimeError, WebSocketDisconnect):
        pass


@app.websocket("/api/v1/ws/sessions/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Точка входа для потокового аудио и событий.

    Текстовые сообщения — JSON-события (ASREvent/VADEvent/InterruptionEvent,
    как раньше). Бинарные сообщения — PCM16-LE mono @16 kHz: они идут в
    речевой каскад (наш VAD -> T-one -> оркестратор -> наш TTS).
    """
    # TODO: Проверка media token перед accept
    await websocket.accept()
    session_manager.transition(session_id, SessionState.CONNECTING)

    generation_task: asyncio.Task | None = None
    speech: SpeechCascade | None = None

    async def stop_generation() -> None:
        nonlocal generation_task
        if generation_task is not None and not generation_task.done():
            generation_task.cancel()
        generation_task = None

    async def on_vad(event: SpeechVADEvent) -> None:
        is_speech = event.type is SpeechVADEventType.SPEECH_START
        state = session_manager.active_sessions.get(session_id)
        if is_speech and state in (
            SessionState.SPEAKING,
            SessionState.GENERATING,
            SessionState.RETRIEVING,
            SessionState.ROUTING,
        ):
            # Звонящий перебивает агента: отменяем генерацию и чистим очередь.
            session_manager.handle_barge_in(session_id)
            await stop_generation()
            interrupted_turn = session_manager.active_turns.get(session_id)
            logger.info("barge_in_detected", session_id=session_id)
            await _safe_send_json(websocket, {
                "type": "InterruptionEvent",
                "payload": {
                    "session_id": session_id,
                    "interrupted_turn_id": interrupted_turn.turn_id if interrupted_turn else "",
                    "timestamp_ms": event.timestamp_ms,
                },
            })
        session_manager.transition(
            session_id,
            SessionState.LISTENING if is_speech else SessionState.ENDPOINT_PENDING,
        )
        await _safe_send_json(websocket, {
            "type": "VADEvent",
            "payload": {
                "session_id": session_id,
                "turn_id": speech.current_turn_id if speech else "",
                "timestamp_ms": event.timestamp_ms,
                "is_speech": is_speech,
                "confidence": event.confidence or 0.0,
            },
        })

    async def on_asr(event: SpeechASREvent) -> None:
        nonlocal generation_task
        if not event.text.strip():
            logger.info("asr_final_empty", session_id=session_id, turn_id=event.turn_id)
            return
        session_manager.transition(session_id, SessionState.TRANSCRIBING_FINAL)
        logger.info("asr_final_received", session_id=session_id, turn_id=event.turn_id)
        await _safe_send_json(websocket, {
            "type": "ASREvent",
            "payload": {**event.model_dump(), "timestamp_ms": event.end_ms or 0},
        })
        # Новый ход вытесняет предыдущую генерацию, если она ещё жива.
        await stop_generation()
        generation_task = asyncio.create_task(
            send_tts_stream(websocket, session_id, event.text)
        )

    try:
        speech = SpeechCascade(session_id, on_vad=on_vad, on_asr=on_asr)
    except SpeechPipelineError as exc:
        logger.error("speech_pipeline_unavailable", session_id=session_id, error=str(exc))
        session_manager.transition(session_id, SessionState.DEGRADED)

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                if speech is not None:
                    try:
                        await speech.feed(message["bytes"])
                    except SpeechPipelineError as exc:
                        logger.error("audio_feed_failed", session_id=session_id, error=str(exc))
                continue

            raw_data = message.get("text")
            if raw_data is None:
                continue
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
                        await stop_generation()
                        generation_task = asyncio.create_task(
                            send_tts_stream(websocket, session_id, asr_event.text)
                        )

                elif event_type == "VADEvent":
                    vad_event = VADEvent(**data["payload"])
                    new_state = SessionState.LISTENING if vad_event.is_speech else SessionState.ENDPOINT_PENDING
                    session_manager.transition(session_id, new_state)

                elif event_type == "InterruptionEvent":
                    # Пользователь перебил бота: отменяем токен генерации[cite: 6, 7]
                    session_manager.handle_barge_in(session_id)
                    await stop_generation()
                    logger.info("barge_in_triggered", session_id=session_id)

            except json.JSONDecodeError:
                logger.warning("invalid_json_received", session_id=session_id)
            except Exception as e:
                logger.error("ws_validation_error", session_id=session_id, error=str(e))

    except WebSocketDisconnect:
        logger.info("ws_disconnected", session_id=session_id)
    finally:
        if speech is not None:
            try:
                await speech.close()
            except Exception as e:  # noqa: BLE001
                logger.error("speech_cascade_close_failed", session_id=session_id, error=str(e))
        await stop_generation()
        session_manager.transition(session_id, SessionState.CLOSED)


@app.post("/api/v1/sessions/{session_id}/handoff/human", response_model=HandoffResponse, tags=["Sessions"])
async def handoff_to_human(session_id: str):
    """Перевод сессии на живого оператора (SIP-трансфер)[cite: 7]."""
    if session_id not in session_manager.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Меняем статус на HANDOFF
    session_manager.transition(session_id, SessionState.HANDOFF)

    # В реальном приложении здесь будет логика отправки SIP REFER или сигнала в LiveKit
    logger.info("handoff_human_initiated", session_id=session_id)

    return HandoffResponse(
        session_id=session_id,
        status="success",
        handoff_type="human",
        message="Session transferred to human operator"
    )


@app.post("/api/v1/sessions/{session_id}/handoff/chat", response_model=HandoffResponse, tags=["Sessions"])
async def handoff_to_chat(session_id: str):
    """Перевод сессии в текстовый чат (генерация короткой ссылки)[cite: 7]."""
    if session_id not in session_manager.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session_manager.transition(session_id, SessionState.HANDOFF)

    # Генерация уникальной ссылки для продолжения в браузере/приложении
    chat_token = str(uuid.uuid4())[:8]
    chat_url = f"{os.getenv('APP_PUBLIC_ORIGIN', 'http://localhost:3000')}/chat/{session_id}?token={chat_token}"

    logger.info("handoff_chat_initiated", session_id=session_id, chat_url=chat_url)

    return HandoffResponse(
        session_id=session_id,
        status="success",
        handoff_type="chat",
        chat_link=chat_url,
        message="Chat link generated successfully"
    )