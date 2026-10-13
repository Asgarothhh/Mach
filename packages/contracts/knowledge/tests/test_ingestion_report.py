from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from mts_contracts.knowledge import IngestionRunReport, IngestionRunStatus, UrlOutcome

RUN_ID = "0b6f7c1e-5a4d-4c3b-9a2f-1e0d9c8b7a65"


def _outcome(kind: str, **extra: Any) -> dict[str, Any]:
    return {"redacted_url": "https://www.acme-it.example/help?q=REDACTED", "outcome": kind, **extra}


@pytest.fixture
def report_data() -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "tenant_id": "acme-it-demo",
        "dry_run": True,
        "status": "completed_with_errors",
        "registry_version": 1,
        "registry_fingerprint": "d" * 64,
        "canonicalization_version": 1,
        "text_normalization_version": 1,
        "started_at": "2026-10-13T10:00:00Z",
        "ended_at": "2026-10-13T10:05:00Z",
        "counts": {
            "discovered": 4,
            "added": 1,
            "unchanged": 1,
            "failed": 1,
            "skipped": 1,
            "documents_extracted": 2,
            "chunks_created": 5,
        },
        "url_outcomes": [
            _outcome("added", canonical_url="https://www.acme-it.example/help", http_status=200),
            _outcome("unchanged", content_hash="e" * 64, revision_id="rev-1"),
            _outcome("failed", detail="HTTP 503", http_status=503),
            _outcome("skipped", reasons=["auth_or_personal_area"]),
        ],
    }


def test_valid_report_baseline(report_data: dict[str, Any]) -> None:
    report = IngestionRunReport.model_validate(report_data)
    assert report.run_id == UUID(RUN_ID)
    assert report.status is IngestionRunStatus.COMPLETED_WITH_ERRORS


@pytest.mark.parametrize("field", ["added", "unchanged", "failed", "skipped", "changed", "deleted"])
def test_counts_must_match_outcome_tallies(report_data: dict[str, Any], field: str) -> None:
    report_data["counts"][field] = report_data["counts"].get(field, 0) + 1
    with pytest.raises(ValidationError, match=f"counts.{field}"):
        IngestionRunReport.model_validate(report_data)


@pytest.mark.parametrize("status", ["queued", "running"])
def test_running_has_no_ended_at(report_data: dict[str, Any], status: str) -> None:
    with pytest.raises(ValidationError, match="ended_at"):
        IngestionRunReport.model_validate({**report_data, "status": status})
    report = IngestionRunReport.model_validate({**report_data, "status": status, "ended_at": None})
    assert report.ended_at is None
    with pytest.raises(ValidationError, match="ended_at"):
        IngestionRunReport.model_validate({**report_data, "ended_at": None})
    with pytest.raises(ValidationError, match="earlier"):
        IngestionRunReport.model_validate({**report_data, "ended_at": "2026-10-13T09:59:59Z"})


def test_succeeded_requires_zero_failed(report_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="succeeded"):
        IngestionRunReport.model_validate({**report_data, "status": "succeeded"})
    report_data["url_outcomes"] = report_data["url_outcomes"][:2] + report_data["url_outcomes"][3:]
    report_data["counts"]["failed"] = 0
    assert IngestionRunReport.model_validate({**report_data, "status": "succeeded"})
    with pytest.raises(ValidationError, match="completed_with_errors"):
        IngestionRunReport.model_validate(report_data)


def test_skipped_requires_reason() -> None:
    with pytest.raises(ValidationError, match="skipped"):
        UrlOutcome.model_validate(_outcome("skipped"))
    with pytest.raises(ValidationError, match="failed"):
        UrlOutcome.model_validate(_outcome("failed"))
    assert UrlOutcome.model_validate(_outcome("failed", reasons=["robots_unavailable"]))


def test_report_json_roundtrip(report_data: dict[str, Any]) -> None:
    report = IngestionRunReport.model_validate(report_data)
    restored = IngestionRunReport.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.model_dump_json() == report.model_dump_json()
