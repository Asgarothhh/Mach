#!/usr/bin/env python3
"""Build the Russian ASR test set for the voice-agent benchmark (ML evaluation).

Categories (approximate counts, see --help):
    calls                 real telephone recordings (OpenSTT calls mirror)
    clean                 clean read speech (FLEURS ru dev, CC-BY-4.0)
    clean-noise           the same clean speech + additive pink noise (~10 dB SNR)
    synthetic-telephony   domain phrases via our MIT Silero voice, 8 kHz
    synthetic-clean       the same domain phrases at 16 kHz

Usage:
    .venv/bin/python scripts/fetch_asr_testset.py --out artifacts/asr_benchmark

Provenance and licenses (also written into the generated README.md):
    * ``Malecc/asr_calls_2_val`` — mirror of the OpenSTT telephone calls; the
      upstream license is NOT stated in the dataset card, so this category is
      for INTERNAL EVALUATION ONLY: never redistribute the audio and never
      commit it to the repository (``artifacts/`` is gitignored).
    * ``google/fleurs`` ru config — CC-BY-4.0 (attribution: Google FLEURS).
    * Synthetic phrases are generated locally with MIT-licensed models
      (Silero v5_cis_base_nostress + silero-stress).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import random
import tarfile
import wave
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
import soxr
from huggingface_hub import hf_hub_download

RNG = random.Random(42)
SAMPLE_RATE = 16000

DOMAIN_PHRASES: list[str] = [
    "Здравствуйте! Меня зовут Анна, я виртуальный ассистент компании.",
    "Подскажите, пожалуйста, сколько стоит подключение?",
    "Тариф стоит 100 рублей в месяц, подключение бесплатное.",
    "Скидка 19,90 руб. действует 14 дней.",
    "Позвоните нам по номеру +375 17 237-98-98.",
    "Для проверки баланса наберите *111*4#.",
    "Стоимость услуги 1 000 рублей в месяц.",
    "Домашний интернет и телевидение подключим за один день.",
    "Оставьте заявку на сайте компании.",
    "Старинный замок возвышается на холме.",
    "Он закрыл дверь на замок и ушёл.",
    "Пшеничная мука рассыпалась по столу.",
]


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------


def read_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    return audio.mean(axis=1).astype(np.float32), int(sample_rate)


def resample(audio: np.ndarray, rate_from: int, rate_to: int) -> np.ndarray:
    if rate_from == rate_to:
        return audio.astype(np.float32)
    return soxr.resample(audio, rate_from, rate_to, quality="HQ").astype(np.float32)


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(pcm.tobytes())


def pink_noise(size: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(size)
    spectrum = np.fft.rfft(white)
    freqs = np.linspace(1.0, size / 2, len(spectrum))
    spectrum = spectrum / np.sqrt(freqs)
    noise = np.fft.irfft(spectrum, size)
    return (noise / (np.abs(noise).max() + 1e-9)).astype(np.float32)


def add_noise(signal: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    signal_power = float(np.mean(signal**2)) + 1e-12
    noise = pink_noise(len(signal), rng)
    noise *= np.sqrt((signal_power / (10 ** (snr_db / 10))) / (float(np.mean(noise**2)) + 1e-12))
    return np.clip(signal + noise, -1.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def fetch_calls(out_dir: Path, count: int) -> list[dict]:
    rows: list[dict] = []
    for split_file in (
        "data/test-00000-of-00001.parquet",
        "data/validation-00000-of-00001.parquet",
    ):
        path = hf_hub_download(
            "Malecc/asr_calls_2_val", split_file, repo_type="dataset"
        )
        rows.extend(pq.read_table(path).to_pylist())

    usable = [
        row
        for row in rows
        if 2.0 <= float(row.get("duration") or 0.0) <= 12.0
        and (row.get("text") or "").strip()
        and row.get("audio")
    ]
    RNG.shuffle(usable)

    entries: list[dict] = []
    for index, row in enumerate(usable[:count]):
        audio, rate = read_wav_bytes(row["audio"]["bytes"])
        audio = resample(audio, rate, SAMPLE_RATE)
        name = f"call_{index:03d}"
        write_wav(out_dir / "audio" / "calls" / f"{name}.wav", audio, SAMPLE_RATE)
        entries.append(
            {
                "id": name,
                "audio": f"audio/calls/{name}.wav",
                "text": (row.get("text") or "").strip(),
                "category": "calls",
                "source": "OpenSTT calls (Malecc/asr_calls_2_val mirror)",
                "duration": round(len(audio) / SAMPLE_RATE, 2),
            }
        )
    return entries


def fetch_fleurs(out_dir: Path, clean_count: int, noise_count: int) -> list[dict]:
    tsv_path = hf_hub_download("google/fleurs", "data/ru_ru/dev.tsv", repo_type="dataset")
    tar_path = hf_hub_download(
        "google/fleurs", "data/ru_ru/audio/dev.tar.gz", repo_type="dataset"
    )

    mapping: dict[str, dict] = {}
    with open(tsv_path, encoding="utf-8") as fh:
        # FLEURS TSVs are header-less: id, filename, transcription, transcription
        # (lowercase), char-separated transcription, samples, gender.
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            row = {
                "id": parts[0],
                "filename": parts[1],
                "transcription": parts[2],
                "transcription_lower": parts[3],
            }
            mapping[Path(row["filename"]).name] = row

    picked: list[tuple[str, str, np.ndarray]] = []
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".wav"):
                continue
            row = mapping.get(Path(member.name).name)
            if row is None:
                continue
            fileobj = tar.extractfile(member)
            if fileobj is None:
                continue
            audio, rate = read_wav_bytes(fileobj.read())
            if rate != SAMPLE_RATE:
                audio = resample(audio, rate, SAMPLE_RATE)
            duration = len(audio) / SAMPLE_RATE
            if not 1.5 <= duration <= 15.0:
                continue
            text = (row.get("transcription") or row.get("raw_transcription") or "").strip()
            if not text:
                continue
            picked.append((Path(member.name).stem, text, audio))
            if len(picked) >= clean_count + noise_count:
                break

    RNG.shuffle(picked)
    entries: list[dict] = []
    for index, (_stem, text, audio) in enumerate(picked[:clean_count]):
        name = f"fleurs_{index:03d}"
        write_wav(out_dir / "audio" / "clean" / f"{name}.wav", audio, SAMPLE_RATE)
        entries.append(
            {
                "id": name,
                "audio": f"audio/clean/{name}.wav",
                "text": text,
                "category": "clean",
                "source": "FLEURS ru dev (CC-BY-4.0, Google)",
                "duration": round(len(audio) / SAMPLE_RATE, 2),
            }
        )
    for index, (_stem, text, audio) in enumerate(
        picked[clean_count : clean_count + noise_count]
    ):
        noisy = add_noise(audio, 10.0, np.random.default_rng(1000 + index))
        name = f"fleurs_noise_{index:03d}"
        write_wav(out_dir / "audio" / "clean-noise" / f"{name}.wav", noisy, SAMPLE_RATE)
        entries.append(
            {
                "id": name,
                "audio": f"audio/clean-noise/{name}.wav",
                "text": text,
                "category": "clean-noise",
                "source": "FLEURS ru dev + pink noise 10 dB (synthetic augmentation)",
                "duration": round(len(audio) / SAMPLE_RATE, 2),
            }
        )
    return entries


async def _synthesize_phrase(adapter: object, phrase: str) -> tuple[np.ndarray, str]:
    """Synthesize one phrase, return (audio float32, spoken text) for the ref."""
    from speech.contracts import CancellationToken, TTSRequest

    request = TTSRequest(
        session_id="asr-testset", turn_id="0", generation_id="g0", segments=[phrase]
    )
    pcm = bytearray()
    spoken = ""
    async for chunk in adapter.synthesize(request, CancellationToken()):  # type: ignore[attr-defined]
        if not spoken:
            spoken = chunk.text
        pcm.extend(chunk.pcm_s16le)
    audio = np.frombuffer(bytes(pcm), dtype="<i2").astype(np.float32) / 32767.0
    return audio, spoken


def fetch_synthetic(out_dir: Path) -> list[dict]:
    from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

    config = SileroTTSConfig(
        model_id="v5_cis_base_nostress",
        speaker="ru_ekaterina",
        sample_rate=24000,
        supports_question_intonation=False,
    )
    adapter = SileroTTSAdapter.from_pretrained(
        config, model_path="models/tts/v5_cis_base_nostress.pt", stress=True
    )

    entries: list[dict] = []
    for index, phrase in enumerate(DOMAIN_PHRASES):
        audio, spoken = asyncio.run(_synthesize_phrase(adapter, phrase))

        for rate_out, category in ((8000, "synthetic-telephony"), (16000, "synthetic-clean")):
            name = f"synth_{index:02d}_{rate_out // 1000}k"
            write_wav(
                out_dir / "audio" / category / f"{name}.wav",
                resample(audio, config.sample_rate, rate_out),
                rate_out,
            )
            entries.append(
                {
                    "id": name,
                    "audio": f"audio/{category}/{name}.wav",
                    "text": spoken,
                    "category": category,
                    "source": "synthetic: Silero v5_cis_base_nostress + silero-stress (MIT)",
                    "duration": round(len(audio) / rate_out, 2),
                }
            )
    return entries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/asr_benchmark")
    parser.add_argument("--calls", type=int, default=110)
    parser.add_argument("--clean", type=int, default=60)
    parser.add_argument("--noise", type=int, default=40)
    args = parser.parse_args()

    out_dir = Path(args.out)
    entries: list[dict] = []
    print("fetching OpenSTT telephone calls ...")
    entries += fetch_calls(out_dir, args.calls)
    print(f"  calls: {len(entries)}")
    before = len(entries)
    print("fetching FLEURS ru (clean + noisy) ...")
    entries += fetch_fleurs(out_dir, args.clean, args.noise)
    print(f"  clean/noise: {len(entries) - before}")
    before = len(entries)
    print("synthesizing domain phrases (MIT voice) ...")
    entries += fetch_synthetic(out_dir)
    print(f"  synthetic: {len(entries) - before}")

    manifest_path = out_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    categories: dict[str, int] = {}
    for entry in entries:
        categories[entry["category"]] = categories.get(entry["category"], 0) + 1
    total_duration = sum(float(entry["duration"]) for entry in entries)

    readme = out_dir / "README.md"
    readme.write_text(
        "# Russian ASR test set (voice agent, ML evaluation)\n\n"
        f"Built by `scripts/fetch_asr_testset.py`, manifest: `manifest.jsonl`.\n\n"
        f"- utterances: {len(entries)} (~{total_duration / 60:.1f} min of audio)\n"
        + "".join(f"- {name}: {count}\n" for name, count in sorted(categories.items()))
        + "\n## Licenses / provenance\n\n"
        "- `calls` — mirror of OpenSTT telephone calls (`Malecc/asr_calls_2_val`):\n"
        "  upstream license NOT stated in the dataset card → **internal evaluation only**,\n"
        "  do not redistribute or commit the audio.\n"
        "- `clean`, `clean-noise` — FLEURS ru dev (CC-BY-4.0, Google) + pink-noise\n"
        "  augmentation generated locally.\n"
        "- `synthetic-*` — generated locally with MIT-licensed models\n"
        "  (Silero v5_cis_base_nostress + silero-stress, voice `ru_ekaterina`).\n",
        encoding="utf-8",
    )

    print(f"\nmanifest: {manifest_path}")
    print(f"total: {len(entries)} utterances, {total_duration / 60:.1f} min")
    for name, count in sorted(categories.items()):
        print(f"  {name:22s} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
