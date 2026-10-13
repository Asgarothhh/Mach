#!/usr/bin/env python3
"""ASR benchmark for the Russian voice agent: WER/CER/RTF by data category.

Engines (all commercially usable licenses):
    t-one            t-tech/T-one — streaming telephony ASR   (Apache-2.0) [onnx-asr]
    gigaam-v3-ctc    GigaAM v3 CTC, Russian SOTA              (MIT)        [onnx-asr]
    vosk-small-ru    Vosk small ru, lightweight streaming     (Apache-2.0) [onnx-asr]
    whisper-turbo    faster-whisper large-v3-turbo baseline   (MIT)        [faster-whisper]

Usage:
    .venv/bin/python scripts/asr_benchmark.py \
        --manifest artifacts/asr_benchmark/manifest.jsonl \
        --out artifacts/asr_benchmark \
        --html demo/vps-showcase/asr-bench.html

The test set is built by ``scripts/fetch_asr_testset.py`` (see its docstring
for provenance and licenses; the OpenSTT calls category is internal-only).
"""

from __future__ import annotations

import argparse
import json
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from speech.metrics import char_edit_units, word_edit_units

RecognizerFn = Callable[[np.ndarray], str]


@dataclass
class EngineDef:
    key: str
    title: str
    license: str
    mode: str  # streaming-native | chunked/offline
    build: Callable[[], RecognizerFn]


def _build_onnx(name: str) -> RecognizerFn:
    import onnx_asr

    model = onnx_asr.load_model(name)

    def recognize(samples: np.ndarray) -> str:
        result = model.recognize(samples, sample_rate=16000)
        if isinstance(result, str):
            return result
        if isinstance(result, (list, tuple)):
            return " ".join(str(item) for item in result)
        return str(result)

    return recognize


def _build_whisper() -> RecognizerFn:
    from faster_whisper import WhisperModel

    model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")

    def recognize(samples: np.ndarray) -> str:
        segments, _info = model.transcribe(samples.astype(np.float32), language="ru", beam_size=5)
        return " ".join(segment.text for segment in segments).strip()

    return recognize


def engine_registry() -> dict[str, EngineDef]:
    return {
        "t-one": EngineDef(
            key="t-one",
            title="T-one (T-Tech, 71M, телефония)",
            license="Apache-2.0",
            mode="streaming-native",
            build=lambda: _build_onnx("t-tech/t-one"),
        ),
        "gigaam-v3-ctc": EngineDef(
            key="gigaam-v3-ctc",
            title="GigaAM v3 CTC (Сбер, 242M)",
            license="MIT",
            mode="offline",
            build=lambda: _build_onnx("gigaam-v3-ctc"),
        ),
        "vosk-small-ru": EngineDef(
            key="vosk-small-ru",
            title="Vosk small ru (20M, стриминг)",
            license="Apache-2.0",
            mode="streaming-capable",
            build=lambda: _build_onnx("alphacep/vosk-model-small-ru"),
        ),
        "whisper-turbo": EngineDef(
            key="whisper-turbo",
            title="Whisper large-v3-turbo (baseline)",
            license="MIT",
            mode="offline",
            build=_build_whisper,
        ),
    }


def read_wav_mono(path: Path) -> tuple[np.ndarray, float, int]:
    """Read a 16-bit PCM WAV into mono float32 [-1; 1], duration and rate."""
    with wave.open(str(path), "rb") as fh:
        rate = fh.getframerate()
        channels = fh.getnchannels()
        raw = fh.readframes(fh.getnframes())
    if channels != 1:
        raise ValueError(f"{path}: expected mono, got {channels} ch")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return audio, len(audio) / rate, rate


def to_16k(audio: np.ndarray, rate: int) -> np.ndarray:
    if rate == 16000:
        return audio
    import soxr

    return soxr.resample(audio, rate, 16000, quality="HQ").astype(np.float32)


def evaluate_engine(
    engine: EngineDef, entries: list[dict], root: Path, limit: int | None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "key": engine.key,
        "title": engine.title,
        "license": engine.license,
        "mode": engine.mode,
        "status": "ok",
        "categories": {},
        "items": [],
    }
    print(f"=== {engine.key}: {engine.title} ===")
    try:
        recognize = engine.build()
    except Exception as exc:  # noqa: BLE001
        result["status"] = "unavailable"
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"  unavailable: {result['error']}")
        return result

    stats: dict[str, dict[str, float]] = {}
    selected = entries[:limit] if limit else entries
    total_process = 0.0
    total_audio = 0.0

    for entry in selected:
        audio, duration, rate = read_wav_mono(root / entry["audio"])
        audio = to_16k(audio, rate)
        started = time.perf_counter()
        try:
            hypothesis = recognize(audio)
        except Exception as exc:  # noqa: BLE001
            hypothesis = ""
            result["items"].append(
                {**entry, "hypothesis": "", "wer": None, "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        process = time.perf_counter() - started
        total_process += process
        total_audio += duration

        wer_distance, wer_len = word_edit_units(entry["text"], hypothesis)
        cer_distance, cer_len = char_edit_units(entry["text"], hypothesis)
        category = entry["category"]
        bucket = stats.setdefault(
            category, {"n": 0.0, "wer_d": 0.0, "wer_l": 0.0, "cer_d": 0.0, "cer_l": 0.0}
        )
        bucket["n"] += 1
        bucket["wer_d"] += wer_distance
        bucket["wer_l"] += max(1, wer_len)
        bucket["cer_d"] += cer_distance
        bucket["cer_l"] += max(1, cer_len)
        result["items"].append(
            {
                "id": entry["id"],
                "category": category,
                "text": entry["text"],
                "hypothesis": hypothesis,
                "wer": round(wer_distance / max(1, wer_len), 3),
                "cer": round(cer_distance / max(1, cer_len), 3),
            }
        )

    corpus_wer_d = corpus_wer_l = corpus_cer_d = corpus_cer_l = 0.0
    for category, bucket in sorted(stats.items()):
        result["categories"][category] = {
            "n": int(bucket["n"]),
            "wer": round(bucket["wer_d"] / max(1.0, bucket["wer_l"]), 4),
            "cer": round(bucket["cer_d"] / max(1.0, bucket["cer_l"]), 4),
        }
        corpus_wer_d += bucket["wer_d"]
        corpus_wer_l += bucket["wer_l"]
        corpus_cer_d += bucket["cer_d"]
        corpus_cer_l += bucket["cer_l"]
        print(
            f"  {category:22s} n={int(bucket['n']):3d} "
            f"WER {bucket['wer_d'] / max(1.0, bucket['wer_l']):.3f} "
            f"CER {bucket['cer_d'] / max(1.0, bucket['cer_l']):.3f}"
        )
    result["overall"] = {
        "n": len(selected),
        "wer": round(corpus_wer_d / max(1.0, corpus_wer_l), 4),
        "cer": round(corpus_cer_d / max(1.0, corpus_cer_l), 4),
        "rtf": round(total_process / total_audio, 4) if total_audio else None,
    }
    print(f"  overall: {result['overall']}")
    return result


def render_html(report: dict[str, Any], html_path: Path) -> None:
    engines = [e for e in report["engines"].values() if e["status"] == "ok"]
    categories = sorted({c for e in engines for c in e["categories"]})

    header = "".join(f"<th>{category}</th>" for category in categories)
    rows = []
    for engine in engines:
        cells = "".join(
            f"<td>{engine['categories'].get(category, {}).get('wer', '—')}</td>"
            for category in categories
        )
        rows.append(
            "<tr>"
            f"<td>{engine['title']}<br><span class='muted'>{engine['license']} · {engine['mode']}</span></td>"
            f"{cells}"
            f"<td><b>{engine['overall']['wer']}</b></td>"
            f"<td>{engine['overall']['cer']}</td>"
            f"<td>{engine['overall']['rtf']}</td>"
            "</tr>"
        )

    sample_blocks = []
    for engine in engines:
        items = [i for i in engine["items"] if i["category"] == "calls"][:4]
        lines = "".join(
            f"<div class='line'><span class='muted'>REF:</span> {i['text']}<br>"
            f"<span class='muted'>HYP:</span> {i['hypothesis']}</div>"
            for i in items
        )
        sample_blocks.append(f"<h3>{engine['title']}</h3>{lines}")

    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ASR benchmark — MTS Voice Agent ML</title>
<style>
 body {{ background:#0f1115; color:#e8eaf0; font:15px/1.5 -apple-system,Roboto,sans-serif; margin:0; }}
 .wrap {{ max-width:980px; margin:0 auto; padding:36px 18px 80px; }}
 h1 {{ font-size:24px; }} h2 {{ margin-top:34px; }} h3 {{ margin-bottom:6px; }}
 table {{ width:100%; border-collapse:collapse; font-size:13px; }}
 th,td {{ padding:7px 9px; border-bottom:1px solid #2a2f3a; text-align:left; vertical-align:top; }}
 .muted {{ color:#9aa3b2; font-size:12px; }}
 .line {{ margin:8px 0; padding:8px 10px; background:#171a21; border:1px solid #2a2f3a; border-radius:8px; }}
 a {{ color:#4da3ff; }}
</style></head><body><div class="wrap">
<h1>ASR benchmark: русская речь для голосового агента</h1>
<p class="muted">Сгенерировано {report['generated_at']} · {report['hardware']} ·
WER/CER корпусные (сумма правок / сумма слов), нормализация: нижний регистр, ё→е, без пунктуации.<br>
Категории: calls — реальные телефонные звонки (внутренняя оценка); clean — FLEURS ru; clean-noise — +шум 10 дБ;
synthetic-* — доменные фразы (числа/телефоны/УССД) нашим MIT-голосом.</p>
<table><tr><th>Движок</th>{header}<th>WER общий</th><th>CER</th><th>RTF</th></tr>
{''.join(rows)}
</table>
<h2>Примеры на звонках</h2>
{''.join(sample_blocks)}
<p class="muted">Стенд: синтетическая и внутренняя оценка, не production-SLA. Страница обновляется скриптом
<code>scripts/asr_benchmark.py</code>.</p>
</div></body></html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")


def hardware_note() -> str:
    import platform

    return f"CPU {platform.processor() or 'x86_64'}, onnxruntime + faster-whisper int8"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="artifacts/asr_benchmark/manifest.jsonl")
    parser.add_argument("--out", default="artifacts/asr_benchmark")
    parser.add_argument("--engines", default="", help="comma-separated engine keys")
    parser.add_argument("--limit", type=int, default=0, help="limit utterances per engine")
    parser.add_argument("--html", default="", help="optional HTML report path")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"manifest not found: {manifest_path}; run scripts/fetch_asr_testset.py first")
        return 2
    entries = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    root = manifest_path.parent

    registry = engine_registry()
    selected = (
        [registry[key] for key in args.engines.split(",") if key]
        if args.engines
        else list(registry.values())
    )

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "hardware": hardware_note(),
        "manifest": str(manifest_path),
        "engines": {},
    }
    for engine in selected:
        report["engines"][engine.key] = evaluate_engine(
            engine, entries, root, args.limit or None
        )

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    report_path = out_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport: {report_path}")

    if args.html:
        render_html(report, Path(args.html))
        print(f"html:   {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
