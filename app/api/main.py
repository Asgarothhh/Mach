import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.admin import router as admin_router
from app.api.deps import AsyncSessionLocal
from app.models.store import SqlAlchemyTurnStore, TurnStore
from app.orchestrator.dialog_flow import DialogOrchestrator, UnknownSessionError
from app.orchestrator.openrouter_client import OpenRouterAdapter
from app.orchestrator.state_machine import SessionBinding, SessionManager, SessionState
from app.rag.retriever import KnowledgeRuntime, build_demo_runtime
from app.schemas.api import (
    HandoffResponse,
    SessionCreateRequest,
    SessionResponse,
    SourceRef,
    TextTurnRequest,
    TextTurnResponse,
)
from app.schemas.events import ASREvent, VADEvent
from app.security.guardrails import GuardrailsService
from app.security.telemetry import get_logger
from app.voice_agent.factory import build_cascade, voice_pipeline_status
from speech.contracts import (
    ASREvent as SpeechASREvent,
    SpeechError as SpeechPipelineError,
    VADEvent as SpeechVADEvent,
    VADEventType as SpeechVADEventType,
)

logger = get_logger("api_main")

session_manager = SessionManager()
guardrails = GuardrailsService()
runtime: KnowledgeRuntime = build_demo_runtime()
store: TurnStore = SqlAlchemyTurnStore(AsyncSessionLocal)

llm_adapter = OpenRouterAdapter(
    api_key=os.getenv("OPENROUTER_API_KEY", ""),
    allowed_models=["meta-llama/llama-3-8b-instruct"]
)

dialog_orchestrator = DialogOrchestrator(
    session_manager, llm_adapter, guardrails, runtime.retriever, store
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await store.ensure_tenants(runtime.tenants)
    except Exception as exc:  # noqa: BLE001 - best-effort startup, never swallow BaseException
        logger.error("ensure_tenants_failed", error_class=exc.__class__.__name__)
    yield


app = FastAPI(title="MTS Voice Agent API", version="1.0", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Заменить на APP_PUBLIC_ORIGIN из .env для продакшена
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health/live", tags=["Health"])
async def liveness():
    """Проверка доступности процесса."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
async def readiness():
    """Retriever must resolve demo tenants. Postgres is reported but does not block ready."""
    probe = await runtime.probe()
    retriever_ok = bool(runtime.tenants) and all(value == "ok" for value in probe.values())
    postgres = "unavailable"
    try:
        async with asyncio.timeout(1.0):
            postgres = "ok" if await store.ping() else "unavailable"
    except Exception:  # noqa: BLE001 - postgres is informational and must not block ready
        postgres = "unavailable"
    checks = {
        "retriever": "ok" if retriever_ok else "unavailable",
        "postgres": postgres,
        "voice": voice_pipeline_status(),
    }
    body = {"status": "ready" if retriever_ok else "not_ready", "checks": checks}
    if retriever_ok:
        return body
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body)


@app.post("/api/v1/sessions", response_model=SessionResponse, tags=["Sessions"])
@limiter.limit("5/minute")
async def create_session(request: Request, req: SessionCreateRequest):
    """Инициализация новой сессии вызова с ограничением частоты[cite: 6]."""
    if req.tenant_id not in runtime.tenants:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant_not_available",
        )

    session_id = str(uuid.uuid4())
    session_manager.transition(session_id, SessionState.CREATED)
    session_manager.bind(
        session_id,
        SessionBinding(tenant_id=req.tenant_id, language=req.language, channel=req.channel),
    )

    try:
        await store.create_session(session_id, req.tenant_id, req.channel, req.language)
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort
        logger.error("session_persist_failed", error_class=exc.__class__.__name__)

    logger.info("session_created", session_id=session_id, tenant_id=req.tenant_id)

    return SessionResponse(
        session_id=session_id,
        status=SessionState.CREATED,
        created_at=datetime.now(UTC)
    )


@app.post(
    "/api/v1/sessions/{session_id}/turns/text",
    response_model=TextTurnResponse,
    tags=["Sessions"],
)
@limiter.limit("5/minute")
async def text_turn(request: Request, session_id: str, body: TextTurnRequest):
    binding = session_manager.get_binding(session_id)
    if (
        binding is None
        or session_manager.active_sessions.get(session_id) in (None, SessionState.CLOSED)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    try:
        outcome = await dialog_orchestrator.run_turn(
            session_id, body.text, channel=binding.channel
        )
    except UnknownSessionError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return TextTurnResponse(
        session_id=outcome.session_id,
        turn_id=outcome.turn_id,
        answer_text=outcome.answer_text,
        answer_status=outcome.answer_status,
        citation_ids=outcome.citation_ids,
        sources=[SourceRef(**source) for source in outcome.sources],
        fallback_reason=outcome.fallback_reason,
        evidence_status=outcome.evidence_status,
        index_revision=outcome.index_revision,
    )


@app.post("/api/v1/sessions/{session_id}/end", tags=["Sessions"])
async def end_session(session_id: str):
    """Принудительное завершение сессии и отмена активных задач."""
    if session_id not in session_manager.active_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session_manager.transition(session_id, SessionState.CLOSED)
    if session_id in session_manager.active_turns:
        session_manager.active_turns[session_id].cancel()
    session_manager.unbind(session_id)

    logger.info("session_ended", session_id=session_id)
    return {"message": "Session terminated"}


async def send_tts_stream(websocket: WebSocket, session_id: str, asr_text: str):
    """Фоновая задача потоковой отправки аудиочанков в сокет.

    Чанки пейсятся по темпу воспроизведения (как делает реальный медиамост):
    иначе тестовый канал получает весь ответ мгновенно и перебить его
    невозможно. При отмене задачи (barge-in) отправка прекращается на
    ближайшем await.
    """
    try:
        stream = dialog_orchestrator.stream_final_asr(session_id, asr_text)
        try:
            async for tts_event in stream:
                context = session_manager.active_turns.get(session_id)
                if context is not None and context.is_cancelled:
                    break
                if (
                    tts_event.generation_id
                    and context is not None
                    and tts_event.generation_id != context.turn_id
                ):
                    continue
                await websocket.send_json({
                    "type": "TTSChunkEvent",
                    "payload": tts_event.model_dump()
                })
                if tts_event.audio_base64 and not tts_event.is_last_chunk:
                    pcm_bytes = len(tts_event.audio_base64) * 3 // 4
                    sample_rate = tts_event.sample_rate or 24000
                    audio_seconds = pcm_bytes / 2 / sample_rate
                    await asyncio.sleep(max(0.0, min(audio_seconds, 2.0)))
        finally:
            # Явно закрываем генератор в этом же контексте: при отмене (barge-in)
            # сборщик мусора иначе финализирует его в чужом контексте и
            # OTel-трейсинг сыплет "Failed to detach context".
            await stream.aclose()
    except asyncio.CancelledError:
        logger.info("tts_stream_task_cancelled", session_id=session_id)
    except Exception as e:  # noqa: BLE001 - keep the websocket loop alive
        logger.error("tts_stream_error", error_class=e.__class__.__name__, session_id=session_id)


async def _safe_send_json(websocket: WebSocket, payload: dict) -> None:
    """Отправляет JSON-событие, если сокет ещё жив."""
    try:
        await websocket.send_json(payload)
    except (RuntimeError, WebSocketDisconnect):
        pass


@app.websocket("/api/v1/ws/sessions/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Точка входа для потокового аудио и событий.

    Текстовые сообщения — JSON-события (ASREvent/VADEvent/InterruptionEvent).
    Бинарные сообщения — PCM16-LE mono @16 kHz: идут в наш речевой каскад
    (VAD -> T-one -> оркестратор -> TTS), см. docs/STAGE1_SPEECH_E2E.md.
    """
    await websocket.accept()
    binding = session_manager.get_binding(session_id)
    if binding is None:
        await websocket.close(code=1008)
        return

    session_manager.transition(session_id, SessionState.CONNECTING)

    generation_task: asyncio.Task | None = None
    speech = None

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
            # Звонящий перебивает агента: отменяем генерацию и чистим аудио.
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
        speech = build_cascade(session_id, on_vad=on_vad, on_asr=on_asr)
    except Exception as exc:  # noqa: BLE001 - keep JSON WS path even if PCM cascade fails
        logger.error(
            "speech_pipeline_unavailable",
            session_id=session_id,
            error_class=exc.__class__.__name__,
        )
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
                        logger.error(
                            "audio_feed_failed",
                            session_id=session_id,
                            error_class=exc.__class__.__name__,
                        )
                continue

            raw_data = message.get("text")
            if raw_data is None:
                continue
            try:
                data = json.loads(raw_data)
                event_type = data.get("type")

                if event_type == "ASREvent":
                    asr_event = ASREvent(**data["payload"])
                    if asr_event.is_final:
                        session_manager.transition(session_id, SessionState.TRANSCRIBING_FINAL)
                        logger.info("asr_final_received", session_id=session_id, turn_id=asr_event.turn_id)

                        await stop_generation()
                        generation_task = asyncio.create_task(
                            send_tts_stream(websocket, session_id, asr_event.text)
                        )

                elif event_type == "VADEvent":
                    vad_event = VADEvent(**data["payload"])
                    new_state = SessionState.LISTENING if vad_event.is_speech else SessionState.ENDPOINT_PENDING
                    session_manager.transition(session_id, new_state)

                elif event_type == "InterruptionEvent":
                    interrupted = session_manager.active_turns.get(session_id)
                    session_manager.handle_barge_in(session_id)
                    await stop_generation()
                    logger.info("barge_in_triggered", session_id=session_id)
                    await _safe_send_json(websocket, {
                        "type": "InterruptionEvent",
                        "payload": {
                            "session_id": session_id,
                            "interrupted_turn_id": interrupted.turn_id if interrupted else "",
                            "timestamp_ms": data.get("payload", {}).get("timestamp_ms", 0),
                        },
                    })

            except json.JSONDecodeError:
                logger.warning("invalid_json_received", session_id=session_id)
            except Exception as e:  # noqa: BLE001 - skip a bad frame, keep the socket
                logger.error(
                    "ws_validation_error",
                    session_id=session_id,
                    error_class=e.__class__.__name__,
                )

    except WebSocketDisconnect:
        logger.info("ws_disconnected", session_id=session_id)
    finally:
        if speech is not None:
            try:
                await speech.close()
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "speech_cascade_close_failed",
                    session_id=session_id,
                    error_class=e.__class__.__name__,
                )
        await stop_generation()
        session_manager.transition(session_id, SessionState.CLOSED)


@app.post("/api/v1/sessions/{session_id}/handoff/human", response_model=HandoffResponse, tags=["Sessions"])
async def handoff_to_human(session_id: str):
    """Перевод сессии на живого оператора (SIP-трансфер)[cite: 7]."""
    if session_id not in session_manager.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session_manager.transition(session_id, SessionState.HUMAN_HANDOFF)

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

    session_manager.transition(session_id, SessionState.CHAT_HANDOFF)

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
