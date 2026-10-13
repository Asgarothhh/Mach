#!/usr/bin/env python3
"""Smoke for the web test console path (page equivalent, no browser needed).

Repeats exactly what ``apps/voice_console`` does in the browser:

1. ``POST /session`` on the console (which creates the call session via the
   API and persists the demo Tenant/Session rows);
2. open ``/api/v1/ws/sessions/{id}`` (works both locally and through the VPS
   Caddy proxy);
3. send one text turn as a JSON ``ASREvent`` (the page's "send as text" path);
4. collect ``TTSChunkEvent``s: expect real audio chunks, the phrase ``text``
   field and the ``is_last_chunk`` marker.

Usage:
    .venv/bin/python scripts/voice_console_check.py \
        --url https://voice.194-146-38-78.sslip.io

Exit code 0 = console path healthy.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
import uuid


async def run(url: str, text: str, timeout: float, tenant: str | None = None) -> int:
    import httpx
    import websockets

    session_path = "session"
    if tenant:
        session_path += f"?tenant={tenant}"
    async with httpx.AsyncClient(base_url=url, timeout=20.0) as client:
        response = await client.post(session_path)
        response.raise_for_status()
        session_id = response.json()["session_id"]
    print(f"session: {session_id}")

    asr_event = {
        "type": "ASREvent",
        "payload": {
            "session_id": session_id,
            "turn_id": str(uuid.uuid4()),
            "timestamp_ms": int(time.time() * 1000),
            "revision": 0,
            "text": text,
            "is_final": True,
            "language": "ru",
        },
    }

    ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/api/v1/ws/sessions/{session_id}"

    chunks = 0
    answer_text: list[str] = []
    finished = False
    deadline = time.monotonic() + timeout

    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(json.dumps(asr_event, ensure_ascii=False))
        while time.monotonic() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
            if isinstance(raw, (bytes, bytearray)):
                continue
            message = json.loads(raw)
            payload = message.get("payload", {}) or {}
            if message.get("type") != "TTSChunkEvent":
                continue
            if payload.get("audio_base64"):
                chunks += 1
                base64.b64decode(payload["audio_base64"])  # decode sanity
            if payload.get("text") and payload["text"] not in answer_text:
                answer_text.append(payload["text"])
            if payload.get("is_last_chunk"):
                finished = True
                break

    passed = chunks > 0 and finished and answer_text
    print(f"TTS-чанков с аудио: {chunks}")
    print(f"текст ответа: {' '.join(answer_text)!r}")
    if passed:
        print("CONSOLE PATH OK: session -> WS -> text turn -> real TTS audio")
        return 0
    print("CONSOLE PATH FAILED", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://100.64.0.4:8124", help="console base URL")
    parser.add_argument("--tenant", default="mts-public-demo", help="demo tenant (fixtures)")
    parser.add_argument(
        "--text",
        default="сколько стоят входящие звонки в турции",
        help="text turn to send",
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    return asyncio.run(run(args.url, args.text, args.timeout, args.tenant))


if __name__ == "__main__":
    raise SystemExit(main())
