#!/usr/bin/env python3
"""Stage-1 E2E smoke: wav "call" -> audio over WS -> VAD -> T-one -> the
orchestrator (guardrails + mock retrieval + mock LLM) -> real Silero TTS -> audio
back; then a barge-in check with a second wav.

The API must be already running (see docs/STAGE1_SPEECH_E2E.md):

    ENVIRONMENT=demo \
    DATABASE_URL=postgresql+asyncpg://admin:123789@127.0.0.1:55432/voice_agent \
    .venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8123

Then run this script with the same DATABASE_URL:

    DATABASE_URL=... .venv/bin/python scripts/stage1_e2e_smoke.py

Acceptance assertions (Stage-1 gate):
    * first wav -> a final ASREvent with non-empty text;
    * the answer arrives as real audio chunks (TTSChunkEvent, PCM base64);
    * a second wav sent while the answer is playing triggers an
      InterruptionEvent, and NO chunks of the interrupted generation arrive
      after it;
    * the barge-in utterance is recognized and answered with a new generation
      that completes (is_last_chunk).

Evidence: artifacts/stage1_e2e/events.jsonl + answer wavs.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import os
import sys
import time
import wave
from pathlib import Path

import httpx
import numpy as np
import soxr
import websockets

SAMPLE_RATE = 16000
CHUNK_MS = 100
TENANT_ID = os.getenv("VOICE_TENANT_ID", "acme-it-demo")

DEFAULT_WAV1 = "artifacts/asr_benchmark/audio/synthetic-telephony/synth_00_8k.wav"
DEFAULT_WAV2 = "artifacts/asr_benchmark/audio/synthetic-telephony/synth_01_8k.wav"


def read_wav_16k_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as fh:
        rate = fh.getframerate()
        channels = fh.getnchannels()
        raw = fh.readframes(fh.getnframes())
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        audio = soxr.resample(audio, rate, SAMPLE_RATE, quality="HQ")
    return (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(pcm)


def silence_16k(seconds: float) -> bytes:
    """PCM16 silence @16 kHz (what a live channel would stream between words)."""
    return bytes(int(SAMPLE_RATE * seconds) * 2)


async def ensure_schema() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.database import Base

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def ensure_session_row(session_id: str, tenant_id: str) -> None:
    """Insert the Tenant/Session rows the dialog flow's Turn FK needs.

    Note: POST /api/v1/sessions only keeps sessions in memory today; persisting
    them is a backend TODO. The smoke creates the rows explicitly.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.database import Session, Tenant

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        if await db.get(Tenant, tenant_id) is None:
            db.add(Tenant(tenant_id=tenant_id, display_name="Stage-1 E2E tenant"))
        if await db.get(Session, session_id) is None:
            db.add(Session(session_id=session_id, tenant_id=tenant_id, channel="stage1-e2e"))
        await db.commit()
    await engine.dispose()


async def stream_pcm(ws, pcm: bytes, *, chunk_ms: int = CHUNK_MS, realtime: bool = True) -> None:
    step = SAMPLE_RATE * 2 * chunk_ms // 1000
    for offset in range(0, len(pcm), step):
        await ws.send(pcm[offset : offset + step])
        if realtime:
            await asyncio.sleep(chunk_ms / 1000)


async def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav1 = read_wav_16k_pcm(Path(args.wav1))
    wav2 = read_wav_16k_pcm(Path(args.wav2))

    await ensure_schema()
    async with httpx.AsyncClient(base_url=args.api, timeout=15.0) as client:
        response = await client.post(
            "/api/v1/sessions", json={"tenant_id": TENANT_ID, "channel": "stage1-e2e"}
        )
        response.raise_for_status()
        session_id = response.json()["session_id"]
    await ensure_session_row(session_id, TENANT_ID)
    print(f"session: {session_id}")

    # -- shared state filled by the reader ------------------------------------
    meta = {
        "gen1": None,
        "gen2": None,
        "completed": set(),
        "interrupted_at": None,
        "last_event_at": {},
    }
    audio_parts: dict[str, bytearray] = {}
    audio_rates: dict[str, int] = {}
    asr_finals: list[tuple[float, str, str]] = []
    chunk_times: dict[str, list[float]] = {}
    answer_started = asyncio.Event()
    answer2_done = asyncio.Event()
    log_path = out_dir / "events.jsonl"
    log_file = log_path.open("w", encoding="utf-8")

    ws_url = args.api.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/v1/ws/sessions/{session_id}"

    async def reader(ws) -> None:
        async for raw in ws:
            if isinstance(raw, (bytes, bytearray)):
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            now = time.monotonic()
            payload = message.get("payload", {}) or {}
            event_type = message.get("type")
            meta["last_event_at"][event_type] = now

            logged = dict(payload)
            if logged.get("audio_base64"):
                logged["audio_base64"] = f"<{len(logged['audio_base64'])} b64 chars>"
            log_file.write(
                json.dumps(
                    {"ts": round(now, 4), "type": event_type, "payload": logged},
                    ensure_ascii=False,
                )
                + "\n"
            )
            log_file.flush()

            if event_type == "ASREvent":
                text = payload.get("text", "")
                asr_finals.append((now, payload.get("turn_id", ""), text))
                print(f"[ASR] {text!r}")
            elif event_type == "TTSChunkEvent":
                generation = payload.get("generation_id") or payload.get("turn_id") or "?"
                audio_b64 = payload.get("audio_base64") or ""
                if audio_b64:
                    audio_parts.setdefault(generation, bytearray()).extend(
                        base64.b64decode(audio_b64)
                    )
                    audio_rates[generation] = int(payload.get("sample_rate") or 24000)
                    chunk_times.setdefault(generation, []).append(now)
                    if meta["gen1"] is None:
                        meta["gen1"] = generation
                        answer_started.set()
                if payload.get("fallback_text"):
                    print(f"[TTS FALLBACK] {payload['fallback_text']!r}")
                if payload.get("is_last_chunk"):
                    meta["completed"].add(generation)
                    if generation != meta["gen1"] and meta["gen1"] is not None:
                        meta["gen2"] = generation
                        answer2_done.set()
            elif event_type == "InterruptionEvent":
                meta["interrupted_at"] = now
                print("[BARGE-IN] interruption event received")

    async with websockets.connect(ws_url, max_size=None) as ws:
        reader_task = asyncio.create_task(reader(ws))

        # Phase 1: the caller says the first phrase (real channels stream
        # silence between utterances; send a tail so VAD can endpoint).
        print("streaming wav #1 (caller asks) ...")
        await stream_pcm(ws, wav1)
        await stream_pcm(ws, silence_16k(1.0))
        await asyncio.wait_for(answer_started.wait(), timeout=args.timeout)
        print("answer started; waiting 0.3 s and interrupting ...")
        await asyncio.sleep(0.3)

        # Phase 2: barge-in - the caller talks over the agent.
        interrupted_before = meta["interrupted_at"]
        t_send2 = time.monotonic()
        await stream_pcm(ws, wav2)
        await stream_pcm(ws, silence_16k(1.0))
        await asyncio.wait_for(answer2_done.wait(), timeout=args.timeout)
        await asyncio.sleep(0.5)
        reader_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader_task

    log_file.close()

    # -- assertions -----------------------------------------------------------
    failures: list[str] = []

    if not asr_finals:
        failures.append("no ASR final events at all")
    first_asr_text = asr_finals[0][2] if asr_finals else ""
    if len(first_asr_text) < 5:
        failures.append(f"first ASR text too short: {first_asr_text!r}")

    gen1 = meta["gen1"]
    if not gen1:
        failures.append("no TTS audio arrived for the first answer")
    if gen1 and len(audio_parts.get(gen1, b"")) == 0:
        failures.append("first generation produced no audio bytes")

    if meta["interrupted_at"] is None:
        failures.append("barge-in did not produce an InterruptionEvent")
    else:
        if interrupted_before is not None:
            failures.append("interruption arrived before the second wav was sent")
        late_gen1 = [
            t for t in chunk_times.get(gen1 or "", []) if t > meta["interrupted_at"] + 0.05
        ]
        if late_gen1:
            failures.append(
                f"{len(late_gen1)} chunks of the interrupted generation arrived after the barge-in"
            )

    gen2 = meta["gen2"]
    if not gen2:
        failures.append("the barge-in utterance was not answered with a new generation")
    elif len(audio_parts.get(gen2, b"")) == 0:
        failures.append("second generation produced no audio bytes")

    second_asr = [text for ts, _, text in asr_finals if ts >= t_send2]
    if not second_asr:
        failures.append("no ASR final for the barge-in utterance")

    # -- artifacts ------------------------------------------------------------
    for index, (generation, data) in enumerate(
        sorted(audio_parts.items(), key=lambda kv: chunk_times.get(kv[0], [0])[0]), start=1
    ):
        path = out_dir / f"answer_{index}_{generation[:8]}.wav"
        write_wav(path, bytes(data), audio_rates.get(generation, 24000))
        print(f"saved {path} ({len(data) / 2 / audio_rates.get(generation, 24000):.2f} s)")
    print(f"events log: {log_path}")
    print(f"ASR finals: {[t for _, _, t in asr_finals]}")

    if failures:
        print("\nSMOKE FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nSMOKE PASSED: call -> ASR -> audio answer -> barge-in cancellation -> new answer")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8123")
    parser.add_argument("--wav1", default=DEFAULT_WAV1)
    parser.add_argument("--wav2", default=DEFAULT_WAV2)
    parser.add_argument("--out", default="artifacts/stage1_e2e")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is required (same value the API runs with)", file=sys.stderr)
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
