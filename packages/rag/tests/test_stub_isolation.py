from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from mts_contracts.knowledge import (
    ChunkMetadata,
    EvidenceStatus,
    FilterExclusionReason,
    IndexRevisionNotFound,
    InvalidRetrievalRequest,
    RetrievalFilters,
    RetrievalResult,
    TenantIsolationError,
)

import mts_rag.stub as stub_module
from mts_rag import InMemoryKnowledgeRetriever
from mts_rag.lexical import tokenize

ChunkFactory = Callable[..., ChunkMetadata]
RetrieverFactory = Callable[..., InMemoryKnowledgeRetriever]

TENANT_B = "other-tenant"
TEXT = "Roaming internet costs 5 BYN per day."


async def _retrieve(
    retriever: InMemoryKnowledgeRetriever,
    tenant_id: str,
    query: str = "roaming internet price per day",
    *,
    filters: RetrievalFilters | None = None,
    index_revision: str = "active",
) -> RetrievalResult:
    return await retriever.retrieve(
        query,
        tenant_id=tenant_id,
        language="en",
        audience="caller",
        filters=filters or RetrievalFilters(),
        index_revision=index_revision,
        deadline_ms=1000,
    )


def test_publish_rejects_foreign_tenant_chunk(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    own = make_chunk(chunk_id="own")
    foreign = make_chunk(chunk_id="foreign", tenant_id=TENANT_B)
    with pytest.raises(TenantIsolationError):
        retriever.publish(tenant_a, "rev-1", [own, foreign])
    retriever.publish(tenant_a, "rev-1", [own])


@pytest.mark.asyncio
async def test_publish_foreign_chunk_stores_nothing(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    with pytest.raises(TenantIsolationError):
        retriever.publish(tenant_a, "rev-1", [make_chunk(tenant_id=TENANT_B)])
    with pytest.raises(IndexRevisionNotFound):
        await _retrieve(retriever, tenant_a)


@pytest.mark.asyncio
async def test_same_text_other_tenant_never_returned(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-a", [make_chunk(chunk_id="shared", text=TEXT)])
    retriever.publish(TENANT_B, "rev-b", [make_chunk(chunk_id="shared", tenant_id=TENANT_B)])
    retriever.publish(
        TENANT_B, "rev-b2", [make_chunk(chunk_id="b-only", tenant_id=TENANT_B, text=TEXT)]
    )

    result = await _retrieve(retriever, tenant_a)

    assert result.evidence_status is EvidenceStatus.SUFFICIENT
    assert [c.metadata.tenant_id for c in result.chunks] == [tenant_a]
    assert [d.chunk_id for d in result.candidates] == ["shared"]
    assert result.applied_filters.tenant_id == tenant_a


@pytest.mark.asyncio
async def test_other_tenant_chunks_never_tokenized(
    make_chunk: ChunkFactory,
    make_retriever: RetrieverFactory,
    tenant_a: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-a", [make_chunk(chunk_id="a1")])
    retriever.publish(
        TENANT_B,
        "rev-b",
        [make_chunk(chunk_id="b1", tenant_id=TENANT_B, text="Tenant B secret roaming offer.")],
    )
    seen: list[str] = []

    def spy(text: str) -> list[str]:
        seen.append(text)
        return tokenize(text)

    monkeypatch.setattr(stub_module, "tokenize", spy)

    await _retrieve(retriever, tenant_a)

    assert seen
    assert not any("Tenant B secret" in text for text in seen)


@pytest.mark.asyncio
async def test_spoofed_chunk_id_filter_other_tenant_returns_no_evidence(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-a", [make_chunk(chunk_id="a1", document_id="a" * 64)])
    retriever.publish(
        TENANT_B,
        "rev-b",
        [make_chunk(chunk_id="b1", tenant_id=TENANT_B, document_id="f" * 64)],
    )

    result = await _retrieve(
        retriever, tenant_a, filters=RetrievalFilters(document_ids=("f" * 64,))
    )

    assert result.evidence_status is EvidenceStatus.NO_EVIDENCE
    assert result.chunks == ()
    assert result.candidates == ()
    assert result.excluded_counts == ((FilterExclusionReason.DOCUMENT_MISMATCH, 1),)


@pytest.mark.asyncio
async def test_other_tenant_revision_name_not_found_same_message(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-a", [make_chunk()])
    retriever.publish(TENANT_B, "rev-b", [make_chunk(tenant_id=TENANT_B)])

    with pytest.raises(IndexRevisionNotFound) as other_tenant:
        await _retrieve(retriever, tenant_a, index_revision="rev-b")
    with pytest.raises(IndexRevisionNotFound) as unknown:
        await _retrieve(retriever, tenant_a, index_revision="rev-missing")
    with pytest.raises(IndexRevisionNotFound) as activate_other:
        retriever.activate(tenant_a, "rev-b")

    assert str(other_tenant.value) == str(unknown.value) == str(activate_other.value)
    assert "rev-b" not in str(other_tenant.value)
    assert TENANT_B not in str(other_tenant.value)


@pytest.mark.asyncio
async def test_other_tenant_expired_chunks_do_not_affect_outdated_matches(
    make_chunk: ChunkFactory,
    make_retriever: RetrieverFactory,
    tenant_a: str,
    now: datetime,
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-a", [])
    retriever.publish(
        TENANT_B,
        "rev-b",
        [
            make_chunk(chunk_id="b-expired", tenant_id=TENANT_B, valid_to=now - timedelta(days=1)),
            make_chunk(chunk_id="b-super", tenant_id=TENANT_B, effective_status="superseded"),
        ],
    )

    result = await _retrieve(retriever, tenant_a)

    assert result.outdated_matches == 0
    assert result.excluded_counts == ()
    assert result.evidence_status is EvidenceStatus.NO_EVIDENCE


@pytest.mark.asyncio
async def test_post_check_raises_isolation_error(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-a", [make_chunk(chunk_id="a1")])
    retriever._buckets[(tenant_a, "rev-a")] = (
        make_chunk(chunk_id="a1"),
        make_chunk(chunk_id="leak", tenant_id=TENANT_B),
    )

    with pytest.raises(TenantIsolationError):
        await _retrieve(retriever, tenant_a)


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant_id", ["", "   ", "Acme-IT-demo", " acme-it-demo", "acme_it", "ab"])
async def test_empty_and_blank_tenant_invalid(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str, tenant_id: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-a", [make_chunk()])

    with pytest.raises(InvalidRetrievalRequest) as exc_info:
        await _retrieve(retriever, tenant_id)

    assert exc_info.value.fields == ("tenant_id",)


@pytest.mark.parametrize("tenant_id", ["", " ", "UPPER", "a"])
def test_publish_rejects_invalid_tenant_id(
    make_retriever: RetrieverFactory, tenant_id: str
) -> None:
    with pytest.raises(ValueError):
        make_retriever().publish(tenant_id, "rev-1", [])
