from __future__ import annotations

from app.voice_agent.worker import ready_ok, refresh_checks, reset_checks_for_tests
from speech.contracts import ErrorCode, SpeechError
from speech.vad.energy import energy_probability
from speech.vad.silero_vad import SileroVADAdapter, VADConfig


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


def test_live_warmup_failure_is_unavailable(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "live")
    monkeypatch.setenv("VOICE_TTS_MODE", "real")

    def boom(*args, **kwargs):
        raise SpeechError(ErrorCode.MODEL_UNAVAILABLE, "weights missing")

    monkeypatch.setattr("app.voice_agent.factory.build_recognizer", boom)
    monkeypatch.setattr("app.voice_agent.factory.get_tts_adapter_for_mode", boom)
    monkeypatch.setattr(
        "speech.vad.silero_vad.SileroVADAdapter.from_pretrained", boom
    )
    reset_checks_for_tests()
    from app.voice_agent.factory import warmup_live_adapters

    adapters = warmup_live_adapters()
    assert adapters["asr"] == "unavailable"
    assert adapters["tts"] == "unavailable"
    checks = refresh_checks()
    assert checks["asr"] == "unavailable"
    assert checks["tts"] == "unavailable"
    assert ready_ok(checks) is False


def test_refresh_checks_does_not_reload_vad_after_success(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "live")
    monkeypatch.setenv("VOICE_TTS_MODE", "real")
    calls = {"vad": 0}

    def fake_from_pretrained(config=None):
        calls["vad"] += 1
        return SileroVADAdapter(energy_probability, config or VADConfig())

    monkeypatch.setattr(
        "speech.vad.silero_vad.SileroVADAdapter.from_pretrained",
        fake_from_pretrained,
    )
    monkeypatch.setattr(
        "app.voice_agent.factory.build_recognizer", lambda: object()
    )
    monkeypatch.setattr(
        "app.voice_agent.factory.get_tts_adapter_for_mode", lambda: object()
    )
    reset_checks_for_tests()
    first = refresh_checks()
    assert first["asr"] == "ok"
    assert first["tts"] == "ok"
    assert ready_ok(first) is True
    second = refresh_checks()
    assert second["asr"] == "ok"
    assert calls["vad"] == 1
