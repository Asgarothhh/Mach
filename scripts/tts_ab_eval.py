#!/usr/bin/env python3
"""A/B evaluation of candidate Russian TTS engines for the voice agent (track 1).

Engines and licenses (see LICENSES.md):

* ``silero-v5``      CC BY-NC-SA  — quality baseline, demo only
* ``silero-mit``     MIT          — Silero v5_cis_base_nostress + silero-stress
* ``chatterbox``     MIT          — Chatterbox Multilingual V3 (GPU)
* ``kokoro-ru``      OpenRAIL     — Kokoro-82M Russian port (CPU)

For every available engine the script:

1. synthesizes a fixed phrase set (greetings, prices, phone number, homographs);
2. measures first-chunk latency and real-time factor (RTF);
3. computes a Whisper round-trip WER as an intelligibility proxy;
4. writes WAVs and ``report.json`` under ``artifacts/tts_ab/``;
5. optionally renders an HTML listening page for the team VPS stand.

Usage:
    .venv/bin/python scripts/tts_ab_eval.py                    # all available
    .venv/bin/python scripts/tts_ab_eval.py --engines silero-mit,kokoro-ru
    .venv/bin/python scripts/tts_ab_eval.py --no-wer           # skip Whisper
    .venv/bin/python scripts/tts_ab_eval.py --html demo/vps-showcase/tts-ab.html
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import platform
import statistics
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from speech.contracts import CancellationToken, TTSRequest
from speech.metrics import word_wer

PHRASES: list[str] = [
    "Здравствуйте! Меня зовут Анна, я виртуальный ассистент компании.",
    "Подскажите, пожалуйста, сколько стоит подключение?",
    "Тариф стоит 100 рублей в месяц, подключение бесплатное.",
    "Позвоните нам по номеру +375 17 237-98-98.",
    "Старинный замок возвышается на холме.",  # за́мок (castle)
    "Он закрыл дверь на замок и ушёл.",  # замо́к (lock)
    "Пшеничная мука рассыпалась по столу.",  # мука́ (flour)
    "Не работа, а настоящая мука.",  # му́ка (torment)
    "Хочу узнать про домашний интернет и телевидение.",
]

# Voices for the MIT-licensed Silero CIS-base model — team shortlist
# (Ekaterina, Saida, Bogdan only; see the playground server for the rationale).
SILERO_MIT_VOICES: list[str] = ["ru_ekaterina", "ru_saida", "ru_bogdan"]


@dataclass
class EngineSpec:
    key: str
    title: str
    license_label: str
    commercial: str  # yes | no | conditional
    build: Callable[[], tuple[Any, int]]
    meta: dict[str, Any] = field(default_factory=dict)


def build_silero_v5() -> tuple[Any, int]:
    from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

    cfg = SileroTTSConfig(
        model_id="v5_5_ru",
        speaker="xenia",
        sample_rate=24000,
        supports_question_intonation=True,
    )
    adapter = SileroTTSAdapter.from_pretrained(cfg, model_path="models/tts/v5_5_ru.pt")
    return adapter, 24000


def build_silero_mit(voice: str) -> Callable[[], tuple[Any, int]]:
    def builder() -> tuple[Any, int]:
        from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

        cfg = SileroTTSConfig(
            model_id="v5_cis_base_nostress",
            speaker=voice,
            sample_rate=24000,
            supports_question_intonation=False,
        )
        adapter = SileroTTSAdapter.from_pretrained(
            cfg, model_path="models/tts/v5_cis_base_nostress.pt", stress=True
        )
        return adapter, 24000

    return builder


def build_chatterbox() -> tuple[Any, int]:
    from speech.tts.chatterbox_tts import ChatterboxTTSAdapter, ChatterboxTTSConfig

    cfg = ChatterboxTTSConfig(language_id="ru", t3_model="v3", device="auto")
    return ChatterboxTTSAdapter.from_pretrained(cfg), 24000


def build_kokoro(voice: str = "sveta") -> Callable[[], tuple[Any, int]]:
    def builder() -> tuple[Any, int]:
        from speech.tts.kokoro_tts import KokoroRuTTSAdapter, KokoroRuTTSConfig

        cfg = KokoroRuTTSConfig(voice=voice)
        return KokoroRuTTSAdapter.from_pretrained(cfg), 24000

    return builder


def engine_registry() -> dict[str, EngineSpec]:
    registry = {
        "silero-v5": EngineSpec(
            key="silero-v5",
            title="Silero v5.5 RU (xenia)",
            license_label="CC BY-NC-SA 4.0",
            commercial="no",
            build=build_silero_v5,
            meta={"model": "v5_5_ru", "voice": "xenia", "role": "quality baseline (demo only)"},
        ),
        "chatterbox": EngineSpec(
            key="chatterbox",
            title="Chatterbox Multilingual V3 (built-in voice)",
            license_label="MIT",
            commercial="yes",
            build=build_chatterbox,
            meta={"model": "ResembleAI/chatterbox", "t3": "v3", "language": "ru"},
        ),
    }
    for voice in SILERO_MIT_VOICES:
        registry[f"silero-mit-{voice}"] = EngineSpec(
            key=f"silero-mit-{voice}",
            title=f"Silero CIS-base MIT ({voice} + silero-stress)",
            license_label="MIT (weights + stress)",
            commercial="yes",
            build=build_silero_mit(voice),
            meta={"model": "v5_cis_base_nostress", "voice": voice, "stress": "silero-stress"},
        )
    registry["kokoro-ru-sveta"] = EngineSpec(
        key="kokoro-ru-sveta",
        title="Kokoro-82M RU (sveta)",
        license_label="OpenRAIL (weights), Apache-2.0 (code)",
        commercial="conditional",
        build=build_kokoro("sveta"),
        meta={"model": "zaakirio/kokoro-ru", "voice": "sveta", "g2p": "ru_g2p + RUAccent (MIT)"},
    )
    return registry


# ---------------------------------------------------------------------------
# Synthesis + metrics
# ---------------------------------------------------------------------------


async def synthesize_phrase(adapter: Any, phrase: str, index: int) -> dict[str, Any]:
    request = TTSRequest(
        session_id="tts-ab",
        turn_id=f"p{index}",
        generation_id="g0",
        segments=[phrase],
    )
    audio_parts: list[bytes] = []
    first_chunk_ms: float | None = None
    sample_rate = 0
    started = time.perf_counter()
    async for chunk in adapter.synthesize(request, CancellationToken()):
        if chunk.is_first_chunk:
            first_chunk_ms = chunk.first_chunk_ms
        audio_parts.append(chunk.pcm_s16le)
        sample_rate = chunk.sample_rate
    total_ms = (time.perf_counter() - started) * 1000.0
    pcm = b"".join(audio_parts)
    audio_ms = len(pcm) / 2 / max(1, sample_rate) * 1000.0
    return {
        "text": phrase,
        "pcm": pcm,
        "sample_rate": sample_rate,
        "first_chunk_ms": round(first_chunk_ms, 1) if first_chunk_ms is not None else None,
        "total_ms": round(total_ms, 1),
        "audio_ms": round(audio_ms, 1),
        "rtf": round(total_ms / audio_ms, 3) if audio_ms else None,
    }


def write_wav(path: Path, pcm_s16le: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(pcm_s16le)


# ---------------------------------------------------------------------------
# Whisper round-trip WER (intelligibility proxy) — metrics live in speech.metrics
# ---------------------------------------------------------------------------


def load_whisper() -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")


def read_wav_float32(path: Path) -> tuple[np.ndarray, int]:
    """Read a 16-bit PCM WAV into mono float32 [-1; 1] + sample rate."""
    with wave.open(str(path), "rb") as fh:
        rate = fh.getframerate()
        channels = fh.getnchannels()
        width = fh.getsampwidth()
        raw = fh.readframes(fh.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit PCM, got {width * 8}-bit")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


def resample_audio(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return audio.astype(np.float32)
    try:
        import soxr

        return soxr.resample(audio, src_rate, dst_rate, quality="HQ").astype(np.float32)
    except ImportError:  # linear fallback is adequate for the WER proxy
        n_out = int(len(audio) * dst_rate / src_rate)
        x_out = np.linspace(0, len(audio) - 1, n_out)
        return np.interp(x_out, np.arange(len(audio)), audio).astype(np.float32)


def transcribe(model: Any, wav_path: Path) -> str:
    """Whisper via numpy input (avoids faster-whisper's PyAV decode path)."""
    audio, rate = read_wav_float32(wav_path)
    audio16 = resample_audio(audio, rate, 16000)
    segments, _info = model.transcribe(audio16, language="ru", beam_size=1)
    return " ".join(segment.text for segment in segments).strip()


def load_mos_scorer() -> Any:
    """UTMOSv2 (SaruLab, MIT): naturalness MOS proxy, 1-5 scale."""
    import utmosv2

    return utmosv2.create_model(pretrained=True)


def score_mos(model: Any, wav_path: Path) -> float | None:
    try:
        return round(float(model.predict(input_path=str(wav_path))), 2)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def evaluate_engine(
    spec: EngineSpec, out_root: Path, whisper: Any | None, mos: Any | None = None
) -> dict[str, Any]:
    engine_dir = out_root / spec.key
    result: dict[str, Any] = {
        "key": spec.key,
        "title": spec.title,
        "license": spec.license_label,
        "commercial": spec.commercial,
        "meta": spec.meta,
        "status": "ok",
        "phrases": [],
    }
    try:
        adapter, native_rate = spec.build()
    except Exception as exc:  # noqa: BLE001 - report any build problem without failing the run
        result["status"] = "unavailable"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    # Warm up the engine once so the first measured phrase is not a cold start
    # (SSOT §5.8 targets are for a warm local model).
    with contextlib.suppress(Exception):
        asyncio.run(synthesize_phrase(adapter, "Проверка прогрева.", -1))

    for index, phrase in enumerate(PHRASES):
        try:
            metrics = asyncio.run(synthesize_phrase(adapter, phrase, index))
        except Exception as exc:  # noqa: BLE001
            result["phrases"].append(
                {"text": phrase, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        wav_path = engine_dir / f"phrase_{index}.wav"
        write_wav(wav_path, metrics.pop("pcm"), metrics["sample_rate"])
        metrics["status"] = "ok"
        metrics["wav"] = f"{spec.key}/phrase_{index}.wav"
        if whisper is not None:
            try:
                hypothesis = transcribe(whisper, wav_path)
                metrics["whisper_text"] = hypothesis
                metrics["wer"] = round(word_wer(phrase, hypothesis), 3)
            except Exception as exc:  # noqa: BLE001
                metrics["wer_error"] = f"{type(exc).__name__}: {exc}"
        if mos is not None:
            mos_score = score_mos(mos, wav_path)
            if mos_score is not None:
                metrics["mos"] = mos_score
        result["phrases"].append(metrics)

    ok = [p for p in result["phrases"] if p.get("status") == "ok"]
    if ok:
        result["aggregate"] = {
            "phrases": len(ok),
            "first_chunk_ms_p50": round(
                statistics.median(
                    [p["first_chunk_ms"] for p in ok if p["first_chunk_ms"] is not None]
                ),
                1,
            )
            if any(p["first_chunk_ms"] is not None for p in ok)
            else None,
            "rtf_mean": round(statistics.mean([p["rtf"] for p in ok if p["rtf"] is not None]), 3)
            if any(p["rtf"] is not None for p in ok)
            else None,
            "wer_mean": round(
                statistics.mean([p["wer"] for p in ok if p.get("wer") is not None]), 3
            )
            if any(p.get("wer") is not None for p in ok)
            else None,
            "mos_mean": round(
                statistics.mean([p["mos"] for p in ok if p.get("mos") is not None]), 2
            )
            if any(p.get("mos") is not None for p in ok)
            else None,
        }
    return result


def hardware_note() -> str:
    try:
        import torch

        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no CUDA"
        return f"CPU {platform.processor() or 'x86_64'} / torch {torch.__version__} / GPU: {gpu}"
    except Exception:  # noqa: BLE001
        return f"CPU {platform.processor() or 'x86_64'}"


def render_html(report: dict[str, Any], html_path: Path, audio_prefix: str) -> None:
    rows = []
    sections = []
    for engine in report["engines"].values():
        aggregate = engine.get("aggregate", {})
        rows.append(
            "<tr>"
            f"<td>{engine['title']}</td>"
            f"<td>{engine['license']}</td>"
            f"<td>{'да' if engine['commercial'] == 'yes' else ('условно' if engine['commercial'] == 'conditional' else 'нет (демо)')}</td>"
            f"<td>{aggregate.get('first_chunk_ms_p50', '—')}</td>"
            f"<td>{aggregate.get('rtf_mean', '—')}</td>"
            f"<td>{aggregate.get('wer_mean', '—')}</td>"
            f"<td>{aggregate.get('mos_mean', '—')}</td>"
            "</tr>"
        )
        players = []
        for phrase in engine.get("phrases", []):
            if phrase.get("status") != "ok":
                continue
            details = [f"первый чанк {phrase['first_chunk_ms']} мс", f"RTF {phrase['rtf']}"]
            if phrase.get("wer") is not None:
                details.append(f"WER {phrase['wer']:.2f}")
            if phrase.get("mos") is not None:
                details.append(f"MOS {phrase['mos']:.2f}")
            players.append(
                '<div class="phrase">'
                f'<div class="ptext">{phrase["text"]}'
                f'<span class="muted"> · {" · ".join(details)}</span></div>'
                f'<audio controls preload="metadata" src="{audio_prefix}/{phrase["wav"]}"></audio>'
                "</div>"
            )
        sections.append(
            f"<h2>{engine['title']}</h2>"
            f'<p class="muted">{engine["license"]} · {engine.get("meta", {})}</p>'
            + "".join(players)
        )
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TTS A/B — подбор голоса для голосового агента</title>
<style>
 body {{ background:#0f1115; color:#e8eaf0; font:16px/1.5 -apple-system,Roboto,sans-serif; margin:0; }}
 .wrap {{ max-width:900px; margin:0 auto; padding:36px 18px 80px; }}
 h1 {{ font-size:24px; }} h2 {{ font-size:18px; margin-top:32px; border-bottom:1px solid #2a2f3a; padding-bottom:6px; }}
 table {{ width:100%; border-collapse:collapse; font-size:14px; }}
 th,td {{ padding:8px; border-bottom:1px solid #2a2f3a; text-align:left; }}
 .muted {{ color:#9aa3b2; font-size:13px; }}
 .phrase {{ margin:10px 0 14px; }} audio {{ width:100%; max-width:520px; }}
 .ptext {{ margin-bottom:4px; }}
</style></head><body><div class="wrap">
<h1>TTS A/B: кандидаты на замену Silero для русского</h1>
<p class="muted">Сгенерировано {report['generated_at']} · {report['hardware']} · синтетическая речь, без персональных данных</p>
<h2>Сводка (медиана первого чанка, средний RTF, WER-прокси, MOS)</h2>
<table><tr><th>Движок</th><th>Лицензия</th><th>Коммерч.</th><th>Первый чанк, мс</th><th>RTF</th><th>WER</th><th>MOS</th></tr>
{''.join(rows)}
</table>
{''.join(sections)}
<p class="muted">WER — прогон синтеза через Whisper large-v3-turbo (оценка разборчивости, не естественности).
Гомографы «за́мок/замо́к» в фразах 5–6 проверяют автоматическую расстановку ударений.</p>
</div></body></html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engines", default="", help="comma-separated engine keys (default: all)")
    parser.add_argument("--out", default="artifacts/tts_ab")
    parser.add_argument("--no-wer", action="store_true", help="skip the Whisper WER pass")
    parser.add_argument("--no-mos", action="store_true", help="skip the UTMOS MOS pass")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="merge results into an existing report.json instead of overwriting it",
    )
    parser.add_argument("--html", default="", help="optional path to an HTML report to render")
    parser.add_argument(
        "--html-audio-prefix",
        default="tts_ab",
        help="audio URL prefix used inside the HTML report",
    )
    args = parser.parse_args()

    registry = engine_registry()
    selected = (
        [registry[key] for key in args.engines.split(",") if key]
        if args.engines
        else list(registry.values())
    )
    unknown = [spec.key for spec in selected if spec.key not in registry]
    if unknown:
        print(f"unknown engines: {unknown}; known: {sorted(registry)}")
        return 2

    whisper = None
    if not args.no_wer:
        try:
            print("loading Whisper large-v3-turbo (int8, CPU) for the WER pass ...")
            whisper = load_whisper()
        except Exception as exc:  # noqa: BLE001
            print(f"WER pass disabled: {type(exc).__name__}: {exc}")

    mos_model = None
    if not args.no_mos:
        try:
            print("loading UTMOSv2 MOS predictor ...")
            mos_model = load_mos_scorer()
        except Exception as exc:  # noqa: BLE001
            print(f"MOS pass disabled: {type(exc).__name__}: {exc}")

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    report_path = out_root / "report.json"
    if args.merge and report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        report["hardware"] = hardware_note()
    else:
        report: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "hardware": hardware_note(),
            "phrases": PHRASES,
            "engines": {},
        }
    for spec in selected:
        print(f"=== {spec.key}: {spec.title} ===")
        engine = evaluate_engine(spec, out_root, whisper, mos_model)
        report["engines"][spec.key] = engine
        if engine["status"] != "ok":
            print(f"  unavailable: {engine.get('error')}")
            continue
        for phrase in engine.get("phrases", []):
            if phrase.get("status") != "ok":
                print(f"  error: {phrase.get('error')}")
                continue
            wer = f" WER {phrase['wer']:.2f}" if phrase.get("wer") is not None else ""
            print(
                f"  [{phrase['first_chunk_ms']} ms, RTF {phrase['rtf']}{wer}] {phrase['text'][:60]}"
            )
        print(f"  aggregate: {engine.get('aggregate')}")

    out_root.mkdir(parents=True, exist_ok=True)
    report_path = out_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport: {report_path}")

    if args.html:
        render_html(report, Path(args.html), args.html_audio_prefix)
        print(f"html:   {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
