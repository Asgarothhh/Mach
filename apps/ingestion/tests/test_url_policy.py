from pathlib import Path
from typing import Any

import pytest
from mts_contracts.knowledge import (
    SourceRecord,
    TenantIsolationError,
    TenantSourceRegistry,
    UrlExclusionReason,
)

from mts_ingestion import (
    RegistryPurpose,
    RobotsRules,
    UrlPolicyConfig,
    canonicalize_url,
    check_url_safety,
    evaluate_url,
    load_registry,
    redact_url,
)

R = UrlExclusionReason
BASE = "https://www.acme-it.example"
PRODUCT = "MtsBot"


def _source(**overrides: Any) -> SourceRecord:
    data: dict[str, Any] = {
        "source_id": "acme-help",
        "tenant_id": "acme-it-demo",
        "url": f"{BASE}/help/",
        "kind": "web_section",
        "priority": "P0",
        "allow_path_prefixes": ["/help"],
        "deny_path_prefixes": ["/help/internal"],
        "refresh_interval": "P1D",
        "language": "ru",
        "audience": "caller",
        "status": "active",
        "owner": "role.business-owner",
        "approval": {
            "status": "approved",
            "approved_by": "role.business-owner",
            "approved_at": "2026-10-12T09:00:00Z",
        },
    }
    data.update(overrides)
    return SourceRecord.model_validate(data)


def _registry(source: SourceRecord | None = None) -> TenantSourceRegistry:
    return TenantSourceRegistry.model_validate(
        {
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
                },
                {
                    "exclusion_id": "mx-002",
                    "match": "exact",
                    "url": f"{BASE}/help/old-faq",
                    "reason": "Superseded FAQ page",
                    "created_by": "role.business-owner",
                    "created_at": "2026-10-12T08:00:00Z",
                },
            ],
            "sources": [(source or _source()).model_dump(mode="json")],
        }
    )


def _reasons(url: str) -> tuple[UrlExclusionReason, ...]:
    return check_url_safety(url).reasons


def test_allows_plain_public_page() -> None:
    decision = check_url_safety(f"{BASE}/help/roaming?utm_source=x")
    assert decision.allowed
    assert decision.reasons == ()
    assert decision.canonical_url == f"{BASE}/help/roaming"


@pytest.mark.parametrize(
    "path",
    [
        "/login",
        "/selfcare/",
        "/account",
        "/accounts/settings",
        "/lk",
        "/my/profile",
        "/sign-in",
        "/logout",
        "/oauth/authorize",
        "/cabinet/",
        "/reset-password",
    ],
)
def test_denies_auth_segments(path: str) -> None:
    assert R.AUTH_OR_PERSONAL_AREA in _reasons(BASE + path)


@pytest.mark.parametrize(
    "path",
    [
        "/LOGIN",
        "/SelfCare/",
        "/%6Cogin",
        "/%256Cogin",
        "/Self%43are",
        "/login.html",
        "/a/..%2Flogin",
        "/help/%2Faccount",
        "/login;jsessionid=1",
    ],
)
def test_denies_case_and_percent_encoded_variants(path: str) -> None:
    assert R.AUTH_OR_PERSONAL_AREA in _reasons(BASE + path)


@pytest.mark.parametrize(
    "path", ["/accountant-services", "/myriad", "/blogin", "/formula", "/apis"]
)
def test_segment_equality_not_substring(path: str) -> None:
    assert check_url_safety(BASE + path).allowed


@pytest.mark.parametrize("path", ["/checkout", "/cart/", "/forms/contact", "/payment", "/basket"])
def test_denies_form_and_cart_paths(path: str) -> None:
    assert R.FORM_OR_TRANSACTION_PATH in _reasons(BASE + path)


@pytest.mark.parametrize("path", ["/api/v1/tariffs", "/graphql", "/API/"])
def test_denies_api_path(path: str) -> None:
    assert R.CLOSED_API_PATH in _reasons(BASE + path)


@pytest.mark.parametrize(
    "query",
    ["token=1", "access_token=", "SessionId=x", "sig=abc", "X-Amz-Signature=f", "code=7"],
)
def test_denies_token_params(query: str) -> None:
    assert R.TOKEN_BEARING_PARAM in _reasons(f"{BASE}/help?{query}")


@pytest.mark.parametrize(
    "value",
    [
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl",
        "0123456789abcdef0123456789abcdef",
        "Qm9sdFJhbmRvbVRva2VuVmFsdWUxMjM0NTY3OA",
    ],
)
def test_denies_jwt_and_long_hex_values(value: str) -> None:
    assert R.TOKEN_LIKE_VALUE in _reasons(f"{BASE}/help?ref={value}")


def test_long_lowercase_slug_value_is_not_token() -> None:
    assert check_url_safety(f"{BASE}/help?topic=mobile-internet-tariffs-for-business-2026").allowed
    assert check_url_safety(f"{BASE}/help/mobile-internet-tariffs-for-business-2026").allowed


def test_denies_jwt_in_path() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    assert R.TOKEN_LIKE_VALUE in _reasons(f"{BASE}/help/reset/{jwt}")


def test_denies_long_hex_in_path() -> None:
    assert R.TOKEN_LIKE_VALUE in _reasons(f"{BASE}/confirm/{'a' * 64}")


def test_redact_path_hides_token_segments() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    hex_token = "a" * 64
    for url in (f"{BASE}/help/reset/{jwt}", f"{BASE}/confirm/{hex_token}"):
        redacted = check_url_safety(url).redacted_url
        assert jwt not in redacted
        assert hex_token not in redacted
        assert "REDACTED" in redacted
        assert jwt not in redact_url(url)
        assert hex_token not in redact_url(url)


def test_denies_jsessionid_path_param() -> None:
    assert R.SESSION_PATH_PARAM in _reasons(f"{BASE}/help;jsessionid=ABC123")
    assert R.SESSION_PATH_PARAM in _reasons(f"{BASE}/help%3Bjsessionid=ABC123")


def test_denies_userinfo() -> None:
    decision = check_url_safety("https://user:pw@www.acme-it.example/help/")
    assert decision.reasons == (R.CREDENTIALS_IN_URL,)
    assert decision.canonical_url is None


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("https://127.0.0.1/", R.IP_LITERAL_HOST),
        ("https://[::1]/", R.IP_LITERAL_HOST),
        ("https://127.1/", R.IP_LITERAL_HOST),
        ("https://0x7f.0x1/", R.IP_LITERAL_HOST),
        ("https://localhost/", R.LOCAL_OR_SINGLE_LABEL_HOST),
        ("https://app.localhost/", R.LOCAL_OR_SINGLE_LABEL_HOST),
        ("https://intranet/", R.LOCAL_OR_SINGLE_LABEL_HOST),
        ("https://srv.internal/", R.LOCAL_OR_SINGLE_LABEL_HOST),
        ("https://printer.local/", R.LOCAL_OR_SINGLE_LABEL_HOST),
        ("https://www.acme-it.example:8443/", R.NON_DEFAULT_PORT),
        ("http://www.acme-it.example/", R.UNSUPPORTED_SCHEME),
    ],
)
def test_denies_ip_localhost_single_label(url: str, reason: UrlExclusionReason) -> None:
    assert reason in _reasons(url)


def test_denies_personal_host_label_lk() -> None:
    assert R.PERSONAL_AREA_HOST in _reasons("https://lk.landing.mts.by/")
    assert R.PERSONAL_AREA_HOST in _reasons("https://my.acme-it.example/")
    assert check_url_safety("https://shop.example.id/").allowed


def test_fullwidth_personal_host_label_denied() -> None:
    fullwidth = "https://ｌｋ.mts.by/"
    ascii_form = "https://lk.mts.by/"
    assert R.PERSONAL_AREA_HOST in _reasons(fullwidth)
    assert R.PERSONAL_AREA_HOST in _reasons(ascii_form)
    assert canonicalize_url(fullwidth) == ascii_form
    assert R.PERSONAL_AREA_HOST in _reasons(canonicalize_url(fullwidth))


def test_fullwidth_lk_landing_evaluate_denied() -> None:
    repo_root = next(
        path
        for path in Path(__file__).resolve().parents
        if (path / "config" / "legacy_demo_sources.mts.by.yaml").is_file()
    )
    loaded = load_registry(
        repo_root / "config" / "legacy_demo_sources.mts.by.yaml",
        purpose=RegistryPurpose.LEGACY_DEMO,
    )
    decision = evaluate_url(
        "https://ＬＫ.landing.mts.by/subs", registry=loaded.tenant("mts-public-demo")
    )
    assert not decision.allowed
    assert R.PERSONAL_AREA_HOST in decision.reasons


def test_denies_fullwidth_auth_path_segment() -> None:
    assert R.AUTH_OR_PERSONAL_AREA in _reasons(f"{BASE}/／ｌｏｇｉｎ")


def test_collects_all_reasons_in_order() -> None:
    url = "http://user:pw@lk.acme-it.example:8080/login/checkout/api?token=abc"
    assert _reasons(url) == (
        R.CREDENTIALS_IN_URL,
        R.UNSUPPORTED_SCHEME,
        R.NON_DEFAULT_PORT,
        R.PERSONAL_AREA_HOST,
        R.TOKEN_BEARING_PARAM,
        R.AUTH_OR_PERSONAL_AREA,
        R.FORM_OR_TRANSACTION_PATH,
        R.CLOSED_API_PATH,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://acme-it.example/help/",
        "https://evil.www.acme-it.example/help/",
        "https://www.acme-it.example.evil.example/help/",
    ],
)
def test_allowlist_host_exact_not_suffix(url: str) -> None:
    decision = evaluate_url(url, registry=_registry())
    assert R.HOST_NOT_ALLOWLISTED in decision.reasons


def test_prefix_segment_boundary() -> None:
    registry = _registry()
    source = registry.sources[0]
    for path in ("/help", "/help/", "/help/x", "/help/x/y?z=1"):
        assert evaluate_url(BASE + path, registry=registry, source=source).allowed, path
    decision = evaluate_url(f"{BASE}/helpdesk", registry=registry, source=source)
    assert decision.reasons == (R.PATH_NOT_ALLOWLISTED,)
    assert evaluate_url(f"{BASE}/Help/x", registry=registry, source=source).reasons == (
        R.PATH_NOT_ALLOWLISTED,
    )


def test_source_deny_prefix() -> None:
    registry = _registry()
    source = registry.sources[0]
    for path in ("/help/internal", "/help/internal/x", "/help/INTERNAL/x", "/help/%69nternal"):
        decision = evaluate_url(BASE + path, registry=registry, source=source)
        assert R.PATH_DENIED_BY_SOURCE in decision.reasons, path
    assert evaluate_url(f"{BASE}/help/internals", registry=registry, source=source).allowed


def test_decision_never_contains_raw_token_values() -> None:
    secrets = ("SuperSecretPw", "TOKVALUE42", "SESSIONVAL", "eyJhbGciOiJIUzI1NiJ9")
    url = (
        f"https://bob:{secrets[0]}@www.acme-it.example/help;jsessionid={secrets[2]}"
        f"?token={secrets[1]}&x={secrets[3]}.eyJzdWIiOiIxIn0.c2ln"
    )
    decision = evaluate_url(url, registry=_registry(), source=_registry().sources[0])
    assert not decision.allowed
    rendered = repr(decision)
    for secret in secrets:
        assert secret not in rendered


def test_manual_exclusion_exact_and_prefix() -> None:
    registry = _registry()
    excluded = [
        "/help/archive/",
        "/help/archive",
        "/help/archive/2024/promo",
        "/help/ARCHIVE/2024",
        "/help/old-faq",
        "/help/old-faq?utm_source=x#top",
    ]
    for path in excluded:
        decision = evaluate_url(BASE + path, registry=registry)
        assert decision.reasons == (R.MANUAL_EXCLUSION,), path
    for path in ("/help/archived", "/help/old-faq/sub", "/help/old-faq-2"):
        assert evaluate_url(BASE + path, registry=registry).allowed, path


def test_configured_tracking_params_apply_to_registry_checks() -> None:
    config = UrlPolicyConfig(tracking_params=frozenset({"ref"}))
    decision = evaluate_url(f"{BASE}/help/old-faq?ref=mail", registry=_registry(), config=config)
    assert decision.reasons == (R.MANUAL_EXCLUSION,)
    assert evaluate_url(f"{BASE}/help/old-faq?ref=mail", registry=_registry()).allowed


def test_manual_exclusion_reason_in_details() -> None:
    decision = evaluate_url(f"{BASE}/help/archive/2024", registry=_registry())
    assert decision.details == ("mx-001: Promotions archive 2024",)


def test_robots_disallowed_and_unavailable() -> None:
    registry = _registry()
    robots = RobotsRules.from_text("User-agent: *\nDisallow: /help/x\n", product_token=PRODUCT)
    decision = evaluate_url(f"{BASE}/help/x/1", registry=registry, robots=robots)
    assert decision.reasons == (R.ROBOTS_DISALLOWED,)
    assert decision.details == ("robots.txt line 2: Disallow: /help/x",)
    assert evaluate_url(f"{BASE}/help/y", registry=registry, robots=robots).allowed
    unavailable = evaluate_url(
        f"{BASE}/help/y", registry=registry, robots=RobotsRules.disallow_all()
    )
    assert unavailable.reasons == (R.ROBOTS_UNAVAILABLE,)


def test_robots_checks_raw_url_too() -> None:
    robots = RobotsRules.from_text("User-agent: *\nDisallow: /*?utm_\n", product_token=PRODUCT)
    decision = evaluate_url(f"{BASE}/help/?utm_source=x", registry=_registry(), robots=robots)
    assert R.ROBOTS_DISALLOWED in decision.reasons


def test_inactive_or_unapproved_source() -> None:
    source = _source(status="review_required", approval={"status": "pending"})
    decision = evaluate_url(f"{BASE}/help/", registry=_registry(source), source=source)
    assert decision.reasons == (R.SOURCE_NOT_ACTIVE, R.APPROVAL_NOT_GRANTED)


def test_foreign_source_rejected() -> None:
    with pytest.raises(TenantIsolationError):
        evaluate_url(
            f"{BASE}/help/", registry=_registry(), source=_source(tenant_id="other-tenant")
        )
