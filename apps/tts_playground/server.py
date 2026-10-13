#!/usr/bin/env python3
"""TTS playground: type a phrase, pick an engine/voice, get audio.

Team-facing demo/testing tool for the ML track. Runs on the demo machine
(GPU/CPU); the public URL is provided by the VPS Caddy reverse proxy over
Tailscale (see demo/vps-showcase/README.md). NOT part of the call path, does
not touch any PII, and does not log synthesized text.

Models are built lazily on the first request for a given engine and cached;
the first request may take tens of seconds (weights load/download).

Usage:
    .venv/bin/python apps/tts_playground/server.py --host 100.64.0.4 --port 8077
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import time
import wave
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from speech.contracts import CancellationToken, SpeechError, TTSRequest

logger = logging.getLogger("tts_playground")

MAX_TEXT_CHARS = 300
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_S = 60.0

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "models" / "tts"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# ru_* voices of the MIT-licensed Silero v5_cis_base_nostress weights.
# Team shortlist (2026-10-13): only Ekaterina, Saida and Bogdan are kept for
# evaluation; the rest of the 29 ru_* voices stay available in the model file
# but are not offered in the playground / A-B page.
SILERO_CIS_VOICES: list[str] = [
    "ru_ekaterina",
    "ru_saida",
    "ru_bogdan",
]


# ---------------------------------------------------------------------------
# Engine registry
# ---------------------------------------------------------------------------


@dataclass
class EngineDef:
    key: str
    title: str
    license: str
    commercial: str  # yes | no | conditional
    voices: list[str]
    sample_rate: int
    build: Callable[[str], Any]
    note: str = ""


def _build_silero_v5(voice: str) -> Any:
    from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

    cfg = SileroTTSConfig(
        model_id="v5_5_ru",
        speaker=voice,
        sample_rate=48000,
        supports_question_intonation=True,
    )
    return SileroTTSAdapter.from_pretrained(cfg, model_path=MODELS_DIR / "v5_5_ru.pt")


def _build_silero_mit(voice: str) -> Any:
    from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

    cfg = SileroTTSConfig(
        model_id="v5_cis_base_nostress",
        speaker=voice,
        sample_rate=24000,
        supports_question_intonation=False,
    )
    return SileroTTSAdapter.from_pretrained(
        cfg, model_path=MODELS_DIR / "v5_cis_base_nostress.pt", stress=True
    )


def _build_kokoro(voice: str) -> Any:
    from speech.tts.kokoro_tts import KokoroRuTTSAdapter, KokoroRuTTSConfig

    return KokoroRuTTSAdapter.from_pretrained(KokoroRuTTSConfig(voice=voice))


def _build_chatterbox(voice: str) -> Any:
    from speech.tts.chatterbox_tts import ChatterboxTTSAdapter, ChatterboxTTSConfig

    return ChatterboxTTSAdapter.from_pretrained(
        ChatterboxTTSConfig(language_id="ru", t3_model="v3", device="auto")
    )


ENGINES: dict[str, EngineDef] = {
    "silero-mit": EngineDef(
        key="silero-mit",
        title="Silero CIS-base MIT + silero-stress (рекомендованный кандидат)",
        license="MIT (веса) + MIT (silero-stress)",
        commercial="yes",
        voices=SILERO_CIS_VOICES,
        sample_rate=24000,
        build=_build_silero_mit,
        note="Та же семья Silero, автоматические ударения и омографы. 8/24/48 кГц, CPU.",
    ),
    "silero-v5": EngineDef(
        key="silero-v5",
        title="Silero v5.5 RU (демо-эталон качества)",
        license="CC BY-NC-SA 4.0 — только демо/оценка",
        commercial="no",
        voices=["xenia", "baya", "kseniya", "aidar", "eugene"],
        sample_rate=48000,
        build=_build_silero_v5,
        note=(
            "Есть интонация вопросов (отмечайте центр звёздочками: *Вы* звоните?). "
            "Не для production."
        ),
    ),
    "kokoro-ru": EngineDef(
        key="kokoro-ru",
        title="Kokoro-82M RU (sveta / masha / dima)",
        license="OpenRAIL (веса); GPL-3.0 в цепочке G2P — см. LICENSES.md",
        commercial="conditional",
        voices=["sveta", "masha", "dima"],
        sample_rate=24000,
        build=_build_kokoro,
        note="Лучшая разборчивость в тестах (WER 0.016), CPU, но первый чанк медленнее.",
    ),
    "chatterbox": EngineDef(
        key="chatterbox",
        title="Chatterbox Multilingual V3 (MIT, GPU)",
        license="MIT",
        commercial="yes",
        voices=["default"],
        sample_rate=24000,
        build=_build_chatterbox,
        note="В тестах: может галлюцинировать на русском, первый чанк ~1.9 с. Экспериментальный.",
    ),
}

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

_adapters: dict[tuple[str, str], Any] = {}
_build_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_synth_lock = asyncio.Lock()  # serialize synthesis: heavy on CPU/GPU
_hits: dict[str, deque[float]] = defaultdict(deque)

app = FastAPI(title="TTS Playground", docs_url=None, redoc_url=None)


class SynthRequest(BaseModel):
    engine: str
    voice: str
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


def _check_rate_limit(client: str) -> None:
    now = time.monotonic()
    queue = _hits[client]
    while queue and now - queue[0] > RATE_LIMIT_WINDOW_S:
        queue.popleft()
    if len(queue) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(429, detail="Слишком много запросов, попробуйте через минуту")
    queue.append(now)


async def _get_adapter(engine: EngineDef, voice: str) -> Any:
    cache_key = (engine.key, voice)
    adapter = _adapters.get(cache_key)
    if adapter is not None:
        return adapter
    async with _build_locks[engine.key]:
        adapter = _adapters.get(cache_key)
        if adapter is None:
            logger.info("building engine %s voice %s (first use)", engine.key, voice)
            try:
                adapter = await asyncio.to_thread(engine.build, voice)
            except SpeechError as exc:
                raise HTTPException(
                    503, detail=f"Движок недоступен: {exc.code.value}"
                ) from exc
            except Exception as exc:  # noqa: BLE001
                logger.exception("engine build failed")
                raise HTTPException(
                    503, detail=f"Не удалось загрузить движок: {type(exc).__name__}"
                ) from exc
            _adapters[cache_key] = adapter
            await _warmup(adapter)
    return adapter


async def _warmup(adapter: Any) -> None:
    """Run one throwaway synthesis so the user's first request is warm."""
    request = TTSRequest(
        session_id="warmup",
        turn_id="warmup",
        generation_id="warmup",
        segments=["Проверка."],
    )
    try:
        async with _synth_lock:
            async for _ in adapter.synthesize(request, CancellationToken()):
                pass
    except Exception:  # noqa: BLE001 - a warm-up failure must not break the build
        logger.exception("warm-up failed")


def _to_wav(pcm_s16le: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(pcm_s16le)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "engines": list(ENGINES),
        "loaded": [f"{key}:{voice}" for key, voice in _adapters],
    }


@app.get("/api/engines")
async def engines() -> list[dict[str, Any]]:
    return [
        {
            "key": engine.key,
            "title": engine.title,
            "license": engine.license,
            "commercial": engine.commercial,
            "voices": engine.voices,
            "sample_rate": engine.sample_rate,
            "note": engine.note,
        }
        for engine in ENGINES.values()
    ]


@app.post("/api/synthesize")
async def synthesize(payload: SynthRequest, request: Request) -> Response:
    client = request.client.host if request.client else "unknown"
    _check_rate_limit(client)

    engine = ENGINES.get(payload.engine)
    if engine is None:
        raise HTTPException(404, detail="Неизвестный движок")
    if payload.voice not in engine.voices:
        raise HTTPException(400, detail="Неизвестный голос для этого движка")
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, detail="Пустой текст")

    adapter = await _get_adapter(engine, payload.voice)

    request_id = str(time.time_ns())
    tts_request = TTSRequest(
        session_id="playground",
        turn_id=request_id,
        generation_id=request_id,
        segments=[text],
    )
    started = time.perf_counter()
    pcm = bytearray()
    sample_rate = engine.sample_rate
    first_chunk_ms: float | None = None
    try:
        async with _synth_lock:
            async for chunk in adapter.synthesize(tts_request, CancellationToken()):
                if chunk.is_first_chunk:
                    first_chunk_ms = chunk.first_chunk_ms
                pcm.extend(chunk.pcm_s16le)
                sample_rate = chunk.sample_rate
    except SpeechError as exc:
        raise HTTPException(503, detail=f"{exc.code.value}: {exc.message}") from exc

    total_ms = (time.perf_counter() - started) * 1000.0
    if not pcm:
        raise HTTPException(500, detail="Синтез не дал аудио")
    audio_ms = len(pcm) / 2 / max(1, sample_rate) * 1000.0

    logger.info(
        "synth engine=%s voice=%s chars=%d first_chunk=%s total=%.0fms rtf=%.3f",
        engine.key,
        payload.voice,
        len(text),
        f"{first_chunk_ms:.0f}ms" if first_chunk_ms is not None else "n/a",
        total_ms,
        total_ms / audio_ms if audio_ms else 0.0,
    )
    headers = {
        "X-TTS-First-Chunk-Ms": f"{first_chunk_ms:.0f}" if first_chunk_ms is not None else "",
        "X-TTS-Total-Ms": f"{total_ms:.0f}",
        "X-TTS-Audio-Ms": f"{audio_ms:.0f}",
        "X-TTS-Rtf": f"{total_ms / audio_ms:.3f}" if audio_ms else "",
    }
    return Response(
        content=_to_wav(bytes(pcm), sample_rate), media_type="audio/wav", headers=headers
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8077)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
