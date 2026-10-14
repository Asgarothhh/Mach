import asyncio
from collections.abc import Sequence
from typing import Literal

import pytest
from mts_contracts.knowledge import RetrievalFilters, RetrievalMode, RetrievalUnavailable
from mts_rag.qdrant import QdrantHybridRetriever
from mts_rag.testing import FailingEmbedder, HashingFakeEmbedder, InMemoryQdrantGateway, SlowEmbedder

from app.rag.demo_fixtures import acme_chunks
from app.rag.retriever import build_knowledge_runtime, seed_revision
from tests.conftest import (
    ACME_ASKING_MTS_QUERY,
    ACME_SUFFICIENT_QUERY,
    NO_EVIDENCE_QUERY,
    bind_session,
    make_orchestrator,
)


async def _wait_seed(runtime, *, timeout: float = 3.0) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            details = await runtime.knowledge_checks()
            if details["seed"] == "ok":
                return details
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_start_seeds_both_tenants_and_restart_same_revision():
    gateway = InMemoryQdrantGateway()
    embedder = HashingFakeEmbedder()
    environ = {
        "QDRANT_URL": "http://qdrant.test",
        "EMBEDDING_MODEL_ID": "none",
        "RERANKER_MODEL_ID": "none",
    }
    runtime = build_knowledge_runtime(environ, gateway=gateway, embedder=embedder)
    await runtime.start()
    details = await _wait_seed(runtime)
    assert details["backend"] == "qdrant"
    probe = await runtime.probe()
    assert probe["acme-it-demo"] == "ok"
    assert probe["mts-public-demo"] == "ok"
    first = await runtime.retriever.retrieve(
        ACME_SUFFICIENT_QUERY,
        tenant_id="acme-it-demo",
        language="ru",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=1000,
    )
    expected = seed_revision(acme_chunks(), embedder=embedder)
    assert first.index_revision == expected
    await runtime.close()

    runtime2 = build_knowledge_runtime(environ, gateway=gateway, embedder=embedder)
    await runtime2.start()
    await _wait_seed(runtime2)
    second = await runtime2.retriever.retrieve(
        ACME_SUFFICIENT_QUERY,
        tenant_id="acme-it-demo",
        language="ru",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=1000,
    )
    assert second.index_revision == first.index_revision
    await runtime2.close()


class _CountingFailingEmbedder(FailingEmbedder):
    def __init__(self) -> None:
        self.calls = 0

    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]:
        self.calls += 1
        return super().embed(texts, kind=kind)


@pytest.mark.asyncio
async def test_failed_embed_warmup_fingerprints_sparse_then_new_hybrid_revision():
    gateway = InMemoryQdrantGateway()
    failing = _CountingFailingEmbedder()
    environ = {
        "QDRANT_URL": "http://qdrant.test",
        "EMBEDDING_MODEL_ID": "none",
        "RERANKER_MODEL_ID": "none",
    }
    runtime = build_knowledge_runtime(environ, gateway=gateway, embedder=failing)
    await runtime.start()
    details = await _wait_seed(runtime)
    assert details["seed"] == "ok"
    assert details["embedder"] == "unavailable"
    assert details["expected_mode"] == "sparse_only"
    warmup_calls = failing.calls
    assert warmup_calls >= 1
    sparse_revision = seed_revision(acme_chunks(), embedder=None)
    first = await runtime.retriever.retrieve(
        ACME_SUFFICIENT_QUERY,
        tenant_id="acme-it-demo",
        language="ru",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=1000,
    )
    assert first.index_revision == sparse_revision
    assert first.retrieval_mode is RetrievalMode.SPARSE_ONLY
    assert failing.calls == warmup_calls
    assert isinstance(runtime.retriever, QdrantHybridRetriever)
    runtime.retriever.set_embedder(HashingFakeEmbedder())
    await runtime.close()

    working = HashingFakeEmbedder()
    runtime2 = build_knowledge_runtime(environ, gateway=gateway, embedder=working)
    await runtime2.start()
    await _wait_seed(runtime2)
    hybrid_revision = seed_revision(acme_chunks(), embedder=working)
    assert hybrid_revision != sparse_revision
    second = await runtime2.retriever.retrieve(
        ACME_SUFFICIENT_QUERY,
        tenant_id="acme-it-demo",
        language="ru",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=1000,
    )
    assert second.index_revision == hybrid_revision
    assert second.retrieval_mode is RetrievalMode.HYBRID
    aliases = await gateway.get_aliases()
    assert any(
        item["alias_name"] == "kb__acme-it-demo__active"
        and item["collection_name"].endswith(hybrid_revision)
        for item in aliases
    )
    dense_info = await gateway.get_collection(f"kb__acme-it-demo__{hybrid_revision}")
    assert working.vector_name in dense_info["config"]["params"]["vectors"]
    sparse_info = await gateway.get_collection(f"kb__acme-it-demo__{sparse_revision}")
    assert sparse_info["config"]["params"]["vectors"] == {}
    await runtime2.close()


@pytest.mark.asyncio
async def test_slow_embedder_does_not_block_sparse_seed(monkeypatch):
    monkeypatch.setattr("app.rag.retriever._EMBED_WARMUP_TIMEOUT_S", 0.05)
    gateway = InMemoryQdrantGateway()
    runtime = build_knowledge_runtime(
        {"QDRANT_URL": "http://qdrant.test"},
        gateway=gateway,
        embedder=SlowEmbedder(delay_s=5.0),
    )
    await runtime.start()
    details = await _wait_seed(runtime)
    assert details["seed"] == "ok"
    assert details["embedder"] == "unavailable"
    assert details["expected_mode"] == "sparse_only"
    probe = await runtime.probe()
    assert probe["acme-it-demo"] == "ok"
    assert probe["mts-public-demo"] == "ok"
    result = await runtime.retriever.retrieve(
        ACME_SUFFICIENT_QUERY,
        tenant_id="acme-it-demo",
        language="ru",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=1000,
    )
    assert result.index_revision == seed_revision(acme_chunks(), embedder=None)
    assert result.retrieval_mode is RetrievalMode.SPARSE_ONLY
    await runtime.close()


class _DocumentFailEmbedder(HashingFakeEmbedder):
    def embed(
        self, texts: Sequence[str], *, kind: Literal["query", "document"]
    ) -> list[list[float]]:
        if kind == "document":
            raise RuntimeError("document embed failed")
        return super().embed(texts, kind=kind)


@pytest.mark.asyncio
async def test_hybrid_publish_failure_keeps_sparse_alias():
    gateway = InMemoryQdrantGateway()
    runtime = build_knowledge_runtime(
        {"QDRANT_URL": "http://qdrant.test"},
        gateway=gateway,
        embedder=_DocumentFailEmbedder(),
    )
    await runtime.start()
    details = await _wait_seed(runtime)
    assert details["seed"] == "ok"
    assert details["expected_mode"] == "sparse_only"
    probe = await runtime.probe()
    assert probe["mts-public-demo"] == "ok"
    result = await runtime.retriever.retrieve(
        ACME_SUFFICIENT_QUERY,
        tenant_id="acme-it-demo",
        language="ru",
        audience="caller",
        filters=RetrievalFilters(),
        index_revision="active",
        deadline_ms=1000,
    )
    assert result.retrieval_mode is RetrievalMode.SPARSE_ONLY
    await runtime.close()


@pytest.mark.asyncio
async def test_gateway_down_unavailable_then_recovers():
    gateway = InMemoryQdrantGateway()
    gateway.down = True
    embedder = HashingFakeEmbedder()
    runtime = build_knowledge_runtime(
        {"QDRANT_URL": "http://qdrant.test"},
        gateway=gateway,
        embedder=embedder,
    )
    await runtime.start()
    await asyncio.sleep(0.05)
    details = await runtime.knowledge_checks()
    assert details["seed"] in {"pending", "failed"}
    probe = await runtime.probe()
    assert all(value == "unavailable" for value in probe.values())
    with pytest.raises(RetrievalUnavailable):
        await runtime.retriever.retrieve(
            ACME_SUFFICIENT_QUERY,
            tenant_id="acme-it-demo",
            language="ru",
            audience="caller",
            filters=RetrievalFilters(),
            index_revision="active",
            deadline_ms=1000,
        )
    gateway.down = False
    await _wait_seed(runtime, timeout=5.0)
    probe = await runtime.probe()
    assert probe["acme-it-demo"] == "ok"
    await runtime.close()


@pytest.mark.asyncio
async def test_orchestrator_grounded_and_abstain(counting_llm):
    gateway = InMemoryQdrantGateway()
    embedder = HashingFakeEmbedder()
    runtime = build_knowledge_runtime(
        {"QDRANT_URL": "http://qdrant.test"},
        gateway=gateway,
        embedder=embedder,
    )
    await runtime.start()
    await _wait_seed(runtime)
    orch, manager, _store, _llm = make_orchestrator(runtime.retriever, llm=counting_llm)
    bind_session(manager, tenant_id="acme-it-demo")
    grounded = await orch.run_turn("s1", ACME_SUFFICIENT_QUERY, channel="text")
    assert grounded.answer_status == "grounded"
    bind_session(manager, session_id="s2", tenant_id="acme-it-demo")
    none = await orch.run_turn("s2", NO_EVIDENCE_QUERY, channel="text")
    assert none.answer_status == "no_evidence"
    bind_session(manager, session_id="s3", tenant_id="acme-it-demo")
    cross = await orch.run_turn("s3", ACME_ASKING_MTS_QUERY, channel="text")
    assert cross.answer_status == "no_evidence"
    await runtime.close()
