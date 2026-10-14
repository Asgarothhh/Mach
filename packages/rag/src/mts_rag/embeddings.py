"""Dense embedder protocol and optional ONNX BGE-M3 adapter (lazy onnxruntime)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable


@runtime_checkable
class DenseEmbedder(Protocol):
    vector_name: str
    dim: int
    model_revision: str

    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]: ...


class OnnxDenseEmbedder:
    """BGE-M3 ONNX, loaded lazily. Missing weights make embed() fail; callers degrade."""

    vector_name: str = "dense_bge_m3_v1"
    dim: int = 1024
    model_revision: str = "bge-m3-onnx"

    def __init__(self, model_dir: Path) -> None:
        self._model_dir = model_dir
        self._session: Any = None
        self._tokenizer: Any = None

    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]:
        self._ensure_loaded()
        max_length = 64 if kind == "query" else 1024
        encodings = [self._tokenizer.encode(text) for text in texts]
        batch = len(encodings)
        seq = min(max_length, max((len(enc.ids) for enc in encodings), default=1))
        input_ids = [[0] * seq for _ in range(batch)]
        attention_mask = [[0] * seq for _ in range(batch)]
        for row, enc in enumerate(encodings):
            ids = enc.ids[:seq]
            input_ids[row][: len(ids)] = ids
            attention_mask[row][: len(ids)] = [1] * len(ids)
        feeds = self._feeds(input_ids, attention_mask)
        outputs = self._session.run(None, feeds)
        pooled = _pool_and_normalize(outputs[0])
        return pooled

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        model_path = self._model_dir / "model.onnx"
        tokenizer_path = self._model_dir / "tokenizer.json"
        if not model_path.is_file() or not tokenizer_path.is_file():
            raise RuntimeError("embedder unavailable")
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError:
            raise RuntimeError("embedder unavailable") from None
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 4
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


def _pool_and_normalize(raw: Any) -> list[list[float]]:
    import numpy as np

    array = np.asarray(raw, dtype=np.float32)
    if array.ndim == 3:
        array = array[:, 0, :]
    elif array.ndim != 2:
        raise RuntimeError("embedder unavailable")
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    array = array / norms
    return [[float(value) for value in row] for row in array.astype(np.float64)]
