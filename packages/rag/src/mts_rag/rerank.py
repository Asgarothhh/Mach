"""Reranker protocol and optional ONNX cross-encoder (lazy onnxruntime)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Reranker(Protocol):
    model_revision: str

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        """Higher is better; values are a sigmoid in [0, 1]."""
        ...


class OnnxCrossEncoderReranker:
    """Generic ONNX cross-encoder. Enabled only when model.onnx is present."""

    model_revision: str = "onnx-cross-encoder"

    def __init__(self, model_dir: Path, *, model_revision: str | None = None) -> None:
        self._model_dir = model_dir
        if model_revision is not None:
            self.model_revision = model_revision
        self._session: Any = None
        self._tokenizer: Any = None

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        self._ensure_loaded()
        encodings = [self._tokenizer.encode(query, doc) for doc in documents]
        seq = min(512, max((len(enc.ids) for enc in encodings), default=1))
        batch = len(encodings)
        input_ids = [[0] * seq for _ in range(batch)]
        attention_mask = [[0] * seq for _ in range(batch)]
        for row, enc in enumerate(encodings):
            ids = enc.ids[:seq]
            input_ids[row][: len(ids)] = ids
            attention_mask[row][: len(ids)] = [1] * len(ids)
        feeds = self._feeds(input_ids, attention_mask)
        outputs = self._session.run(None, feeds)
        logits = outputs[0]
        scores: list[float] = []
        for row in logits:
            value = float(row[0] if hasattr(row, "__len__") else row)
            scores.append(1.0 / (1.0 + math.exp(-value)))
        return scores

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        model_path = self._model_dir / "model.onnx"
        tokenizer_path = self._model_dir / "tokenizer.json"
        if not model_path.is_file() or not tokenizer_path.is_file():
            raise RuntimeError("reranker unavailable")
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError:
            raise RuntimeError("reranker unavailable") from None
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 2
        session_options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path), sess_options=session_options, providers=["CPUExecutionProvider"]
        )
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))

    def _feeds(self, input_ids: list[list[int]], attention_mask: list[list[int]]) -> dict[str, Any]:
        import numpy as np

        names = {inp.name for inp in self._session.get_inputs()}
        feeds: dict[str, Any] = {}
        if "input_ids" in names:
            feeds["input_ids"] = np.asarray(input_ids, dtype=np.int64)
        if "attention_mask" in names:
            feeds["attention_mask"] = np.asarray(attention_mask, dtype=np.int64)
        if "token_type_ids" in names:
            feeds["token_type_ids"] = np.zeros_like(feeds["input_ids"])
        if not feeds:
            first = self._session.get_inputs()[0].name
            feeds[first] = np.asarray(input_ids, dtype=np.int64)
        return feeds
