#!/usr/bin/env python3
"""TTS smoke benchmark: synthesize demo phrases, write WAVs, print latencies.

Usage:
    python scripts/fetch_models.py silero-tts-v5_5_ru --output-dir models/tts
    python scripts/tts_smoke.py --model-path models/tts/v5_5_ru.pt \
        --sample-rate 8000 --out artifacts/tts

Measures the metrics of SSOT §5.7/§11.4 for the local TTS stage:
first-chunk latency, per-segment synthesis time and real-time factor (RTF).
Inspect the produced WAVs for intelligibility, numbers, abbreviations and
question intonation ("*word*" marks the intonation center).
"""

from __future__ import annotations

import argparse
import asyncio
import time
import wave
from pathlib import Path

from speech.contracts import CancellationToken, TTSRequest
from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

DEMO_SEGMENTS = [
    "Здравствуйте! Меня зовут Анна, я виртуальный ассистент компании.",
    "*Вы* звоните по поводу стоимости услуг?",
    "Тариф стоит 100 рублей в месяц, подключение бесплатное.",
    "Соединить вас с сотрудником?",
]


async def run(args: argparse.Namespace) -> int:
    config = SileroTTSConfig(
        sample_rate=args.sample_rate,
        speaker=args.speaker,
        model_id=args.model_id,
        max_chunk_ms=args.chunk_ms,
    )
    print(f"loading model: {args.model_path or args.model_id} ({config.model_id})")
    t_load = time.perf_counter()
    adapter = SileroTTSAdapter.from_pretrained(config, model_path=args.model_path)
    print(f"model ready in {(time.perf_counter() - t_load) * 1000:.0f} ms")

    segments = args.text if args.text else DEMO_SEGMENTS
    request = TTSRequest(
        session_id="smoke",
        turn_id="t0",
        generation_id="g0",
        segments=segments,
    )

    if not args.no_warmup:
        warmup_request = TTSRequest(
            session_id="warmup", turn_id="w0", generation_id="w0", segments=["Проверка."]
        )
        t_warm = time.perf_counter()
        async for _ in adapter.synthesize(warmup_request, CancellationToken()):
            pass
        print(f"warm-up: {(time.perf_counter() - t_warm) * 1000:.0f} ms")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunk_times: list[float] = []
    segment_first_chunk_ms: dict[int, float] = {}
    pcm_per_segment: dict[int, bytearray] = {}
    started = time.perf_counter()
    first_chunk_ms: float | None = None

    async for chunk in adapter.synthesize(request, CancellationToken()):
        elapsed = (time.perf_counter() - started) * 1000.0
        chunk_times.append(elapsed)
        segment_first_chunk_ms.setdefault(chunk.segment_id, elapsed)
        pcm_per_segment.setdefault(chunk.segment_id, bytearray()).extend(chunk.pcm_s16le)
        if chunk.is_first_chunk:
            first_chunk_ms = chunk.first_chunk_ms

    total_ms = (time.perf_counter() - started) * 1000.0
    total_samples = sum(len(segment) for segment in pcm_per_segment.values()) // 2
    audio_ms = total_samples / config.sample_rate * 1000.0

    for segment_id, pcm in sorted(pcm_per_segment.items()):
        path = out_dir / f"segment_{segment_id}.wav"
        with wave.open(str(path), "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(config.sample_rate)
            fh.writeframes(bytes(pcm))
        print(f"wrote {path}")

    print()
    print("--- TTS smoke results -------------------------------------------")
    print(f"segments:          {len(segments)}")
    print(f"chunks:            {len(chunk_times)}")
    if first_chunk_ms is not None:
        print(f"first chunk:       {first_chunk_ms:.1f} ms  (SSOT target 50-150 ms warm)")
    else:
        print("first chunk:       n/a")
    for segment_id in sorted(segment_first_chunk_ms):
        print(f"  segment {segment_id} first chunk: {segment_first_chunk_ms[segment_id]:7.1f} ms")
    print(f"total synthesis:   {total_ms:.1f} ms")
    print(f"audio duration:    {audio_ms:.1f} ms")
    if audio_ms > 0:
        print(f"RTF:               {total_ms / audio_ms:.3f}  (< 1.0 means faster than realtime)")
    print(f"hardware note:     {args.note or 'record CPU/GPU model here'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", default=None, help="path to pinned .pt weights")
    parser.add_argument("--model-id", default="v5_5_ru", help="Silero model id")
    parser.add_argument("--speaker", default="xenia")
    parser.add_argument("--sample-rate", type=int, default=8000, choices=[8000, 24000, 48000])
    parser.add_argument("--chunk-ms", type=int, default=120)
    parser.add_argument("--out", default="artifacts/tts")
    parser.add_argument("--note", default="", help="hardware/benchmark note")
    parser.add_argument(
        "--no-warmup", action="store_true", help="skip the warm-up synthesis"
    )
    parser.add_argument("--text", action="append", help="custom segment (repeatable)")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
