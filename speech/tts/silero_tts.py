"""Streaming TTS adapter for Silero v5 Russian voices.

Model choice / license status — see ``LICENSES.md`` and
``config/models.lock.yaml``:

* ``v5_5_ru`` / ``v5_4_ru`` support question intonation (``*слово*`` marks the
  intonation center, habr.com/ru/articles/1015942) plus automatic stress and
  homographs, and run on CPU; they are published under **CC BY-NC-SA 4.0** and
  are therefore allowed for the demo stand only until a commercial license
  decision is recorded;
* the MIT-licensed fallback is ``v5_cis_base_nostress`` (``ru_*`` speakers)
  which needs explicit stress markup.

Contract (SSOT §5.7): audio chunks carry chunk/segment/generation IDs so the
orchestrator can drop chunks of cancelled generations; the first chunk of a
request reports ``first_chunk_ms`` for the latency budget.
"""

from __future__ import annotations

import asyncio
import time
import wave
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel, Field

from speech.audio import float32_to_pcm16, iter_pcm16_chunks
from speech.contracts import (
    CancellationToken,
    ErrorCode,
    SpeechError,
    TTSChunk,
    TTSRequest,
)
from speech.text_norm import normalize_for_tts

__all__ = ["SileroTTSAdapter", "SileroTTSConfig", "TTSEngine"]


@runtime_checkable
class TTSEngine(Protocol):
    """Synchronous synthesis backend producing mono float32 audio in [-1; 1]."""

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray: ...


class SileroTTSConfig(BaseModel):
    """Adapter configuration. Values are pinned per deployment."""

    model_id: str = Field(default="v5_5_ru", description="Silero model id (models.yml)")
    speaker: str = "xenia"
    sample_rate: int = Field(
        default=24000, gt=0, description="8000 for telephony, 48000 for WebRTC"
    )
    supports_question_intonation: bool = True
    put_accent: bool = True
    put_yo: bool = True
    max_chunk_ms: int = Field(default=120, gt=0, description="Transport chunk granularity")


class SileroTTSAdapter:
    """Phrase-segmented streaming TTS on top of a Silero engine."""

    def __init__(self, engine: TTSEngine, config: SileroTTSConfig | None = None) -> None:
        self._engine = engine
        self.config = config or SileroTTSConfig()

    # -- construction -----------------------------------------------------

    @classmethod
    def from_pretrained(
        cls,
        config: SileroTTSConfig | None = None,
        model_path: str | Path | None = None,
    ) -> SileroTTSAdapter:
        """Build an adapter.

        ``model_path`` points to a pinned ``torch.package`` weight file
        (download with ``scripts/fetch_models.py``) — the preferred mode for
        demo/production: no surprise downloads at start (SSOT §12.1).
        Without it the ``silero`` pip package downloads the model on demand —
        dev convenience only.
        """
        cfg = config or SileroTTSConfig()
        if model_path is not None:
            engine: TTSEngine = _PackagedSileroEngine(cfg, Path(model_path))
        else:
            engine = _PipSileroEngine(cfg)
        return cls(engine, cfg)

    # -- streaming synthesis ----------------------------------------------

    async def synthesize(
        self, request: TTSRequest, cancel: CancellationToken
    ) -> AsyncIterator[TTSChunk]:
        cfg = self.config
        speaker = request.speaker or cfg.speaker
        sample_rate = request.sample_rate or cfg.sample_rate
        started = time.perf_counter()
        chunk_id = 0
        first_chunk_ms: float | None = None
        last_segment = len(request.segments) - 1

        for segment_id, raw_text in enumerate(request.segments):
            cancel.raise_if_cancelled()
            normalized = normalize_for_tts(
                raw_text, supports_question_intonation=cfg.supports_question_intonation
            )
            if not normalized.spoken:
                continue

            t0 = time.perf_counter()
            try:
                audio = await asyncio.to_thread(
                    self._engine.synthesize,
                    normalized.spoken,
                    speaker=speaker,
                    sample_rate=sample_rate,
                )
            except SpeechError:
                raise
            except Exception as exc:  # defensive: engine failure must be typed
                raise SpeechError(
                    ErrorCode.SYNTHESIS_FAILED, f"TTS engine failed: {exc}"
                ) from exc
            synthesis_ms = (time.perf_counter() - t0) * 1000.0

            pcm = float32_to_pcm16(np.asarray(audio, dtype=np.float32).reshape(-1))
            if len(pcm) == 0:
                raise SpeechError(ErrorCode.SYNTHESIS_FAILED, "TTS produced empty audio")

            chunks = list(
                iter_pcm16_chunks(pcm, sample_rate=sample_rate, chunk_ms=cfg.max_chunk_ms)
            )
            for index, chunk_pcm in enumerate(chunks):
                # Cancellation is checked between transport chunks; a segment
                # itself is short by design, so barge-in latency stays bounded.
                cancel.raise_if_cancelled()
                is_first = chunk_id == 0
                if is_first:
                    first_chunk_ms = (time.perf_counter() - started) * 1000.0
                yield TTSChunk(
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    generation_id=request.generation_id,
                    segment_id=segment_id,
                    chunk_id=chunk_id,
                    text=normalized.spoken,
                    pcm_s16le=chunk_pcm,
                    sample_rate=sample_rate,
                    is_first_chunk=is_first,
                    is_last_chunk=(segment_id == last_segment and index == len(chunks) - 1),
                    first_chunk_ms=first_chunk_ms if is_first else None,
                    synthesis_ms=synthesis_ms if index == 0 else None,
                )
                chunk_id += 1


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------


def _to_numpy(audio: object) -> np.ndarray:
    detach = getattr(audio, "detach", None)
    if callable(detach):  # torch.Tensor
        audio = detach().cpu().numpy()
    return np.asarray(audio, dtype=np.float32).reshape(-1)


class _PackagedSileroEngine:
    """Standalone engine: ``torch.package`` weights fetched by fetch_models.py."""

    def __init__(self, cfg: SileroTTSConfig, model_path: Path) -> None:
        if not model_path.is_file():
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                f"model file not found: {model_path} (run scripts/fetch_models.py)",
            )
        try:
            import torch
        except ImportError as exc:
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                "torch is required; install with `pip install -e .[tts]`",
            ) from exc
        self._torch = torch
        self._cfg = cfg
        self._model = torch.package.PackageImporter(str(model_path)).load_pickle(
            "tts_models", "model"
        )
        self._model.to(torch.device("cpu"))

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray:
        kwargs = {"text": text, "speaker": speaker, "sample_rate": sample_rate}
        apply_tts = getattr(self._model, "apply_tts", None)
        with self._torch.no_grad():
            if apply_tts is not None:
                try:
                    audio = apply_tts(
                        **kwargs,
                        put_accent=self._cfg.put_accent,
                        put_yo=self._cfg.put_yo,
                    )
                except TypeError:
                    audio = apply_tts(**kwargs)
                return _to_numpy(audio)
            return _to_numpy(_save_wav_fallback(self._model, self._torch, kwargs))


class _PipSileroEngine:
    """Dev engine backed by the ``silero`` pip package (downloads on demand)."""

    def __init__(self, cfg: SileroTTSConfig) -> None:
        try:
            import torch
            from silero import silero_tts
        except ImportError as exc:
            raise SpeechError(
                ErrorCode.MODEL_UNAVAILABLE,
                "torch and the `silero` pip package are required; "
                "install with `pip install -e .[tts]`",
            ) from exc
        self._torch = torch
        self._cfg = cfg
        self._model, _ = silero_tts(language="ru", speaker=cfg.model_id)
        self._model.to(torch.device("cpu"))

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray:
        with self._torch.no_grad():
            audio = self._model.apply_tts(
                text=text,
                speaker=speaker,
                sample_rate=sample_rate,
                put_accent=self._cfg.put_accent,
                put_yo=self._cfg.put_yo,
            )
        return _to_numpy(audio)


def _save_wav_fallback(model: object, torch_module: object, kwargs: dict) -> np.ndarray:
    """Fallback for packaged models without ``apply_tts``: save_wav + read back."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "segment.wav"
        model.save_wav(**kwargs, audio_path=str(path))  # type: ignore[attr-defined]
        with wave.open(str(path), "rb") as fh:
            raw = fh.readframes(fh.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0
