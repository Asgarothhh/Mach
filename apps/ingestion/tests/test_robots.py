import inspect
import time

import pytest

from mts_ingestion import RobotsRules
from mts_ingestion.robots import MAX_ROBOTS_BYTES

PRODUCT = "MtsBot"


def _rules(text: str | bytes, agent: str = PRODUCT) -> RobotsRules:
    return RobotsRules.from_text(text, product_token=agent)


def test_disallow_respected() -> None:
    rules = _rules("User-agent: *\nDisallow: /private\n")
    assert not rules.is_allowed("https://www.acme-it.example/private/x")
    assert rules.is_allowed("https://www.acme-it.example/public")


def test_longest_match_allow_overrides_disallow() -> None:
    rules = _rules("User-agent: *\nDisallow: /help\nAllow: /help/faq\n")
    assert rules.is_allowed("/help/faq/roaming")
    assert not rules.is_allowed("/help/internal")


def test_allow_first_does_not_override_longer_disallow() -> None:
    rules = _rules("User-agent: *\nAllow: /\nDisallow: /x\n")
    assert not rules.is_allowed("/x")
    assert not rules.is_allowed("/x/y")
    assert rules.is_allowed("/y")


def test_tie_prefers_allow() -> None:
    assert _rules("User-agent: *\nDisallow: /page\nAllow: /page\n").is_allowed("/page")
    assert _rules("User-agent: *\nDisallow: /page\nAllow: /pag*\n").is_allowed("/page")


def test_wildcard_and_end_anchor() -> None:
    rules = _rules("User-agent: *\nDisallow: /*.pdf$\nDisallow: /private*/data\n")
    assert not rules.is_allowed("/docs/price.pdf")
    assert rules.is_allowed("/docs/price.pdf?v=2")
    assert rules.is_allowed("/docs/price.pdfx")
    assert not rules.is_allowed("/private-area/data/1")
    assert rules.is_allowed("/private-area/info")
    assert not _rules("User-agent: *\nDisallow: /a$\n").is_allowed("/a")
    assert _rules("User-agent: *\nDisallow: /a$\n").is_allowed("/ab")


def test_query_included_in_match() -> None:
    rules = _rules("User-agent: *\nDisallow: /*?sort=\n")
    assert not rules.is_allowed("https://www.acme-it.example/help?sort=asc")
    assert rules.is_allowed("https://www.acme-it.example/help")


def test_specific_group_over_star() -> None:
    text = "User-agent: *\nDisallow: /\n\nUser-agent: MtsBot/1.0\nDisallow: /drafts\n"
    rules = _rules(text, agent="mtsbot")
    assert rules.is_allowed("/help")
    assert not rules.is_allowed("/drafts/x")
    assert not _rules(text, agent="OtherBot").is_allowed("/help")


def test_merges_duplicate_groups() -> None:
    text = (
        "User-agent: MtsBot\nDisallow: /a\n\n"
        "User-agent: other\nUser-agent: mtsbot\nDisallow: /b\n"
        "Sitemap: https://www.acme-it.example/sitemap.xml\n"
    )
    rules = _rules(text)
    assert not rules.is_allowed("/a")
    assert not rules.is_allowed("/b")
    assert rules.is_allowed("/c")


def test_empty_disallow_allows_all() -> None:
    rules = _rules("User-agent: *\nDisallow:\n")
    assert rules.is_allowed("/anything")
    assert rules.rules == ()


def test_no_matching_group_allows_all() -> None:
    assert _rules("User-agent: OtherBot\nDisallow: /\n").is_allowed("/x")
    assert _rules("").is_allowed("/x")
    assert _rules("Disallow: /\n").is_allowed("/x")


def test_robots_txt_always_allowed() -> None:
    assert _rules("User-agent: *\nDisallow: /\n").is_allowed("/robots.txt")
    assert RobotsRules.disallow_all().is_allowed("https://www.acme-it.example/robots.txt")


def test_disallow_all_and_allow_all_factories() -> None:
    assert RobotsRules.allow_all().is_allowed("/x")
    assert not RobotsRules.allow_all().unavailable
    blocked = RobotsRules.disallow_all()
    assert not blocked.is_allowed("/x")
    assert blocked.unavailable


def test_crawl_delay_exposed() -> None:
    assert _rules("User-agent: *\nCrawl-delay: 2.5\nDisallow: /x\n").crawl_delay == 2.5
    assert _rules("User-agent: *\nCrawl-delay: nan\n").crawl_delay is None
    assert _rules("User-agent: *\nDisallow: /x\n").crawl_delay is None


def test_oversize_input_truncated() -> None:
    padding = "# pad\n" * (MAX_ROBOTS_BYTES // 6 + 1)
    rules = _rules("User-agent: *\n" + padding + "Disallow: /secret\n")
    assert rules.is_allowed("/secret")
    assert _rules(b"User-agent: *\nDisallow: /secret\n").is_allowed("/public")


def test_overlong_line_ignored() -> None:
    rules = _rules("User-agent: *\nDisallow: /" + "a" * 2100 + "\nDisallow: /b\n")
    assert rules.is_allowed("/" + "a" * 2100)
    assert not rules.is_allowed("/b")


def test_pathological_wildcards_fast() -> None:
    pattern = "/" + "*a" * 900 + "*b"
    text = "User-agent: *\n" + "".join(f"Disallow: {pattern}\n" for _ in range(20))
    rules = _rules(text)
    target = "/" + "a" * 1900
    start = time.perf_counter()
    allowed = rules.is_allowed(target)
    elapsed = time.perf_counter() - start
    assert allowed
    assert elapsed < 0.05


def test_explain_returns_rule_and_line() -> None:
    rules = _rules("# header\nUser-agent: *\nDisallow: /help\nAllow: /help/faq  # public\n")
    verdict = rules.explain("/help/faq/x")
    assert verdict.allowed
    assert verdict.matched_rule == "Allow: /help/faq"
    assert verdict.line_no == 4
    denied = rules.explain("/help/x")
    assert (denied.allowed, denied.matched_rule, denied.line_no) == (False, "Disallow: /help", 3)
    assert rules.explain("/other").matched_rule is None


def test_percent_encoding_normalized_both_sides() -> None:
    rules = _rules("User-agent: *\nDisallow: /путь\nDisallow: /%7euser\n")
    assert not rules.is_allowed("/%D0%BF%D1%83%D1%82%D1%8C/x")
    assert not rules.is_allowed("/~user")


def test_malformed_patterns_fail_closed() -> None:
    rules = _rules("User-agent: *\nDisallow: private\nAllow: public\nDisallow: /public\n")
    assert not rules.is_allowed("/private")
    assert not rules.is_allowed("/public")


def test_product_token_required_without_default() -> None:
    parameter = inspect.signature(RobotsRules.from_text).parameters["product_token"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    for invalid in ("", "Mts Bot", "MtsBot/1.0"):
        with pytest.raises(ValueError, match="product_token"):
            RobotsRules.from_text("", product_token=invalid)
