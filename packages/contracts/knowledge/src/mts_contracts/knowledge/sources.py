from datetime import timedelta
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from mts_contracts.knowledge._base import ContractModel
from mts_contracts.knowledge._types import (
    SORTED_UNIQUE,
    AbsoluteHttpUrl,
    HostName,
    Identifier,
    LanguageCode,
    PathPrefix,
    ShortText,
    TenantId,
    UtcDatetime,
)
from mts_contracts.knowledge.enums import (
    ApprovalStatus,
    Audience,
    FreshnessClass,
    SourceKind,
    SourcePriority,
    SourceStatus,
)

_MIN_REFRESH_INTERVAL = timedelta(hours=1)
_MAX_REFRESH_INTERVAL = timedelta(days=30)


def _path_within_prefix(path: str, prefix: str) -> bool:
    return prefix == "/" or path == prefix or path.startswith(prefix + "/")


class SourceApproval(ContractModel):
    status: ApprovalStatus
    approved_by: Identifier | None = None
    approved_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def _check_approver(self) -> Self:
        has_by = self.approved_by is not None
        has_at = self.approved_at is not None
        if self.status is ApprovalStatus.APPROVED:
            if not (has_by and has_at):
                raise ValueError("approved status requires approved_by and approved_at")
        elif has_by or has_at:
            raise ValueError("approved_by and approved_at are only allowed for approved status")
        return self


class ManualExclusion(ContractModel):
    exclusion_id: Identifier
    match: Literal["exact", "prefix"]
    url: AbsoluteHttpUrl
    reason: ShortText
    created_by: Identifier
    created_at: UtcDatetime


class SourceRecord(ContractModel):
    source_id: Identifier
    tenant_id: TenantId
    url: AbsoluteHttpUrl
    kind: SourceKind
    priority: SourcePriority
    allow_path_prefixes: tuple[PathPrefix, ...] = Field(min_length=1, max_length=50)
    deny_path_prefixes: tuple[PathPrefix, ...] = Field(default=(), max_length=200)
    refresh_interval: timedelta
    freshness_class: FreshnessClass | None = None
    language: LanguageCode
    audience: Audience
    status: SourceStatus
    exclusion_reason: ShortText | None = None
    owner: Identifier
    approval: SourceApproval
    notes: ShortText | None = None

    @field_validator("refresh_interval")
    @classmethod
    def _check_refresh_interval(cls, value: timedelta) -> timedelta:
        if not _MIN_REFRESH_INTERVAL <= value <= _MAX_REFRESH_INTERVAL:
            raise ValueError("refresh_interval must be between 1 hour and 30 days")
        return value

    @model_validator(mode="after")
    def _check_status_consistency(self) -> Self:
        excluded = self.status is SourceStatus.EXCLUDED
        if excluded and self.exclusion_reason is None:
            raise ValueError("excluded sources require exclusion_reason")
        if not excluded and self.exclusion_reason is not None:
            raise ValueError("exclusion_reason is only allowed for excluded sources")
        if (
            self.status is SourceStatus.ACTIVE
            and self.approval.status is not ApprovalStatus.APPROVED
        ):
            raise ValueError("active sources require approved approval status")
        if not excluded:
            path = urlsplit(self.url).path or "/"
            if not any(_path_within_prefix(path, p) for p in self.allow_path_prefixes):
                raise ValueError("source url path must be within allow_path_prefixes")
        return self

    @property
    def is_active_and_approved(self) -> bool:
        return (
            self.status is SourceStatus.ACTIVE and self.approval.status is ApprovalStatus.APPROVED
        )


class TenantSourceRegistry(ContractModel):
    tenant_id: TenantId
    registry_version: int = Field(ge=1)
    display_name: ShortText
    updated_at: UtcDatetime
    allowed_hosts: Annotated[
        tuple[HostName, ...], Field(min_length=1, max_length=100), SORTED_UNIQUE
    ]
    manual_exclusions: tuple[ManualExclusion, ...] = Field(default=(), max_length=1000)
    sources: tuple[SourceRecord, ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def _check_records(self) -> Self:
        if any(s.tenant_id != self.tenant_id for s in self.sources):
            raise ValueError("every source tenant_id must equal the registry tenant_id")
        source_ids = [s.source_id for s in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_id must be unique within a tenant")
        exclusion_ids = [e.exclusion_id for e in self.manual_exclusions]
        if len(exclusion_ids) != len(set(exclusion_ids)):
            raise ValueError("exclusion_id must be unique within a tenant")
        return self


class SourceRegistryDocument(ContractModel):
    schema_version: Literal[1]
    tenants: tuple[TenantSourceRegistry, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _check_unique_tenants(self) -> Self:
        tenant_ids = [t.tenant_id for t in self.tenants]
        if len(tenant_ids) != len(set(tenant_ids)):
            raise ValueError("tenant_id must be unique within a registry document")
        return self
