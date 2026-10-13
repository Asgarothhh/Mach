"""ASR adapters (ML). Live onnx-asr is imported lazily."""

from __future__ import annotations

from typing import Any

from speech.asr.mock import MockASRAdapter
from speech.asr.scripted import ScriptedRecognizer

__all__ = [
    "MockASRAdapter",
    "OnnxAsrAdapter",
    "OnnxAsrConfig",
    "OnnxAsrRecognizer",
    "ScriptedRecognizer",
]


def __getattr__(name: str) -> Any:
    if name in {"OnnxAsrAdapter", "OnnxAsrConfig", "OnnxAsrRecognizer"}:
        from speech.asr.onnx_asr_adapter import OnnxAsrAdapter, OnnxAsrConfig, OnnxAsrRecognizer

        return {"OnnxAsrAdapter": OnnxAsrAdapter, "OnnxAsrConfig": OnnxAsrConfig, "OnnxAsrRecognizer": OnnxAsrRecognizer}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
