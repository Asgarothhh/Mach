"""Streaming TTS adapter for the Russian Kokoro-82M port (zaakirio/kokoro-ru).

License status (see ``LICENSES.md``): weights are **OpenRAIL**, the code is
Apache-2.0, the Russian G2P stack (``ru_g2p.py`` + RUAccent, MIT) resolves
stress, ё and homographs. Three fixed voices from consented studio actors
(``sveta``, ``masha``, ``dima``). Published numbers: RTF ~0.10 (9.8x realtime)
on a laptop CPU, Whisper round-trip WER 2.5% vs Piper 4.4% on the author's set.

This is the CPU/VPS-friendly candidate: no GPU required, 82M parameters, but
the prosody is deterministic (style vector is chosen by phoneme length) and the
timbre is darker than Silero.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

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

__all__ = ["KokoroRuTTSAdapter", "KokoroRuTTSConfig"]

NATIVE_SAMPLE_RATE = 24000
SUPPORTED_VOICES = ("sveta", "masha", "dima")


class KokoroRuTTSConfig(BaseModel):
    """Adapter configuration for the Kokoro-ru engine."""

    repo_id: str = "zaakirio/kokoro-ru"
    voice: str = Field(default="sveta", description="sveta | masha | dima")
    speed: float = Field(default=1.0, gt=0.0)
    sample_rate: int = Field(default=NATIVE_SAMPLE_RATE, gt=0)
    max_chunk_ms: int = Field(default=120, gt=0)
    assets_dir: str = Field(
        default="models/kokoro-ru-assets",
        description="Local dir for ru_g2p.py + acute-aware espeak-data (real files, not symlinks)",
    )


class KokoroRuTTSAdapter:
    """Phrase-segmented streaming TTS on top of the Kokoro-ru engine."""

    def __init__(
        self,
        engine: SegmentEngine,
        config: KokoroRuTTSConfig | None = None,
        preprocessor: TextPreprocessor | None = None,
    ) -> None:
        self._engine = engine
        self.config = config or KokoroRuTTSConfig()
        self._preprocessor = preprocessor

    @classmethod
    def from_pretrained(
        cls,
        config: KokoroRuTTSConfig | None = None,
        preprocessor: TextPreprocessor | None = None,
    ) -> KokoroRuTTSAdapter:
        cfg = config or KokoroRuTTSConfig()
        return cls(_KokoroRuEngine(cfg), cfg, preprocessor)

    async def synthesize(
        self, request: TTSRequest, cancel: CancellationToken
    ) -> AsyncIterator[TTSChunk]:
        if request.sample_rate is not None and request.sample_rate != NATIVE_SAMPLE_RATE:
            raise SpeechError(
                ErrorCode.INVALID_AUDIO,
                "Kokoro-ru produces "
                f"{NATIVE_SAMPLE_RATE} Hz only; requested {request.sample_rate} Hz. "
                "Resample downstream for telephony.",
            )
        if request.speaker is not None and request.speaker != self.config.voice:
            raise SpeechError(
                ErrorCode.INVALID_AUDIO,
                "one voice per engine instance: "
                f"requested {request.speaker!r}, config voice is {self.config.voice!r}",
            )
        async for chunk in synthesize_segments(
            self._engine,
            request,
            cancel,
            max_chunk_ms=self.config.max_chunk_ms,
            default_speaker=self.config.voice,
            default_sample_rate=NATIVE_SAMPLE_RATE,
            supports_question_intonation=False,
            preprocessor=self._preprocessor,
        ):
            yield chunk


class _KokoroRuEngine:
    """Wraps ``kokoro.KModel`` + ``ru_g2p.RuG2P`` (lazy imports)."""

    def __init__(self, cfg: KokoroRuTTSConfig) -> None:
        if cfg.voice not in SUPPORTED_VOICES:
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                f"unknown Kokoro-ru voice {cfg.voice!r}; expected one of {SUPPORTED_VOICES}",
            )
        try:
            import importlib.util
            import sys

            import torch
            from huggingface_hub import hf_hub_download, snapshot_download
            from kokoro import KModel
        except ImportError as exc:  # pragma: no cover - depends on env
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                "kokoro + huggingface_hub are required; install with `pip install kokoro`",
            ) from exc

        self._torch = torch
        self._cfg = cfg

        # Russian G2P lives next to the weights in the model repo and expects
        # its acute-aware espeak-data directory as a sibling file. Download with
        # ``local_dir`` so files are real (ru_g2p.py resolves assets via
        # ``Path(__file__).resolve().parent`` — symlinked snapshots break it).
        assets = snapshot_download(
            cfg.repo_id,
            allow_patterns=["ru_g2p.py", "espeak-data/**", "espeak-data/*", "kokoro-config.json"],
            local_dir=cfg.assets_dir,
        )
        g2p_path = Path(assets) / "ru_g2p.py"
        spec = importlib.util.spec_from_file_location("kokoro_ru_g2p", g2p_path)
        if spec is None or spec.loader is None:  # pragma: no cover
            raise SpeechError(ErrorCode.MODEL_UNAVAILABLE, f"cannot import {g2p_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["kokoro_ru_g2p"] = module
        spec.loader.exec_module(module)
        self._g2p = module.RuG2P()

        checkpoint = "kokoro-ru-v2-dima.pth" if cfg.voice == "dima" else "kokoro-ru-v2-base.pth"
        self._kmodel = KModel(
            repo_id=cfg.repo_id, model=hf_hub_download(cfg.repo_id, checkpoint)
        ).eval()
        self._pack = torch.load(
            hf_hub_download(cfg.repo_id, f"voices/{cfg.voice}.pt"),
            map_location="cpu",
            weights_only=False,
        )

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray:
        ipa, oov = self._g2p(text)
        if oov:
            raise SpeechError(
                ErrorCode.SYNTHESIS_FAILED, f"OOV phonemes for Kokoro vocab: {sorted(oov)}"
            )
        if len(ipa) >= 510:
            raise SpeechError(
                ErrorCode.SYNTHESIS_FAILED,
                "segment too long for the Kokoro style pack (>=510 phonemes); "
                "send shorter phrases",
            )
        with self._torch.no_grad():
            output = self._kmodel_output(ipa)
        return output

    def _kmodel_output(self, ipa: str) -> np.ndarray:
        result = self._kmodel(ipa, self._pack[len(ipa) - 1], self._cfg.speed, return_output=True)
        audio = getattr(result, "audio", result)
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        return np.asarray(audio, dtype=np.float32).reshape(-1)
