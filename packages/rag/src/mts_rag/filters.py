"""Metadata filters applied before ranking (SSOT §6.7.5)."""

from dataclasses import dataclass
from datetime import datetime

from mts_contracts.knowledge import (
    AppliedFilters,
    Audience,
    ChunkMetadata,
    EffectiveStatus,
    FilterExclusionReason,
    RetrievalFilters,
    SourceType,
)


@dataclass(frozen=True, slots=True)
class ResolvedFilter:
    applied: AppliedFilters
    services: frozenset[str] | None
    topics: frozenset[str] | None
    source_types: frozenset[SourceType] | None
    document_ids: frozenset[str] | None
    effective_statuses: frozenset[EffectiveStatus]

    @property
    def reference_time(self) -> datetime:
        return self.applied.reference_time


def _as_set[T](values: tuple[T, ...] | None) -> frozenset[T] | None:
    return None if values is None else frozenset(values)


def resolve_filters(
    filters: RetrievalFilters,
    *,
    tenant_id: str,
    language: str,
    audience: Audience | str,
    now: datetime,
) -> ResolvedFilter:
    """Combine call arguments and optional filters into the applied filter set.

    `now` is used as the reference time unless `filters.reference_time` is set.
    """
    applied = AppliedFilters(
        tenant_id=tenant_id,
        language=language,
        audience=Audience(audience),
        services=filters.services,
        topics=filters.topics,
        source_types=filters.source_types,
        document_ids=filters.document_ids,
        effective_statuses=filters.effective_statuses,
        reference_time=filters.reference_time if filters.reference_time is not None else now,
    )
    return ResolvedFilter(
        applied=applied,
        services=_as_set(applied.services),
        topics=_as_set(applied.topics),
        source_types=_as_set(applied.source_types),
        document_ids=_as_set(applied.document_ids),
        effective_statuses=frozenset(applied.effective_statuses),
    )


def scope_exclusion(chunk: ChunkMetadata, resolved: ResolvedFilter) -> FilterExclusionReason | None:
    """First matching scope reason: language, audience, service, topic, source type, document."""
    applied = resolved.applied
    if chunk.language != applied.language:
        return FilterExclusionReason.LANGUAGE_MISMATCH
    if chunk.audience is not applied.audience:
        return FilterExclusionReason.AUDIENCE_MISMATCH
    if resolved.services is not None and chunk.service not in resolved.services:
        return FilterExclusionReason.SERVICE_MISMATCH
    if resolved.topics is not None and chunk.topic not in resolved.topics:
        return FilterExclusionReason.TOPIC_MISMATCH
    if resolved.source_types is not None and chunk.source_type not in resolved.source_types:
        return FilterExclusionReason.SOURCE_TYPE_MISMATCH
    if resolved.document_ids is not None and chunk.document_id not in resolved.document_ids:
        return FilterExclusionReason.DOCUMENT_MISMATCH
    return None


def temporal_exclusion(
    chunk: ChunkMetadata, resolved: ResolvedFilter
) -> FilterExclusionReason | None:
    """First matching lifecycle reason: status, not yet valid, expired.

    The validity interval is half-open: a chunk is valid at t when valid_from <= t < valid_to.
    """
    t = resolved.reference_time
    if chunk.effective_status not in resolved.effective_statuses:
        return FilterExclusionReason.STATUS_NOT_ALLOWED
    if chunk.valid_from is not None and chunk.valid_from > t:
        return FilterExclusionReason.NOT_YET_VALID
    if chunk.valid_to is not None and chunk.valid_to <= t:
        return FilterExclusionReason.EXPIRED
    return None
