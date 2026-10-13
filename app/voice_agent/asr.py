"""Shared ASR recognizer for the voice agent (ML side of the junction).

T-one (Apache-2.0, streaming telephony model) runs through the onnx-asr
runtime; the recognizer is process-wide because loading the ONNX model is
expensive. T-one has no working CUDA path on this stack (unsupported
depthwise convolution in onnxruntime's cuDNN frontend), so the default
device is CPU — it is fast enough for the segment pipeline (RTF ~0.06 on the
demo machine).

Override with env: ``ASR_MODEL`` (default ``t-tech/t-one``),
``ASR_DEVICE`` (``cpu`` / ``cuda`` / ``auto``).
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from speech.asr.onnx_asr_adapter import OnnxAsrRecognizer

__all__ = ["get_recognizer"]

_recognizer: OnnxAsrRecognizer | None = None
_lock = threading.Lock()


def get_recognizer() -> OnnxAsrRecognizer:
    global _recognizer
    if _recognizer is None:
        with _lock:
            if _recognizer is None:
                from speech.asr.onnx_asr_adapter import OnnxAsrRecognizer

                model = os.getenv("ASR_MODEL", "t-tech/t-one")
                device = os.getenv("ASR_DEVICE", "cpu")
                _recognizer = OnnxAsrRecognizer(model, device=device)
    return _recognizer
