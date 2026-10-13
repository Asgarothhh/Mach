import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from mts_contracts.knowledge import (
    Audience,
    ChunkMetadata,
    ConflictReason,
    EffectiveStatus,
    EvidenceStatus,
    FilterExclusionReason,
    IndexRevisionNotFound,
    InvalidRetrievalRequest,
    KnowledgeRetriever,
    RetrievalConfig,
    RetrievalFilters,
    RetrievalMode,
    RetrievalResult,
    SourceType,
    StaleReason,
)

from mts_rag import InMemoryKnowledgeRetriever, LexicalStubSettings

ChunkFactory = Callable[..., ChunkMetadata]
RetrieverFactory = Callable[..., InMemoryKnowledgeRetriever]

_: KnowledgeRetriever = InMemoryKnowledgeRetriever()

QUERY = "roaming internet price per day"


async def _retrieve(
    retriever: InMemoryKnowledgeRetriever,
    tenant_id: str,
    query: str = QUERY,
    **overrides: Any,
) -> RetrievalResult:
    arguments: dict[str, Any] = {
        "language": "en",
        "audience": "caller",
        "filters": RetrievalFilters(),
        "index_revision": "active",
        "deadline_ms": 1000,
    }
    arguments.update(overrides)
    return await retriever.retrieve(query, tenant_id=tenant_id, **arguments)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"language": "EN"}, "language"),
        ({"language": "english"}, "language"),
        ({"language": ""}, "language"),
        ({"audience": "public"}, "audience"),
        ({"audience": ""}, "audience"),
        ({"deadline_ms": 0}, "deadline_ms"),
        ({"deadline_ms": -1}, "deadline_ms"),
        ({"deadline_ms": 60_001}, "deadline_ms"),
        ({"deadline_ms": True}, "deadline_ms"),
        ({"deadline_ms": 100.0}, "deadline_ms"),
        ({"index_revision": ""}, "index_revision"),
        ({"index_revision": "rev 1"}, "index_revision"),
        ({"filters": {"services": ["roaming"]}}, "filters"),
        ({"query": ""}, "query"),
        ({"query": "   \n\t "}, "query"),
        ({"query": "x" * 1001}, "query"),
    ],
)
async def test_invalid_language_audience_deadline_query(
    make_chunk: ChunkFactory,
    make_retriever: RetrieverFactory,
    tenant_a: str,
    overrides: dict[str, Any],
    field: str,
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [make_chunk()])
    query = overrides.pop("query", QUERY)

    with pytest.raises(InvalidRetrievalRequest) as exc_info:
        await _retrieve(retriever, tenant_a, query, **overrides)

    assert exc_info.value.fields == (field,)


@pytest.mark.asyncio
async def test_invalid_request_error_omits_query(
    make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    personal_text = "my phone is +375291234567 "
    retriever = make_retriever()

    with pytest.raises(InvalidRetrievalRequest) as exc_info:
        await _retrieve(retriever, tenant_a, personal_text * 100, language="??")

    error = exc_info.value
    assert set(error.fields) == {"query", "language"}
    for rendered in (str(error), repr(error), repr(error.args)):
        assert "375291234567" not in rendered
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.asyncio
async def test_query_whitespace_normalized_into_variants(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [make_chunk()])

    result = await _retrieve(retriever, tenant_a, "  quokka \n zebra\troaming  ")

    assert result.query_variants == ("quokka zebra roaming",)
    assert "quokka" not in repr(result)


@pytest.mark.asyncio
async def test_active_alias_resolves_to_concrete(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [make_chunk(chunk_id="old")])
    retriever.publish(tenant_a, "rev-2", [make_chunk(chunk_id="new")], activate=False)

    assert (await _retrieve(retriever, tenant_a)).index_revision == "rev-1"
    pinned = await _retrieve(retriever, tenant_a, index_revision="rev-2")
    assert pinned.index_revision == "rev-2"
    assert [c.metadata.chunk_id for c in pinned.chunks] == ["new"]

    retriever.activate(tenant_a, "rev-2")
    result = await _retrieve(retriever, tenant_a)
    assert result.index_revision == "rev-2"
    assert [c.metadata.chunk_id for c in result.chunks] == ["new"]


@pytest.mark.asyncio
async def test_unknown_revision_raises(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    with pytest.raises(IndexRevisionNotFound) as no_tenant:
        await _retrieve(retriever, tenant_a)

    retriever.publish(tenant_a, "rev-1", [make_chunk()], activate=False)
    with pytest.raises(IndexRevisionNotFound) as no_active:
        await _retrieve(retriever, tenant_a)
    with pytest.raises(IndexRevisionNotFound) as unknown:
        await _retrieve(retriever, tenant_a, index_revision="rev-9")
    with pytest.raises(IndexRevisionNotFound):
        retriever.activate(tenant_a, "rev-9")

    assert str(no_tenant.value) == str(no_active.value) == str(unknown.value)


def test_revisions_immutable(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [make_chunk()])
    with pytest.raises(ValueError, match="immutable"):
        retriever.publish(tenant_a, "rev-1", [make_chunk(chunk_id="other")])
    with pytest.raises(ValueError, match="duplicate"):
        retriever.publish(tenant_a, "rev-2", [make_chunk(), make_chunk()])


def test_reserved_active_name(make_retriever: RetrieverFactory, tenant_a: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        make_retriever().publish(tenant_a, "active", [])


@pytest.mark.asyncio
async def test_snapshot_consistent_under_concurrent_activate(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [make_chunk(chunk_id="r1-a"), make_chunk(chunk_id="r1-b")])
    retriever.publish(tenant_a, "rev-2", [make_chunk(chunk_id="r2-a")], activate=False)

    task = asyncio.create_task(_retrieve(retriever, tenant_a))
    await asyncio.sleep(0)
    retriever.activate(tenant_a, "rev-2")
    result = await task

    assert result.index_revision == "rev-1"
    assert {d.chunk_id for d in result.candidates} == {"r1-a", "r1-b"}
    assert (await _retrieve(retriever, tenant_a)).index_revision == "rev-2"


@pytest.mark.asyncio
async def test_empty_index_no_evidence(make_retriever: RetrieverFactory, tenant_a: str) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [])

    result = await _retrieve(retriever, tenant_a)

    assert result.evidence_status is EvidenceStatus.NO_EVIDENCE
    assert result.chunks == ()
    assert result.candidates == ()
    assert result.top_score is None
    assert not result.is_answerable


@pytest.mark.asyncio
async def test_no_overlap_no_evidence(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [make_chunk()])

    result = await _retrieve(retriever, tenant_a, "television subscription")

    assert result.evidence_status is EvidenceStatus.NO_EVIDENCE
    assert result.candidates == ()


@pytest.mark.asyncio
async def test_weak_overlap_low_relevance(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(tenant_a, "rev-1", [make_chunk(text="Internet speed test.", title="Speed")])

    result = await _retrieve(retriever, tenant_a, "internet tv bundle discount")

    assert result.evidence_status is EvidenceStatus.LOW_RELEVANCE
    assert result.chunks == ()
    assert result.top_score == 0.25
    assert [d.selected for d in result.candidates] == [False]


@pytest.mark.asyncio
async def test_expired_only_match_stale_only(
    make_chunk: ChunkFactory,
    make_retriever: RetrieverFactory,
    tenant_a: str,
    now: datetime,
) -> None:
    retriever = make_retriever()
    retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(chunk_id="expired", valid_to=now - timedelta(days=1)),
            make_chunk(chunk_id="superseded", effective_status="superseded"),
            make_chunk(chunk_id="future", valid_from=now + timedelta(days=1)),
            make_chunk(chunk_id="weak", text="Speed test.", title="Speed", section_path=[]),
        ],
    )

    result = await _retrieve(retriever, tenant_a)

    assert result.evidence_status is EvidenceStatus.STALE_ONLY
    assert result.chunks == ()
    assert result.outdated_matches == 2
    assert result.excluded_counts == (
        (FilterExclusionReason.EXPIRED, 1),
        (FilterExclusionReason.NOT_YET_VALID, 1),
        (FilterExclusionReason.STATUS_NOT_ALLOWED, 1),
    )


@pytest.mark.asyncio
async def test_crawl_age_all_stale_stale_only(
    make_chunk: ChunkFactory,
    make_retriever: RetrieverFactory,
    tenant_a: str,
    now: datetime,
) -> None:
    settings = LexicalStubSettings(config=RetrievalConfig(stale_after=timedelta(days=1)))
    retriever = make_retriever(settings)
    retriever.publish(tenant_a, "rev-1", [make_chunk(crawled_at=now - timedelta(days=3))])

    result = await _retrieve(retriever, tenant_a)

    assert result.evidence_status is EvidenceStatus.STALE_ONLY
    assert result.chunks == ()
    assert len(result.candidates) == 1


@pytest.mark.asyncio
async def test_crawl_age_partial_stale_marks_chunks(
    make_chunk: ChunkFactory,
    make_retriever: RetrieverFactory,
    tenant_a: str,
    now: datetime,
) -> None:
    settings = LexicalStubSettings(config=RetrievalConfig(stale_after=timedelta(days=1)))
    retriever = make_retriever(settings)
    retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(chunk_id="fresh", crawled_at=now - timedelta(hours=1)),
            make_chunk(chunk_id="old", crawled_at=now - timedelta(days=3), document_id="d" * 64),
        ],
    )

    result = await _retrieve(retriever, tenant_a)

    assert result.evidence_status is EvidenceStatus.SUFFICIENT
    flags = {c.metadata.chunk_id: (c.is_stale, c.stale_reasons) for c in result.chunks}
    assert flags == {
        "fresh": (False, ()),
        "old": (True, (StaleReason.CRAWL_AGE_EXCEEDED,)),
    }


@pytest.mark.asyncio
async def test_two_active_revisions_same_document_conflict(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(chunk_id="v1", revision_id="doc-rev-1", text="Roaming costs 5 BYN per day."),
            make_chunk(chunk_id="v2", revision_id="doc-rev-2", text="Roaming costs 7 BYN per day."),
        ],
    )

    result = await _retrieve(retriever, tenant_a)

    assert result.evidence_status is EvidenceStatus.EVIDENCE_CONFLICT
    assert not result.is_answerable
    (conflict,) = result.conflicts
    assert conflict.reason is ConflictReason.MULTIPLE_ACTIVE_REVISIONS
    assert conflict.revision_ids == ("doc-rev-1", "doc-rev-2")
    assert conflict.chunk_ids == ("v1", "v2")
    assert {c.metadata.chunk_id for c in result.chunks} == {"v1", "v2"}


@pytest.mark.asyncio
async def test_sufficient_returns_context_top_k_ordered(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    settings = LexicalStubSettings(config=RetrievalConfig(context_top_k=2))
    retriever = make_retriever(settings)
    common: dict[str, Any] = {"title": "Info", "section_path": []}
    retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(chunk_id="half", text="roaming internet", **common),
            make_chunk(chunk_id="full", text="roaming internet price per day", **common),
            make_chunk(chunk_id="most", text="roaming internet price", **common),
            make_chunk(chunk_id="low", text="roaming only", **common),
        ],
    )

    result = await _retrieve(retriever, tenant_a, "roaming internet price day")

    assert result.evidence_status is EvidenceStatus.SUFFICIENT
    assert result.is_answerable
    assert [(c.rank, c.metadata.chunk_id, c.score) for c in result.chunks] == [
        (1, "full", 1.0),
        (2, "most", 0.75),
    ]
    assert [(d.chunk_id, d.selected) for d in result.candidates] == [
        ("full", True),
        ("most", True),
        ("half", False),
        ("low", False),
    ]
    assert result.top_score == 1.0
    assert result.retrieval_mode is RetrievalMode.STUB_LEXICAL
    assert result.config_version == "retrieval-v1"
    assert result.degraded == ()


@pytest.mark.asyncio
async def test_deterministic_tie_break_by_chunk_id(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(
        tenant_a,
        "rev-1",
        [make_chunk(chunk_id=chunk_id) for chunk_id in ("c-3", "c-1", "c-2")],
    )

    first = await _retrieve(retriever, tenant_a)
    second = await _retrieve(retriever, tenant_a)

    assert [d.chunk_id for d in first.candidates] == ["c-1", "c-2", "c-3"]
    assert [c.metadata.chunk_id for c in first.chunks] == ["c-1", "c-2", "c-3"]
    assert first == second


@pytest.mark.asyncio
async def test_diagnostics_sparse_and_rrf_filled_dense_rerank_none(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    retriever = make_retriever()
    retriever.publish(
        tenant_a,
        "rev-1",
        [make_chunk(chunk_id="best"), make_chunk(chunk_id="weak", text="Speed test.")],
    )

    result = await _retrieve(retriever, tenant_a, "roaming internet")

    for rank, diagnostics in enumerate(result.candidates, start=1):
        assert diagnostics.sparse_rank == rank
        assert diagnostics.sparse_score is not None
        assert diagnostics.rrf_rank == rank
        assert diagnostics.rrf_score == 1 / (60 + rank)
        assert diagnostics.dense_rank is None
        assert diagnostics.dense_score is None
        assert diagnostics.rerank_rank is None
        assert diagnostics.rerank_score is None
    assert result.candidates[0].document_id == "a" * 64
    assert result.candidates[0].revision_id == "rev-1"


@pytest.mark.asyncio
async def test_candidates_capped_by_sparse_top_k(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    config = RetrievalConfig(
        sparse_top_k=3, dense_top_k=1, rrf_top_k=2, rerank_top_k=2, context_top_k=1
    )
    retriever = make_retriever(LexicalStubSettings(config=config))
    retriever.publish(tenant_a, "rev-1", [make_chunk(chunk_id=f"c-{i}") for i in range(5)])

    result = await _retrieve(retriever, tenant_a)

    assert [d.chunk_id for d in result.candidates] == ["c-0", "c-1", "c-2"]
    assert [d.rrf_rank for d in result.candidates] == [1, 2, None]
    assert [c.metadata.chunk_id for c in result.chunks] == ["c-0"]


@pytest.mark.asyncio
async def test_applied_filters_echoed(
    make_chunk: ChunkFactory,
    make_retriever: RetrieverFactory,
    tenant_a: str,
    now: datetime,
) -> None:
    retriever = make_retriever()
    retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(chunk_id="ok"),
            make_chunk(chunk_id="ru", language="ru"),
            make_chunk(chunk_id="internal", audience="internal"),
            make_chunk(chunk_id="tv", service="tv"),
        ],
    )
    reference = now - timedelta(days=2)
    filters = RetrievalFilters(
        services=("roaming", "internet"),
        source_types=(SourceType.HTML,),
        effective_statuses=(EffectiveStatus.SUPERSEDED, EffectiveStatus.ACTIVE),
        reference_time=reference,
    )

    result = await _retrieve(retriever, tenant_a, filters=filters)

    applied = result.applied_filters
    assert applied.tenant_id == tenant_a
    assert applied.language == "en"
    assert applied.audience is Audience.CALLER
    assert applied.services == ("internet", "roaming")
    assert applied.topics is None
    assert applied.source_types == (SourceType.HTML,)
    assert applied.document_ids is None
    assert applied.effective_statuses == (EffectiveStatus.ACTIVE, EffectiveStatus.SUPERSEDED)
    assert applied.reference_time == reference
    assert result.excluded_counts == (
        (FilterExclusionReason.AUDIENCE_MISMATCH, 1),
        (FilterExclusionReason.LANGUAGE_MISMATCH, 1),
        (FilterExclusionReason.SERVICE_MISMATCH, 1),
    )
    assert [c.metadata.chunk_id for c in result.chunks] == ["ok"]

    default = await _retrieve(retriever, tenant_a)
    assert default.applied_filters.reference_time == now
    assert default.applied_filters.effective_statuses == (EffectiveStatus.ACTIVE,)


@pytest.mark.asyncio
async def test_snippet_truncated(
    make_chunk: ChunkFactory, make_retriever: RetrieverFactory, tenant_a: str
) -> None:
    settings = LexicalStubSettings(config=RetrievalConfig(snippet_max_chars=50))
    retriever = make_retriever(settings)
    long_text = "Roaming internet price per day is 5 BYN " + "extraordinarily " * 10
    unbroken = "roaming" + "x" * 100
    retriever.publish(
        tenant_a,
        "rev-1",
        [
            make_chunk(chunk_id="long", text=long_text),
            make_chunk(chunk_id="short", text="Roaming internet 5 BYN."),
            make_chunk(chunk_id="unbroken", text=unbroken, title="Roaming internet"),
        ],
    )

    result = await _retrieve(retriever, tenant_a, "roaming internet")
    snippets = {c.metadata.chunk_id: c.snippet for c in result.chunks}

    assert snippets["long"] == "Roaming internet price per day is 5 BYN"
    assert snippets["short"] == "Roaming internet 5 BYN."
    assert snippets["unbroken"] == unbroken[:50]
    assert all(len(s) <= 50 for s in snippets.values())


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
def test_settings_reject_out_of_range_threshold(threshold: float) -> None:
    with pytest.raises(ValueError):
        LexicalStubSettings(min_relevance_score=threshold)
