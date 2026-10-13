import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from mts_contracts.knowledge import (
    ApprovalStatus,
    SourceApproval,
    SourceRecord,
    SourceRegistryDocument,
    SourceStatus,
    TenantSourceRegistry,
)


def test_excluded_requires_reason(source_data: dict[str, Any]) -> None:
    data = {**source_data, "status": "excluded", "approval": {"status": "rejected"}}
    with pytest.raises(ValidationError, match="exclusion_reason"):
        SourceRecord.model_validate(data)
    record = SourceRecord.model_validate({**data, "exclusion_reason": "auth_area: SSOT §6.2.3"})
    assert record.status is SourceStatus.EXCLUDED
    assert not record.is_active_and_approved


@pytest.mark.parametrize("status", ["active", "review_required"])
def test_reason_forbidden_when_not_excluded(source_data: dict[str, Any], status: str) -> None:
    data = {**source_data, "status": status, "exclusion_reason": "not applicable"}
    with pytest.raises(ValidationError, match="exclusion_reason"):
        SourceRecord.model_validate(data)


@pytest.mark.parametrize("approval_status", ["pending", "rejected"])
def test_active_requires_approved(source_data: dict[str, Any], approval_status: str) -> None:
    data = {**source_data, "approval": {"status": approval_status}}
    with pytest.raises(ValidationError, match="approved"):
        SourceRecord.model_validate(data)
    review = SourceRecord.model_validate({**data, "status": "review_required"})
    assert not review.is_active_and_approved
    assert SourceRecord.model_validate(source_data).is_active_and_approved


def test_approved_requires_actor_and_time() -> None:
    approved_at = datetime(2026, 10, 12, 9, tzinfo=UTC)
    with pytest.raises(ValidationError):
        SourceApproval(status=ApprovalStatus.APPROVED)
    with pytest.raises(ValidationError):
        SourceApproval(status=ApprovalStatus.APPROVED, approved_by="role.owner")
    with pytest.raises(ValidationError):
        SourceApproval(status=ApprovalStatus.APPROVED, approved_at=approved_at)
    with pytest.raises(ValidationError):
        SourceApproval(status=ApprovalStatus.PENDING, approved_by="role.owner")
    with pytest.raises(ValidationError):
        SourceApproval(status=ApprovalStatus.REJECTED, approved_at=approved_at)
    approval = SourceApproval(
        status=ApprovalStatus.APPROVED, approved_by="role.owner", approved_at=approved_at
    )
    assert approval.approved_at == approved_at


def test_record_url_must_be_within_allow_prefixes(source_data: dict[str, Any]) -> None:
    for url in ["https://www.acme-it.example/helpdesk", "https://www.acme-it.example/"]:
        with pytest.raises(ValidationError, match="allow_path_prefixes"):
            SourceRecord.model_validate({**source_data, "url": url})
    for url in [
        "https://www.acme-it.example/help",
        "https://www.acme-it.example/help/",
        "https://www.acme-it.example/help/roaming",
    ]:
        assert SourceRecord.model_validate({**source_data, "url": url}).url == url
    root = SourceRecord.model_validate(
        {**source_data, "url": "https://www.acme-it.example", "allow_path_prefixes": ["/"]}
    )
    assert root.allow_path_prefixes == ("/",)
    excluded = SourceRecord.model_validate(
        {
            **source_data,
            "url": "https://www.acme-it.example/login",
            "status": "excluded",
            "exclusion_reason": "auth_area",
            "approval": {"status": "rejected"},
        }
    )
    assert excluded.status is SourceStatus.EXCLUDED


def test_refresh_interval_parses_iso8601_and_bounds(source_data: dict[str, Any]) -> None:
    expected = {"PT1H": timedelta(hours=1), "PT6H": timedelta(hours=6), "P7D": timedelta(days=7)}
    for raw, value in expected.items():
        record = SourceRecord.model_validate({**source_data, "refresh_interval": raw})
        assert record.refresh_interval == value
    assert SourceRecord.model_validate(
        {**source_data, "refresh_interval": "P30D"}
    ).refresh_interval == timedelta(days=30)
    for raw in ["PT59M", "P31D", "PT0S", "-P1D"]:
        with pytest.raises(ValidationError, match="refresh_interval"):
            SourceRecord.model_validate({**source_data, "refresh_interval": raw})


def test_registry_rejects_foreign_tenant_record(registry_data: dict[str, Any]) -> None:
    registry_data["sources"][0]["tenant_id"] = "other-tenant"
    with pytest.raises(ValidationError, match="tenant_id"):
        TenantSourceRegistry.model_validate(registry_data)


def test_registry_rejects_duplicate_source_id(registry_data: dict[str, Any]) -> None:
    registry_data["sources"].append(copy.deepcopy(registry_data["sources"][0]))
    with pytest.raises(ValidationError, match="source_id must be unique"):
        TenantSourceRegistry.model_validate(registry_data)


def test_registry_rejects_duplicate_exclusion_id(registry_data: dict[str, Any]) -> None:
    registry_data["manual_exclusions"].append(copy.deepcopy(registry_data["manual_exclusions"][0]))
    with pytest.raises(ValidationError, match="exclusion_id must be unique"):
        TenantSourceRegistry.model_validate(registry_data)


def test_registry_allowed_hosts_sorted_unique(registry_data: dict[str, Any]) -> None:
    registry_data["allowed_hosts"] = ["www.acme-it.example", "help.acme-it.example"] * 2
    registry = TenantSourceRegistry.model_validate(registry_data)
    assert registry.allowed_hosts == ("help.acme-it.example", "www.acme-it.example")
    with pytest.raises(ValidationError):
        TenantSourceRegistry.model_validate({**registry_data, "allowed_hosts": []})


def test_document_rejects_duplicate_tenant(registry_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="tenant_id must be unique"):
        SourceRegistryDocument.model_validate(
            {"schema_version": 1, "tenants": [registry_data, copy.deepcopy(registry_data)]}
        )
    with pytest.raises(ValidationError):
        SourceRegistryDocument.model_validate({"schema_version": 1, "tenants": []})


@pytest.mark.parametrize("version", [0, 2, "1", None])
def test_schema_version_must_be_1(registry_data: dict[str, Any], version: object) -> None:
    with pytest.raises(ValidationError):
        SourceRegistryDocument.model_validate(
            {"schema_version": version, "tenants": [registry_data]}
        )
    document = SourceRegistryDocument.model_validate(
        {"schema_version": 1, "tenants": [registry_data]}
    )
    assert document.tenants[0].tenant_id == "acme-it-demo"


def test_models_are_frozen_and_forbid_extra(registry_data: dict[str, Any]) -> None:
    registry = TenantSourceRegistry.model_validate(registry_data)
    with pytest.raises(ValidationError):
        registry.registry_version = 2  # type: ignore[misc]
    with pytest.raises(ValidationError, match="Extra inputs"):
        TenantSourceRegistry.model_validate({**registry_data, "unexpected": True})
