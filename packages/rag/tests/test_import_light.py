import sys
from pathlib import Path

import pytest


def test_qdrant_imports_without_onnxruntime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    sys.modules.pop("mts_rag.qdrant", None)
    sys.modules.pop("mts_rag.embeddings", None)
    sys.modules.pop("mts_rag.rerank", None)
    import mts_rag.qdrant as qdrant_mod

    assert qdrant_mod.QdrantHybridRetriever is not None
    assert Path(qdrant_mod.__file__).name == "qdrant.py"


def test_init_does_not_export_qdrant() -> None:
    import mts_rag

    assert "qdrant" not in mts_rag.__all__
    assert not hasattr(mts_rag, "QdrantHybridRetriever")
