"""Integration smoke test on real Silero TTS weights (marked ``integration``).

Run manually after fetching weights (not part of the default CI set, see
speech/README.md):

    python scripts/fetch_models.py silero-tts-v5_5_ru --output-dir models/tts
    pytest tests/speech/test_silero_tts_integration.py -m integration -s
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from speech.contracts import CancellationToken, TTSRequest

pytestmark = pytest.mark.integration

MODEL_PATH = Path(os.environ.get("SILERO_TTS_MODEL_PATH", "models/tts/v5_5_ru.pt"))


@pytest.mark.skipif(
    not MODEL_PATH.is_file(), reason="run scripts/fetch_models.py to fetch the weights"
)
def test_real_silero_tts_streams_audio_8khz() -> None:
    from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

    config = SileroTTSConfig(sample_rate=8000, speaker="xenia", max_chunk_ms=120)
    adapter = SileroTTSAdapter.from_pretrained(config, model_path=MODEL_PATH)
    req = TTSRequest(
        session_id="integration",
        turn_id="t0",
        generation_id="g0",
        segments=["Здравствуйте! *Вы* звоните по поводу тарифов?"],
    )

    async def collect() -> list:
        return [chunk async for chunk in adapter.synthesize(req, CancellationToken())]

    chunks = asyncio.run(collect())
    assert chunks
    assert chunks[0].first_chunk_ms is not None
    assert sum(len(chunk.pcm_s16le) for chunk in chunks) > 0
    assert all(chunk.sample_rate == 8000 for chunk in chunks)
