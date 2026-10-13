"""Voice-agent process: honest health for ASR/TTS/LiveKit (SSOT §12.4).

The speech cascade still runs inside the API process. This worker reports
readiness of the intended voice adapters and does not pretend LiveKit is up.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.voice_agent.factory import warmup_live_adapters

HOST = os.getenv("VOICE_AGENT_HOST", "0.0.0.0")
PORT = int(os.getenv("VOICE_AGENT_PORT", "8100"))

_checks: dict[str, str] = {
    "asr": "unavailable",
    "tts": "unavailable",
    "livekit": "not_configured",
    "llm_policy": "mock",
}


def _llm_policy() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if key and key != "your_test_key_here":
        return "openrouter"
    return "mock"


def refresh_checks() -> dict[str, str]:
    adapters = warmup_live_adapters()
    _checks.update(adapters)
    _checks["livekit"] = "not_configured"
    _checks["llm_policy"] = _llm_policy()
    return dict(_checks)


def ready_ok(checks: dict[str, str]) -> bool:
    asr_ok = checks.get("asr") in {"ok", "mock"}
    tts_ok = checks.get("tts") in {"ok", "mock"}
    return asr_ok and tts_ok


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health/live":
            self._write(200, {"status": "ok"})
            return
        if self.path.rstrip("/") == "/health/ready":
            checks = refresh_checks()
            if ready_ok(checks):
                self._write(200, {"status": "ready", "checks": checks})
            else:
                self._write(503, {"status": "not_ready", "checks": checks})
            return
        self._write(404, {"status": "not_found"})


def main() -> None:
    refresh_checks()
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    print(f"Voice agent health listening on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
