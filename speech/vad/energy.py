"""RMS-energy speech probability for the mock/demo VAD path.

Reuses ``SileroVADAdapter`` endpointing; this module only supplies a
torch-free probability function so the API image can run without ``[vad]``.
"""

from __future__ import annotations

import numpy as np

__all__ = ["energy_probability"]

_FLOOR = 0.005
_SPAN = 0.04


def energy_probability(frame: np.ndarray, sample_rate: int) -> float:
    """Map window RMS energy to a speech probability in ``[0, 1]``."""
    del sample_rate
    if frame.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(frame.astype(np.float64)))))
    return float(np.clip((rms - _FLOOR) / _SPAN, 0.0, 1.0))
