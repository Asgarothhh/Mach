from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from mts_contracts.knowledge import (
    AbsoluteHttpUrl,
    HostName,
    Identifier,
    PathPrefix,
    ShortText,
    TenantId,
    UtcDatetime,
)

tenant_id = TypeAdapter(TenantId)
identifier = TypeAdapter(Identifier)
utc_datetime = TypeAdapter(UtcDatetime)
short_text = TypeAdapter(ShortText)
abs_url = TypeAdapter(AbsoluteHttpUrl)
path_prefix = TypeAdapter(PathPrefix)
host_name = TypeAdapter(HostName)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "Acme-IT",
        "ACME",
        " acme-it",
        "acme-it ",
        "ab",
        "-acme",
        "acme-",
        "acme_it",
        "a" * 65,
    ],
)
def test_tenant_id_rejects_empty_blank_upper_padded(value: str) -> None:
    with pytest.raises(ValidationError):
        tenant_id.validate_python(value)


@pytest.mark.parametrize(
    "value", ["acme-it-demo", "mts-public-demo", "abc", "3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6b"]
)
def test_tenant_id_accepts_slug_and_lower_uuid(value: str) -> None:
    assert tenant_id.validate_python(value) == value


@pytest.mark.parametrize("value", ["owner@acme.example", "John Smith", "", " role", "-x"])
def test_identifier_rejects_email_and_spaces(value: str) -> None:
    with pytest.raises(ValidationError):
        identifier.validate_python(value)


def test_utc_datetime_rejects_naive() -> None:
    with pytest.raises(ValidationError):
        utc_datetime.validate_python(datetime(2026, 10, 13, 10, 0))
    with pytest.raises(ValidationError):
        utc_datetime.validate_python("2026-10-13T10:00:00")


def test_utc_datetime_converts_offset_to_utc() -> None:
    minsk = timezone(timedelta(hours=3))
    value = utc_datetime.validate_python(datetime(2026, 10, 31, 23, 59, tzinfo=minsk))
    assert value == datetime(2026, 10, 31, 20, 59, tzinfo=UTC)
    assert value.utcoffset() == timedelta(0)
    assert value.tzinfo is UTC
    parsed = utc_datetime.validate_python("2026-10-13T13:00:00+03:00")
    assert parsed == datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    assert parsed.tzinfo is UTC


@pytest.mark.parametrize(
    "value", ["a\x00b", "a\x1bb", "a\rb", "a\x7fb", "price\u202e01", "x\u2066y", "   ", ""]
)
def test_short_text_rejects_control_and_bidi_chars(value: str) -> None:
    with pytest.raises(ValidationError):
        short_text.validate_python(value)
    assert short_text.validate_python("Line one\nline\ttwo") == "Line one\nline\ttwo"
    with pytest.raises(ValidationError):
        short_text.validate_python("x" * 501)


@pytest.mark.parametrize(
    "value",
    [
        "/help",
        "help/page",
        "ftp://www.acme-it.example/file",
        "mailto:owner@acme-it.example",
        "https://",
        "https:///path",
        "https://www.acme-it.example/a b",
        "https://www.acme-it.example/" + "a" * 2048,
    ],
)
def test_abs_http_url_rejects_relative_and_ftp(value: str) -> None:
    with pytest.raises(ValidationError):
        abs_url.validate_python(value)
    assert abs_url.validate_python("https://www.acme-it.example/help?a=1") == (
        "https://www.acme-it.example/help?a=1"
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://user:pw@www.acme-it.example/help",
        "https://user@www.acme-it.example/help",
        "https://:pw@www.acme-it.example/help",
    ],
)
def test_abs_http_url_rejects_userinfo(value: str) -> None:
    with pytest.raises(ValidationError):
        abs_url.validate_python(value)


def test_path_prefix_normalizes_trailing_slash_and_rejects_dotdot() -> None:
    assert path_prefix.validate_python("/help/") == "/help"
    assert path_prefix.validate_python("/help") == "/help"
    assert path_prefix.validate_python("/") == "/"
    assert path_prefix.validate_python("//") == "/"
    for bad in ["help", "/help/../admin", "/help?x=1", "/help#top", "/he lp", ""]:
        with pytest.raises(ValidationError):
            path_prefix.validate_python(bad)


@pytest.mark.parametrize(
    "value",
    [
        "192.168.0.1",
        "10.0.0.1",
        "[::1]",
        "www.acme-it.example:8443",
        "localhost",
        "intranet",
        "www.acme-it.example.",
        "WWW.Acme-IT.example",
        "-bad.example",
        "bad-.example",
        "a..example",
        "under_score.example",
        "",
    ],
)
def test_host_rejects_ip_port_single_label(value: str) -> None:
    with pytest.raises(ValidationError):
        host_name.validate_python(value)
    assert host_name.validate_python("www.acme-it.example") == "www.acme-it.example"
    assert host_name.validate_python("xn--90ais.xn--90ais") == "xn--90ais.xn--90ais"
