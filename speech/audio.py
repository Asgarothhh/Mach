"""PCM16 audio helpers shared by the speech adapters.

All internal audio is mono PCM16 little-endian; conversion to float32 [-1; 1]
happens only at model boundaries.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "float32_to_pcm16",
    "iter_pcm16_chunks",
    "pcm16_duration_ms",
    "pcm16_to_float32",
]

_INT16_MAX = 32767


def pcm16_to_float32(pcm_s16le: bytes) -> NDArray[np.float32]:
    """Decode PCM16-LE bytes into a mono float32 array in [-1; 1]."""
    if len(pcm_s16le) % 2 != 0:
        raise ValueError("PCM16 payload must contain an even number of bytes")
    if not pcm_s16le:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / _INT16_MAX


def float32_to_pcm16(audio: NDArray[np.floating]) -> bytes:
    """Encode a mono float32 array in [-1; 1] into PCM16-LE bytes with clipping."""
    clipped = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    return (clipped * _INT16_MAX).astype("<i2").tobytes()


def pcm16_duration_ms(pcm_s16le: bytes, sample_rate: int, channels: int = 1) -> float:
    """Duration of a PCM16 payload in milliseconds."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    samples = len(pcm_s16le) / (2 * channels)
    return samples / sample_rate * 1000.0


def iter_pcm16_chunks(
    pcm_s16le: bytes,
    *,
    sample_rate: int,
    chunk_ms: int,
    channels: int = 1,
) -> Iterator[bytes]:
    """Split a PCM16 payload into ~``chunk_ms`` slices aligned to whole frames."""
    if chunk_ms <= 0:
        raise ValueError("chunk_ms must be positive")
    bytes_per_frame = 2 * channels
    frames_per_chunk = max(1, int(sample_rate * chunk_ms / 1000))
    chunk_bytes = frames_per_chunk * bytes_per_frame
    for start in range(0, len(pcm_s16le), chunk_bytes):
        yield pcm_s16le[start : start + chunk_bytes]
