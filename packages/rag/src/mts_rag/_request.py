"""Shared retrieval request parsing (SSOT §14.2)."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any

from mts_contracts.knowledge import (
    Audience,
    Identifier,
    InvalidRetrievalRequest,
    LanguageCode,
    RetrievalFilters,
    TenantId,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    ValidationError,
    ValidationInfo,
    field_validator,
)

MAX_DEADLINE_MS = 60_000
_TRAILING_PARTIAL_WORD = re.compile(r"\s+\S*$")


class _RetrievalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    query: str
    tenant_id: TenantId
    language: LanguageCode
    audience: Annotated[Audience, Field(strict=False)]
    filters: InstanceOf[RetrievalFilters]
    index_revision: Identifier
    deadline_ms: int = Field(ge=1, le=MAX_DEADLINE_MS)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str, info: ValidationInfo) -> str:
        normalized = " ".join(value.split())
        max_chars: int = (info.context or {})["max_query_chars"]
        if not 1 <= len(normalized) <= max_chars:
            raise ValueError("query length out of range")
        return normalized


def _parse_request(data: dict[str, Any], *, max_query_chars: int) -> _RetrievalRequest:
    fields: list[str] = []
    try:
        return _RetrievalRequest.model_validate(data, context={"max_query_chars": max_query_chars})
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False, include_context=False):
            name = str(error["loc"][0]) if error["loc"] else "request"
            if name not in fields:
                fields.append(name)
    # Raised outside the except block so the ValidationError, whose text contains the
    # query, is not attached as __context__.
    raise InvalidRetrievalRequest(fields)


parse_request = _parse_request


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _snippet(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if not text[max_chars].isspace():
        shortened = _TRAILING_PARTIAL_WORD.sub("", cut)
        if shortened:
            cut = shortened
    return cut.rstrip()
