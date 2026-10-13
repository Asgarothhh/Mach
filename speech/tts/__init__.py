"""TTS adapters (ML)."""

from speech.tts.chatterbox_tts import ChatterboxTTSAdapter, ChatterboxTTSConfig
from speech.tts.kokoro_tts import KokoroRuTTSAdapter, KokoroRuTTSConfig
from speech.tts.preprocess import SileroStressPreprocessor, TextPreprocessor
from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig, TTSEngine

__all__ = [
    "ChatterboxTTSAdapter",
    "ChatterboxTTSConfig",
    "KokoroRuTTSAdapter",
    "KokoroRuTTSConfig",
    "SileroStressPreprocessor",
    "SileroTTSAdapter",
    "SileroTTSConfig",
    "TTSEngine",
    "TextPreprocessor",
]
