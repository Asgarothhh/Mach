"""Streaming TTS adapter for Silero v5 Russian voices.

Model choice / license status — see ``LICENSES.md`` and
``config/models.lock.yaml``:

* ``v5_5_ru`` / ``v5_4_ru`` support question intonation (``*слово*`` marks the
  intonation center, habr.com/ru/articles/1015942) plus automatic stress and
  homographs, and run on CPU; they are published under **CC BY-NC-SA 4.0** and
  are therefore allowed for the demo stand only until a commercial license
  decision is recorded;
* the MIT-licensed fallback is ``v5_cis_base_nostress`` (``ru_*`` speakers)
  which needs explicit stress markup — combine it with
  :class:`speech.tts.preprocess.SileroStressPreprocessor` (``stress=True``).

Contract (SSOT §5.7): audio chunks carry chunk/segment/generation IDs so the
orchestrator can drop chunks of cancelled generations; the first chunk of a
request reports ``first_chunk_ms`` for the latency budget.
"""

from __future__ import annotations

import logging
import wave
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
from speech.tts.preprocess import SileroStressPreprocessor, TextPreprocessor

__all__ = ["SileroTTSAdapter", "SileroTTSConfig", "TTSEngine"]

logger = logging.getLogger(__name__)


# Backwards-compatible name for the engine protocol used by tests.
TTSEngine = SegmentEngine


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

    def __init__(
        self,
        engine: SegmentEngine,
        config: SileroTTSConfig | None = None,
        preprocessor: TextPreprocessor | None = None,
    ) -> None:
        self._engine = engine
        self.config = config or SileroTTSConfig()
        self._preprocessor = preprocessor

    # -- construction -----------------------------------------------------

    @classmethod
    def from_pretrained(
        cls,
        config: SileroTTSConfig | None = None,
        model_path: str | Path | None = None,
        *,
        stress: bool = False,
    ) -> SileroTTSAdapter:
        """Build an adapter.

        ``model_path`` points to a pinned ``torch.package`` weight file
        (download with ``scripts/fetch_models.py``) — the preferred mode for
        demo/production: no surprise downloads at start (SSOT §12.1).

        ``stress=True`` enables :class:`SileroStressPreprocessor` (silero-stress,
        MIT) — required by MIT-licensed ``v5_cis_base*`` models for Russian.
        """
        cfg = config or SileroTTSConfig()
        if model_path is not None:
            engine: SegmentEngine = _PackagedSileroEngine(cfg, Path(model_path))
        else:
            engine = _PipSileroEngine(cfg)
        preprocessor = SileroStressPreprocessor.from_pretrained() if stress else None
        return cls(engine, cfg, preprocessor)

    # -- streaming synthesis ----------------------------------------------

    async def synthesize(
        self, request: TTSRequest, cancel: CancellationToken
    ) -> AsyncIterator[TTSChunk]:
        async for chunk in synthesize_segments(
            self._engine,
            request,
            cancel,
            max_chunk_ms=self.config.max_chunk_ms,
            default_speaker=self.config.speaker,
            default_sample_rate=self.config.sample_rate,
            supports_question_intonation=self.config.supports_question_intonation,
            preprocessor=self._preprocessor,
        ):
            yield chunk


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
        previous_threads = torch.get_num_threads()
        self._model = torch.package.PackageImporter(str(model_path)).load_pickle(
            "tts_models", "model"
        )
        self._model.to(torch.device("cpu"))
        # IMPORTANT: the packaged Silero model calls torch.set_num_threads(1)
        # during import. Left as-is it silently throttles every other torch
        # engine in the process (measured: Kokoro RTF 0.21 -> 0.75). Restore
        # the process-wide value right after the load.
        torch.set_num_threads(previous_threads)
        # v5_5_ru restores single-threading on *every* apply_tts call, so keep
        # the desired value and re-apply it after each synthesis as well.
        self._preferred_threads = previous_threads
        symbols = getattr(self._model, "symbols", None)
        self._allowed_symbols: set[str] | None = (
            set(symbols) if symbols is not None else None
        )
        self._warned_leftovers: set[str] = set()

    def _warn_unsupported(self, text: str) -> None:
        """Warn once per character about symbols the Silero frontend drops.

        The model lowercases text internally, so the check is case-insensitive.
        """
        if self._allowed_symbols is None:
            return
        leftovers = {
            char
            for char in text
            if char.lower() not in self._allowed_symbols and not char.isspace()
        } - self._warned_leftovers
        if leftovers:
            self._warned_leftovers |= leftovers
            logger.warning(
                "Silero frontend will drop unsupported characters: %s",
                " ".join(sorted(leftovers)),
            )

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray:
        self._warn_unsupported(text)
        kwargs = {"text": text, "speaker": speaker, "sample_rate": sample_rate}
        apply_tts = getattr(self._model, "apply_tts", None)
        try:
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
                return _to_numpy(_save_wav_fallback(self._model, kwargs))
        finally:
            # The Silero frontend sets torch threads to 1 inside its calls;
            # restore so other torch engines in the process are not throttled.
            self._torch.set_num_threads(self._preferred_threads)


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
        previous_threads = torch.get_num_threads()
        self._model, _ = silero_tts(language="ru", speaker=cfg.model_id)
        self._model.to(torch.device("cpu"))
        # See _PackagedSileroEngine: the Silero code sets torch threads to 1.
        torch.set_num_threads(previous_threads)
        self._preferred_threads = previous_threads

    def synthesize(self, text: str, *, speaker: str, sample_rate: int) -> np.ndarray:
        try:
            with self._torch.no_grad():
                audio = self._model.apply_tts(
                    text=text,
                    speaker=speaker,
                    sample_rate=sample_rate,
                    put_accent=self._cfg.put_accent,
                    put_yo=self._cfg.put_yo,
                )
            return _to_numpy(audio)
        finally:
            self._torch.set_num_threads(self._preferred_threads)


def _save_wav_fallback(model: object, kwargs: dict) -> np.ndarray:
    """Fallback for packaged models without ``apply_tts``: save_wav + read back."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "segment.wav"
        model.save_wav(**kwargs, audio_path=str(path))  # type: ignore[attr-defined]
        with wave.open(str(path), "rb") as fh:
            raw = fh.readframes(fh.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0
