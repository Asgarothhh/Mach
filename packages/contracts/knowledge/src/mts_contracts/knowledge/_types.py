import re
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, AwareDatetime, StringConstraints

# C0 controls except \t and \n, DEL, and bidi embedding/override/isolate characters.
_CONTROL_OR_BIDI = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]")
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_MAX_URL_LENGTH = 2048
_MAX_HOST_LENGTH = 253


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def reject_blank_or_control(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    if _CONTROL_OR_BIDI.search(value):
        raise ValueError("control or bidi characters are not allowed")
    return value


def _absolute_http_url(value: str) -> str:
    if (
        len(value) > _MAX_URL_LENGTH
        or any(c.isspace() for c in value)
        or _CONTROL_OR_BIDI.search(value)
    ):
        raise ValueError("invalid URL")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("absolute http(s) URL required")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValueError("userinfo is not allowed")
    return value


def _path_prefix(value: str) -> str:
    if (
        not value.startswith("/")
        or any(c in value for c in "?#")
        or ".." in value
        or any(c.isspace() for c in value)
        or _CONTROL_OR_BIDI.search(value)
    ):
        raise ValueError(
            "path prefix must be an absolute path without query, fragment or dot-segments"
        )
    return value.rstrip("/") or "/"


def _host_name(value: str) -> str:
    if not value or len(value) > _MAX_HOST_LENGTH or value != value.lower():
        raise ValueError("host must be a lowercase ASCII host name")
    labels = value.split(".")
    if len(labels) < 2:
        raise ValueError("host must have at least two labels")
    if not all(_HOST_LABEL.match(label) for label in labels):
        raise ValueError("host labels must match [a-z0-9-], 1-63 chars, no edge hyphens")
    if labels[-1].isdigit():
        raise ValueError("IP literal hosts are not allowed")
    return value


def sorted_unique[T: str](values: tuple[T, ...]) -> tuple[T, ...]:
    return tuple(sorted(set(values)))


# Set-like fields are serialised as sorted unique tuples so that JSON (and cache keys, §6.7.8)
# is deterministic.
SORTED_UNIQUE = AfterValidator(sorted_unique)

TenantId = Annotated[
    str,
    StringConstraints(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"),
]
Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Slug = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$"),
]
LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
HostName = Annotated[str, AfterValidator(_host_name)]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]
ShortText = Annotated[
    str, StringConstraints(max_length=500), AfterValidator(reject_blank_or_control)
]
AbsoluteHttpUrl = Annotated[str, AfterValidator(_absolute_http_url)]
PathPrefix = Annotated[str, AfterValidator(_path_prefix)]
