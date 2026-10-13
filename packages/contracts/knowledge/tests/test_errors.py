from typing import Annotated

import pytest
from pydantic import BaseModel, StringConstraints, ValidationError

from mts_contracts.knowledge import (
    IndexRevisionNotFound,
    InvalidRetrievalRequest,
    KnowledgeError,
    RegistryIssue,
    RegistryValidationError,
    RetrievalDeadlineExceeded,
    RetrievalUnavailable,
    TenantId,
    TenantIsolationError,
)


def test_hierarchy_and_codes() -> None:
    expected = {
        KnowledgeError: ("knowledge_error", False),
        InvalidRetrievalRequest: ("invalid_retrieval_request", False),
        RetrievalUnavailable: ("retrieval_unavailable", True),
        RetrievalDeadlineExceeded: ("retrieval_deadline_exceeded", False),
        IndexRevisionNotFound: ("index_revision_not_found", False),
        TenantIsolationError: ("tenant_isolation_violation", False),
        RegistryValidationError: ("registry_invalid", False),
    }
    for cls, (code, retryable) in expected.items():
        assert issubclass(cls, KnowledgeError)
        assert issubclass(cls, Exception)
        assert cls.code == code
        assert cls.retryable is retryable
    assert len({code for code, _ in expected.values()}) == len(expected)


def test_deadline_is_unavailable_subclass_not_retryable() -> None:
    assert issubclass(RetrievalDeadlineExceeded, RetrievalUnavailable)
    with pytest.raises(RetrievalUnavailable) as excinfo:
        raise RetrievalDeadlineExceeded("deadline exceeded")
    assert excinfo.value.retryable is False
    assert RetrievalUnavailable("down").retryable is True


def test_invalid_request_message_has_no_input_values() -> None:
    class _Request(BaseModel):
        query: Annotated[str, StringConstraints(max_length=10)]
        tenant_id: TenantId

    private_query = "my passport number is 1234567"
    with pytest.raises(ValidationError) as excinfo:
        _Request.model_validate({"query": private_query, "tenant_id": " Acme "})
    assert private_query in str(excinfo.value)
    fields = [
        ".".join(str(part) for part in err["loc"])
        for err in excinfo.value.errors(include_input=False, include_url=False)
    ]
    error = InvalidRetrievalRequest(fields)
    assert error.fields == ("query", "tenant_id")
    assert "query" in str(error)
    assert "tenant_id" in str(error)
    assert "Acme" not in str(error)
    assert "passport" not in str(error)
    assert "1234567" not in str(error)
    assert str(InvalidRetrievalRequest([])) == "invalid retrieval request fields: -"


def test_registry_error_collects_all_issues() -> None:
    issues = [
        RegistryIssue("duplicate_source_id", "acme-it-demo", "acme-help", "duplicate source_id"),
        RegistryIssue("tenant_mismatch", "acme-it-demo", "x", "foreign tenant"),
        RegistryIssue("duplicate_source_id", "acme-it-demo", "acme-faq", "duplicate source_id"),
    ]
    error = RegistryValidationError(issues)
    assert error.issues == tuple(issues)
    assert str(error) == "3 registry issue(s): duplicate_source_id, tenant_mismatch"
