#!/usr/bin/env python3
"""Load hub-hosted speech runtimes so Docker bake can cache their weights.

Requires the extras from ``requirements-speech.txt`` plus CPU torch.
Used by ``apps/api/Dockerfile`` at image build; fails the build if a load fails.
"""

from __future__ import annotations

import os
import sys


def _prefetch_vad() -> None:
    from silero_vad import load_silero_vad

    load_silero_vad(onnx=False)
    print("prefetch: silero-vad ok", flush=True)


def _prefetch_asr() -> None:
    import onnx_asr

    model = os.getenv("ASR_MODEL", "t-tech/t-one")
    onnx_asr.load_model(model)
    print(f"prefetch: asr {model} ok", flush=True)


def _prefetch_stress() -> None:
    from silero_stress import load_accentor

    load_accentor()
    print("prefetch: silero-stress ok", flush=True)


def main() -> int:
    steps = (
        ("silero-vad", _prefetch_vad),
        ("asr", _prefetch_asr),
        ("silero-stress", _prefetch_stress),
    )
    for name, fn in steps:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - fail the image build
            print(f"prefetch failed ({name}): {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
