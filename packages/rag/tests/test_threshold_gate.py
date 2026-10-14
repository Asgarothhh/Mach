from mts_rag.qdrant import QdrantRetrieverSettings


def test_demo_thresholds_match_lockfile_defaults() -> None:
    settings = QdrantRetrieverSettings()
    assert settings.min_term_coverage == 0.5
    assert settings.min_dense_score == 0.55
    assert settings.min_rerank_score == 0.5
    assert settings.embed_timeout_ms == 180
