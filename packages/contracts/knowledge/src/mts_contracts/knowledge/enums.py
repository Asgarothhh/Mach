from enum import StrEnum


class SourceStatus(StrEnum):
    ACTIVE = "active"
    EXCLUDED = "excluded"
    REVIEW_REQUIRED = "review_required"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SourceKind(StrEnum):
    WEB_PAGE = "web_page"
    WEB_SECTION = "web_section"
    SITEMAP = "sitemap"
    DOCUMENT = "document"
    FAQ = "faq"


class SourcePriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class FreshnessClass(StrEnum):
    """Refresh classes from SSOT §6.3."""

    DYNAMIC_CONDITIONS = "dynamic_conditions"
    SERVICE_PAGE = "service_page"
    LEGAL = "legal"
    STATIC_REFERENCE = "static_reference"


class SourceType(StrEnum):
    """Content format of a document, SSOT §6.5 `source_type`."""

    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    TABLE = "table"


class Audience(StrEnum):
    CALLER = "caller"
    INTERNAL = "internal"


class EffectiveStatus(StrEnum):
    """Document lifecycle from SSOT §6.4."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REMOVED_AT_SOURCE = "removed_at_source"


class TrustLevel(StrEnum):
    TENANT_APPROVED_SOURCE = "tenant_approved_source"
    LEGACY_DEMO_FIXTURE = "legacy_demo_fixture"


class EvidenceStatus(StrEnum):
    SUFFICIENT = "sufficient"
    NO_EVIDENCE = "no_evidence"
    LOW_RELEVANCE = "low_relevance"
    EVIDENCE_CONFLICT = "evidence_conflict"
    STALE_ONLY = "stale_only"


class RetrievalMode(StrEnum):
    HYBRID = "hybrid"
    SPARSE_ONLY = "sparse_only"
    DENSE_ONLY = "dense_only"
    STUB_LEXICAL = "stub_lexical"


class DegradationReason(StrEnum):
    EMBEDDER_UNAVAILABLE = "embedder_unavailable"
    DENSE_UNAVAILABLE = "dense_unavailable"
    SPARSE_UNAVAILABLE = "sparse_unavailable"
    RERANKER_UNAVAILABLE = "reranker_unavailable"


class FilterExclusionReason(StrEnum):
    LANGUAGE_MISMATCH = "language_mismatch"
    AUDIENCE_MISMATCH = "audience_mismatch"
    SERVICE_MISMATCH = "service_mismatch"
    TOPIC_MISMATCH = "topic_mismatch"
    SOURCE_TYPE_MISMATCH = "source_type_mismatch"
    DOCUMENT_MISMATCH = "document_mismatch"
    STATUS_NOT_ALLOWED = "status_not_allowed"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"


class StaleReason(StrEnum):
    CRAWL_AGE_EXCEEDED = "crawl_age_exceeded"


class ConflictReason(StrEnum):
    MULTIPLE_ACTIVE_REVISIONS = "multiple_active_revisions"


class UrlExclusionReason(StrEnum):
    INVALID_URL = "invalid_url"
    UNSUPPORTED_SCHEME = "unsupported_scheme"
    CREDENTIALS_IN_URL = "credentials_in_url"
    IP_LITERAL_HOST = "ip_literal_host"
    LOCAL_OR_SINGLE_LABEL_HOST = "local_or_single_label_host"
    NON_DEFAULT_PORT = "non_default_port"
    TOKEN_BEARING_PARAM = "token_bearing_param"  # noqa: S105
    TOKEN_LIKE_VALUE = "token_like_value"  # noqa: S105
    SESSION_PATH_PARAM = "session_path_param"
    AUTH_OR_PERSONAL_AREA = "auth_or_personal_area"
    PERSONAL_AREA_HOST = "personal_area_host"
    FORM_OR_TRANSACTION_PATH = "form_or_transaction_path"
    CLOSED_API_PATH = "closed_api_path"
    HOST_NOT_ALLOWLISTED = "host_not_allowlisted"
    PATH_NOT_ALLOWLISTED = "path_not_allowlisted"
    PATH_DENIED_BY_SOURCE = "path_denied_by_source"
    MANUAL_EXCLUSION = "manual_exclusion"
    ROBOTS_DISALLOWED = "robots_disallowed"
    ROBOTS_UNAVAILABLE = "robots_unavailable"
    SOURCE_NOT_ACTIVE = "source_not_active"
    APPROVAL_NOT_GRANTED = "approval_not_granted"


class IngestionRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UrlOutcomeKind(StrEnum):
    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    DELETED = "deleted"
    FAILED = "failed"
    SKIPPED = "skipped"
