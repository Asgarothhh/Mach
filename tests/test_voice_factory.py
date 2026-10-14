from __future__ import annotations

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


def test_live_status_does_not_instantiate_engines(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "live")
    monkeypatch.setenv("VOICE_TTS_MODE", "real")
    from app.voice_agent import factory

    assert factory.voice_pipeline_status() == "live"
    assert "torch" not in sys.modules
    assert "onnx_asr" not in sys.modules


def test_build_cascade_raises_when_live_fails(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "live")
    from app.voice_agent import factory
    from app.voice_agent.factory import reset_live_vad_for_tests

    def boom(config=None):
        raise SpeechError(ErrorCode.MODEL_UNAVAILABLE, "no weights")

    monkeypatch.setattr("speech.vad.silero_vad.SileroVADAdapter.from_pretrained", boom)
    reset_live_vad_for_tests()
    with pytest.raises(SpeechError) as excinfo:
        factory.build_cascade("s1", on_vad=lambda _: None, on_asr=lambda _: None)
    assert excinfo.value.code is ErrorCode.MODEL_UNAVAILABLE


def test_live_tts_missing_model_raises(monkeypatch):
    monkeypatch.setenv("VOICE_TTS_MODE", "real")
    from app.voice_agent import factory

    def boom():
        raise SpeechError(ErrorCode.MODEL_UNAVAILABLE, "no tts weights")

    monkeypatch.setattr("app.voice_agent.tts.get_tts_adapter", boom)
    with pytest.raises(SpeechError) as excinfo:
        factory.get_tts_adapter_for_mode()
    assert excinfo.value.code is ErrorCode.MODEL_UNAVAILABLE


def test_live_missing_model_raises(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "live")
    from app.voice_agent import factory
    from app.voice_agent.factory import reset_live_vad_for_tests

    def boom(config=None):
        raise SpeechError(ErrorCode.MODEL_UNAVAILABLE, "no weights")

    monkeypatch.setattr("speech.vad.silero_vad.SileroVADAdapter.from_pretrained", boom)
    reset_live_vad_for_tests()
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


def test_live_vad_fork_does_not_share_model_state(monkeypatch):
    monkeypatch.setenv("VOICE_ASR_MODE", "live")
    from app.voice_agent import factory
    from app.voice_agent.factory import reset_live_vad_for_tests

    class _NoGrad:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _TorchStub:
        def no_grad(self):
            return _NoGrad()

        def from_numpy(self, frame):
            return frame

    monkeypatch.setitem(sys.modules, "torch", _TorchStub())

    class CounterModel:
        def __init__(self, n: int = 0) -> None:
            self.n = n

        def __call__(self, tensor, sample_rate: int):
            del tensor, sample_rate
            self.n += 1
            return float(self.n)

        def reset_states(self) -> None:
            return None

    def fake_from_pretrained(config=None):
        return SileroVADAdapter.from_loaded_model(CounterModel(), config)

    monkeypatch.setattr(SileroVADAdapter, "from_pretrained", fake_from_pretrained)
    reset_live_vad_for_tests()
    first = factory.build_vad()
    second = factory.build_vad()
    import numpy as np

    frame = np.zeros(512, dtype=np.float32)
    assert first._speech_probability(frame, 16000) == 1.0
    assert second._speech_probability(frame, 16000) == 1.0
    assert first._speech_probability(frame, 16000) == 2.0
    assert first is not second
