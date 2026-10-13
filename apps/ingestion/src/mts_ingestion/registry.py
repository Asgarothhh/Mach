"""Tenant source registry loading and validation (MLB-SRC-01).

Checks that need canonical URLs or several records live here rather than in the contract
models, which must not depend on ingestion. All issues are collected and raised together;
issue messages never contain input values.
"""

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from mts_contracts.knowledge import (
    LEGACY_DEMO_TENANT_ID,
    Identifier,
    RegistryIssue,
    RegistryValidationError,
    SourceRegistryDocument,
    SourceStatus,
    TenantId,
    TenantSourceRegistry,
    UrlExclusionReason,
)
from pydantic import TypeAdapter, ValidationError

from mts_ingestion._yaml import YamlStructureError, load_strict
from mts_ingestion.url_canonical import UrlCanonicalizationError, canonicalize_url
from mts_ingestion.url_policy import (
    DEFAULT_URL_POLICY,
    UrlPolicyConfig,
    check_url_safety,
    evaluate_url,
)

MAX_REGISTRY_BYTES = 1024 * 1024
LEGACY_DEMO_DOMAIN = "mts.by"

_tenant_id_adapter: TypeAdapter[str] = TypeAdapter(TenantId)
_identifier_adapter: TypeAdapter[str] = TypeAdapter(Identifier)
_SAFE_LOC_PART = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_MESSAGE_ERROR_TYPES = frozenset({"value_error", "assertion_error"})


class RegistryPurpose(StrEnum):
    BUSINESS = "business"
    LEGACY_DEMO = "legacy_demo"


@dataclass(frozen=True)
class SourceDecision:
    tenant_id: str
    source_id: str
    canonical_url: str
    indexable: bool
    reasons: tuple[UrlExclusionReason, ...]
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadedRegistry:
    document: SourceRegistryDocument
    decisions: Mapping[tuple[str, str], SourceDecision]
    fingerprints: Mapping[str, str]

    def tenant(self, tenant_id: str) -> TenantSourceRegistry:
        for tenant in self.document.tenants:
            if tenant.tenant_id == tenant_id:
                return tenant
        raise KeyError(tenant_id)


def _issue(
    code: str, message: str, tenant_id: str | None = None, source_id: str | None = None
) -> RegistryIssue:
    return RegistryIssue(code=code, tenant_id=tenant_id, source_id=source_id, message=message)


def _safe_id(value: object, adapter: TypeAdapter[str]) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return adapter.validate_python(value)
    except ValidationError:
        return None


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _duplicates(values: Iterable[object]) -> list[object]:
    seen: set[object] = set()
    duplicates: list[object] = []
    for value in values:
        if not isinstance(value, str):
            continue
        if value in seen:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _raw_prechecks(data: object) -> tuple[list[RegistryIssue], set[int], bool]:
    """Checks on the raw mapping that give precise codes for what the models only reject."""
    issues: list[RegistryIssue] = []
    flagged_tenants: set[int] = set()
    tenants = _as_list(_as_dict(data).get("tenants"))
    duplicate_tenants = _duplicates(_as_dict(t).get("tenant_id") for t in tenants)
    for duplicate in duplicate_tenants:
        issues.append(
            _issue(
                "duplicate_tenant",
                "tenant_id appears more than once",
                _safe_id(duplicate, _tenant_id_adapter),
            )
        )
    for index, raw_tenant in enumerate(tenants):
        tenant = _as_dict(raw_tenant)
        raw_tenant_id = tenant.get("tenant_id")
        tenant_id = _safe_id(raw_tenant_id, _tenant_id_adapter)
        sources = [_as_dict(s) for s in _as_list(tenant.get("sources"))]
        for source in sources:
            source_tenant = source.get("tenant_id")
            if isinstance(source_tenant, str) and source_tenant != raw_tenant_id:
                flagged_tenants.add(index)
                issues.append(
                    _issue(
                        "tenant_mismatch",
                        "source tenant_id differs from the enclosing tenant",
                        tenant_id,
                        _safe_id(source.get("source_id"), _identifier_adapter),
                    )
                )
        for duplicate in _duplicates(s.get("source_id") for s in sources):
            flagged_tenants.add(index)
            issues.append(
                _issue(
                    "duplicate_source_id",
                    "source_id appears more than once in the tenant",
                    tenant_id,
                    _safe_id(duplicate, _identifier_adapter),
                )
            )
        exclusions = [_as_dict(e) for e in _as_list(tenant.get("manual_exclusions"))]
        for _ in _duplicates(e.get("exclusion_id") for e in exclusions):
            flagged_tenants.add(index)
            issues.append(
                _issue(
                    "duplicate_exclusion_id",
                    "exclusion_id appears more than once in the tenant",
                    tenant_id,
                )
            )
    return issues, flagged_tenants, bool(duplicate_tenants)


def _ids_from_loc(data: object, loc: Sequence[int | str]) -> tuple[str | None, str | None]:
    if len(loc) < 2 or loc[0] != "tenants" or not isinstance(loc[1], int):
        return None, None
    tenants = _as_list(_as_dict(data).get("tenants"))
    if not 0 <= loc[1] < len(tenants):
        return None, None
    tenant = _as_dict(tenants[loc[1]])
    tenant_id = _safe_id(tenant.get("tenant_id"), _tenant_id_adapter)
    if len(loc) < 4 or loc[2] != "sources" or not isinstance(loc[3], int):
        return tenant_id, None
    sources = _as_list(tenant.get("sources"))
    if not 0 <= loc[3] < len(sources):
        return tenant_id, None
    return tenant_id, _safe_id(_as_dict(sources[loc[3]]).get("source_id"), _identifier_adapter)


def _schema_issues(
    data: object, error: ValidationError, flagged_tenants: set[int], duplicate_tenants: bool
) -> list[RegistryIssue]:
    issues: list[RegistryIssue] = []
    details = error.errors(include_input=False, include_url=False, include_context=False)
    parent_locs = {d["loc"][:i] for d in details for i in range(1, len(d["loc"]))}
    for detail in details:
        loc = detail["loc"]
        # pydantic-core also reports `too_short` when every item of a non-empty tuple failed.
        if detail["type"] == "too_short" and loc in parent_locs:
            continue
        is_model_error = detail["type"] in _MESSAGE_ERROR_TYPES
        if is_model_error and (
            (len(loc) == 2 and loc[0] == "tenants" and loc[1] in flagged_tenants)
            or (not loc and duplicate_tenants)
        ):
            continue
        where = ".".join(
            str(part) if isinstance(part, int) or _SAFE_LOC_PART.match(part) else "<key>"
            for part in loc
        )
        message = f"{where or '<root>'}: {detail['type']}"
        if is_model_error:
            message = f"{message}: {detail['msg']}"
        tenant_id, source_id = _ids_from_loc(data, loc)
        issues.append(_issue("schema_invalid", message, tenant_id, source_id))
    return issues


def _is_demo_host(host: str | None) -> bool:
    return host is not None and (
        host == LEGACY_DEMO_DOMAIN or host.endswith("." + LEGACY_DEMO_DOMAIN)
    )


def _shared_host_issues(tenants: Iterable[TenantSourceRegistry]) -> list[RegistryIssue]:
    owners: dict[str, str] = {}
    issues: list[RegistryIssue] = []
    for tenant in tenants:
        for host in tenant.allowed_hosts:
            owner = owners.setdefault(host, tenant.tenant_id)
            if owner != tenant.tenant_id:
                issues.append(
                    _issue(
                        "host_shared_across_tenants",
                        f"host {host} is also allowlisted for tenant {owner}",
                        tenant.tenant_id,
                    )
                )
    return issues


def _tenant_checks(
    tenant: TenantSourceRegistry,
    purpose: RegistryPurpose,
    policy: UrlPolicyConfig,
    decisions: dict[tuple[str, str], SourceDecision],
) -> list[RegistryIssue]:
    tid = tenant.tenant_id
    issues: list[RegistryIssue] = []
    if purpose is RegistryPurpose.BUSINESS and tid == LEGACY_DEMO_TENANT_ID:
        issues.append(
            _issue(
                "legacy_demo_tenant_in_business_registry",
                "the legacy demo tenant must live in the legacy demo registry (SSOT §6.1)",
                tid,
            )
        )
    if purpose is RegistryPurpose.LEGACY_DEMO and tid != LEGACY_DEMO_TENANT_ID:
        issues.append(
            _issue(
                "non_demo_tenant_in_legacy_registry",
                f"only {LEGACY_DEMO_TENANT_ID} is allowed in the legacy demo registry",
                tid,
            )
        )
    business = purpose is RegistryPurpose.BUSINESS
    for host in tenant.allowed_hosts:
        if business and _is_demo_host(host):
            issues.append(
                _issue(
                    "demo_host_in_business_tenant",
                    f"allowed host {host} belongs to the legacy demo corpus",
                    tid,
                )
            )
    for exclusion in tenant.manual_exclusions:
        try:
            canonicalize_url(exclusion.url, tracking_params=policy.tracking_params)
        except UrlCanonicalizationError as exc:
            issues.append(
                _issue(
                    "uncanonicalizable_url",
                    f"manual exclusion {exclusion.exclusion_id}: {exc.reason.value}",
                    tid,
                )
            )
    seen: dict[str, str] = {}
    for source in tenant.sources:
        sid = source.source_id
        try:
            canonical = canonicalize_url(source.url, tracking_params=policy.tracking_params)
        except UrlCanonicalizationError as exc:
            issues.append(_issue("uncanonicalizable_url", exc.reason.value, tid, sid))
            continue
        source_host = urlsplit(canonical).hostname
        if business and _is_demo_host(source_host):
            issues.append(
                _issue(
                    "demo_host_in_business_tenant",
                    "source host belongs to the legacy demo corpus",
                    tid,
                    sid,
                )
            )
        other = seen.setdefault(canonical, sid)
        if other != sid:
            issues.append(
                _issue(
                    "duplicate_canonical_url",
                    f"same canonical URL as source {other}",
                    tid,
                    sid,
                )
            )
        if source.status is SourceStatus.ACTIVE:
            if source_host not in tenant.allowed_hosts:
                issues.append(
                    _issue(
                        "active_source_outside_allowlist",
                        "active source host is not in allowed_hosts",
                        tid,
                        sid,
                    )
                )
            safety = check_url_safety(source.url, policy)
            if not safety.allowed:
                reasons = ", ".join(r.value for r in safety.reasons)
                issues.append(
                    _issue(
                        "active_source_denied_by_policy",
                        f"active source is denied by URL policy: {reasons}",
                        tid,
                        sid,
                    )
                )
        decision = evaluate_url(source.url, registry=tenant, source=source, config=policy)
        decisions[(tid, sid)] = SourceDecision(
            tenant_id=tid,
            source_id=sid,
            canonical_url=canonical,
            indexable=decision.allowed,
            reasons=decision.reasons,
            details=decision.details,
        )
    return issues


def _fingerprint(tenant: TenantSourceRegistry) -> str:
    payload = json.dumps(
        tenant.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build(
    document: SourceRegistryDocument,
    decisions: Mapping[tuple[str, str], SourceDecision],
) -> LoadedRegistry:
    return LoadedRegistry(
        document=document,
        decisions=MappingProxyType(dict(decisions)),
        fingerprints=MappingProxyType({t.tenant_id: _fingerprint(t) for t in document.tenants}),
    )


def _decode(text: str | bytes) -> str:
    size = len(text.encode("utf-8")) if isinstance(text, str) else len(text)
    if size > MAX_REGISTRY_BYTES:
        raise RegistryValidationError(
            [_issue("file_too_large", f"registry exceeds {MAX_REGISTRY_BYTES} bytes")]
        )
    if isinstance(text, str):
        return text
    try:
        return text.decode("utf-8")
    except UnicodeDecodeError:
        raise RegistryValidationError(
            [_issue("encoding_invalid", "registry must be UTF-8")]
        ) from None


def parse_registry(
    text: str | bytes,
    *,
    purpose: RegistryPurpose,
    policy: UrlPolicyConfig = DEFAULT_URL_POLICY,
) -> LoadedRegistry:
    try:
        data = load_strict(_decode(text))
    except YamlStructureError as exc:
        where = f"line {exc.line}" if exc.line is not None else "document"
        raise RegistryValidationError(
            [_issue(exc.code, f"YAML structure rejected at {where}")]
        ) from None
    issues, flagged_tenants, duplicate_tenants = _raw_prechecks(data)
    try:
        document = SourceRegistryDocument.model_validate(data)
    except ValidationError as exc:
        issues.extend(_schema_issues(data, exc, flagged_tenants, duplicate_tenants))
        raise RegistryValidationError(issues) from None
    decisions: dict[tuple[str, str], SourceDecision] = {}
    for tenant in document.tenants:
        issues.extend(_tenant_checks(tenant, purpose, policy, decisions))
    issues.extend(_shared_host_issues(document.tenants))
    if issues:
        raise RegistryValidationError(issues)
    return _build(document, decisions)


def load_registry(
    path: str | os.PathLike[str],
    *,
    purpose: RegistryPurpose,
    policy: UrlPolicyConfig = DEFAULT_URL_POLICY,
) -> LoadedRegistry:
    with open(path, "rb") as handle:
        data = handle.read(MAX_REGISTRY_BYTES + 1)
    return parse_registry(data, purpose=purpose, policy=policy)


def merge_registries(*registries: LoadedRegistry) -> LoadedRegistry:
    """Combine separately validated registries (e.g. business + legacy demo)."""
    if not registries:
        raise ValueError("at least one registry is required")
    tenants = [t for r in registries for t in r.document.tenants]
    issues = [
        _issue("duplicate_tenant", "tenant_id appears in more than one registry", tenant_id)
        for tenant_id in _duplicates(t.tenant_id for t in tenants)
        if isinstance(tenant_id, str)
    ]
    issues.extend(_shared_host_issues(tenants))
    if issues:
        raise RegistryValidationError(issues)
    try:
        document = SourceRegistryDocument(schema_version=1, tenants=tuple(tenants))
    except ValidationError as exc:
        raise RegistryValidationError(_schema_issues(None, exc, set(), False)) from None
    decisions = {key: d for r in registries for key, d in r.decisions.items()}
    return _build(document, decisions)


def crawl_scope(loaded: LoadedRegistry, tenant_id: str) -> tuple[tuple[str, str], ...]:
    """`(host, path_prefix)` pairs of indexable sources only, sorted and unique."""
    tenant = loaded.tenant(tenant_id)
    scope: set[tuple[str, str]] = set()
    for source in tenant.sources:
        decision = loaded.decisions.get((tenant_id, source.source_id))
        if decision is None or not decision.indexable:
            continue
        host = urlsplit(decision.canonical_url).hostname or ""
        scope.update((host, prefix) for prefix in source.allow_path_prefixes)
    return tuple(sorted(scope))
