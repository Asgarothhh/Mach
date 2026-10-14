from __future__ import annotations

import uuid

from speech.contracts import ErrorCode, SpeechError
from tests.conftest import ACME_SUFFICIENT_QUERY


def _create_session(client, tenant_id: str = "acme-it-demo") -> str:
    response = client.post(
        "/api/v1/sessions",
        json={"tenant_id": tenant_id, "channel": "webrtc", "language": "ru"},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def _drain_tts(websocket, *, limit: int = 20) -> list[dict]:
    chunks = []
    for _ in range(limit):
        message = websocket.receive_json()
        chunks.append(message)
        if message["type"] == "TTSChunkEvent" and message["payload"].get("is_last_chunk"):
            break
    return chunks


def test_ws_stays_up_when_build_cascade_fails(api_client, monkeypatch):
    def boom(*args, **kwargs):
        raise SpeechError(ErrorCode.MODEL_UNAVAILABLE, "weights missing")

    monkeypatch.setattr("app.api.main.build_cascade", boom)
    session_id = _create_session(api_client)
    with api_client.websocket_connect(f"/api/v1/ws/sessions/{session_id}") as websocket:
        error = websocket.receive_json()
        assert error["type"] == "SpeechError"
        assert error["payload"] == {
            "code": "model_unavailable",
            "session_id": session_id,
        }
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


def test_ws_feed_error_is_degraded_not_fatal(api_client, monkeypatch):
    class BoomCascade:
        current_turn_id = ""
        feeds = 0
        closes = 0

        async def feed(self, pcm):
            type(self).feeds += 1
            raise SpeechError(ErrorCode.MODEL_UNAVAILABLE, "asr down")

        async def close(self):
            type(self).closes += 1

    BoomCascade.feeds = 0
    BoomCascade.closes = 0
    monkeypatch.setattr("app.api.main.build_cascade", lambda *a, **k: BoomCascade())
    session_id = _create_session(api_client)
    with api_client.websocket_connect(f"/api/v1/ws/sessions/{session_id}") as websocket:
        websocket.send_bytes(b"\x00\x00")
        error = websocket.receive_json()
        assert error["type"] == "SpeechError"
        assert error["payload"]["code"] == "model_unavailable"
        assert error["payload"]["session_id"] == session_id
        websocket.send_bytes(b"\x00\x00")
        websocket.send_bytes(b"\x00\x00")
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
