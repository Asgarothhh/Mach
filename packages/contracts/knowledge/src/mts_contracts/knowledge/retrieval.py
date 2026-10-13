from collections.abc import Mapping
from datetime import timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from mts_contracts.knowledge._base import ContractModel
from mts_contracts.knowledge._types import (
    SORTED_UNIQUE,
    Identifier,
    LanguageCode,
    Sha256Hex,
    Slug,
    TenantId,
    UtcDatetime,
)
from mts_contracts.knowledge.chunks import ChunkMetadata
from mts_contracts.knowledge.constants import ACTIVE_INDEX_REVISION
from mts_contracts.knowledge.enums import (
    Audience,
    ConflictReason,
    DegradationReason,
    EffectiveStatus,
    EvidenceStatus,
    FilterExclusionReason,
    RetrievalMode,
    SourceType,
    StaleReason,
)

_ServiceSet = Annotated[tuple[Slug, ...], Field(min_length=1, max_length=20), SORTED_UNIQUE]
_TopicSet = Annotated[tuple[Slug, ...], Field(min_length=1, max_length=20), SORTED_UNIQUE]
_SourceTypeSet = Annotated[tuple[SourceType, ...], Field(min_length=1), SORTED_UNIQUE]
_DocumentIdSet = Annotated[
    tuple[Sha256Hex, ...], Field(min_length=1, max_length=100), SORTED_UNIQUE
]
_EffectiveStatusSet = Annotated[tuple[EffectiveStatus, ...], Field(min_length=1), SORTED_UNIQUE]

_MAX_RESULT_CHUNKS = 50
_ANSWERABLE_WITH_CHUNKS = frozenset({EvidenceStatus.SUFFICIENT, EvidenceStatus.EVIDENCE_CONFLICT})


class RetrievalFilters(ContractModel):
    """Optional retrieval restrictions.

    tenant_id, language and audience are deliberately absent: they are passed only as
    `KnowledgeRetriever.retrieve` arguments. None means "no restriction"; empty tuples are
    rejected.
    """

    services: _ServiceSet | None = None
    topics: _TopicSet | None = None
    source_types: _SourceTypeSet | None = None
    document_ids: _DocumentIdSet | None = None
    effective_statuses: _EffectiveStatusSet = (EffectiveStatus.ACTIVE,)
    reference_time: UtcDatetime | None = None


class AppliedFilters(ContractModel):
    """The filter set actually applied by a retrieval call (SSOT §6.7.7)."""

    tenant_id: TenantId
    language: LanguageCode
    audience: Audience
    services: _ServiceSet | None
    topics: _TopicSet | None
    source_types: _SourceTypeSet | None
    document_ids: _DocumentIdSet | None
    effective_statuses: _EffectiveStatusSet
    reference_time: UtcDatetime


class RetrievalConfig(ContractModel):
    """Retrieval parameters; defaults are the SSOT §6.7 initial values."""

    version: Identifier = "retrieval-v1"
    dense_top_k: int = Field(30, ge=1, le=200)
    sparse_top_k: int = Field(30, ge=1, le=200)
    rrf_top_k: int = Field(30, ge=1, le=200)
    rerank_top_k: int = Field(20, ge=1, le=200)
    context_top_k: int = Field(6, ge=1, le=50)
    rrf_k: int = Field(60, ge=1)
    snippet_max_chars: int = Field(500, ge=50, le=4000)
    max_query_chars: int = Field(1000, ge=1, le=10_000)
    # SSOT §6.7.3: 1-3 query variants.
    max_query_variants: int = Field(3, ge=1, le=3)
    stale_after: timedelta | None = None

    @field_validator("stale_after")
    @classmethod
    def _check_stale_after(cls, value: timedelta | None) -> timedelta | None:
        if value is not None and value <= timedelta(0):
            raise ValueError("stale_after must be positive")
        return value

    @model_validator(mode="after")
    def _check_top_k_order(self) -> Self:
        if not (
            self.context_top_k
            <= self.rerank_top_k
            <= self.rrf_top_k
            <= self.dense_top_k + self.sparse_top_k
        ):
            raise ValueError(
                "require context_top_k <= rerank_top_k <= rrf_top_k <= dense_top_k + sparse_top_k"
            )
        return self


class CandidateDiagnostics(ContractModel):
    chunk_id: Identifier
    document_id: Sha256Hex
    revision_id: Identifier
    dense_rank: int | None = Field(None, ge=1)
    dense_score: float | None = None
    sparse_rank: int | None = Field(None, ge=1)
    sparse_score: float | None = None
    rrf_rank: int | None = Field(None, ge=1)
    rrf_score: float | None = None
    rerank_rank: int | None = Field(None, ge=1)
    rerank_score: float | None = None
    selected: bool

    @model_validator(mode="after")
    def _check_rank_score_pairs(self) -> Self:
        pairs = {
            "dense": (self.dense_rank, self.dense_score),
            "sparse": (self.sparse_rank, self.sparse_score),
            "rrf": (self.rrf_rank, self.rrf_score),
            "rerank": (self.rerank_rank, self.rerank_score),
        }
        for stage, (rank, score) in pairs.items():
            if (rank is None) != (score is None):
                raise ValueError(f"{stage}_rank and {stage}_score must be set together")
        if self.dense_rank is None and self.sparse_rank is None:
            raise ValueError("a candidate must come from dense or sparse retrieval")
        return self


class RetrievedChunk(ContractModel):
    rank: int = Field(ge=1)
    score: float
    snippet: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    metadata: ChunkMetadata
    is_stale: bool = False
    stale_reasons: Annotated[tuple[StaleReason, ...], SORTED_UNIQUE] = ()

    @model_validator(mode="after")
    def _check_stale(self) -> Self:
        if self.is_stale != bool(self.stale_reasons):
            raise ValueError("is_stale must be true exactly when stale_reasons is non-empty")
        return self


class ConflictIndicator(ContractModel):
    reason: ConflictReason
    document_id: Sha256Hex
    revision_ids: Annotated[tuple[Identifier, ...], Field(min_length=2), SORTED_UNIQUE]
    chunk_ids: Annotated[tuple[Identifier, ...], Field(min_length=2), SORTED_UNIQUE]

    @model_validator(mode="after")
    def _check_distinct(self) -> Self:
        if len(self.revision_ids) < 2 or len(self.chunk_ids) < 2:
            raise ValueError("a conflict requires at least two distinct revisions and chunks")
        return self


class RetrievalResult(ContractModel):
    schema_version: Literal[1] = 1
    tenant_id: TenantId
    index_revision: Identifier
    retrieval_mode: RetrievalMode
    config_version: Identifier
    # Raw user text: excluded from repr; persist only a redacted form or a hash (SSOT §8.3).
    query_variants: tuple[str, ...] = Field(min_length=1, max_length=3, repr=False)
    applied_filters: AppliedFilters
    candidates: tuple[CandidateDiagnostics, ...]
    chunks: tuple[RetrievedChunk, ...] = Field(max_length=_MAX_RESULT_CHUNKS)
    evidence_status: EvidenceStatus
    top_score: float | None
    conflicts: tuple[ConflictIndicator, ...] = ()
    outdated_matches: int = Field(0, ge=0)
    excluded_counts: tuple[tuple[FilterExclusionReason, int], ...] = ()
    degraded: Annotated[tuple[DegradationReason, ...], SORTED_UNIQUE] = ()
    duration_ms: int = Field(ge=0)

    @field_validator("index_revision")
    @classmethod
    def _check_concrete_revision(cls, value: str) -> str:
        if value == ACTIVE_INDEX_REVISION:
            raise ValueError("index_revision must be the resolved concrete revision")
        return value

    @field_validator("excluded_counts", mode="before")
    @classmethod
    def _coerce_excluded_counts(cls, value: object) -> object:
        if isinstance(value, Mapping):
            return tuple(value.items())
        return value

    @field_validator("excluded_counts")
    @classmethod
    def _check_excluded_counts(
        cls, value: tuple[tuple[FilterExclusionReason, int], ...]
    ) -> tuple[tuple[FilterExclusionReason, int], ...]:
        if any(count < 1 for _, count in value):
            raise ValueError("excluded_counts values must be >= 1; omit zero entries")
        reasons = [reason for reason, _ in value]
        if len(reasons) != len(set(reasons)):
            raise ValueError("excluded_counts reasons must be unique")
        return tuple(sorted(value, key=lambda item: item[0].value))

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.applied_filters.tenant_id != self.tenant_id:
            raise ValueError("applied_filters.tenant_id must equal tenant_id")
        if any(c.metadata.tenant_id != self.tenant_id for c in self.chunks):
            raise ValueError("every chunk must belong to the result tenant")

        if [c.rank for c in self.chunks] != list(range(1, len(self.chunks) + 1)):
            raise ValueError("chunk ranks must be 1..n in order")

        candidate_ids = [d.chunk_id for d in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate chunk_ids must be unique")
        chunk_ids = [c.metadata.chunk_id for c in self.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk chunk_ids must be unique")
        selected_ids = {d.chunk_id for d in self.candidates if d.selected}
        if set(chunk_ids) != selected_ids:
            raise ValueError("selected candidates must be exactly the returned chunks")

        if bool(self.chunks) != (self.evidence_status in _ANSWERABLE_WITH_CHUNKS):
            raise ValueError(
                "chunks must be non-empty exactly for sufficient or evidence_conflict status"
            )
        if bool(self.conflicts) != (self.evidence_status is EvidenceStatus.EVIDENCE_CONFLICT):
            raise ValueError("conflicts must be non-empty exactly for evidence_conflict status")
        known_ids = set(candidate_ids)
        if any(not set(c.chunk_ids) <= known_ids for c in self.conflicts):
            raise ValueError("conflict chunk_ids must reference candidates")

        if (self.top_score is None) != (not self.candidates):
            raise ValueError("top_score must be null exactly when there are no candidates")
        return self

    @property
    def is_answerable(self) -> bool:
        return self.evidence_status is EvidenceStatus.SUFFICIENT
