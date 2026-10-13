"""URL admission policy (SSOT §6.1, §6.2.3; decomposition §4 MLB-SRC-03/05).

Allow rules match narrowly (case-sensitive, canonical path); deny rules match broadly
(case-insensitive, fully percent-decoded) so `/LOGIN` or `/%6Cogin` cannot bypass them.
"""

import ipaddress
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import SplitResult, parse_qsl, unquote, urlsplit

from mts_contracts.knowledge import (
    ApprovalStatus,
    ManualExclusion,
    SourceRecord,
    SourceStatus,
    TenantIsolationError,
    TenantSourceRegistry,
    UrlExclusionReason,
)

from mts_ingestion.robots import RobotsRules
from mts_ingestion.url_canonical import (
    DEFAULT_TRACKING_PARAMS,
    UrlCanonicalizationError,
    canonicalize_path,
    canonicalize_url,
    looks_like_token,
    redact_url,
    split_url,
)

R = UrlExclusionReason

_DEFAULT_PORTS = {"http": 80, "https": 443}
_MAX_DECODE_ROUNDS = 3


@dataclass(frozen=True)
class UrlPolicyConfig:
    personal_host_labels: frozenset[str] = frozenset(
        {"lk", "my", "selfcare", "login", "auth", "sso", "account", "passport", "id"}
    )
    token_param_names: frozenset[str] = frozenset(
        {
            "token",
            "access_token",
            "id_token",
            "refresh_token",
            "auth",
            "authorization",
            "session",
            "sessionid",
            "session_id",
            "sid",
            "jsessionid",
            "phpsessid",
            "sig",
            "signature",
            "api_key",
            "apikey",
            "key",
            "password",
            "passwd",
            "pwd",
            "otp",
            "code",
            "state",
            "ticket",
            "jwt",
            "sso",
            "x-amz-signature",
            "x-amz-credential",
            "x-goog-signature",
        }
    )
    auth_segments: frozenset[str] = frozenset(
        {
            "login",
            "logout",
            "signin",
            "sign-in",
            "signup",
            "sign-up",
            "register",
            "auth",
            "oauth",
            "sso",
            "selfcare",
            "self-care",
            "account",
            "accounts",
            "profile",
            "cabinet",
            "lk",
            "my",
            "password",
            "reset-password",
        }
    )
    form_segments: frozenset[str] = frozenset(
        {"form", "forms", "checkout", "cart", "basket", "payment"}
    )
    api_segments: frozenset[str] = frozenset({"api", "graphql"})
    local_suffixes: frozenset[str] = frozenset({"localhost", "local", "internal"})
    tracking_params: frozenset[str] = DEFAULT_TRACKING_PARAMS
    min_token_length: int = 32
    require_https: bool = True


DEFAULT_URL_POLICY = UrlPolicyConfig()


@dataclass(frozen=True)
class UrlDecision:
    """Explainable admission decision; never contains raw query values or credentials."""

    redacted_url: str
    canonical_url: str | None
    allowed: bool
    reasons: tuple[UrlExclusionReason, ...]
    details: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.allowed == bool(self.reasons):
            raise ValueError("allowed must be true exactly when there are no reasons")
        if not self.allowed and self.canonical_url is not None:
            raise ValueError("canonical_url is only set for allowed URLs")


class _Reasons:
    def __init__(self) -> None:
        self.items: list[UrlExclusionReason] = []
        self.details: list[str] = []

    def add(self, reason: UrlExclusionReason, detail: str | None = None) -> None:
        if reason not in self.items:
            self.items.append(reason)
        if detail is not None and detail not in self.details:
            self.details.append(detail)


def fully_decoded(value: str) -> str:
    """Repeated percent-decoding (defeats double encoding)."""
    decoded = value
    for _ in range(_MAX_DECODE_ROUNDS):
        step = unquote(decoded)
        if step == decoded:
            break
        decoded = step
    return decoded


def fully_decoded_lower(value: str) -> str:
    """Repeated percent-decoding, then NFKC-casefold so fullwidth segments cannot bypass denies."""
    return unicodedata.normalize("NFKC", fully_decoded(value)).casefold()


def path_within_prefix(path: str, prefix: str) -> bool:
    """Segment-boundary match: `/help` covers `/help`, `/help/`, `/help/x`, not `/helpdesk`."""
    prefix = prefix.rstrip("/") or "/"
    return prefix == "/" or path == prefix or path.startswith(prefix + "/")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return True
    last = host.rsplit(".", 1)[-1]
    # Numeric/hex last labels are resolved as IPv4 by many resolvers (e.g. `127.1`, `0x7f.1`).
    return last.isdigit() or (last.startswith("0x") and len(last) > 2)


def _folded_host(host: str) -> str:
    """IDNA/ASCII form used by canonicalize_url; NFKC-casefold if IDNA cannot be applied."""
    if ":" in host:
        return host
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return unicodedata.normalize("NFKC", host).casefold()


def _hosts_for_deny(host: str) -> tuple[str, ...]:
    folded = _folded_host(host)
    return (host,) if folded == host else (host, folded)


def _check_host(parts: SplitResult, scheme: str, config: UrlPolicyConfig, out: _Reasons) -> bool:
    host = (parts.hostname or "").rstrip(".")
    if not host:
        out.add(R.INVALID_URL)
        return False
    try:
        port = parts.port
    except ValueError:
        out.add(R.INVALID_URL)
        return False
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        out.add(R.NON_DEFAULT_PORT)
    for candidate in _hosts_for_deny(host):
        ip_literal = _is_ip_literal(candidate)
        labels = candidate.split(".")
        if ip_literal:
            out.add(R.IP_LITERAL_HOST)
        elif len(labels) < 2 or labels[-1] in config.local_suffixes:
            out.add(R.LOCAL_OR_SINGLE_LABEL_HOST)
        # The last label is a TLD (`.id`, `.my` are ccTLDs), not a personal-area marker.
        if not ip_literal and any(label in config.personal_host_labels for label in labels[:-1]):
            out.add(R.PERSONAL_AREA_HOST)
    return True


def _check_tokens(parts: SplitResult, config: UrlPolicyConfig, out: _Reasons) -> None:
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if any(name.lower() in config.token_param_names for name, _ in pairs):
        out.add(R.TOKEN_BEARING_PARAM)
    if any(
        looks_like_token(item, min_length=config.min_token_length)
        for pair in pairs
        for item in pair
    ):
        out.add(R.TOKEN_LIKE_VALUE)
    for raw in fully_decoded(parts.path).replace("\\", "/").split("/"):
        segment = raw.split(";", 1)[0]
        nfkc = unicodedata.normalize("NFKC", segment)
        if looks_like_token(segment, min_length=config.min_token_length) or looks_like_token(
            nfkc, min_length=config.min_token_length
        ):
            out.add(R.TOKEN_LIKE_VALUE)
            break
    if ";" in fully_decoded_lower(parts.path):
        out.add(R.SESSION_PATH_PARAM)


def _path_segments(path: str) -> set[str]:
    segments: set[str] = set()
    for raw in fully_decoded_lower(path).replace("\\", "/").split("/"):
        segment = raw.split(";", 1)[0]
        if segment:
            segments.add(segment)
            segments.add(segment.split(".", 1)[0])
    return segments


def _check_path(parts: SplitResult, config: UrlPolicyConfig, out: _Reasons) -> None:
    segments = _path_segments(parts.path)
    if segments & config.auth_segments:
        out.add(R.AUTH_OR_PERSONAL_AREA)
    if segments & config.form_segments:
        out.add(R.FORM_OR_TRANSACTION_PATH)
    if segments & config.api_segments:
        out.add(R.CLOSED_API_PATH)


def _safety_reasons(url: str, config: UrlPolicyConfig, out: _Reasons) -> None:
    try:
        parts = split_url(url)
    except UrlCanonicalizationError as exc:
        out.add(exc.reason)
        return
    scheme = parts.scheme.lower()
    if "@" in parts.netloc:
        out.add(R.CREDENTIALS_IN_URL)
    if scheme not in _DEFAULT_PORTS or (config.require_https and scheme != "https"):
        out.add(R.UNSUPPORTED_SCHEME)
    if not _check_host(parts, scheme, config, out):
        return
    _check_tokens(parts, config, out)
    _check_path(parts, config, out)


def _canonical_or_none(url: str, config: UrlPolicyConfig, out: _Reasons) -> str | None:
    try:
        return canonicalize_url(url, tracking_params=config.tracking_params)
    except UrlCanonicalizationError as exc:
        out.add(exc.reason)
        return None


def _decision(url: str, canonical: str | None, out: _Reasons) -> UrlDecision:
    allowed = not out.items
    return UrlDecision(
        redacted_url=redact_url(url),
        canonical_url=canonical if allowed else None,
        allowed=allowed,
        reasons=tuple(out.items),
        details=tuple(out.details),
    )


def check_url_safety(url: str, config: UrlPolicyConfig = DEFAULT_URL_POLICY) -> UrlDecision:
    """Tenant-independent checks (MLB-SRC-03). All reasons are collected in a fixed order."""
    out = _Reasons()
    _safety_reasons(url, config, out)
    canonical = _canonical_or_none(url, config, out)
    return _decision(url, canonical, out)


def manual_exclusion_matches(
    exclusion: ManualExclusion,
    canonical_url: str,
    *,
    tracking_params: frozenset[str] = DEFAULT_TRACKING_PARAMS,
) -> bool:
    """Deny rule: compared case-insensitively on decoded canonical URLs.

    A prefix exclusion covers the same origin and every path under its path
    (segment boundary); its query, if any, is ignored, which only widens the exclusion.
    """
    try:
        excluded = canonicalize_url(exclusion.url, tracking_params=tracking_params)
    except UrlCanonicalizationError:
        return False
    if exclusion.match == "exact":
        return fully_decoded_lower(excluded) == fully_decoded_lower(canonical_url)
    target, rule = urlsplit(canonical_url), urlsplit(excluded)
    if (target.scheme, target.netloc) != (rule.scheme, rule.netloc):
        return False
    return path_within_prefix(fully_decoded_lower(target.path), fully_decoded_lower(rule.path))


def _check_registry(
    parts: SplitResult,
    canonical: str,
    registry: TenantSourceRegistry,
    source: SourceRecord | None,
    config: UrlPolicyConfig,
    out: _Reasons,
) -> None:
    host = parts.hostname or ""
    if host not in registry.allowed_hosts:
        out.add(R.HOST_NOT_ALLOWLISTED)
    if source is not None:
        try:
            source_canonical = canonicalize_url(source.url, tracking_params=config.tracking_params)
            source_host = urlsplit(source_canonical).hostname
        except UrlCanonicalizationError:
            source_host = None
        within = any(
            path_within_prefix(parts.path, canonicalize_path(prefix))
            for prefix in source.allow_path_prefixes
        )
        if host != source_host or not within:
            out.add(R.PATH_NOT_ALLOWLISTED)
        decoded = fully_decoded_lower(parts.path)
        if any(
            path_within_prefix(decoded, fully_decoded_lower(prefix))
            for prefix in source.deny_path_prefixes
        ):
            out.add(R.PATH_DENIED_BY_SOURCE)
    for exclusion in registry.manual_exclusions:
        if manual_exclusion_matches(exclusion, canonical, tracking_params=config.tracking_params):
            out.add(R.MANUAL_EXCLUSION, f"{exclusion.exclusion_id}: {exclusion.reason}")


def _check_robots(url: str, canonical: str, robots: RobotsRules, out: _Reasons) -> None:
    if robots.unavailable:
        out.add(R.ROBOTS_UNAVAILABLE)
        return
    candidates = [canonical]
    try:
        split_url(url)
        candidates.append(url)
    except UrlCanonicalizationError:
        pass
    for candidate in candidates:
        verdict = robots.explain(candidate)
        if not verdict.allowed:
            line = verdict.line_no if verdict.line_no is not None else "-"
            out.add(R.ROBOTS_DISALLOWED, f"robots.txt line {line}: {verdict.matched_rule}")
            return


def evaluate_url(
    url: str,
    *,
    registry: TenantSourceRegistry,
    source: SourceRecord | None = None,
    robots: RobotsRules | None = None,
    config: UrlPolicyConfig = DEFAULT_URL_POLICY,
) -> UrlDecision:
    """Full admission decision for one URL of one tenant (safety, scope, exclusions, robots)."""
    if source is not None and source.tenant_id != registry.tenant_id:
        raise TenantIsolationError("source does not belong to the registry tenant")
    out = _Reasons()
    _safety_reasons(url, config, out)
    canonical = _canonical_or_none(url, config, out)
    if canonical is not None:
        _check_registry(urlsplit(canonical), canonical, registry, source, config, out)
        if robots is not None:
            _check_robots(url, canonical, robots, out)
    if source is not None:
        if source.status is not SourceStatus.ACTIVE:
            out.add(R.SOURCE_NOT_ACTIVE)
        if source.approval.status is not ApprovalStatus.APPROVED:
            out.add(R.APPROVAL_NOT_GRANTED)
    return _decision(url, canonical, out)
