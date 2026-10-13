"""Typed knowledge errors.

Messages must never contain query text, chunk text, or raw URLs with query values.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar


class KnowledgeError(Exception):
    code: ClassVar[str] = "knowledge_error"
    retryable: ClassVar[bool] = False


class InvalidRetrievalRequest(KnowledgeError):
    code = "invalid_retrieval_request"

    def __init__(self, fields: Sequence[str]) -> None:
        self.fields: tuple[str, ...] = tuple(fields)
        super().__init__(f"invalid retrieval request fields: {', '.join(self.fields) or '-'}")


class RetrievalUnavailable(KnowledgeError):
    code = "retrieval_unavailable"
    retryable = True


class RetrievalDeadlineExceeded(RetrievalUnavailable):
    code = "retrieval_deadline_exceeded"
    retryable = False


class IndexRevisionNotFound(KnowledgeError):
    code = "index_revision_not_found"


class TenantIsolationError(KnowledgeError):
    code = "tenant_isolation_violation"


@dataclass(frozen=True)
class RegistryIssue:
    code: str
    tenant_id: str | None
    source_id: str | None
    message: str


class RegistryValidationError(KnowledgeError):
    code = "registry_invalid"

    def __init__(self, issues: Sequence[RegistryIssue]) -> None:
        self.issues: tuple[RegistryIssue, ...] = tuple(issues)
        codes = ", ".join(sorted({issue.code for issue in self.issues}))
        super().__init__(f"{len(self.issues)} registry issue(s): {codes or '-'}")
