from __future__ import annotations

from app.voice_agent.worker import ready_ok, refresh_checks


def test_mock_mode_ready(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "mock")
    monkeypatch.setenv("VOICE_TTS_MODE", "mock")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    checks = refresh_checks()
    assert checks["asr"] == "mock"
    assert checks["tts"] == "mock"
    assert checks["livekit"] == "not_configured"
    assert checks["llm_policy"] == "mock"
    assert ready_ok(checks) is True


def test_livekit_never_pretends_ready(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "mock")
    monkeypatch.setenv("VOICE_TTS_MODE", "mock")
    checks = refresh_checks()
    assert checks["livekit"] == "not_configured"


def test_ready_ok_requires_asr_and_tts():
    assert ready_ok({"asr": "unavailable", "tts": "mock"}) is False
    assert ready_ok({"asr": "mock", "tts": "unavailable"}) is False
    assert ready_ok({"asr": "ok", "tts": "ok"}) is True
