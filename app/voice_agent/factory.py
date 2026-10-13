"""Runtime selection of VAD/ASR/TTS adapters (mock vs live).

Default is mock so the API process starts without torch, onnx-asr, or weights.
Live mode is opt-in via ``VOICE_ASR_MODE=live`` / ``VOICE_TTS_MODE=real``.
"""

from __future__ import annotations

import os
from typing import Literal

from speech.asr.scripted import ScriptedRecognizer
from speech.contracts import ErrorCode, SpeechError, TTSAdapter
from speech.tts.mock_tts import MockTTSAdapter
from speech.vad.energy import energy_probability
from speech.vad.silero_vad import SileroVADAdapter, VADConfig

VoiceMode = Literal["mock", "live"]

__all__ = [
    "asr_mode",
    "build_cascade",
    "build_recognizer",
    "build_vad",
    "get_tts_adapter_for_mode",
    "tts_mode",
    "voice_pipeline_status",
    "warmup_live_adapters",
]


def asr_mode() -> VoiceMode:
    raw = os.getenv("VOICE_ASR_MODE", "mock").strip().lower()
    return "live" if raw in {"live", "real"} else "mock"


def tts_mode() -> VoiceMode:
    raw = os.getenv("VOICE_TTS_MODE", "mock").strip().lower()
    if raw in {"live", "real"}:
        return "live"
    return "mock"


def voice_pipeline_status() -> str:
    """Label for ``/health/ready``: intended mode, not a model-load probe."""
    if asr_mode() == "live" or tts_mode() == "live":
        return "live"
    return "mock"


def build_vad() -> SileroVADAdapter:
    if asr_mode() == "live":
        try:
            return SileroVADAdapter.from_pretrained(
                VADConfig(sample_rate=16000, prefix_padding_ms=400)
            )
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001 - typed failure for the WS loop
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE, f"live VAD unavailable: {exc}"
            ) from exc
    return SileroVADAdapter(
        energy_probability,
        VADConfig(sample_rate=16000, prefix_padding_ms=400),
    )


def build_recognizer() -> object:
    if asr_mode() == "live":
        try:
            from app.voice_agent.asr import get_recognizer

            return get_recognizer()
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE, f"live ASR unavailable: {exc}"
            ) from exc
    return ScriptedRecognizer()


def get_tts_adapter_for_mode() -> TTSAdapter:
    if tts_mode() == "live":
        try:
            from app.voice_agent.tts import get_tts_adapter

            return get_tts_adapter()
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE, f"live TTS unavailable: {exc}"
            ) from exc
    return MockTTSAdapter()


def build_cascade(session_id: str, *, on_vad, on_asr):
    """Construct a cascade with injected adapters. Never imports torch in mock mode."""
    try:
        from app.voice_agent.speech_cascade import SpeechCascade

        return SpeechCascade(
            session_id,
            on_vad=on_vad,
            on_asr=on_asr,
            vad_adapter=build_vad(),
            recognizer=build_recognizer(),
        )
    except SpeechError:
        raise
    except Exception as exc:  # noqa: BLE001 - WS must stay up
        raise SpeechError(
            ErrorCode.MODEL_UNAVAILABLE, f"speech cascade unavailable: {exc}"
        ) from exc


def warmup_live_adapters() -> dict[str, str]:
    """Best-effort probe used by the voice-agent health worker."""
    checks = {"asr": "unavailable", "tts": "unavailable"}
    if asr_mode() == "mock":
        checks["asr"] = "mock"
    else:
        try:
            build_recognizer()
            build_vad()
            checks["asr"] = "ok"
        except SpeechError:
            checks["asr"] = "unavailable"
    if tts_mode() == "mock":
        checks["tts"] = "mock"
    else:
        try:
            get_tts_adapter_for_mode()
            checks["tts"] = "ok"
        except SpeechError:
            checks["tts"] = "unavailable"
    return checks
