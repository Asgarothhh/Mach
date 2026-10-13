from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from mts_contracts.knowledge import (
    Audience,
    ChunkMetadata,
    EffectiveStatus,
    FilterExclusionReason,
    RetrievalFilters,
    SourceType,
)

from mts_rag.filters import ResolvedFilter, resolve_filters, scope_exclusion, temporal_exclusion

ChunkFactory = Callable[..., ChunkMetadata]


def _resolve(
    now: datetime,
    filters: RetrievalFilters | None = None,
    *,
    language: str = "en",
    audience: str = "caller",
) -> ResolvedFilter:
    return resolve_filters(
        filters or RetrievalFilters(),
        tenant_id="acme-it-demo",
        language=language,
        audience=audience,
        now=now,
    )


def test_language_mismatch_excluded(make_chunk: ChunkFactory, now: datetime) -> None:
    resolved = _resolve(now, language="ru")
    assert scope_exclusion(make_chunk(language="en"), resolved) is (
        FilterExclusionReason.LANGUAGE_MISMATCH
    )
    assert scope_exclusion(make_chunk(language="ru"), resolved) is None


def test_audience_exact_match(make_chunk: ChunkFactory, now: datetime) -> None:
    caller = _resolve(now, audience="caller")
    internal = _resolve(now, audience="internal")
    assert scope_exclusion(make_chunk(audience="internal"), caller) is (
        FilterExclusionReason.AUDIENCE_MISMATCH
    )
    assert scope_exclusion(make_chunk(audience="caller"), internal) is (
        FilterExclusionReason.AUDIENCE_MISMATCH
    )
    assert scope_exclusion(make_chunk(audience="caller"), caller) is None


@pytest.mark.parametrize(
    ("filters", "overrides", "reason"),
    [
        (RetrievalFilters(services=("tv",)), {}, FilterExclusionReason.SERVICE_MISMATCH),
        (RetrievalFilters(topics=("faq",)), {}, FilterExclusionReason.TOPIC_MISMATCH),
        (
            RetrievalFilters(source_types=(SourceType.PDF,)),
            {},
            FilterExclusionReason.SOURCE_TYPE_MISMATCH,
        ),
        (
            RetrievalFilters(document_ids=("c" * 64,)),
            {},
            FilterExclusionReason.DOCUMENT_MISMATCH,
        ),
        (RetrievalFilters(services=("tv", "roaming")), {}, None),
        (RetrievalFilters(topics=("pricing",)), {}, None),
        (RetrievalFilters(source_types=(SourceType.PDF, SourceType.HTML)), {}, None),
        (RetrievalFilters(document_ids=("a" * 64,)), {}, None),
        (RetrievalFilters(services=("tv",)), {"service": "tv"}, None),
    ],
)
def test_service_topic_source_type_document_filters(
    make_chunk: ChunkFactory,
    now: datetime,
    filters: RetrievalFilters,
    overrides: dict[str, str],
    reason: FilterExclusionReason | None,
) -> None:
    assert scope_exclusion(make_chunk(**overrides), _resolve(now, filters)) is reason


def test_none_means_no_restriction(make_chunk: ChunkFactory, now: datetime) -> None:
    resolved = _resolve(now)
    assert resolved.services is None
    assert resolved.topics is None
    assert resolved.source_types is None
    assert resolved.document_ids is None
    for chunk in (
        make_chunk(service="tv", topic="faq", source_type="pdf", document_id="d" * 64),
        make_chunk(service="internet", topic="contacts", source_type="table"),
    ):
        assert scope_exclusion(chunk, resolved) is None
        assert temporal_exclusion(chunk, resolved) is None


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (EffectiveStatus.ACTIVE, None),
        (EffectiveStatus.SUPERSEDED, FilterExclusionReason.STATUS_NOT_ALLOWED),
        (EffectiveStatus.EXPIRED, FilterExclusionReason.STATUS_NOT_ALLOWED),
        (EffectiveStatus.REMOVED_AT_SOURCE, FilterExclusionReason.STATUS_NOT_ALLOWED),
    ],
)
def test_default_statuses_active_only(
    make_chunk: ChunkFactory,
    now: datetime,
    status: EffectiveStatus,
    reason: FilterExclusionReason | None,
) -> None:
    resolved = _resolve(now)
    assert resolved.effective_statuses == frozenset({EffectiveStatus.ACTIVE})
    assert temporal_exclusion(make_chunk(effective_status=status), resolved) is reason


def test_explicit_statuses_allow_superseded(make_chunk: ChunkFactory, now: datetime) -> None:
    resolved = _resolve(
        now,
        RetrievalFilters(effective_statuses=(EffectiveStatus.ACTIVE, EffectiveStatus.SUPERSEDED)),
    )
    assert temporal_exclusion(make_chunk(effective_status="superseded"), resolved) is None


def test_valid_to_past_excluded(make_chunk: ChunkFactory, now: datetime) -> None:
    chunk = make_chunk(valid_to=now - timedelta(seconds=1))
    assert temporal_exclusion(chunk, _resolve(now)) is FilterExclusionReason.EXPIRED


def test_valid_to_equal_reference_excluded(make_chunk: ChunkFactory, now: datetime) -> None:
    chunk = make_chunk(valid_to=now)
    assert temporal_exclusion(chunk, _resolve(now)) is FilterExclusionReason.EXPIRED


def test_valid_from_future_excluded(make_chunk: ChunkFactory, now: datetime) -> None:
    chunk = make_chunk(valid_from=now + timedelta(seconds=1))
    assert temporal_exclusion(chunk, _resolve(now)) is FilterExclusionReason.NOT_YET_VALID


def test_open_interval_included(make_chunk: ChunkFactory, now: datetime) -> None:
    resolved = _resolve(now)
    assert temporal_exclusion(make_chunk(valid_from=now), resolved) is None
    assert temporal_exclusion(make_chunk(valid_to=now + timedelta(seconds=1)), resolved) is None
    assert temporal_exclusion(make_chunk(valid_from=None, valid_to=None), resolved) is None
    bounded = make_chunk(valid_from=now - timedelta(days=1), valid_to=now + timedelta(days=1))
    assert temporal_exclusion(bounded, resolved) is None


def test_reference_time_override(make_chunk: ChunkFactory, now: datetime) -> None:
    past = now - timedelta(days=30)
    chunk = make_chunk(valid_to=now - timedelta(days=1))
    resolved = _resolve(now, RetrievalFilters(reference_time=past))
    assert resolved.reference_time == past
    assert resolved.applied.reference_time == past
    assert temporal_exclusion(chunk, resolved) is None
    assert temporal_exclusion(chunk, _resolve(now)) is FilterExclusionReason.EXPIRED


def test_exclusion_reason_order_first_wins(make_chunk: ChunkFactory, now: datetime) -> None:
    resolved = _resolve(
        now,
        RetrievalFilters(
            services=("tv",),
            topics=("faq",),
            source_types=(SourceType.PDF,),
            document_ids=("c" * 64,),
        ),
        language="ru",
        audience="internal",
    )
    all_mismatched = make_chunk(language="en", audience="caller")
    assert scope_exclusion(all_mismatched, resolved) is FilterExclusionReason.LANGUAGE_MISMATCH
    assert scope_exclusion(make_chunk(language="ru"), resolved) is (
        FilterExclusionReason.AUDIENCE_MISMATCH
    )
    assert scope_exclusion(make_chunk(language="ru", audience="internal"), resolved) is (
        FilterExclusionReason.SERVICE_MISMATCH
    )

    temporal = _resolve(now)
    superseded_expired = make_chunk(
        effective_status="superseded",
        valid_from=now + timedelta(days=1),
        valid_to=now + timedelta(days=2),
    )
    assert temporal_exclusion(superseded_expired, temporal) is (
        FilterExclusionReason.STATUS_NOT_ALLOWED
    )
    not_yet_valid = make_chunk(valid_from=now + timedelta(days=1), valid_to=now + timedelta(days=2))
    assert temporal_exclusion(not_yet_valid, temporal) is FilterExclusionReason.NOT_YET_VALID


def test_applied_filters_carry_call_arguments(now: datetime) -> None:
    resolved = _resolve(now, RetrievalFilters(services=("tv", "roaming")), language="ru")
    applied = resolved.applied
    assert applied.tenant_id == "acme-it-demo"
    assert applied.language == "ru"
    assert applied.audience is Audience.CALLER
    assert applied.services == ("roaming", "tv")
    assert applied.reference_time == now
