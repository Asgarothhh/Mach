"""robots.txt evaluation per RFC 9309 (no network).

`urllib.robotparser` is not used: it applies the first matching rule instead of the
longest match (RFC 9309 §2.2.2) and ignores the `*` and `$` wildcards.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from mts_ingestion.url_canonical import canonicalize_path, normalize_percent_encoding

# RFC 9309 §2.5: crawlers must parse at least the first 500 KiB.
MAX_ROBOTS_BYTES = 500 * 1024
MAX_LINE_CHARS = 2000

_PRODUCT_TOKEN = re.compile(r"^[A-Za-z_-]+$")
_UA_TOKEN = re.compile(r"^[A-Za-z_-]+")
_MULTI_STAR = re.compile(r"\*{2,}")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_ROBOTS_PATH = "/robots.txt"
_QUERY_SAFE = "/%:@!$&'()*+,;=-._~?"


@dataclass(frozen=True)
class RobotsRule:
    allow: bool
    pattern: str
    line_no: int | None

    @property
    def text(self) -> str:
        return f"{'Allow' if self.allow else 'Disallow'}: {self.pattern}"


@dataclass(frozen=True)
class RobotsVerdict:
    allowed: bool
    matched_rule: str | None
    line_no: int | None


def _normalize_target(value: str) -> str:
    path, sep, query = value.partition("?")
    normalized = canonicalize_path(path)
    if sep:
        normalized += "?" + normalize_percent_encoding(query, safe=_QUERY_SAFE)
    return normalized


def _normalize_pattern(value: str) -> str:
    """RFC 9309 §2.2.2: patterns and paths are compared with the same percent-encoding."""
    anchored = value.endswith("$")
    body = _MULTI_STAR.sub("*", value[:-1] if anchored else value)
    literals = [normalize_percent_encoding(part, safe=_QUERY_SAFE) for part in body.split("*")]
    return "*".join(literals) + ("$" if anchored else "")


def _pattern_matches(pattern: str, target: str) -> bool:
    """Wildcard match without regex so untrusted patterns cannot backtrack catastrophically."""
    anchored = pattern.endswith("$")
    parts = (pattern[:-1] if anchored else pattern).split("*")
    first = parts[0]
    if not target.startswith(first):
        return False
    position = len(first)
    if len(parts) == 1:
        return not anchored or position == len(target)
    for part in parts[1:-1]:
        index = target.find(part, position)
        if index < 0:
            return False
        position = index + len(part)
    last = parts[-1]
    if anchored:
        return target.endswith(last) and len(target) - len(last) >= position
    return target.find(last, position) >= 0


@dataclass
class _Group:
    agents: list[str]
    rules: list[RobotsRule]
    crawl_delay: float | None = None


def _parse_groups(text: str) -> list[_Group]:
    groups: list[_Group] = []
    current: _Group | None = None
    in_agent_lines = False
    for line_no, raw in enumerate(_LINE_BREAK.split(text), start=1):
        if len(raw) > MAX_LINE_CHARS:
            continue
        line = raw.split("#", 1)[0].strip()
        if line_no == 1:
            line = line.lstrip("\ufeff").strip()
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if current is None or not in_agent_lines:
                current = _Group(agents=[], rules=[])
                groups.append(current)
            in_agent_lines = True
            current.agents.append(value)
            continue
        if current is None or key not in ("allow", "disallow", "crawl-delay"):
            continue
        in_agent_lines = False
        if key == "crawl-delay":
            if current.crawl_delay is None:
                current.crawl_delay = _parse_delay(value)
            continue
        rule = _make_rule(key == "allow", value, line_no)
        if rule is not None:
            current.rules.append(rule)
    return groups


def _make_rule(allow: bool, value: str, line_no: int) -> RobotsRule | None:
    if not value:
        return None
    if not value.startswith(("/", "*")):
        # Fail closed on malformed patterns: such a Disallow is read as a path, such an
        # Allow is ignored.
        if allow:
            return None
        value = "/" + value
    return RobotsRule(allow=allow, pattern=_normalize_pattern(value), line_no=line_no)


def _parse_delay(value: str) -> float | None:
    try:
        delay = float(value)
    except ValueError:
        return None
    if not math.isfinite(delay) or delay < 0:
        return None
    return delay


def _agent_token(value: str) -> str:
    if value.strip() == "*":
        return "*"
    match = _UA_TOKEN.match(value.strip())
    return match.group(0).lower() if match else ""


class RobotsRules:
    """Rules applicable to one product token, with explainable verdicts."""

    def __init__(
        self,
        rules: Sequence[RobotsRule],
        *,
        crawl_delay: float | None = None,
        unavailable: bool = False,
    ) -> None:
        self._rules = tuple(rules)
        self._crawl_delay = crawl_delay
        self._unavailable = unavailable

    @classmethod
    def from_text(cls, text: str | bytes, *, product_token: str) -> "RobotsRules":
        if not _PRODUCT_TOKEN.match(product_token):
            raise ValueError("product_token must match [A-Za-z_-]+ (RFC 9309 §2.2.1)")
        data = text if isinstance(text, bytes) else text.encode("utf-8")
        decoded = data[:MAX_ROBOTS_BYTES].decode("utf-8", errors="ignore")
        groups = _parse_groups(decoded)
        token = product_token.lower()
        selected = [g for g in groups if any(_agent_token(a) == token for a in g.agents)]
        if not selected:
            selected = [g for g in groups if any(_agent_token(a) == "*" for a in g.agents)]
        rules = [rule for group in selected for rule in group.rules]
        delays = [g.crawl_delay for g in selected if g.crawl_delay is not None]
        return cls(rules, crawl_delay=delays[0] if delays else None)

    @classmethod
    def allow_all(cls) -> "RobotsRules":
        """robots.txt answered 4xx (RFC 9309 §2.3.1.3)."""
        return cls(())

    @classmethod
    def disallow_all(cls) -> "RobotsRules":
        """robots.txt unreachable or 5xx (RFC 9309 §2.3.1.4)."""
        return cls((RobotsRule(allow=False, pattern="/", line_no=None),), unavailable=True)

    @property
    def unavailable(self) -> bool:
        return self._unavailable

    @property
    def crawl_delay(self) -> float | None:
        return self._crawl_delay

    @property
    def rules(self) -> tuple[RobotsRule, ...]:
        return self._rules

    def explain(self, url: str) -> RobotsVerdict:
        """`url` is an absolute URL or a path (optionally with query)."""
        if url.startswith("/"):
            target = url.split("#", 1)[0]
        else:
            parts = urlsplit(url)
            target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        target = _normalize_target(target)
        if target == _ROBOTS_PATH:
            return RobotsVerdict(allowed=True, matched_rule=None, line_no=None)
        best: RobotsRule | None = None
        for rule in self._rules:
            if not _pattern_matches(rule.pattern, target):
                continue
            if (
                best is None
                or len(rule.pattern) > len(best.pattern)
                or (len(rule.pattern) == len(best.pattern) and rule.allow and not best.allow)
            ):
                best = rule
        if best is None:
            return RobotsVerdict(allowed=True, matched_rule=None, line_no=None)
        return RobotsVerdict(allowed=best.allow, matched_rule=best.text, line_no=best.line_no)

    def is_allowed(self, url: str) -> bool:
        return self.explain(url).allowed
