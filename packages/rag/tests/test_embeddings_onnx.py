from pathlib import Path

import pytest

_ONNX_DIR = Path(__file__).resolve().parents[3] / "models" / "rag" / "bge-m3-onnx"


@pytest.mark.integration
@pytest.mark.skipif(not _ONNX_DIR.exists(), reason="models/rag/bge-m3-onnx is not present")
def test_onnx_embedder_ru_paraphrase_outscores_unrelated() -> None:
    from mts_rag.embeddings import OnnxDenseEmbedder

    embedder = OnnxDenseEmbedder(_ONNX_DIR)
    query, paraphrase, unrelated = embedder.embed(
        [
            "сколько стоит роуминг",
            "какова цена роуминга",
            "рецепт борща",
        ],
        kind="query",
    )
    assert len(query) == 1024
    qn = sum(value * value for value in query) ** 0.5
    assert abs(qn - 1.0) < 0.05

    def cosine(left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=True))

    assert cosine(query, paraphrase) > cosine(query, unrelated)
