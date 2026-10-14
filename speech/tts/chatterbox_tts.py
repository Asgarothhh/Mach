"""Streaming TTS adapter for Chatterbox Multilingual (Resemble AI, MIT).

Why it is a candidate to replace Silero RU (see ``LICENSES.md``):

* **MIT license** for code and weights — commercial use allowed;
* 23 languages including Russian (``language_id="ru"``);
* V3 multilingual checkpoint: improved speaker similarity, fewer
  hallucinations; a built-in default voice is used when no reference clip is
  passed (no voice-rights questions for the demo), and an optional
  ``audio_prompt_path`` conditions the timbre on a reference clip;
* every output is watermarked by Resemble's PerTh (responsible-AI feature).

Trade-offs recorded for the benchmark: an autoregressive 0.5B model needs a
GPU for comfortable latency; the output rate is 24 kHz (telephony 8 kHz needs
downstream resampling); no manual stress/intonation control.

The adapter follows the same contract as the Silero one (SSOT §5.7).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np
from pydantic import BaseModel, Field

from speech.contracts import (
    CancellationToken,
    ErrorCode,
    SpeechError,
    TTSChunk,
    TTSRequest,
)
from speech.tts._streaming import SegmentEngine, synthesize_segments
from speech.tts.preprocess import TextPreprocessor

__all__ = ["ChatterboxTTSAdapter", "ChatterboxTTSConfig"]

NATIVE_SAMPLE_RATE = 24000


class ChatterboxTTSConfig(BaseModel):
    """Adapter configuration for the Chatterbox multilingual engine."""

    language_id: str = Field(default="ru", description="Chatterbox language code")
    t3_model: str = Field(default="v3", description="Multilingual checkpoint: v3 (default) or v2")
    device: str = Field(default="auto", description="auto | cuda | cpu")
    exaggeration: float = Field(default=0.5, ge=0.0)
    cfg_weight: float = Field(default=0.5, ge=0.0)
    audio_prompt_path: str | None = Field(
        default=None,
        description="Optional reference clip conditioning the voice; None uses the built-in voice",
    )
    sample_rate: int = Field(default=NATIVE_SAMPLE_RATE, gt=0)
    max_chunk_ms: int = Field(default=120, gt=0)


def _generate_kwargs(cfg: ChatterboxTTSConfig) -> dict[str, object]:
    """Model kwargs for one ``generate`` call (kept separate for unit tests)."""
    kwargs: dict[str, object] = {
        "language_id": cfg.language_id,
        "exaggeration": cfg.exaggeration,
        "cfg_weight": cfg.cfg_weight,
    }
    if cfg.audio_prompt_path:
        kwargs["audio_prompt_path"] = cfg.audio_prompt_path
    return kwargs


class ChatterboxTTSAdapter:
    """Phrase-segmented streaming TTS on top of a Chatterbox engine."""

    def __init__(
        self,
        engine: SegmentEngine,
        config: ChatterboxTTSConfig | None = None,
        preprocessor: TextPreprocessor | None = None,
    ) -> None:
        self._engine = engine
        self.config = config or ChatterboxTTSConfig()
        self._preprocessor = preprocessor

    @classmethod
    def from_pretrained(
        cls,
        config: ChatterboxTTSConfig | None = None,
        preprocessor: TextPreprocessor | None = None,
    ) -> ChatterboxTTSAdapter:
        cfg = config or ChatterboxTTSConfig()
        return cls(_ChatterboxEngine(cfg), cfg, preprocessor)

    async def synthesize(
        self, request: TTSRequest, cancel: CancellationToken
    ) -> AsyncIterator[TTSChunk]:
        if request.sample_rate is not None and request.sample_rate != NATIVE_SAMPLE_RATE:
            raise SpeechError(
                ErrorCode.INVALID_AUDIO,
                "Chatterbox produces "
                f"{NATIVE_SAMPLE_RATE} Hz only; requested {request.sample_rate} Hz. "
                "Resample downstream for telephony.",
            )
        if request.speaker is not None and request.speaker != "default":
            raise SpeechError(
                ErrorCode.INVALID_AUDIO,
                "Chatterbox uses its built-in default voice; "
                f"request.speaker={request.speaker!r} is not supported",
            )
        async for chunk in synthesize_segments(
            self._engine,
            request,
            cancel,
            max_chunk_ms=self.config.max_chunk_ms,
            default_speaker="default",
            default_sample_rate=NATIVE_SAMPLE_RATE,
            supports_question_intonation=False,
            preprocessor=self._preprocessor,
        ):
            yield chunk


class _ChatterboxEngine:
    """Wraps ``chatterbox.mtl_tts.ChatterboxMultilingualTTS`` (lazy import)."""

    def __init__(self, cfg: ChatterboxTTSConfig) -> None:
        try:
            import torch
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        except ImportError as exc:  # pragma: no cover - depends on env
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                "chatterbox-tts is required; install with `pip install chatterbox-tts`",
            ) from exc

        device = cfg.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._cfg = cfg
        self._torch = torch
        self._device = device
        try:
            self._model = ChatterboxMultilingualTTS.from_pretrained(
                device=device, t3_model=cfg.t3_model
            )
        except TypeError:
            # Older pip releases (0.1.x) have no ``t3_model`` parameter.
            self._model = ChatterboxMultilingualTTS.from_pretrained(device=device)

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray:
        # ``speaker``/``sample_rate`` are fixed by the model (built-in default
        # voice, 24 kHz): documented above, enforced by the adapter.
        with self._torch.no_grad():
            wav = self._model.generate(text, **_generate_kwargs(self._cfg))
        if hasattr(wav, "detach"):
            wav = wav.detach().cpu().numpy()
        return np.asarray(wav, dtype=np.float32).reshape(-1)
