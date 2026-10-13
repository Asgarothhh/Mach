import pytest
from mts_contracts.knowledge import UrlExclusionReason

from mts_ingestion import (
    UrlCanonicalizationError,
    canonicalize_url,
    derive_document_id,
    redact_url,
)

BASE = "https://www.acme-it.example"
TENANT = "acme-it-demo"


def test_removes_utm_and_click_ids() -> None:
    url = f"{BASE}/help/?utm_source=x&utm_medium=y&gclid=1&fbclid=2&yclid=3&ysclid=4&_ga=5"
    assert canonicalize_url(url) == f"{BASE}/help/"


def test_tracking_match_case_insensitive() -> None:
    assert canonicalize_url(f"{BASE}/p?UTM_Source=x&GCLID=1&Msclkid=2") == f"{BASE}/p"


def test_keeps_meaningful_params_and_values() -> None:
    url = f"{BASE}/tariffs?region=minsk&page=2&utm_campaign=z&empty="
    assert canonicalize_url(url) == f"{BASE}/tariffs?empty=&page=2&region=minsk"


def test_sorts_params_deterministically() -> None:
    a = canonicalize_url(f"{BASE}/p?b=2&a=1&a=0")
    b = canonicalize_url(f"{BASE}/p?a=0&b=2&a=1")
    assert a == b == f"{BASE}/p?a=0&a=1&b=2"


def test_drops_fragment() -> None:
    assert canonicalize_url(f"{BASE}/help/faq#roaming") == f"{BASE}/help/faq"
    assert canonicalize_url(f"{BASE}/help/faq?x=1#roaming") == f"{BASE}/help/faq?x=1"


def test_lowercases_scheme_and_host_not_path() -> None:
    url = "HTTPS://WWW.Acme-IT.Example/Help/FAQ"
    assert canonicalize_url(url) == f"{BASE}/Help/FAQ"


def test_strips_default_port_and_trailing_dot() -> None:
    assert canonicalize_url("https://www.acme-it.example.:443/x") == f"{BASE}/x"
    assert canonicalize_url("http://www.acme-it.example:80/x") == "http://www.acme-it.example/x"
    assert canonicalize_url("https://www.acme-it.example:8443/x") == f"{BASE}:8443/x"


def test_idna_cyrillic_host() -> None:
    canonical = canonicalize_url("https://Пример.бел/Путь")
    host = "пример.бел".encode("idna").decode("ascii")
    assert host.endswith(".xn--90ais")
    assert canonical == f"https://{host}/%D0%9F%D1%83%D1%82%D1%8C"


def test_decodes_unreserved_not_slash() -> None:
    assert canonicalize_url(f"{BASE}/a%7eb%2fc%41%2D") == f"{BASE}/a~b%2FcA-"


def test_removes_dot_segments_including_encoded() -> None:
    assert canonicalize_url(f"{BASE}/a/b/../c/./d") == f"{BASE}/a/c/d"
    assert canonicalize_url(f"{BASE}/a/%2E%2E/b") == f"{BASE}/b"
    assert canonicalize_url(f"{BASE}/a/%2e/b") == f"{BASE}/a/b"
    assert canonicalize_url(f"{BASE}/../../x") == f"{BASE}/x"


def test_empty_path_becomes_root() -> None:
    assert canonicalize_url("https://www.acme-it.example") == f"{BASE}/"
    assert canonicalize_url("https://www.acme-it.example?utm_source=x") == f"{BASE}/"


def test_preserves_trailing_slash() -> None:
    assert canonicalize_url(f"{BASE}/help/") == f"{BASE}/help/"
    assert canonicalize_url(f"{BASE}/help") == f"{BASE}/help"
    assert canonicalize_url(f"{BASE}/a//b/") == f"{BASE}/a//b/"


CORPUS = [
    f"{BASE}/help/?utm_source=x&b=2&a=1#f",
    "HTTPS://WWW.ACME-IT.EXAMPLE.:443/A/./B/../C%7e?Z=%7a&y=a+b",
    "https://пример.бел/путь/к/файлу.pdf?имя=значение",
    f"{BASE}/a%2Fb/%2e%2E/c?q=%2B%20%26",
    f"{BASE}/100%/bad%zzescape?x=%",
    "http://[2001:DB8::0:1]:8080/x",
    f"{BASE}/a//b/?flag",
    f"{BASE}/tariffs;v=1?k=v&k=&k",
]


@pytest.mark.parametrize("url", CORPUS)
def test_idempotent_over_corpus(url: str) -> None:
    once = canonicalize_url(url)
    assert canonicalize_url(once) == once


def test_rejects_userinfo() -> None:
    with pytest.raises(UrlCanonicalizationError) as info:
        canonicalize_url("https://user:s3cr3t@www.acme-it.example/help/")
    assert info.value.reason is UrlExclusionReason.CREDENTIALS_IN_URL
    assert "s3cr3t" not in str(info.value)


@pytest.mark.parametrize(
    "url", ["ftp://www.acme-it.example/f", "javascript:alert(1)", "file:///etc/passwd"]
)
def test_rejects_non_http_scheme(url: str) -> None:
    with pytest.raises(UrlCanonicalizationError) as info:
        canonicalize_url(url)
    assert info.value.reason is UrlExclusionReason.UNSUPPORTED_SCHEME


@pytest.mark.parametrize(
    "url", ["", "https:///nohost", "https://a b.example/", "https://x.example/\x00", "x" * 3000]
)
def test_rejects_invalid(url: str) -> None:
    with pytest.raises(UrlCanonicalizationError) as info:
        canonicalize_url(url)
    assert info.value.reason is UrlExclusionReason.INVALID_URL


def test_document_id_stable_across_tracking_and_fragment() -> None:
    ids = {
        derive_document_id(TENANT, canonicalize_url(u))
        for u in (
            f"{BASE}/help/faq",
            f"{BASE}/help/faq#top",
            f"{BASE}/help/faq?utm_source=mail&gclid=1",
            "HTTPS://www.acme-it.example:443/help/./faq",
        )
    }
    assert len(ids) == 1


def test_document_id_differs_by_tenant() -> None:
    canonical = canonicalize_url(f"{BASE}/help/faq")
    assert derive_document_id(TENANT, canonical) != derive_document_id("other-tenant", canonical)


def test_document_id_is_not_url() -> None:
    canonical = canonicalize_url(f"{BASE}/help/faq")
    document_id = derive_document_id(TENANT, canonical)
    assert len(document_id) == 64
    assert all(c in "0123456789abcdef" for c in document_id)
    assert "acme" not in document_id
    with pytest.raises(ValueError, match="canonical"):
        derive_document_id(TENANT, f"{BASE}/help/faq?utm_source=x")
    with pytest.raises(ValueError, match="tenant"):
        derive_document_id(" Acme ", canonical)


def test_redact_url_hides_query_values_and_userinfo() -> None:
    url = "https://user:s3cr3t@www.acme-it.example/p;jsessionid=ABC123?token=xyz&q=1#frag"
    redacted = redact_url(url)
    assert redacted == f"{BASE}/p;jsessionid=REDACTED?token=REDACTED&q=REDACTED"
    for secret in ("user", "s3cr3t", "ABC123", "xyz", "frag"):
        assert secret not in redacted


def test_redact_url_hides_token_like_param_names_and_never_raises() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    assert jwt not in redact_url(f"{BASE}/cb?{jwt}")
    assert redact_url("https://[broken/") == "[unparseable-url]"


def test_invalid_utf8_query_escapes_do_not_collide() -> None:
    ff = canonicalize_url(f"{BASE}/p?id=%FF")
    fe = canonicalize_url(f"{BASE}/p?id=%FE")
    assert ff != fe
    assert canonicalize_url(ff) == ff
    assert canonicalize_url(fe) == fe
    assert derive_document_id(TENANT, ff) != derive_document_id(TENANT, fe)
