"""Canonical URL form and document identity (SSOT §6.5 `canonical_url`, `document_id`).

Changing any rule here changes `document_id` for existing documents: bump
`CANONICALIZATION_VERSION` and record the migration in an ADR.
"""

import hashlib
import ipaddress
import re
from collections.abc import Iterable
from urllib.parse import SplitResult, parse_qsl, quote, unquote, urlsplit

from mts_contracts.knowledge import TenantId, UrlExclusionReason
from pydantic import TypeAdapter, ValidationError

CANONICALIZATION_VERSION = 1

MAX_URL_LENGTH = 2048

DEFAULT_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "gclid",
        "fbclid",
        "yclid",
        "ysclid",
        "msclkid",
        "dclid",
        "gbraid",
        "wbraid",
        "_openstat",
        "_ga",
        "_gl",
        "mc_cid",
        "mc_eid",
    }
)

_DEFAULT_PORTS = {"http": 80, "https": 443}
_DOCUMENT_ID_NAMESPACE = b"mts-doc-v1"
_REDACTED = "REDACTED"

_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_PATH_SAFE = "/%:@!$&'()*+,;=-._~"
_QUERY_SAFE = "-._~!$'()*,;:@/?"
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_STRAY_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_JWT = re.compile(r"^eyJ[\w-]+\.[\w-]+\.[\w-]*$", re.ASCII)
_HEX = re.compile(r"^[0-9A-Fa-f]+$")
_BASE64ISH = re.compile(r"^[A-Za-z0-9_\-+/]+={0,2}$")

_tenant_id_adapter: TypeAdapter[str] = TypeAdapter(TenantId)


class UrlCanonicalizationError(ValueError):
    """The URL cannot be put into canonical form. The message never contains the URL."""

    def __init__(self, reason: UrlExclusionReason) -> None:
        self.reason = reason
        super().__init__(f"url cannot be canonicalized: {reason.value}")


def looks_like_token(value: str, *, min_length: int = 32) -> bool:
    """JWT, long hex, or long base64(url) with mixed case and digits.

    The mixed-character requirement keeps long lowercase slugs such as
    `mobile-internet-tariffs-for-business-2026` from being treated as secrets.
    """
    if _JWT.match(value):
        return True
    if len(value) < min_length:
        return False
    if _HEX.match(value):
        return True
    return bool(
        _BASE64ISH.match(value)
        and any(c.isupper() for c in value)
        and any(c.islower() for c in value)
        and any(c.isdigit() for c in value)
    )


def _normalize_escapes(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else f"%{match.group(1).upper()}"

    return _PERCENT_ESCAPE.sub(replace, _STRAY_PERCENT.sub("%25", value))


def normalize_percent_encoding(value: str, *, safe: str = _PATH_SAFE) -> str:
    """Encode unsafe/non-ASCII characters, uppercase escapes, decode unreserved ones."""
    return _normalize_escapes(quote(value, safe=safe))


def remove_dot_segments(path: str) -> str:
    """RFC 3986 §5.2.4. Unlike `posixpath.normpath`, keeps `//` and trailing slashes."""
    output: list[str] = []
    remaining = path
    while remaining:
        if remaining.startswith("../"):
            remaining = remaining[3:]
        elif remaining.startswith("./") or remaining.startswith("/./"):
            remaining = remaining[2:]
        elif remaining == "/.":
            remaining = "/"
        elif remaining.startswith("/../"):
            remaining = remaining[3:]
            if output:
                output.pop()
        elif remaining == "/..":
            remaining = "/"
            if output:
                output.pop()
        elif remaining in (".", ".."):
            remaining = ""
        else:
            start = 1 if remaining.startswith("/") else 0
            end = remaining.find("/", start)
            if end == -1:
                end = len(remaining)
            output.append(remaining[:end])
            remaining = remaining[end:]
    return "".join(output)


def canonicalize_path(path: str) -> str:
    """Canonical path: escapes normalised, unreserved characters decoded, dot-segments removed.

    `%2F` is never decoded, case and trailing slash are preserved.
    """
    if not path:
        return "/"
    result = remove_dot_segments(normalize_percent_encoding(path))
    return result if result.startswith("/") else "/" + result


def _canonical_host(parts: SplitResult) -> str:
    host = parts.hostname
    if not host:
        raise UrlCanonicalizationError(UrlExclusionReason.INVALID_URL)
    host = host.rstrip(".")
    if not host:
        raise UrlCanonicalizationError(UrlExclusionReason.INVALID_URL)
    if ":" in host:
        try:
            return f"[{ipaddress.IPv6Address(host).compressed}]"
        except ValueError as exc:
            raise UrlCanonicalizationError(UrlExclusionReason.INVALID_URL) from exc
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UrlCanonicalizationError(UrlExclusionReason.INVALID_URL) from exc


def _quote_query(value: str) -> str:
    return quote(value, safe=_QUERY_SAFE, encoding="utf-8", errors="surrogateescape")


def _canonical_query(query: str, tracking_params: Iterable[str]) -> str:
    tracking = {name.lower() for name in tracking_params}
    pairs = [
        (name, value)
        for name, value in parse_qsl(
            query, keep_blank_values=True, encoding="utf-8", errors="surrogateescape"
        )
        if not (name.lower().startswith("utm_") or name.lower() in tracking)
    ]
    pairs.sort()
    return "&".join(f"{_quote_query(name)}={_quote_query(value)}" for name, value in pairs)


def split_url(url: str) -> SplitResult:
    """Strict pre-parse shared by canonicalization and the URL policy."""
    if (
        not url
        or len(url) > MAX_URL_LENGTH
        or any(c.isspace() for c in url)
        or _CONTROL.search(url)
        or "\\" in url
    ):
        raise UrlCanonicalizationError(UrlExclusionReason.INVALID_URL)
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise UrlCanonicalizationError(UrlExclusionReason.INVALID_URL) from exc
    return parts


def canonicalize_url(url: str, *, tracking_params: Iterable[str] = DEFAULT_TRACKING_PARAMS) -> str:
    parts = split_url(url)
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise UrlCanonicalizationError(UrlExclusionReason.UNSUPPORTED_SCHEME)
    if "@" in parts.netloc:
        raise UrlCanonicalizationError(UrlExclusionReason.CREDENTIALS_IN_URL)
    host = _canonical_host(parts)
    try:
        port = parts.port
    except ValueError as exc:
        raise UrlCanonicalizationError(UrlExclusionReason.INVALID_URL) from exc
    netloc = host if port is None or port == _DEFAULT_PORTS[scheme] else f"{host}:{port}"
    query = _canonical_query(parts.query, tracking_params)
    result = f"{scheme}://{netloc}{canonicalize_path(parts.path)}"
    if query:
        result = f"{result}?{query}"
    if len(result) > MAX_URL_LENGTH:
        raise UrlCanonicalizationError(UrlExclusionReason.INVALID_URL)
    return result


def derive_document_id(tenant_id: str, canonical_url: str) -> str:
    """Tenant-scoped document identity; accepts only an already canonical URL."""
    try:
        _tenant_id_adapter.validate_python(tenant_id)
    except ValidationError as exc:
        raise ValueError("invalid tenant_id") from exc
    if canonicalize_url(canonical_url) != canonical_url:
        raise ValueError("document_id requires a canonical URL")
    digest = hashlib.sha256()
    digest.update(_DOCUMENT_ID_NAMESPACE + b"\x00")
    digest.update(tenant_id.encode("utf-8") + b"\x00")
    digest.update(canonical_url.encode("utf-8"))
    return digest.hexdigest()


def _redact_path(path: str) -> str:
    segments = []
    for segment in path.split("/"):
        base, sep, params = segment.partition(";")
        if looks_like_token(base) or looks_like_token(unquote(base)):
            base = _REDACTED
        if sep:
            names = [param.partition("=")[0] for param in params.split(";")]
            segment = base + "".join(f";{quote(name, safe='')}={_REDACTED}" for name in names)
        else:
            segment = base
        segments.append(segment)
    return quote("/".join(segments), safe=_PATH_SAFE)


def redact_url(url: str) -> str:
    """Report/log-safe form (NFR-03): no userinfo, no query or matrix values, no fragment.

    Never raises; unparseable input becomes a fixed placeholder.
    """
    try:
        parts = urlsplit(url[: MAX_URL_LENGTH * 2])
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return "[unparseable-url]"
    if host:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            host = quote(host, safe=".-")
        if ":" in host:
            host = f"[{quote(host, safe=':.')}]"
    netloc = host if port is None else f"{host}:{port}"
    prefix = f"{quote(parts.scheme.lower(), safe='')}://{netloc}" if parts.scheme or netloc else ""
    names = [
        _REDACTED if looks_like_token(name) else quote(name, safe="")
        for name, _ in parse_qsl(parts.query, keep_blank_values=True)
    ]
    query = "&".join(f"{name}={_REDACTED}" for name in names)
    result = prefix + _redact_path(parts.path)
    if query:
        result = f"{result}?{query}"
    return result[:MAX_URL_LENGTH] or "[empty-url]"
