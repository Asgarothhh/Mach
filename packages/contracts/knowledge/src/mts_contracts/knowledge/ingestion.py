from collections import Counter
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from mts_contracts.knowledge._base import ContractModel
from mts_contracts.knowledge._types import (
    AbsoluteHttpUrl,
    Identifier,
    Sha256Hex,
    ShortText,
    TenantId,
    UtcDatetime,
)
from mts_contracts.knowledge.enums import IngestionRunStatus, UrlExclusionReason, UrlOutcomeKind

_UNFINISHED_STATUSES = frozenset({IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING})


class IngestionCounts(ContractModel):
    discovered: int = Field(0, ge=0)
    added: int = Field(0, ge=0)
    changed: int = Field(0, ge=0)
    unchanged: int = Field(0, ge=0)
    # Documents marked removed_at_source; their history is kept (SSOT §6.4).
    deleted: int = Field(0, ge=0)
    failed: int = Field(0, ge=0)
    skipped: int = Field(0, ge=0)
    documents_extracted: int = Field(0, ge=0)
    chunks_created: int = Field(0, ge=0)


class UrlOutcome(ContractModel):
    # Only the redacted form is ever stored (NFR-03): no userinfo, no query values.
    redacted_url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    canonical_url: AbsoluteHttpUrl | None = None
    source_id: Identifier | None = None
    outcome: UrlOutcomeKind
    reasons: tuple[UrlExclusionReason, ...] = ()
    detail: ShortText | None = None
    http_status: int | None = Field(None, ge=100, le=599)
    content_hash: Sha256Hex | None = None
    revision_id: Identifier | None = None

    @model_validator(mode="after")
    def _check_explained(self) -> Self:
        if self.outcome is UrlOutcomeKind.SKIPPED and not self.reasons:
            raise ValueError("skipped outcomes require at least one reason")
        if self.outcome is UrlOutcomeKind.FAILED and not (self.reasons or self.detail):
            raise ValueError("failed outcomes require reasons or detail")
        return self


class IngestionRunReport(ContractModel):
    schema_version: Literal[1] = 1
    run_id: UUID
    tenant_id: TenantId
    dry_run: bool
    status: IngestionRunStatus
    registry_version: int = Field(ge=1)
    registry_fingerprint: Sha256Hex
    canonicalization_version: int = Field(ge=1)
    text_normalization_version: int = Field(ge=1)
    started_at: UtcDatetime
    ended_at: UtcDatetime | None = None
    counts: IngestionCounts
    url_outcomes: tuple[UrlOutcome, ...] = ()

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        unfinished = self.status in _UNFINISHED_STATUSES
        if unfinished != (self.ended_at is None):
            raise ValueError("ended_at must be null exactly for queued or running runs")
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must not be earlier than started_at")

        tallies = Counter(o.outcome for o in self.url_outcomes)
        for kind in UrlOutcomeKind:
            if getattr(self.counts, kind.value) != tallies[kind]:
                raise ValueError(
                    f"counts.{kind.value} must equal the number of {kind.value} outcomes"
                )

        if self.status is IngestionRunStatus.SUCCEEDED and self.counts.failed != 0:
            raise ValueError("succeeded runs must have no failed URLs")
        if self.status is IngestionRunStatus.COMPLETED_WITH_ERRORS and self.counts.failed < 1:
            raise ValueError("completed_with_errors runs must have at least one failed URL")
        return self
