from pathlib import Path
from typing import Any

import pytest
import yaml
from mts_contracts.knowledge import RegistryValidationError, UrlExclusionReason

from mts_ingestion import (
    MAX_REGISTRY_BYTES,
    LoadedRegistry,
    RegistryPurpose,
    crawl_scope,
    load_registry,
    merge_registries,
    parse_registry,
)

R = UrlExclusionReason
BUSINESS = RegistryPurpose.BUSINESS
LEGACY = RegistryPurpose.LEGACY_DEMO
BASE = "https://www.acme-it.example"
APPROVED = {
    "status": "approved",
    "approved_by": "role.business-owner",
    "approved_at": "2026-10-12T09:00:00Z",
}


def _source(source_id: str = "acme-help", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "source_id": source_id,
        "tenant_id": "acme-it-demo",
        "url": f"{BASE}/help/",
        "kind": "web_section",
        "priority": "P0",
        "allow_path_prefixes": ["/help"],
        "refresh_interval": "P1D",
        "language": "ru",
        "audience": "caller",
        "status": "active",
        "owner": "role.business-owner",
        "approval": dict(APPROVED),
    }
    data.update(overrides)
    return data


def _tenant(*sources: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "tenant_id": "acme-it-demo",
        "registry_version": 1,
        "display_name": "Acme IT",
        "updated_at": "2026-10-13T10:00:00Z",
        "allowed_hosts": ["www.acme-it.example"],
        "manual_exclusions": [
            {
                "exclusion_id": "mx-001",
                "match": "prefix",
                "url": f"{BASE}/help/archive/",
                "reason": "Promotions archive 2024",
                "created_by": "role.business-owner",
                "created_at": "2026-10-12T08:00:00Z",
            }
        ],
        "sources": list(sources) if sources else [_source()],
    }
    data.update(overrides)
    return data


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def _yaml(*tenants: dict[str, Any]) -> str:
    document = {"schema_version": 1, "tenants": list(tenants) or [_tenant()]}
    return yaml.dump(document, Dumper=_NoAliasDumper, sort_keys=False, allow_unicode=True)


def _codes(text: str | bytes, purpose: RegistryPurpose = BUSINESS) -> list[str]:
    with pytest.raises(RegistryValidationError) as info:
        parse_registry(text, purpose=purpose)
    return [issue.code for issue in info.value.issues]


def _demo_tenant(*hosts: str) -> dict[str, Any]:
    return _tenant(
        _source(
            "mts-help",
            tenant_id="mts-public-demo",
            url="https://www.mts.by/help/",
            approval={**APPROVED, "approved_by": "role.demo-fixture-maintainer"},
        ),
        tenant_id="mts-public-demo",
        allowed_hosts=list(hosts or ("www.mts.by",)),
        manual_exclusions=[],
    )


def test_loads_valid_registry() -> None:
    loaded = parse_registry(_yaml(), purpose=BUSINESS)
    assert isinstance(loaded, LoadedRegistry)
    decision = loaded.decisions[("acme-it-demo", "acme-help")]
    assert decision.indexable
    assert decision.canonical_url == f"{BASE}/help/"
    assert decision.reasons == ()
    assert set(loaded.fingerprints) == {"acme-it-demo"}
    assert loaded.tenant("acme-it-demo").registry_version == 1


def test_rejects_duplicate_yaml_keys() -> None:
    assert _codes("schema_version: 1\nschema_version: 1\ntenants: []\n") == ["yaml_duplicate_key"]
    nested = _yaml().replace("    approval:\n", "    approval: {status: pending}\n    approval:\n")
    with pytest.raises(RegistryValidationError) as info:
        parse_registry(nested, purpose=BUSINESS)
    issue = info.value.issues[0]
    assert issue.code == "yaml_duplicate_key"
    assert "line" in issue.message


def test_rejects_yaml_aliases() -> None:
    assert _codes("base: &a {x: 1}\nother: *a\n") == ["yaml_alias_forbidden"]
    assert _codes("base: &a 1\n") == ["yaml_alias_forbidden"]
    assert _codes("tenants:\n  - <<: {tenant_id: x}\n    tenant_id: y\n") == [
        "yaml_alias_forbidden"
    ]


def test_empty_tenants_reported() -> None:
    assert _codes("schema_version: 1\ntenants: []\n") == ["schema_invalid"]


def test_rejects_invalid_yaml_and_encoding() -> None:
    assert _codes("tenants: [unclosed\n") == ["yaml_invalid"]
    assert _codes("a: 1\n---\nb: 2\n") == ["yaml_invalid"]
    assert _codes("!!python/object:os.system {}\n") == ["yaml_invalid"]
    assert _codes(b"schema_version: 1\n\xff\xfe") == ["encoding_invalid"]


def test_rejects_oversize_file(tmp_path: Path) -> None:
    oversize = "#" * (MAX_REGISTRY_BYTES + 1)
    assert _codes(oversize) == ["file_too_large"]
    path = tmp_path / "big.yaml"
    path.write_text(oversize, encoding="utf-8")
    with pytest.raises(RegistryValidationError) as info:
        load_registry(path, purpose=BUSINESS)
    assert [i.code for i in info.value.issues] == ["file_too_large"]


def test_schema_error_has_no_input_values() -> None:
    source = _source(
        priority="SECRET-PRIORITY",
        url="ftp://SECRET-HOST.example/help/",
        notes="\x07SECRET-NOTES",
    )
    source["SECRET-KEY-NAME"] = "SECRET-VALUE"
    tenant = _tenant(source, display_name="SECRET-DISPLAY\u202e")
    with pytest.raises(RegistryValidationError) as info:
        parse_registry(_yaml(tenant), purpose=BUSINESS)
    issues = info.value.issues
    assert {i.code for i in issues} == {"schema_invalid"}
    assert len(issues) >= 5
    rendered = str(info.value) + repr(issues)
    assert "SECRET" not in rendered
    assert all(i.tenant_id == "acme-it-demo" for i in issues)
    source_issues = [i for i in issues if ".sources.0." in i.message]
    assert len(source_issues) == 4
    assert all(i.source_id == "acme-help" for i in source_issues)


def test_collects_multiple_issues() -> None:
    tenant = _tenant(
        _source("a"),
        _source("b", url=f"{BASE}/help/?utm_source=x"),
        _source("c", url="https://other.example/help/"),
        _source("d", url=f"{BASE}/login", allow_path_prefixes=["/login"]),
    )
    codes = _codes(_yaml(tenant))
    assert codes == [
        "duplicate_canonical_url",
        "active_source_outside_allowlist",
        "active_source_denied_by_policy",
    ]


def test_tenant_mismatch_and_duplicate_ids_have_precise_codes() -> None:
    tenant = _tenant(
        _source("a"),
        _source("a", url=f"{BASE}/help/x"),
        _source("b", url=f"{BASE}/help/y", tenant_id="other-tenant"),
    )
    tenant["manual_exclusions"] = tenant["manual_exclusions"] * 2
    codes = _codes(_yaml(tenant, tenant))
    assert codes.count("duplicate_tenant") == 1
    assert codes.count("tenant_mismatch") == 2
    assert codes.count("duplicate_source_id") == 2
    assert codes.count("duplicate_exclusion_id") == 2
    assert "schema_invalid" not in codes


def test_duplicate_canonical_url_via_tracking_params() -> None:
    tenant = _tenant(
        _source("a", url=f"{BASE}/help/faq"),
        _source(
            "b",
            url=f"{BASE}/help/faq?utm_source=mail#top",
            status="review_required",
            approval={"status": "pending"},
        ),
    )
    with pytest.raises(RegistryValidationError) as info:
        parse_registry(_yaml(tenant), purpose=BUSINESS)
    (issue,) = info.value.issues
    assert (issue.code, issue.source_id) == ("duplicate_canonical_url", "b")
    assert issue.message == "same canonical URL as source a"


def test_uncanonicalizable_url_reported_without_credentials() -> None:
    tenant = _tenant(
        _source(
            "a",
            url="https://www.acme-it.example/help/hunter2\\x",
            status="excluded",
            exclusion_reason="backslash",
            approval={"status": "rejected"},
        ),
    )
    with pytest.raises(RegistryValidationError) as info:
        parse_registry(_yaml(tenant), purpose=BUSINESS)
    (issue,) = info.value.issues
    assert issue.code == "uncanonicalizable_url"
    assert "hunter2" not in issue.message
    userinfo = _tenant(
        _source(
            "a",
            url="https://bob:hunter2@www.acme-it.example/help/",
            status="excluded",
            exclusion_reason="credentials",
            approval={"status": "rejected"},
        ),
    )
    with pytest.raises(RegistryValidationError) as leaked:
        parse_registry(_yaml(userinfo), purpose=BUSINESS)
    rendered = str(leaked.value) + repr(leaked.value.issues)
    assert "hunter2" not in rendered
    assert {issue.code for issue in leaked.value.issues} == {"schema_invalid"}


def test_fullwidth_personal_host_active_source_rejected() -> None:
    tenant = _tenant(
        _source(
            "lk-fullwidth",
            url="https://ｌｋ.acme-two.example/",
            allow_path_prefixes=["/"],
        ),
        allowed_hosts=["lk.acme-two.example"],
    )
    with pytest.raises(RegistryValidationError) as info:
        parse_registry(_yaml(tenant), purpose=BUSINESS)
    assert "active_source_denied_by_policy" in {issue.code for issue in info.value.issues}


def test_active_outside_allowlist_rejected() -> None:
    tenant = _tenant(_source(url="https://other.example/help/"))
    assert _codes(_yaml(tenant)) == ["active_source_outside_allowlist"]


def test_active_login_url_rejected() -> None:
    tenant = _tenant(_source(url=f"{BASE}/login", allow_path_prefixes=["/login"]))
    with pytest.raises(RegistryValidationError) as info:
        parse_registry(_yaml(tenant), purpose=BUSINESS)
    (issue,) = info.value.issues
    assert issue.code == "active_source_denied_by_policy"
    assert "auth_or_personal_area" in issue.message


def test_review_required_denied_url_loads_not_indexable() -> None:
    tenant = _tenant(
        _source(),
        _source(
            "acme-account",
            url="https://lk.acme-it.example/account/",
            allow_path_prefixes=["/account"],
            status="review_required",
            approval={"status": "pending"},
        ),
    )
    loaded = parse_registry(_yaml(tenant), purpose=BUSINESS)
    decision = loaded.decisions[("acme-it-demo", "acme-account")]
    assert not decision.indexable
    assert decision.reasons == (
        R.PERSONAL_AREA_HOST,
        R.AUTH_OR_PERSONAL_AREA,
        R.HOST_NOT_ALLOWLISTED,
        R.SOURCE_NOT_ACTIVE,
        R.APPROVAL_NOT_GRANTED,
    )


def test_unapproved_not_indexable() -> None:
    tenant = _tenant(
        _source("pending", status="review_required", approval={"status": "pending"}),
        _source(
            "approved-review",
            url=f"{BASE}/help/x",
            status="review_required",
        ),
    )
    loaded = parse_registry(_yaml(tenant), purpose=BUSINESS)
    pending = loaded.decisions[("acme-it-demo", "pending")]
    assert pending.reasons == (R.SOURCE_NOT_ACTIVE, R.APPROVAL_NOT_GRANTED)
    review = loaded.decisions[("acme-it-demo", "approved-review")]
    assert (review.indexable, review.reasons) == (False, (R.SOURCE_NOT_ACTIVE,))


def test_manual_exclusion_makes_active_not_indexable() -> None:
    tenant = _tenant(_source(url=f"{BASE}/help/archive/2024/"))
    loaded = parse_registry(_yaml(tenant), purpose=BUSINESS)
    decision = loaded.decisions[("acme-it-demo", "acme-help")]
    assert not decision.indexable
    assert decision.reasons == (R.MANUAL_EXCLUSION,)
    assert decision.details == ("mx-001: Promotions archive 2024",)


def test_demo_tenant_forbidden_in_business_file() -> None:
    codes = _codes(_yaml(_demo_tenant()), BUSINESS)
    assert codes[0] == "legacy_demo_tenant_in_business_registry"
    assert set(codes) == {"legacy_demo_tenant_in_business_registry", "demo_host_in_business_tenant"}
    parse_registry(_yaml(_demo_tenant()), purpose=LEGACY)


def test_business_tenant_forbidden_in_legacy_file() -> None:
    assert _codes(_yaml(_tenant()), LEGACY) == ["non_demo_tenant_in_legacy_registry"]


@pytest.mark.parametrize("host", ["mts.by", "help.mts.by", "www.mts.by"])
def test_mts_host_forbidden_in_business_tenant(host: str) -> None:
    tenant = _tenant(allowed_hosts=["www.acme-it.example", host])
    assert _codes(_yaml(tenant)) == ["demo_host_in_business_tenant"]


def test_lookalike_host_not_treated_as_demo() -> None:
    tenant = _tenant(allowed_hosts=["www.acme-it.example", "notmts.by"])
    parse_registry(_yaml(tenant), purpose=BUSINESS)


def test_merge_rejects_shared_host_and_duplicate_tenant() -> None:
    first = parse_registry(_yaml(_tenant()), purpose=BUSINESS)
    other = _tenant(
        _source("b-help", tenant_id="beta-demo"),
        tenant_id="beta-demo",
        manual_exclusions=[],
    )
    second = parse_registry(_yaml(other), purpose=BUSINESS)
    with pytest.raises(RegistryValidationError) as info:
        merge_registries(first, second)
    (issue,) = info.value.issues
    assert (issue.code, issue.tenant_id) == ("host_shared_across_tenants", "beta-demo")
    with pytest.raises(RegistryValidationError) as info:
        merge_registries(first, first)
    assert [i.code for i in info.value.issues] == ["duplicate_tenant"]
    assert _codes(_yaml(_tenant(), other)) == ["host_shared_across_tenants"]
    with pytest.raises(ValueError, match="at least one"):
        merge_registries()


def test_merge_combines_business_and_legacy() -> None:
    business = parse_registry(_yaml(_tenant()), purpose=BUSINESS)
    legacy = parse_registry(_yaml(_demo_tenant()), purpose=LEGACY)
    merged = merge_registries(business, legacy)
    assert {t.tenant_id for t in merged.document.tenants} == {"acme-it-demo", "mts-public-demo"}
    assert set(merged.decisions) == set(business.decisions) | set(legacy.decisions)
    assert merged.fingerprints == {**business.fingerprints, **legacy.fingerprints}


def test_fingerprint_stable_and_changes_on_edit() -> None:
    tenant = _tenant()
    first = parse_registry(_yaml(tenant), purpose=BUSINESS).fingerprints["acme-it-demo"]
    reordered = dict(reversed(list(tenant.items())))
    assert parse_registry(_yaml(reordered), purpose=BUSINESS).fingerprints["acme-it-demo"] == first
    edited = _tenant(display_name="Acme IT (edited)")
    assert parse_registry(_yaml(edited), purpose=BUSINESS).fingerprints["acme-it-demo"] != first
    assert len(first) == 64


def test_crawl_scope_only_indexable() -> None:
    tenant = _tenant(
        _source(),
        _source("contacts", url=f"{BASE}/contacts/", allow_path_prefixes=["/contacts"]),
        _source(
            "pending",
            url=f"{BASE}/news/",
            allow_path_prefixes=["/news"],
            status="review_required",
            approval={"status": "pending"},
        ),
        _source("archived", url=f"{BASE}/help/archive/", allow_path_prefixes=["/help/archive"]),
    )
    loaded = parse_registry(_yaml(tenant), purpose=BUSINESS)
    assert crawl_scope(loaded, "acme-it-demo") == (
        ("www.acme-it.example", "/contacts"),
        ("www.acme-it.example", "/help"),
    )
    with pytest.raises(KeyError):
        crawl_scope(loaded, "unknown-tenant")
