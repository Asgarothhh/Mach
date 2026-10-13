from __future__ import annotations

import importlib.util
import sys

import pytest

from speech.asr.scripted import ScriptedRecognizer
from speech.contracts import ErrorCode, SpeechError
from speech.tts.mock_tts import MockTTSAdapter
from speech.vad.silero_vad import SileroVADAdapter


def test_modes_default_to_mock(monkeypatch):
    monkeypatch.delenv("VOICE_ASR_MODE", raising=False)
    monkeypatch.delenv("VOICE_TTS_MODE", raising=False)
    from app.voice_agent import factory

    assert factory.asr_mode() == "mock"
    assert factory.tts_mode() == "mock"
    assert factory.voice_pipeline_status() == "mock"


def test_off_maps_to_mock_tts(monkeypatch):
    monkeypatch.setenv("VOICE_TTS_MODE", "off")
    from app.voice_agent import factory

    assert factory.tts_mode() == "mock"


def test_build_mock_adapters_without_torch(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "mock")
    monkeypatch.setenv("VOICE_TTS_MODE", "mock")
    from app.voice_agent import factory

    vad = factory.build_vad()
    recognizer = factory.build_recognizer()
    tts = factory.get_tts_adapter_for_mode()
    assert isinstance(vad, SileroVADAdapter)
    assert isinstance(recognizer, ScriptedRecognizer)
    assert isinstance(tts, MockTTSAdapter)
    assert "torch" not in sys.modules
    assert "onnx_asr" not in sys.modules
    assert "silero_vad" not in sys.modules


def test_api_import_does_not_load_torch():
    import app.api.main  # noqa: F401

    assert "torch" not in sys.modules
    assert "onnx_asr" not in sys.modules


@pytest.mark.skipif(
    importlib.util.find_spec("silero_vad") is not None,
    reason="live Silero VAD is installed in this environment",
)
def test_live_missing_model_raises(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "live")
    from app.voice_agent import factory

    with pytest.raises(SpeechError) as excinfo:
        factory.build_vad()
    assert excinfo.value.code is ErrorCode.MODEL_UNAVAILABLE


def test_live_vad_wraps_unexpected_errors(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "live")
    from app.voice_agent import factory

    def boom(config=None):
        raise OSError("weights missing")

    monkeypatch.setattr("speech.vad.silero_vad.SileroVADAdapter.from_pretrained", boom)
    with pytest.raises(SpeechError) as excinfo:
        factory.build_vad()
    assert excinfo.value.code is ErrorCode.MODEL_UNAVAILABLE
