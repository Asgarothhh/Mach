"""TTS adapters (ML). Heavy engines are imported lazily."""

from __future__ import annotations

from typing import Any

__all__ = [
    "ChatterboxTTSAdapter",
    "ChatterboxTTSConfig",
    "KokoroRuTTSAdapter",
    "KokoroRuTTSConfig",
    "MockTTSAdapter",
    "SileroStressPreprocessor",
    "SileroTTSAdapter",
    "SileroTTSConfig",
    "TTSEngine",
    "TextPreprocessor",
]


def __getattr__(name: str) -> Any:
    if name in {"ChatterboxTTSAdapter", "ChatterboxTTSConfig"}:
        from speech.tts.chatterbox_tts import ChatterboxTTSAdapter, ChatterboxTTSConfig

        return ChatterboxTTSAdapter if name == "ChatterboxTTSAdapter" else ChatterboxTTSConfig
    if name in {"KokoroRuTTSAdapter", "KokoroRuTTSConfig"}:
        from speech.tts.kokoro_tts import KokoroRuTTSAdapter, KokoroRuTTSConfig

        return KokoroRuTTSAdapter if name == "KokoroRuTTSAdapter" else KokoroRuTTSConfig
    if name in {"SileroTTSAdapter", "SileroTTSConfig", "TTSEngine"}:
        from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig, TTSEngine

        return {"SileroTTSAdapter": SileroTTSAdapter, "SileroTTSConfig": SileroTTSConfig, "TTSEngine": TTSEngine}[name]
    if name in {"SileroStressPreprocessor", "TextPreprocessor"}:
        from speech.tts.preprocess import SileroStressPreprocessor, TextPreprocessor

        return SileroStressPreprocessor if name == "SileroStressPreprocessor" else TextPreprocessor
    if name == "MockTTSAdapter":
        from speech.tts.mock_tts import MockTTSAdapter

        return MockTTSAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
