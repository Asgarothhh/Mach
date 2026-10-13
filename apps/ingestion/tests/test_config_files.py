import re
from pathlib import Path
from urllib.parse import urlsplit

from mts_contracts.knowledge import (
    LEGACY_DEMO_TENANT_ID,
    ApprovalStatus,
    SourceStatus,
    UrlExclusionReason,
)

from mts_ingestion import RegistryPurpose, canonicalize_url, load_registry, merge_registries

REPO_ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "config" / "sources.by_tenant.yaml").is_file()
)
BUSINESS_FILE = REPO_ROOT / "config" / "sources.by_tenant.yaml"
LEGACY_FILE = REPO_ROOT / "config" / "legacy_demo_sources.mts.by.yaml"
SSOT_FILE = REPO_ROOT / "docs" / "SPEC_MTS_VOICE_AGENT_TRACK1.md"

R = UrlExclusionReason
PENDING_REVIEW = {"https://lk.landing.mts.by/", "https://shop.mts.by/", "https://help.mts.by/"}
SELFCARE = "https://ihelper.mts.by/selfcare/"


def _ssot_17_demo_urls() -> list[str]:
    text = SSOT_FILE.read_text(encoding="utf-8")
    section = text.split("### Наследуемые демо-источники", 1)[1].split("\n### ", 1)[0]
    return re.findall(r"^- [^:\n]+: (https://\S+)$", section, flags=re.MULTILINE)


def test_repo_business_config_valid() -> None:
    loaded = load_registry(BUSINESS_FILE, purpose=RegistryPurpose.BUSINESS)
    (tenant,) = loaded.document.tenants
    assert tenant.tenant_id == "acme-it-demo"
    assert tenant.allowed_hosts == ("www.acme-it.example",)
    indexable = {sid for (_, sid), d in loaded.decisions.items() if d.indexable}
    assert indexable == {"acme-help", "acme-price-list", "acme-contacts"}
    login = loaded.decisions[("acme-it-demo", "acme-login")]
    assert R.AUTH_OR_PERSONAL_AREA in login.reasons
    assert tenant.manual_exclusions[0].exclusion_id == "mx-001"


def test_repo_legacy_config_valid_and_selfcare_excluded_lk_review() -> None:
    loaded = load_registry(LEGACY_FILE, purpose=RegistryPurpose.LEGACY_DEMO)
    (tenant,) = loaded.document.tenants
    assert tenant.tenant_id == LEGACY_DEMO_TENANT_ID
    by_url = {s.url: s for s in tenant.sources}

    selfcare = by_url[SELFCARE]
    assert selfcare.status is SourceStatus.EXCLUDED
    assert selfcare.approval.status is ApprovalStatus.REJECTED
    assert selfcare.exclusion_reason is not None
    assert "§6.2.3" in selfcare.exclusion_reason
    assert "C6" in selfcare.exclusion_reason
    selfcare_decision = loaded.decisions[(tenant.tenant_id, selfcare.source_id)]
    assert not selfcare_decision.indexable
    assert R.AUTH_OR_PERSONAL_AREA in selfcare_decision.reasons

    for url in PENDING_REVIEW:
        source = by_url[url]
        assert source.status is SourceStatus.REVIEW_REQUIRED, url
        assert source.approval.status is ApprovalStatus.PENDING, url
        assert not loaded.decisions[(tenant.tenant_id, source.source_id)].indexable
    lk = loaded.decisions[(tenant.tenant_id, by_url["https://lk.landing.mts.by/"].source_id)]
    assert R.PERSONAL_AREA_HOST in lk.reasons

    for url, source in by_url.items():
        if url in PENDING_REVIEW or url == SELFCARE:
            continue
        assert source.status is SourceStatus.ACTIVE, url
        assert source.approval.approved_by == "role.demo-fixture-maintainer", url
        assert loaded.decisions[(tenant.tenant_id, source.source_id)].indexable, url


def test_repo_legacy_config_contains_all_ssot_17_urls() -> None:
    ssot_urls = _ssot_17_demo_urls()
    assert len(ssot_urls) == 11
    loaded = load_registry(LEGACY_FILE, purpose=RegistryPurpose.LEGACY_DEMO)
    (tenant,) = loaded.document.tenants
    configured = {canonicalize_url(s.url) for s in tenant.sources}
    assert {canonicalize_url(u) for u in ssot_urls} <= configured
    assert {urlsplit(u).hostname for u in ssot_urls} <= set(tenant.allowed_hosts)


def test_repo_configs_merge_without_conflicts() -> None:
    merged = merge_registries(
        load_registry(BUSINESS_FILE, purpose=RegistryPurpose.BUSINESS),
        load_registry(LEGACY_FILE, purpose=RegistryPurpose.LEGACY_DEMO),
    )
    assert {t.tenant_id for t in merged.document.tenants} == {
        "acme-it-demo",
        LEGACY_DEMO_TENANT_ID,
    }
