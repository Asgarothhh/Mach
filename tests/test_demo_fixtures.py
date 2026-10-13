from urllib.parse import urlsplit

from app.rag.demo_fixtures import (
    ACME_TENANT_ID,
    MTS_TENANT_ID,
    acme_chunks,
    mts_chunks,
)
from app.rag.retriever import build_demo_runtime

_BLOCKED_HOSTS = {
    "ihelper.mts.by",
    "lk.landing.mts.by",
    "shop.mts.by",
    "help.mts.by",
}


def test_both_tenants_publish():
    runtime = build_demo_runtime()
    assert runtime.tenants == frozenset({ACME_TENANT_ID, MTS_TENANT_ID})


def test_chunks_validate_and_acme_uses_example_hosts():
    chunks = acme_chunks()
    assert chunks
    for chunk in chunks:
        assert chunk.tenant_id == ACME_TENANT_ID
        assert chunk.trust_level.value == "tenant_approved_source"
        host = urlsplit(chunk.canonical_url).hostname
        assert host is not None
        assert host.endswith(".example")
        assert chunk.language == "ru"
        assert chunk.audience.value == "caller"


def test_mts_legacy_demo_on_help_host():
    chunks = mts_chunks()
    assert chunks
    for chunk in chunks:
        assert chunk.tenant_id == MTS_TENANT_ID
        assert chunk.trust_level.value == "legacy_demo_fixture"
        host = urlsplit(chunk.canonical_url).hostname
        assert host == "www.mts.by"
        assert urlsplit(chunk.canonical_url).path.startswith("/help")


def test_no_blocked_or_review_required_hosts():
    urls = [c.canonical_url for c in (*acme_chunks(), *mts_chunks())]
    urls += [c.source_url for c in (*acme_chunks(), *mts_chunks())]
    for url in urls:
        host = urlsplit(url).hostname or ""
        assert host not in _BLOCKED_HOSTS
        assert "/selfcare/" not in url
