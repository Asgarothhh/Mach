from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from mts_contracts.knowledge import LEGACY_DEMO_TENANT_ID, ChunkMetadata

SSOT_6_5_KEYS = (
    "chunk_id",
    "document_id",
    "revision_id",
    "source_url",
    "canonical_url",
    "title",
    "section_path",
    "tenant_id",
    "service",
    "topic",
    "audience",
    "language",
    "content_hash",
    "crawled_at",
    "published_at",
    "valid_from",
    "valid_to",
    "effective_status",
    "source_type",
    "trust_level",
    "text",
)
NULLABLE_KEYS = ("published_at", "valid_from", "valid_to")


def test_ssot_key_list_is_complete() -> None:
    assert len(SSOT_6_5_KEYS) == 21
    required = {name for name, field in ChunkMetadata.model_fields.items() if field.is_required()}
    assert required == set(SSOT_6_5_KEYS)


@pytest.mark.parametrize("key", SSOT_6_5_KEYS)
def test_each_ssot_6_5_field_missing_fails(chunk_data: dict[str, Any], key: str) -> None:
    ChunkMetadata.model_validate(chunk_data)
    del chunk_data[key]
    with pytest.raises(ValidationError) as excinfo:
        ChunkMetadata.model_validate(chunk_data)
    errors = excinfo.value.errors()
    assert any(e["type"] == "missing" and e["loc"] == (key,) for e in errors)


def test_nullable_fields_accept_explicit_null(chunk_data: dict[str, Any]) -> None:
    chunk = ChunkMetadata.model_validate(chunk_data)
    for key in NULLABLE_KEYS:
        assert getattr(chunk, key) is None
    assert chunk.source_id is None
    assert chunk.anchor is None
    assert chunk.parser_version is None


def test_datetimes_normalized_to_utc(chunk_data: dict[str, Any]) -> None:
    chunk_data["crawled_at"] = "2026-10-11T03:00:00+03:00"
    chunk_data["valid_to"] = "2026-11-01T00:00:00+03:00"
    chunk = ChunkMetadata.model_validate(chunk_data)
    assert chunk.crawled_at == datetime(2026, 10, 11, tzinfo=UTC)
    assert chunk.crawled_at.tzinfo is UTC
    assert chunk.valid_to == datetime(2026, 10, 31, 21, tzinfo=UTC)
    chunk_data["crawled_at"] = "2026-10-11T00:00:00"
    with pytest.raises(ValidationError):
        ChunkMetadata.model_validate(chunk_data)


def test_valid_from_before_valid_to(chunk_data: dict[str, Any]) -> None:
    chunk_data["valid_from"] = "2026-10-01T00:00:00Z"
    chunk_data["valid_to"] = "2026-10-31T21:00:00Z"
    ChunkMetadata.model_validate(chunk_data)
    for valid_to in ["2026-10-01T00:00:00Z", "2026-09-30T00:00:00Z"]:
        with pytest.raises(ValidationError, match="valid_from"):
            ChunkMetadata.model_validate({**chunk_data, "valid_to": valid_to})


def test_demo_tenant_requires_demo_trust_level(chunk_data: dict[str, Any]) -> None:
    chunk_data["tenant_id"] = LEGACY_DEMO_TENANT_ID
    with pytest.raises(ValidationError, match="legacy_demo_fixture"):
        ChunkMetadata.model_validate(chunk_data)
    chunk = ChunkMetadata.model_validate({**chunk_data, "trust_level": "legacy_demo_fixture"})
    assert chunk.tenant_id == LEGACY_DEMO_TENANT_ID


def test_business_tenant_rejects_demo_trust_level(chunk_data: dict[str, Any]) -> None:
    chunk_data["trust_level"] = "legacy_demo_fixture"
    with pytest.raises(ValidationError, match="legacy_demo_fixture"):
        ChunkMetadata.model_validate(chunk_data)


def test_canonical_url_rejects_fragment(chunk_data: dict[str, Any]) -> None:
    chunk_data["canonical_url"] = "https://www.acme-it.example/help/roaming#prices"
    with pytest.raises(ValidationError, match="fragment"):
        ChunkMetadata.model_validate(chunk_data)


def test_canonical_url_rejects_userinfo(chunk_data: dict[str, Any]) -> None:
    chunk_data["canonical_url"] = "https://user:pw@www.acme-it.example/help/roaming"
    with pytest.raises(ValidationError):
        ChunkMetadata.model_validate(chunk_data)


@pytest.mark.parametrize("key", ["document_id", "content_hash"])
@pytest.mark.parametrize("value", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, ""])
def test_hashes_require_64_lower_hex(chunk_data: dict[str, Any], key: str, value: str) -> None:
    chunk_data[key] = value
    with pytest.raises(ValidationError):
        ChunkMetadata.model_validate(chunk_data)


def test_text_rejects_blank_control_and_oversize(chunk_data: dict[str, Any]) -> None:
    for text in ["  \n ", "bad\x00text", "x" * 20_001]:
        with pytest.raises(ValidationError):
            ChunkMetadata.model_validate({**chunk_data, "text": text})


def test_chunk_is_frozen_and_forbids_extra(chunk_data: dict[str, Any]) -> None:
    chunk = ChunkMetadata.model_validate(chunk_data)
    with pytest.raises(ValidationError):
        chunk.text = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="Extra inputs"):
        ChunkMetadata.model_validate({**chunk_data, "phone": "+375000000000"})
    assert ChunkMetadata.model_validate_json(chunk.model_dump_json()) == chunk
