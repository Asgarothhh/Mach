from typing import Annotated, Self

from pydantic import AfterValidator, Field, StringConstraints, field_validator, model_validator

from mts_contracts.knowledge._base import ContractModel
from mts_contracts.knowledge._types import (
    AbsoluteHttpUrl,
    Identifier,
    LanguageCode,
    Sha256Hex,
    ShortText,
    Slug,
    TenantId,
    UtcDatetime,
    reject_blank_or_control,
)
from mts_contracts.knowledge.constants import LEGACY_DEMO_TENANT_ID
from mts_contracts.knowledge.enums import Audience, EffectiveStatus, SourceType, TrustLevel

ChunkText = Annotated[
    str, StringConstraints(max_length=20_000), AfterValidator(reject_blank_or_control)
]


class ChunkMetadata(ContractModel):
    """Chunk metadata, SSOT §6.5.

    All §6.5 keys are required; nullable keys must be present with an explicit null.
    The validity interval is half-open: [valid_from, valid_to).
    """

    chunk_id: Identifier
    document_id: Sha256Hex
    revision_id: Identifier
    source_url: AbsoluteHttpUrl
    canonical_url: AbsoluteHttpUrl
    title: ShortText
    section_path: tuple[ShortText, ...] = Field(max_length=16)
    tenant_id: TenantId
    service: Slug
    topic: Slug
    audience: Audience
    language: LanguageCode
    content_hash: Sha256Hex
    crawled_at: UtcDatetime
    published_at: UtcDatetime | None
    valid_from: UtcDatetime | None
    valid_to: UtcDatetime | None
    effective_status: EffectiveStatus
    source_type: SourceType
    trust_level: TrustLevel
    text: ChunkText
    source_id: Identifier | None = None
    anchor: ShortText | None = None
    parser_version: Identifier | None = None

    @field_validator("canonical_url")
    @classmethod
    def _check_no_fragment(cls, value: str) -> str:
        if "#" in value:
            raise ValueError("canonical_url must not contain a fragment")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from >= self.valid_to
        ):
            raise ValueError("valid_from must be earlier than valid_to")
        is_demo_tenant = self.tenant_id == LEGACY_DEMO_TENANT_ID
        is_demo_trust = self.trust_level is TrustLevel.LEGACY_DEMO_FIXTURE
        if is_demo_tenant != is_demo_trust:
            raise ValueError(
                "legacy_demo_fixture trust level is reserved for the legacy demo tenant"
            )
        return self
