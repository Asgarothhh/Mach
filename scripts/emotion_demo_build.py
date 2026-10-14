#!/usr/bin/env python3
"""Mascot-cube emotion atlas: demo audio builder (spec ``docs/SPEC_MASCOT_FACE.md`` v0.2).

For every emotion of the atlas (§6) the script renders one synthetic phrase twice:

* ``chatterbox`` — Chatterbox Multilingual V3 (MIT, GPU): *native* emotionality via
  the ``exaggeration`` parameter of ``speech/tts/chatterbox_tts.py``. Russian is
  upgraded by the same hooks the runtime uses: the RUAccent stress preprocessor
  (``speech/tts/preprocess.py``), a reference voice for timbre
  (``audio_prompt_path``) and a lower ``cfg_weight``. The model is reloaded every
  few samples because the upstream model is known to degrade over long serial
  runs (resemble-ai/chatterbox issue #360).
* ``silero``     — Silero v5_cis_base_nostress (MIT) + stress: *honest degradation*,
  no native emotion control, shaped only by the spec §9.3 prosody table.

On top of both engines the script applies the spec §9.3 prosody post-processing
(rate / pitch / gain) through ffmpeg's formant-preserving rubberband filter, so
the demo reflects the target directive without phase-vocoder damage (librosa
remains only as a no-ffmpeg fallback). It then renders a
self-contained HTML page (matching the other ``demo/vps-showcase`` pages): one
sample, switchable emotions with an animated cube and live lipsync driven by the
actual audio amplitude.

Outputs (git-ignored under ``artifacts/``)::

    artifacts/emotions_demo/audio/<emotion>__<engine>.wav
    artifacts/emotions_demo/voice_reference_ekaterina.wav
    artifacts/emotions_demo/report.json

Usage::

    .venv/bin/python scripts/emotion_demo_build.py \
        --html demo/vps-showcase/mascot-emotions.html \
        --html-audio-prefix mascot-emotions/audio
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import math
import platform
import shutil
import subprocess
import time
import wave
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np

from speech.contracts import CancellationToken, TTSRequest

PHRASE = "Добрый день! Я виртуальный ассистент компании. Чем я могу вам помочь?"
SPEC_REF = "docs/SPEC_MASCOT_FACE.md (v0.2) §6 атлас, §9.3 просодия"


@dataclass(frozen=True)
class Emotion:
    """One atlas row: presentation values + target prosody from the spec §9.3."""

    id: str
    ru: str
    rate: float
    pitch_pct: float
    gain: float
    exaggeration: float


# 14 emotions of the atlas, in the spec §9.3 order. ``exaggeration`` is only used
# by the Chatterbox engine; rate/pitch/gain are applied to every engine.
ATLAS: tuple[Emotion, ...] = (
    Emotion("neutral", "Спокойствие", 1.00, 0, 1.00, 0.35),
    Emotion("attentive", "Внимание", 1.00, 1, 1.00, 0.35),
    Emotion("curious", "Любопытство", 1.05, 3, 1.05, 0.50),
    Emotion("thinking", "Задумчивость", 0.95, -2, 1.00, 0.25),
    Emotion("speaking", "Речь", 1.00, 2, 1.05, 0.45),
    Emotion("joyful", "Радость", 1.05, 6, 1.10, 0.70),
    Emotion("surprised", "Удивление", 1.10, 10, 1.10, 0.80),
    Emotion("confused", "Непонимание", 0.95, 4, 1.00, 0.50),
    Emotion("skeptical", "Сомнение", 0.95, -2, 1.00, 0.40),
    Emotion("empathetic", "Сочувствие", 0.90, -3, 0.92, 0.40),
    Emotion("sad", "Грусть", 0.90, -5, 0.92, 0.50),
    Emotion("apologetic", "Сожаление", 0.92, -3, 0.92, 0.45),
    Emotion("relieved", "Облегчение", 0.95, -2, 1.00, 0.40),
    Emotion("angry", "Злость (демо, policy-off)", 1.10, 5, 1.10, 0.90),
)

ENGINE_TITLES = {
    "chatterbox": {
        "title": "Chatterbox Multilingual V3 (Resemble AI)",
        "short": "Chatterbox V3",
        "license": "MIT (код и веса)",
        "native_emotion": True,
        "badge": "нативно: exaggeration",
        "quality": "стресс ruaccent · референс тембра ru_ekaterina · cfg_weight 0.30 · перезагрузка модели каждые N сэмплов",
    },
    "silero": {
        "title": "Silero v5_cis_base_nostress + stress (голос ru_alexandr)",
        "short": "Silero MIT",
        "license": "MIT",
        "native_emotion": False,
        "badge": "деградация: только просодия",
        "quality": "голос ru_alexandr · silero-stress (ударения внутри модели)",
    },
}

# Voice-quality constants picked by the lab run (UTMOSv2 MOS + Whisper WER):
# reference voice MOS 3.59 vs 2.71 for the built-in default with default cfg.
CHATTERBOX_CFG_WEIGHT = 0.30
CHATTERBOX_REBUILD_EVERY = 4  # upstream model degrades on long serial runs (#360)
REFERENCE_VOICE = "ru_ekaterina"  # Silero MIT voice used to build the reference clip
SILERO_VOICE = "ru_alexandr"


# ---------------------------------------------------------------------------
# Synthesis (adapters from speech/tts) + spec prosody post-processing
# ---------------------------------------------------------------------------


async def collect_pcm(adapter: Any, text: str, turn_id: str) -> dict[str, Any]:
    """Run one phrase through a TTS adapter and return PCM + measured metrics."""
    request = TTSRequest(
        session_id="emotion-demo",
        turn_id=turn_id,
        generation_id="g0",
        segments=[text],
    )
    parts: list[bytes] = []
    sample_rate = 0
    first_chunk_ms: float | None = None
    started = time.perf_counter()
    async for chunk in adapter.synthesize(request, CancellationToken()):
        if chunk.is_first_chunk:
            first_chunk_ms = chunk.first_chunk_ms
        parts.append(chunk.pcm_s16le)
        sample_rate = chunk.sample_rate
    synth_ms = (time.perf_counter() - started) * 1000.0
    return {
        "pcm": b"".join(parts),
        "sample_rate": sample_rate,
        "first_chunk_ms": round(first_chunk_ms, 1) if first_chunk_ms is not None else None,
        "synth_ms": round(synth_ms, 1),
    }


def apply_prosody(pcm_s16le: bytes, sample_rate: int, emotion: Emotion) -> np.ndarray:
    """Spec §9.3 prosody (rate / pitch / gain) with a formant-preserving backend.

    ffmpeg's rubberband filter keeps speech natural at the ±10% deltas of the
    table; the librosa phase-vocoder fallback remains only for environments
    without ffmpeg — it audibly damages quality (UTMOS ~1.1 vs ~2.5).
    """
    audio = np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
    if emotion.rate == 1.0 and not emotion.pitch_pct and emotion.gain == 1.0:
        return audio
    if shutil.which("ffmpeg"):
        params = []
        if emotion.pitch_pct:
            params.append(f"pitch={1.0 + emotion.pitch_pct / 100.0}")
        if abs(emotion.rate - 1.0) > 1e-3:
            params.append(f"tempo={emotion.rate}")
        filters = []
        if params:
            filters.append(f"rubberband={':'.join(params)}:formant=preserved")
        if emotion.gain != 1.0:
            filters.append(f"volume={emotion.gain}")
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
            "-af", ",".join(filters),
            "-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "pipe:1",
        ]
        proc = subprocess.run(
            cmd, input=audio.astype(np.float32).tobytes(), capture_output=True, check=False
        )
        if proc.returncode == 0 and proc.stdout:
            out = np.frombuffer(proc.stdout, dtype="<f4").astype(np.float32)
            peak = float(np.max(np.abs(out))) if out.size else 0.0
            if peak > 0.98:
                out = out / peak * 0.98
            return out
        # any ffmpeg failure falls through to the librosa path below

    import librosa

    if emotion.pitch_pct:
        n_steps = 12.0 * math.log2(1.0 + emotion.pitch_pct / 100.0)
        audio = librosa.effects.pitch_shift(y=audio, sr=sample_rate, n_steps=n_steps)
    if abs(emotion.rate - 1.0) > 1e-3:
        audio = librosa.effects.time_stretch(y=np.ascontiguousarray(audio), rate=emotion.rate)
    audio = audio * emotion.gain
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.98:
        audio = audio / peak * 0.98
    return audio.astype(np.float32)


def write_wav(path: Path, audio_f32: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio_f32 * 32767.0, -32768.0, 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(pcm)


def build_engine(key: str, reference: Path | None = None) -> Any:
    """Instantiate one of the already-integrated adapters (no new code paths)."""
    if key == "chatterbox":
        from speech.tts.chatterbox_tts import ChatterboxTTSAdapter, ChatterboxTTSConfig
        from speech.tts.preprocess import RuAccentStressPreprocessor

        cfg = ChatterboxTTSConfig(
            language_id="ru",
            t3_model="v3",
            device="auto",
            cfg_weight=CHATTERBOX_CFG_WEIGHT,
            audio_prompt_path=str(reference) if reference else None,
        )
        preprocessor = RuAccentStressPreprocessor.from_pretrained()
        return ChatterboxTTSAdapter.from_pretrained(cfg, preprocessor=preprocessor)
    if key == "silero":
        from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

        cfg = SileroTTSConfig(
            model_id="v5_cis_base_nostress",
            speaker=SILERO_VOICE,
            sample_rate=24000,
            supports_question_intonation=False,
        )
        return SileroTTSAdapter.from_pretrained(
            cfg, model_path="models/tts/v5_cis_base_nostress.pt", stress=True
        )
    raise ValueError(f"unknown engine: {key}")


def make_reference(out_root: Path) -> Path:
    """Build the Chatterbox reference clip from a Silero MIT voice.

    Synthetic voice only (no actor recordings to clear); this conditions the
    Chatterbox timbre and scored MOS 3.59 vs 2.71 for the built-in default.
    """
    from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

    cfg = SileroTTSConfig(
        model_id="v5_cis_base_nostress",
        speaker=REFERENCE_VOICE,
        sample_rate=24000,
        supports_question_intonation=False,
    )
    adapter = SileroTTSAdapter.from_pretrained(
        cfg, model_path="models/tts/v5_cis_base_nostress.pt", stress=True
    )
    synth = asyncio.run(collect_pcm(adapter, PHRASE, "reference"))
    path = out_root / f"voice_reference_{REFERENCE_VOICE.removeprefix('ru_')}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(synth["sample_rate"])
        fh.writeframes(synth["pcm"])
    print(f"reference voice clip: {path}")
    return path


def render_engine(
    key: str,
    adapter: Any,
    out_root: Path,
    emotions: tuple[Emotion, ...],
    make_adapter: Callable[[], Any] | None = None,
    rebuild_every: int | None = None,
) -> dict[str, Any]:
    """Render every emotion for one engine; returns a report fragment.

    ``make_adapter``/``rebuild_every`` compensate the upstream Chatterbox
    degradation on long serial runs (resemble-ai/chatterbox #360): the model is
    discarded and rebuilt every ``rebuild_every`` samples.
    """
    meta = dict(ENGINE_TITLES[key])
    fragment: dict[str, Any] = {**meta, "status": "ok", "samples": {}}

    def warmup() -> None:
        # Warm up so the first measured phrase is not a cold start (SSOT §5.8).
        try:
            asyncio.run(collect_pcm(adapter, "Проверка прогрева.", "warmup"))
        except Exception as exc:  # noqa: BLE001 - warm-up must not fail the run
            print(f"  warm-up skipped: {type(exc).__name__}: {exc}")

    warmup()
    for index, emotion in enumerate(emotions):
        if rebuild_every and make_adapter is not None and index and index % rebuild_every == 0:
            print(f"  [{key}] reload after {index} samples (serial-degradation mitigation)")
            del adapter
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001 - best-effort cleanup only
                pass
            adapter = make_adapter()
            warmup()
        try:
            if key == "chatterbox":
                # Public attribute of the adapter config shared with the engine;
                # the model reads it on every ``generate`` call.
                adapter.config.exaggeration = emotion.exaggeration
            synth = asyncio.run(collect_pcm(adapter, PHRASE, emotion.id))
            proc_started = time.perf_counter()
            audio = apply_prosody(synth["pcm"], synth["sample_rate"], emotion)
            proc_ms = (time.perf_counter() - proc_started) * 1000.0
            wav_name = f"{emotion.id}__{key}.wav"
            write_wav(out_root / "audio" / wav_name, audio, synth["sample_rate"])
            audio_ms = round(len(audio) / synth["sample_rate"] * 1000.0, 1)
            fragment["samples"][emotion.id] = {
                "wav": wav_name,
                "first_chunk_ms": synth["first_chunk_ms"],
                "synth_ms": synth["synth_ms"],
                "proc_ms": round(proc_ms, 1),
                "audio_ms": audio_ms,
                "rtf": round(synth["synth_ms"] / audio_ms, 3) if audio_ms else None,
            }
            print(
                f"  [{key}/{emotion.id}] first {synth['first_chunk_ms']} ms · "
                f"synth {synth['synth_ms']} ms · audio {audio_ms} ms"
            )
        except Exception as exc:  # noqa: BLE001 - report per-emotion failure honestly
            fragment["samples"][emotion.id] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            print(f"  [{key}/{emotion.id}] error: {type(exc).__name__}: {exc}")
    return fragment


# ---------------------------------------------------------------------------
# HTML report (self-contained; matches the other demo/vps-showcase pages)
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Маскот-куб — как звучит каждая эмоция</title>
<style>
  :root {
    --bg: #0f1115; --panel: #171a21; --panel-2: #1c2028; --border: #2a2f3a;
    --text: #e8eaf0; --muted: #9aa3b2; --accent: #ff4d4d; --accent2: #4da3ff;
    --cube: #ed0010; --mouth: #ffffff;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  .wrap { max-width: 1040px; margin: 0 auto; padding: 40px 20px 80px; }
  h1 { font-size: 27px; margin: 0 0 8px; }
  h2 { font-size: 18px; margin: 38px 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
  .sub { color: var(--muted); margin: 0 0 14px; max-width: 860px; }
  .badge { display: inline-block; font-size: 12px; font-weight: 600; letter-spacing: .04em;
           text-transform: uppercase; color: #fff; background: var(--accent);
           border-radius: 999px; padding: 3px 10px; margin-bottom: 14px; }
  .muted { color: var(--muted); font-size: 13px; }
  code { background: #1e222b; padding: 1px 6px; border-radius: 5px; font-size: 13px; color: #ffd479; }
  a { color: var(--accent2); }
  .toggle { display: inline-flex; gap: 8px; flex-wrap: wrap; margin: 6px 0 14px; }
  .toggle button { border: 1px solid var(--border); background: var(--panel); color: var(--muted);
                   border-radius: 10px; padding: 10px 16px; font: inherit; font-size: 14px; cursor: pointer; }
  .toggle button.is-active { color: #fff; border-color: var(--accent); background: #241a1d; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; }
  .hero { display: grid; grid-template-columns: 260px 1fr; gap: 22px; align-items: center;
          padding: 26px; margin-top: 6px;
          background: radial-gradient(1200px 400px at 20% -30%, #221820, transparent), var(--panel); }
  .cube-wrap { perspective: 520px; display: grid; place-items: center; }
  .stage { display: grid; place-items: center; width: 210px; height: 210px; border-radius: 42px;
           background: radial-gradient(circle at 50% 38%, #232936, #14171d 72%); }
  .cube { width: 168px; height: 168px; filter: drop-shadow(0 14px 18px rgba(0,0,0,.45));
          transform-origin: 50% 62%; animation-fill-mode: both; }
  .hero-info h3 { margin: 0 0 6px; font-size: 22px; }
  .params { margin: 0 0 12px; color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }
  audio { width: 100%; max-width: 520px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 999px;
          background: var(--panel); border: 1px solid var(--border); color: var(--text); font: inherit;
          font-size: 13px; cursor: pointer; transition: border-color .15s ease, transform .15s ease; }
  .chip:hover:not(:disabled) { border-color: #6b3a41; transform: translateY(-1px); }
  .chip.is-active { border-color: var(--accent); background: #241a1d; }
  .chip svg { width: 22px; height: 14px; color: #fff; }
  .chip.is-active svg { color: var(--accent); }
  .chip:disabled { opacity: .55; cursor: not-allowed; }
  .mouth-group { transform-box: fill-box; transform-origin: 50% 60%; }
  .is-playing .mouth-talk { animation: none; }
  ul { padding-left: 20px; } li { margin: 5px 0; }
  .sample-count { color: var(--muted); font-size: 12px; }
  @media (max-width: 720px) { .hero { grid-template-columns: 1fr; } }
  @media (prefers-reduced-motion: reduce) { .cube { animation: none !important; } .mouth-talk { animation: none !important; } }

  /* Motion vocabulary of the atlas (spec §8): every emotion has its own body language. */
  @keyframes float { 0%,100% { transform: translateY(-3px); } 50% { transform: translateY(3px); } }
  @keyframes breathe { 0%,100% { transform: translateY(0) scale(1); } 50% { transform: translateY(1px) scale(1.015); } }
  @keyframes tiltWobble { 0%,100% { transform: rotate(0) translateY(0); } 25% { transform: rotate(5deg) translateY(-2px); } 75% { transform: rotate(-4deg) translateY(1px); } }
  @keyframes tiltSlow { 0%,100% { transform: rotate(-3deg); } 50% { transform: rotate(5deg); } }
  @keyframes bounce { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
  @keyframes talk { 0%,100% { transform: scaleY(.3); } 50% { transform: scaleY(1); } }
  @keyframes hop { 0%,100% { transform: translateY(0) scaleY(1); } 40% { transform: translateY(-8px) scaleY(1.05); } 62% { transform: translateY(0) scaleY(.97); } }
  @keyframes pop { 0%,100% { transform: scale(1); } 12% { transform: scale(1.08) translateY(-6px); } 34% { transform: scale(1); } }
  @keyframes leanBack { 0%,100% { transform: rotate(0); } 50% { transform: rotate(-4deg) translateY(2px); } }
  @keyframes nodSlow { 0%,100% { transform: rotate(0) translateY(0); } 50% { transform: translateY(3px) rotate(2deg); } }
  @keyframes deflate { 0%,100% { transform: scaleY(.93) translateY(6px); } 50% { transform: scaleY(.95) translateY(5px); } }
  @keyframes bow { 0%,100% { transform: translateY(0) rotateX(0); } 50% { transform: translateY(6px) rotateX(12deg); } }
  @keyframes rise { 0%,100% { transform: translateY(3px); } 50% { transform: translateY(-5px); } }
  @keyframes shake { 0%,100% { transform: translate(0,0) rotate(0); } 25% { transform: translate(-2px,1px) rotate(-1deg); } 75% { transform: translate(2px,-1px) rotate(1deg); } }

  .cube--neutral   { animation: float 4s ease-in-out infinite; }
  .cube--attentive { animation: breathe 3.6s ease-in-out infinite; }
  .cube--curious   { animation: tiltWobble 5s ease-in-out infinite; }
  .cube--thinking  { animation: tiltSlow 4.2s ease-in-out infinite; }
  .cube--speaking  { animation: bounce 1.1s ease-in-out infinite; }
  .cube--joyful    { animation: hop 1.7s ease-in-out infinite; }
  .cube--surprised { animation: pop 2.6s ease-in-out infinite; }
  .cube--confused  { animation: tiltWobble 3.2s ease-in-out infinite; }
  .cube--skeptical { animation: leanBack 4s ease-in-out infinite; }
  .cube--empathetic{ animation: nodSlow 4.2s ease-in-out infinite; }
  .cube--sad       { animation: deflate 4.6s ease-in-out infinite; }
  .cube--apologetic{ animation: bow 4.4s ease-in-out infinite; }
  .cube--relieved  { animation: rise 4s ease-in-out infinite; }
  .cube--angry     { animation: shake .09s linear infinite; }
  .cube--speaking .mouth-talk { animation: talk .16s ease-in-out infinite; transform-origin: 120px 136px; }
</style>
</head>
<body>
<div class="wrap">
  <span class="badge">Маскот-куб · эмоции · озвучка</span>
  <h1>Как звучит каждая эмоция</h1>
  <p class="sub">
    Одна и та же фраза синтезирована для всех 14 эмоций атласа
    (<code>docs/SPEC_MASCOT_FACE.md</code> §6/§9.3): один сэмпл — листайте эмоции
    и смотрите, как куб говорит вместе с голосом (рот синхронизирован с
    амплитудой звука). Chatterbox передаёт эмоцию нативно через
    <code>exaggeration</code>; Silero MIT нативной эмоции не имеет — это честная
    деградация, где применена только таблица просодии (темп, высота, громкость).
    Выберите движок:
  </p>
  <div class="toggle" id="engine-toggle"></div>
  <p class="muted">Фраза: «__PHRASE__» · сгенерировано __GENERATED__ · __HARDWARE__ · синтетическая речь, без персональных данных</p>

  <section class="hero card" id="hero">
    <div class="cube-wrap"><div class="stage" id="cube-stage"></div></div>
    <div class="hero-info">
      <h3 id="hero-name">…</h3>
      <p class="params" id="hero-params"></p>
      <audio id="player" controls preload="metadata"></audio>
      <p class="params" id="hero-metrics"></p>
      <p class="muted" id="hero-note"></p>
    </div>
  </section>

  <h2>Эмоции атласа</h2>
  <p class="muted">Клик по эмоции — куб меняет мимику, а озвучка переключается на её сэмпл.</p>
  <div class="chips" id="chips"></div>

  <h2>Честные пометки</h2>
  <ul class="muted">
    <li><b>Chatterbox V3</b> (MIT, код и веса): эмоциональность — нативный параметр
        <code>exaggeration</code> адаптера <code>speech/tts/chatterbox_tts.py</code>;
        каждый выход содержит PerTh-водяной знак Resemble AI.</li>
    <li><b>Голос Chatterbox улучшен</b> по результатам лабораторного прогона
        (UTMOSv2 MOS 2.71 → 3.59): предустановка ударений
        (<code>RuAccentStressPreprocessor</code>, ruaccent MIT — заменяет
        недоступный <code>russian_text_stresser</code>), референс тембра
        (синтез Silero MIT <code>ru_ekaterina</code>) и <code>cfg_weight 0.30</code>.
        Модель перезагружается каждые 4 сэмпла: у Chatterbox есть известная
        деградация качества на длинных сериях (resemble-ai/chatterbox #360).</li>
    <li><b>Silero v5_cis_base_nostress</b> (MIT, голос ru_alexandr): нативного
        управления эмоцией нет; применена только просодия из спеки — так выглядит
        «честная деградация», когда движок не умеет эмоцию (SSOT NFR-10).</li>
    <li>Просодия из таблицы §9.3 (темп/высота/энергия) применена ffmpeg-фильтром
        <code>rubberband</code> с сохранением формант: phase vocoder давал слышимые
        артефакты (UTMOS 1.1 против 2.5 после фикса). Перед внедрением в агент таблицу
        нужно проверить бенчмарком разборчивости (<code>scripts/tts_ab_eval.py</code>,
        WER round-trip) и зафиксировать ADR + правку SSOT §5.7.</li>
    <li><b>Злость</b> в агенте — policy-off: по умолчанию не направляется клиенту, здесь
        показана только как часть атласа.</li>
    <li>Эта страница и аудио собраны <code>scripts/emotion_demo_build.py</code>;
        значения <code>exaggeration</code> и просодии — из спеки, не из рантайма агента.</li>
  </ul>
</div>
<script>
const REPORT = __REPORT__;
const AUDIO_PREFIX = "__AUDIO_PREFIX__";
const MOUTHS = {
  neutral:    '<path d="M 96 132 Q 120 142 144 132"/>',
  attentive:  '<path d="M 104 134 Q 120 142 136 134"/>',
  curious:    '<circle cx="120" cy="136" r="13" fill="#fff"/>',
  thinking:   '<path d="M 98 137 L 142 133"/>',
  speaking:   '<ellipse class="mouth-talk" cx="120" cy="136" rx="24" ry="13" fill="#fff"/>',
  joyful:     '<path d="M 88 126 Q 120 154 152 126"/>',
  surprised:  '<circle cx="120" cy="138" r="19" fill="#fff"/>',
  confused:   '<path d="M 94 138 Q 106 130 118 138 T 142 138"/>',
  skeptical:  '<path d="M 96 138 Q 116 144 138 128"/>',
  empathetic: '<path d="M 96 138 Q 120 130 144 138"/>',
  sad:        '<path d="M 92 142 Q 120 122 148 142"/>',
  apologetic: '<path d="M 94 141 Q 106 133 120 139 Q 134 133 146 141"/>',
  relieved:   '<path d="M 100 134 Q 120 144 140 134"/>',
  angry:      '<path d="M 94 136 L 146 136" stroke-width="13"/>',
};
function cubeSVG(id) {
  const mouth = MOUTHS[id] || MOUTHS.neutral;
  return '<svg class="cube cube--' + id + '" viewBox="0 0 240 240" role="img" aria-label="Маскот: ' + id + '">' +
    '<rect x="22" y="22" width="196" height="196" rx="56" fill="var(--cube)"/>' +
    '<rect x="34" y="30" width="172" height="72" rx="40" fill="#ffffff" opacity="0.07"/>' +
    '<g class="mouth-group"><g fill="none" stroke="#ffffff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round">' +
    mouth + '</g></g></svg>';
}
function chipIcon(id) {
  const mouth = MOUTHS[id] || MOUTHS.neutral;
  return '<svg viewBox="86 118 68 40" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="10" stroke-linecap="round" stroke-linejoin="round">' + mouth + '</g></svg>';
}
const state = {
  engine: (REPORT.engines.chatterbox && REPORT.engines.chatterbox.status === 'ok') ? 'chatterbox' : 'silero',
  selected: REPORT.emotions[0] ? REPORT.emotions[0].id : 'neutral',
};
function sampleFor(id) {
  const emo = REPORT.emotions.find((e) => e.id === id);
  if (!emo) return null;
  const sample = emo.samples[state.engine];
  return (sample && sample.status !== 'error') ? { emo, sample } : null;
}
function engineBadge() { return (REPORT.engines[state.engine] || {}).badge || state.engine; }
const ENGINE_SHORT = { chatterbox: 'Chatterbox V3', silero: 'Silero MIT' };
function engineShort() { const eng = REPORT.engines[state.engine] || {}; return eng.short || ENGINE_SHORT[state.engine] || state.engine; }
function renderToggle() {
  const box = document.getElementById('engine-toggle');
  const player = document.getElementById('player');
  box.innerHTML = '';
  for (const [key, eng] of Object.entries(REPORT.engines)) {
    const btn = document.createElement('button');
    btn.textContent = eng.title.split(' (')[0] + ' — ' + eng.badge;
    btn.className = key === state.engine ? 'is-active' : '';
    btn.disabled = eng.status !== 'ok';
    btn.onclick = () => {
      const wasPlaying = !player.paused && !player.ended;
      state.engine = key;
      renderAll();
      if (wasPlaying) playSelected();
    };
    box.appendChild(btn);
  }
}
function renderHero() {
  const found = sampleFor(state.selected);
  const emo = REPORT.emotions.find((e) => e.id === state.selected);
  document.getElementById('cube-stage').innerHTML = cubeSVG(state.selected);
  document.getElementById('hero-name').textContent = emo ? emo.ru : state.selected;
  const params = ['темп ×' + emo.rate.toFixed(2), 'высота ' + (emo.pitch_pct > 0 ? '+' : '') + emo.pitch_pct + '%', 'энергия ×' + emo.gain.toFixed(2)];
  if (state.engine === 'chatterbox') params.push('exaggeration ' + emo.exaggeration.toFixed(2));
  document.getElementById('hero-params').textContent = params.join(' · ') + ' · движок ' + engineShort() + ' (' + engineBadge() + ')';
  const player = document.getElementById('player');
  if (found) {
    if (player.dataset.wav !== found.sample.wav) {
      player.dataset.wav = found.sample.wav;
      player.src = AUDIO_PREFIX + '/' + found.sample.wav;
    }
    player.disabled = false;
    document.getElementById('hero-metrics').textContent =
      'первый чанк ' + found.sample.first_chunk_ms + ' мс · синтез ' + found.sample.synth_ms +
      ' мс · длительность ' + (found.sample.audio_ms / 1000).toFixed(1) + ' с · RTF ' + found.sample.rtf;
    document.getElementById('hero-note').textContent = '';
  } else {
    delete player.dataset.wav;
    player.removeAttribute('src'); player.disabled = true;
    document.getElementById('hero-metrics').textContent = '';
    document.getElementById('hero-note').textContent = 'Для этого движка сэмпл недоступен.';
  }
}
function renderChips() {
  const box = document.getElementById('chips');
  box.innerHTML = '';
  for (const emo of REPORT.emotions) {
    const found = sampleFor(emo.id);
    const btn = document.createElement('button');
    btn.className = 'chip' + (emo.id === state.selected ? ' is-active' : '');
    btn.innerHTML = chipIcon(emo.id) + '<span>' + emo.ru + '</span>';
    btn.disabled = !found;
    if (found) btn.onclick = () => { state.selected = emo.id; renderAll(); playSelected(); };
    box.appendChild(btn);
  }
}
function renderAll() { renderToggle(); renderHero(); renderChips(); }
renderAll();

// Live lipsync: mouth openness follows the actual amplitude of the played audio.
const player = document.getElementById('player');
const hero = document.getElementById('hero');
const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let audioCtx = null, analyser = null, dataArr = null;
function ensureAudio() {
  if (audioCtx || reduceMotion) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  try {
    audioCtx = new Ctx();
    const srcNode = audioCtx.createMediaElementSource(player);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    srcNode.connect(analyser);
    analyser.connect(audioCtx.destination);
    dataArr = new Uint8Array(analyser.fftSize);
  } catch (err) { audioCtx = null; analyser = null; }
}
function resetMouth() {
  const g = document.querySelector('.hero .mouth-group');
  const stage = document.getElementById('cube-stage');
  if (g) g.style.transform = '';
  if (stage) stage.style.transform = '';
}
function playSelected() {
  const found = sampleFor(state.selected);
  if (!found) return;
  ensureAudio();
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  if (player.dataset.wav !== found.sample.wav) {
    player.dataset.wav = found.sample.wav;
    player.src = found.sample.wav;
  }
  player.play().catch(() => {});
}
player.addEventListener('play', () => {
  ensureAudio();
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  hero.classList.add('is-playing');
});
player.addEventListener('pause', () => { hero.classList.remove('is-playing'); resetMouth(); });
player.addEventListener('ended', () => { hero.classList.remove('is-playing'); resetMouth(); });
(function loop() {
  requestAnimationFrame(loop);
  const g = document.querySelector('.hero .mouth-group');
  const stage = document.getElementById('cube-stage');
  if (!g || !analyser || player.paused || player.ended) return;
  analyser.getByteTimeDomainData(dataArr);
  let sum = 0;
  for (let i = 0; i < dataArr.length; i += 1) { const d = (dataArr[i] - 128) / 128; sum += d * d; }
  const rms = Math.sqrt(sum / dataArr.length);
  const open = Math.min(1, rms * 5.5);
  g.style.transform = 'scaleY(' + (0.55 + open * 1.1).toFixed(3) + ')';
  if (stage) stage.style.transform = 'translateY(' + (-2.5 * open).toFixed(1) + 'px)';
})();
</script>
</body>
</html>
"""


def hardware_note() -> str:
    try:
        import torch

        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no CUDA"
        return f"CPU {platform.processor() or 'x86_64'} / torch {torch.__version__} / GPU: {gpu}"
    except Exception:  # noqa: BLE001
        return f"CPU {platform.processor() or 'x86_64'}"


def render_html(report: dict[str, Any], html_path: Path) -> None:
    html = (
        HTML_TEMPLATE.replace("__REPORT__", json.dumps(report, ensure_ascii=False))
        .replace("__PHRASE__", report["phrase"])
        .replace("__GENERATED__", report["generated_at"])
        .replace("__HARDWARE__", report["hardware"])
        .replace("__AUDIO_PREFIX__", report["audio_prefix"])
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engines",
        default="chatterbox,silero",
        help="comma-separated engine keys: chatterbox, silero",
    )
    parser.add_argument("--out", default="artifacts/emotions_demo")
    parser.add_argument(
        "--emotions",
        default="",
        help="optional comma-separated emotion ids to render (default: all 14)",
    )
    parser.add_argument("--html", default="", help="optional path to the HTML report to render")
    parser.add_argument(
        "--html-audio-prefix",
        default="mascot-emotions/audio",
        help="audio URL prefix used inside the HTML report",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="re-render the HTML from an existing report.json without synthesis",
    )
    args = parser.parse_args()

    if args.html_only:
        if not args.html:
            print("--html-only requires --html")
            return 2
        report_path = Path(args.out) / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["audio_prefix"] = args.html_audio_prefix
        render_html(report, Path(args.html))
        print(f"html:   {args.html} (from {report_path})")
        return 0

    emotions = ATLAS
    if args.emotions:
        wanted = {key.strip() for key in args.emotions.split(",") if key.strip()}
        emotions = tuple(emotion for emotion in ATLAS if emotion.id in wanted)
        unknown = sorted(wanted - {emotion.id for emotion in ATLAS})
        if unknown:
            print(f"unknown emotions: {unknown}; known: {[e.id for e in ATLAS]}")
            return 2

    out_root = Path(args.out)
    (out_root / "audio").mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "hardware": hardware_note(),
        "spec": SPEC_REF,
        "phrase": PHRASE,
        "audio_prefix": args.html_audio_prefix,
        "prosody_backend": (
            "ffmpeg rubberband (formant=preserved)"
            if shutil.which("ffmpeg")
            else "librosa phase vocoder (fallback, ниже качество)"
        ),
        "engines": {},
        "emotions": [],
    }

    reference: Path | None = None
    for key in [part.strip() for part in args.engines.split(",") if part.strip()]:
        if key not in ENGINE_TITLES:
            print(f"unknown engine: {key}; known: {sorted(ENGINE_TITLES)}")
            return 2
        print(f"=== {key}: {ENGINE_TITLES[key]['title']} ===")
        if key == "chatterbox" and reference is None:
            reference = make_reference(out_root)
        make_adapter = partial(build_engine, key, reference)
        try:
            adapter = make_adapter()
        except Exception as exc:  # noqa: BLE001 - keep the other engine usable
            print(f"  unavailable: {type(exc).__name__}: {exc}")
            report["engines"][key] = {**ENGINE_TITLES[key], "status": "unavailable", "error": str(exc)}
            continue
        is_chatterbox = key == "chatterbox"
        fragment = render_engine(
            key,
            adapter,
            out_root,
            emotions,
            make_adapter=make_adapter if is_chatterbox else None,
            rebuild_every=CHATTERBOX_REBUILD_EVERY if is_chatterbox else None,
        )
        report["engines"][key] = fragment
        # Free GPU/CPU memory before the next engine (chatterbox is heavy).
        del adapter
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - best-effort cleanup only
            pass

    report["voice_reference"] = str(reference) if reference else None

    for emotion in emotions:
        row = asdict(emotion)
        row["samples"] = {
            key: frag["samples"].get(emotion.id)
            for key, frag in report["engines"].items()
            if frag.get("status") == "ok" and emotion.id in frag.get("samples", {})
        }
        report["emotions"].append(row)

    report_path = out_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport: {report_path}")

    if args.html:
        render_html(report, Path(args.html))
        print(f"html:   {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
