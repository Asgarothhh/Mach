from __future__ import annotations

import base64
import uuid

import numpy as np

from speech.audio import float32_to_pcm16
from tests.conftest import ACME_SUFFICIENT_QUERY

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512


def _create_session(client, tenant_id: str = "acme-it-demo") -> str:
    response = client.post(
        "/api/v1/sessions",
        json={"tenant_id": tenant_id, "channel": "webrtc", "language": "ru"},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def _frame(amplitude: float) -> bytes:
    if amplitude == 0:
        samples = np.zeros(FRAME_SAMPLES, dtype=np.float32)
    else:
        samples = (
            amplitude * np.sin(np.linspace(0, 8 * np.pi, FRAME_SAMPLES))
        ).astype(np.float32)
    return float32_to_pcm16(samples)


def _drain_tts(websocket, *, limit: int = 20) -> list[dict]:
    chunks = []
    for _ in range(limit):
        message = websocket.receive_json()
        if message["type"] != "TTSChunkEvent":
            chunks.append(message)
            continue
        chunks.append(message)
        if message["payload"].get("is_last_chunk"):
            break
    return chunks


def test_json_asr_yields_pcm_tts_with_generation_id(api_client):
    session_id = _create_session(api_client)
    with api_client.websocket_connect(f"/api/v1/ws/sessions/{session_id}") as websocket:
        websocket.send_json(
            {
                "type": "ASREvent",
                "payload": {
                    "session_id": session_id,
                    "turn_id": str(uuid.uuid4()),
                    "timestamp_ms": 1,
                    "revision": 1,
                    "text": ACME_SUFFICIENT_QUERY,
                    "is_final": True,
                    "language": "ru",
                },
            }
        )
        messages = _drain_tts(websocket)
        tts = [item for item in messages if item["type"] == "TTSChunkEvent"]
        assert tts
        assert tts[-1]["payload"]["is_last_chunk"] is True
        audio = [item for item in tts if item["payload"]["audio_base64"]]
        assert audio
        first = audio[0]["payload"]
        assert first["generation_id"] == first["turn_id"]
        assert first["sample_rate"] == 24000
        pcm = base64.b64decode(first["audio_base64"])
        assert len(pcm) % 2 == 0
        assert len(pcm) > 0


def test_second_json_asr_cancels_previous_generation(api_client):
    session_id = _create_session(api_client)
    with api_client.websocket_connect(f"/api/v1/ws/sessions/{session_id}") as websocket:
        websocket.send_json(
            {
                "type": "ASREvent",
                "payload": {
                    "session_id": session_id,
                    "turn_id": "turn-a",
                    "timestamp_ms": 1,
                    "revision": 1,
                    "text": ACME_SUFFICIENT_QUERY,
                    "is_final": True,
                    "language": "ru",
                },
            }
        )
        first = websocket.receive_json()
        assert first["type"] == "TTSChunkEvent"
        old_gen = first["payload"]["generation_id"]
        websocket.send_json(
            {
                "type": "ASREvent",
                "payload": {
                    "session_id": session_id,
                    "turn_id": "turn-b",
                    "timestamp_ms": 2,
                    "revision": 1,
                    "text": ACME_SUFFICIENT_QUERY,
                    "is_final": True,
                    "language": "ru",
                },
            }
        )
        seen_new = False
        stale_after_new = []
        for _ in range(30):
            message = websocket.receive_json()
            if message["type"] != "TTSChunkEvent":
                continue
            gen = message["payload"]["generation_id"]
            if gen != old_gen:
                seen_new = True
            elif seen_new:
                stale_after_new.append(gen)
            if seen_new and message["payload"].get("is_last_chunk"):
                break
        assert seen_new
        assert stale_after_new == []


def test_pcm_mock_cascade_and_barge_in(api_client, monkeypatch):
    monkeypatch.setenv("VOICE_MOCK_ASR_TEXT", ACME_SUFFICIENT_QUERY)
    session_id = _create_session(api_client)
    with api_client.websocket_connect(f"/api/v1/ws/sessions/{session_id}") as websocket:
        websocket.send_json(
            {
                "type": "ASREvent",
                "payload": {
                    "session_id": session_id,
                    "turn_id": str(uuid.uuid4()),
                    "timestamp_ms": 1,
                    "revision": 1,
                    "text": ACME_SUFFICIENT_QUERY,
                    "is_final": True,
                    "language": "ru",
                },
            }
        )
        first = websocket.receive_json()
        assert first["type"] == "TTSChunkEvent"
        old_gen = first["payload"]["generation_id"]

        for _ in range(12):
            websocket.send_bytes(_frame(0.4))
        for _ in range(16):
            websocket.send_bytes(_frame(0.0))

        got_interrupt = False
        stale_after = []
        new_gen = None
        for _ in range(40):
            message = websocket.receive_json()
            kind = message["type"]
            if kind == "InterruptionEvent":
                got_interrupt = True
                continue
            if kind == "TTSChunkEvent":
                gen = message["payload"]["generation_id"]
                if got_interrupt and gen == old_gen:
                    stale_after.append(gen)
                if got_interrupt and gen != old_gen:
                    new_gen = gen
                if new_gen and message["payload"].get("is_last_chunk"):
                    break
        assert got_interrupt
        assert stale_after == []
