"""Real TTS for the voice agent (ML side of the junction).

Silero v5 CIS-base (MIT) + silero-stress (MIT), voice ``ru_bogdan`` — the
best MOS of the permitted shortlist in our benchmark (43 ms first chunk,
RTF ~0.017 on the demo CPU). Weights are expected under ``models/tts/``
(see ``scripts/fetch_models.py``); override with ``TTS_MODEL_PATH``,
``TTS_VOICE``, ``TTS_SAMPLE_RATE``.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from speech.tts.silero_tts import SileroTTSAdapter, SileroTTSConfig

__all__ = ["get_tts_adapter"]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MODEL = _REPO_ROOT / "models" / "tts" / "v5_cis_base_nostress.pt"

_adapter: SileroTTSAdapter | None = None
_lock = threading.Lock()


def get_tts_adapter() -> SileroTTSAdapter:
    """Lazy process-wide adapter; raises SpeechError(model_unavailable) if weights are missing."""
    global _adapter
    if _adapter is None:
        with _lock:
            if _adapter is None:
                config = SileroTTSConfig(
                    model_id="v5_cis_base_nostress",
                    speaker=os.getenv("TTS_VOICE", "ru_bogdan"),
                    sample_rate=int(os.getenv("TTS_SAMPLE_RATE", "24000")),
                    supports_question_intonation=False,
                )
                model_path = Path(os.getenv("TTS_MODEL_PATH", str(_DEFAULT_MODEL)))
                _adapter = SileroTTSAdapter.from_pretrained(
                    config, model_path=model_path, stress=True
                )
    return _adapter
