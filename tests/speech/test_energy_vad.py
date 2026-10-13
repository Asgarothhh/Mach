from __future__ import annotations

import asyncio

import numpy as np

from speech.audio import float32_to_pcm16
from speech.contracts import AudioFrame, VADEventType
from speech.vad.energy import energy_probability
from speech.vad.silero_vad import SileroVADAdapter, VADConfig


def test_energy_probability_silence_and_tone():
    silence = np.zeros(512, dtype=np.float32)
    tone = (0.3 * np.sin(np.linspace(0, 8 * np.pi, 512))).astype(np.float32)
    assert energy_probability(silence, 16000) == 0.0
    assert energy_probability(tone, 16000) >= 0.9
    assert energy_probability(np.zeros(0, dtype=np.float32), 16000) == 0.0


def test_energy_vad_emits_start_and_end():
    config = VADConfig(
        min_speech_duration_ms=64,
        min_silence_duration_ms=64,
        prefix_padding_ms=32,
    )
    adapter = SileroVADAdapter(energy_probability, config)
    frames = []
    for index in range(16):
        if 3 <= index < 10:
            samples = (0.3 * np.sin(np.linspace(0, 8 * np.pi, 512))).astype(np.float32)
        else:
            samples = np.zeros(512, dtype=np.float32)
        frames.append(
            AudioFrame(
                session_id="s1",
                seq=index,
                timestamp_ms=index * 32,
                sample_rate=16000,
                pcm_s16le=float32_to_pcm16(samples),
            )
        )

    async def collect():
        async def agen():
            for frame in frames:
                yield frame

        return [event async for event in adapter.stream(agen())]

    events = asyncio.run(collect())
    types = [event.type for event in events]
    assert VADEventType.SPEECH_START in types
    assert VADEventType.SPEECH_END in types
