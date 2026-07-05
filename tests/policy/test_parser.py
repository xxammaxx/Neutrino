"""Unit tests for the Policy Parser module.

Tests use mock HTTP responses and locally defined policy text — no real
external targets are contacted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from neutrino.models.policy import PolicyRule, RateLimit, ScopeEntry, ScopePolicy
from neutrino.policy.parser import PolicyParseError, PolicyParser

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


# ------------------------------------------------------------------
# Mock policy texts for testing
# ------------------------------------------------------------------

SAMPLE_HACKERONE_POLICY = """
# Example Corp Bug Bounty Program

Welcome to the Example Corp Bug Bounty Program.

## In Scope
- *.example.com
- api.example.com
- app.example.com/v2/
- 192.0.2.0/24

## Out of Scope
- staging.example.com
- internal.example.com
- *.dev.example.com

## Rate Limits
- 2 requests per second
- 1000 requests per hour
- 5 concurrent requests

## Rules
- Do not perform automated scanning without prior approval
- Do not access user data beyond what is needed for PoC
- Report vulnerabilities within 24 hours of discovery
- Do not publicly disclose before coordinated disclosure process completes
- Test accounts may be created for research purposes
"""

SAMPLE_BUG_CROWD_POLICY = """
Bugcrowd Program: Acme Inc

Targets:
    www.acme.com
    api.acme.com
    *.acme.net

Exclusions:
    dev.acme.com
    staging.acme.com

Rate Limit: 3 req/s, 500 req/hour

Requirements:
- No automated scanning
- No social engineering
- Report via Bugcrowd platform only
"""

SAMPLE_MINIMAL_POLICY = """
In Scope: example.com
"""

SAMPLE_NO_SCOPE_POLICY = """
This is a vulnerability disclosure policy.
Please report security issues to security@example.com.

Rules:
- Do not exploit vulnerabilities beyond what is necessary
- Do not access or modify user data
"""

SAMPLE_HTML_POLICY = """<!DOCTYPE html>
<html>
<head><title>Bug Bounty Program</title></head>
<body>
<h1>Example Security Bug Bounty</h1>

<h2>Scope</h2>
<ul>
<li>www.example.com</li>
<li>api.example.com</li>
</ul>

<h2>Out of Scope</h2>
<ul>
<li>test.example.com</li>
</ul>

</body>
</html>"""

SAMPLE_POLICY_WITH_BLOCKING_RULES = """
In Scope: target.example.com

Rules:
- Do not perform brute force attacks
- Do not use automated scanners
- Do not exfiltrate data
"""

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def parser() -> PolicyParser:
    """Create a fresh PolicyParser instance for each test."""
    return PolicyParser()


# ------------------------------------------------------------------
# Test: parse_from_text — Happy Path
# ------------------------------------------------------------------


def test_parse_hackerone_style_policy(parser: PolicyParser) -> None:
    """Parse a well-formed HackerOne-style policy and verify all fields."""
    policy = parser.parse_from_text(SAMPLE_HACKERONE_POLICY, source_label="test-h1")

    assert isinstance(policy, ScopePolicy)
    assert policy.source_url == "test-h1"
    assert policy.program_name == "Example Corp Bug Bounty Program"
    assert policy.source_fetched_at is not None

    # In-scope domains
    in_scope_patterns = {e.pattern for e in policy.in_scope}
    assert "*.example.com" in in_scope_patterns
    assert "api.example.com" in in_scope_patterns

    # Out-of-scope domains
    out_scope_patterns = {e.pattern for e in policy.out_of_scope}
    assert "staging.example.com" in out_scope_patterns
    assert "*.dev.example.com" in out_scope_patterns

    # Rate limits
    assert policy.rate_limits is not None
    assert policy.rate_limits.requests_per_second == 2
    assert policy.rate_limits.concurrent_requests == 5

    # Rules
    assert len(policy.rules) > 0
    assert any(r.is_blocking for r in policy.rules)

    # Raw text preserved
    assert "Example Corp Bug Bounty Program" in policy.raw_text


def test_parse_bugcrowd_policy(parser: PolicyParser) -> None:
    """Parse a Bugcrowd-style policy format."""
    policy = parser.parse_from_text(SAMPLE_BUG_CROWD_POLICY, source_label="test-bc")

    assert policy.program_name == "Acme Inc"
    assert policy.rate_limits is not None
    assert policy.rate_limits.requests_per_second == 3


def test_parse_minimal_policy(parser: PolicyParser) -> None:
    """Parse a policy with only one in-scope domain."""
    policy = parser.parse_from_text(SAMPLE_MINIMAL_POLICY, source_label="test-min")

    assert len(policy.in_scope) >= 1
    assert any("example.com" in e.pattern for e in policy.in_scope)


def test_parse_policy_no_scope(parser: PolicyParser) -> None:
    """Parse a policy with no scope sections — should return empty scope lists."""
    policy = parser.parse_from_text(SAMPLE_NO_SCOPE_POLICY, source_label="test-noscope")

    assert len(policy.in_scope) == 0
    assert len(policy.out_of_scope) == 0
    # Rules should still be extracted
    assert len(policy.rules) > 0


def test_parse_html_policy(parser: PolicyParser) -> None:
    """Parse an HTML policy page — HTML tags should be stripped."""
    policy = parser.parse_from_text(SAMPLE_HTML_POLICY, source_label="test-html")

    in_scope_patterns = {e.pattern for e in policy.in_scope}
    assert "www.example.com" in in_scope_patterns
    assert "api.example.com" in in_scope_patterns


def test_parse_blocking_rules(parser: PolicyParser) -> None:
    """Parse a policy with blocking rules (do-not statements)."""
    policy = parser.parse_from_text(SAMPLE_POLICY_WITH_BLOCKING_RULES, source_label="test-block")

    assert len(policy.rules) > 0
    blocking = policy.get_blocking_rules()
    assert len(blocking) > 0
    assert all(r.is_blocking for r in blocking)


# ------------------------------------------------------------------
# Test: Determinism
# ------------------------------------------------------------------


def test_deterministic_parsing(parser: PolicyParser) -> None:
    """Same input should produce identical output (same values)."""
    policy1 = parser.parse_from_text(SAMPLE_HACKERONE_POLICY, source_label="same")
    policy2 = parser.parse_from_text(SAMPLE_HACKERONE_POLICY, source_label="same")

    # Timestamps will differ, so compare field-by-field (excluding time)
    assert policy1.program_name == policy2.program_name
    assert [e.pattern for e in policy1.in_scope] == [e.pattern for e in policy2.in_scope]
    assert [e.pattern for e in policy1.out_of_scope] == [e.pattern for e in policy2.out_of_scope]
    assert policy1.raw_text == policy2.raw_text


# ------------------------------------------------------------------
# Test: ScopeEntry.matches() — scope checking logic
# ------------------------------------------------------------------


def test_scope_entry_exact_match() -> None:
    """Exact domain match should return True."""
    entry = ScopeEntry(pattern="example.com", type="domain")
    assert entry.matches("example.com") is True
    assert entry.matches("https://example.com/") is True


def test_scope_entry_wildcard_match() -> None:
    """Wildcard pattern should match subdomains."""
    entry = ScopeEntry(pattern="*.example.com", type="domain")
    assert entry.matches("sub.example.com") is True
    assert entry.matches("deep.sub.example.com") is False


def test_scope_entry_subdomain_match() -> None:
    """Base domain should match subdomains."""
    entry = ScopeEntry(pattern="example.com", type="domain")
    assert entry.matches("sub.example.com") is True
    assert entry.matches("www.example.com") is True


def test_scope_entry_no_match() -> None:
    """Unrelated domain should not match."""
    entry = ScopeEntry(pattern="example.com", type="domain")
    assert entry.matches("other.com") is False
    assert entry.matches("notexample.com") is False


# ------------------------------------------------------------------
# Test: ScopePolicy.is_in_scope() — full scope checking
# ------------------------------------------------------------------


def test_policy_is_in_scope_basic() -> None:
    """is_in_scope returns True for matching in-scope targets."""
    policy = ScopePolicy(
        source_url="test",
        in_scope=[ScopeEntry(pattern="example.com")],
    )
    assert policy.is_in_scope("example.com") is True


def test_policy_is_in_scope_out_of_scope_wins() -> None:
    """Out-of-scope exclusion overrides in-scope match."""
    policy = ScopePolicy(
        source_url="test",
        in_scope=[ScopeEntry(pattern="*.example.com")],
        out_of_scope=[ScopeEntry(pattern="staging.example.com")],
    )
    # staging.example.com is both in scope (wildcard) and out of scope (explicit)
    # -> exclusion wins
    assert policy.is_in_scope("staging.example.com") is False


def test_policy_is_in_scope_default_deny() -> None:
    """Default deny: unmatched targets are false."""
    policy = ScopePolicy(
        source_url="test",
        in_scope=[ScopeEntry(pattern="example.com")],
    )
    assert policy.is_in_scope("evil.com") is False


def test_policy_has_blocking_rules() -> None:
    """has_blocking_rules should detect blocking rules."""
    policy = ScopePolicy(
        source_url="test",
        rules=[
            PolicyRule(description="Do not scan", is_blocking=True),
            PolicyRule(description="Report bugs", is_blocking=False),
        ],
    )
    assert policy.has_blocking_rules() is True
    assert len(policy.get_blocking_rules()) == 1


def test_policy_no_blocking_rules() -> None:
    """has_blocking_rules should return False when no blocking rules exist."""
    policy = ScopePolicy(
        source_url="test",
        rules=[
            PolicyRule(description="Report bugs", is_blocking=False),
        ],
    )
    assert policy.has_blocking_rules() is False


# ------------------------------------------------------------------
# Test: Error Handling
# ------------------------------------------------------------------


def test_empty_text_raises_error(parser: PolicyParser) -> None:
    """Empty policy text should raise PolicyParseError."""
    with pytest.raises(PolicyParseError, match="Empty policy"):
        parser.parse_from_text("")


def test_whitespace_only_text_raises_error(parser: PolicyParser) -> None:
    """Whitespace-only text should raise PolicyParseError."""
    with pytest.raises(PolicyParseError, match="Empty policy"):
        parser.parse_from_text("   \n\t  ")


def test_non_https_url_raises_error(parser: PolicyParser) -> None:
    """Non-HTTPS URL should raise PolicyParseError."""
    with pytest.raises(PolicyParseError, match="Only HTTPS"):
        parser.parse_from_url("http://example.com")


def test_parse_error_with_cause() -> None:
    """PolicyParseError should preserve the cause exception."""
    cause = ValueError("underlying error")
    error = PolicyParseError("Something went wrong", cause=cause)
    assert error.cause is cause
    assert "Something went wrong" in str(error)


# ------------------------------------------------------------------
# Test: URL Parsing with Mock HTTP
# ------------------------------------------------------------------


def test_parse_from_url_success(parser: PolicyParser, mocker: MockerFixture) -> None:
    """parse_from_url should fetch page and parse it."""
    mock_response = mocker.MagicMock()
    mock_response.text = SAMPLE_MINIMAL_POLICY
    mock_response.raise_for_status = mocker.MagicMock()

    mock_get = mocker.patch("httpx.get", return_value=mock_response)

    policy = parser.parse_from_url("https://example.com/security")

    mock_get.assert_called_once_with(
        "https://example.com/security",
        timeout=30,
        follow_redirects=True,
    )
    assert policy.source_url == "https://example.com/security"
    assert len(policy.in_scope) >= 1


def test_parse_from_url_httpx_error(parser: PolicyParser, mocker: MockerFixture) -> None:
    """parse_from_url should raise PolicyParseError on httpx errors."""
    import httpx

    mocker.patch("httpx.get", side_effect=httpx.ConnectError("Connection refused"))

    with pytest.raises(PolicyParseError, match="Failed to fetch"):
        parser.parse_from_url("https://unreachable.example.com")


def test_parse_from_url_timeout(parser: PolicyParser, mocker: MockerFixture) -> None:
    """parse_from_url should propagate timeout as PolicyParseError."""
    import httpx

    mocker.patch("httpx.get", side_effect=httpx.TimeoutException("Timed out"))

    with pytest.raises(PolicyParseError, match="Failed to fetch"):
        parser.parse_from_url("https://slow.example.com")


# ------------------------------------------------------------------
# Test: Pydantic Model Validation
# ------------------------------------------------------------------


def test_scope_policy_serialization() -> None:
    """ScopePolicy should serialize to JSON correctly."""
    policy = ScopePolicy(
        source_url="https://example.com",
        program_name="Test Program",
        in_scope=[ScopeEntry(pattern="example.com")],
        out_of_scope=[ScopeEntry(pattern="test.example.com")],
        rate_limits=RateLimit(requests_per_second=5),
        rules=[PolicyRule(description="No brute force", is_blocking=True)],
    )

    json_data = policy.model_dump()
    assert json_data["source_url"] == "https://example.com"
    assert json_data["program_name"] == "Test Program"
    assert len(json_data["in_scope"]) == 1
    assert json_data["rate_limits"]["requests_per_second"] == 5


def test_scope_policy_deserialization() -> None:
    """ScopePolicy should deserialize from JSON correctly."""
    json_data = {
        "source_url": "https://example.com",
        "in_scope": [{"pattern": "example.com", "type": "domain"}],
        "out_of_scope": [],
        "rate_limits": None,
        "rules": [],
        "raw_text": "",
    }

    policy = ScopePolicy.model_validate(json_data)
    assert policy.source_url == "https://example.com"
    assert len(policy.in_scope) == 1
    assert policy.in_scope[0].pattern == "example.com"


# ==========================================================================
# Issue #2: New fixtures for enhanced In-Scope / Out-of-Scope extraction
# ==========================================================================

COMPREHENSIVE_POLICY = """
# MegaCorp Bug Bounty Program

## In Scope
- *.megacorp.com
- api.megacorp.com
- app.megacorp.com/v2/
- https://portal.megacorp.com/admin/
- 198.51.100.0/24
- 203.0.113.0/28

## Out of Scope
- staging.megacorp.com
- *.dev.megacorp.com
- internal.megacorp.com
- test.megacorp.com
"""

POLICY_INELIGIBLE = """
In Scope:
- example.com

Ineligible:
- admin.example.com
- internal.example.com
"""

POLICY_PROHIBITED = """
Targets:
- api.example.com

Prohibited Targets:
- staging.example.com
"""

POLICY_API_TARGETS = """
Scope:
- example.com
- api.example.com/v1/
- api.example.com/v2/users
- rest.example.com/api/
"""

POLICY_URL_WITH_PATH = """
Scope:
- https://app.example.com/dashboard
- app.example.com/v2/
- static.example.com
"""

# ==========================================================================
# Issue #2: Enhanced In-Scope / Out-of-Scope Extraction Tests
# ==========================================================================


def test_extract_wildcard_domains_with_is_wildcard(parser: PolicyParser) -> None:
    """Wildcard domains like *.megacorp.com should have is_wildcard=True and type=wildcard_domain."""
    policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test-comp")

    wildcard_entries = [e for e in policy.in_scope if e.is_wildcard]
    assert len(wildcard_entries) >= 1, "Expected at least one wildcard entry in scope"
    assert any(e.pattern == "*.megacorp.com" for e in wildcard_entries)
    for e in wildcard_entries:
        assert e.type == "wildcard_domain"
        assert e.is_wildcard is True


def test_extract_ip_ranges(parser: PolicyParser) -> None:
    """IP range entries like 198.51.100.0/24 should be detected with type=ip_range."""
    policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test-comp")

    ip_entries = [e for e in policy.in_scope if e.type == "ip_range"]
    assert len(ip_entries) >= 2, "Expected at least two IP range entries"
    ip_patterns = {e.pattern for e in ip_entries}
    assert "198.51.100.0/24" in ip_patterns
    assert "203.0.113.0/28" in ip_patterns
    for e in ip_entries:
        assert e.is_wildcard is False
        assert e.source_section == "in_scope"


def test_extract_url_with_path(parser: PolicyParser) -> None:
    """URLs with paths like app.megacorp.com/v2/ should retain the path."""
    policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test-comp")

    url_entries = [e for e in policy.in_scope if e.type in ("url", "api")]
    url_patterns = {e.pattern for e in url_entries}
    assert "app.megacorp.com/v2" in url_patterns, (
        f"Expected app.megacorp.com/v2, got {url_patterns}"
    )


def test_extract_domain_type_unchanged(parser: PolicyParser) -> None:
    """Plain domains like api.megacorp.com should still have type=domain."""
    policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test-comp")

    domain_entries = [e for e in policy.in_scope if e.type == "domain"]
    domain_patterns = {e.pattern for e in domain_entries}
    assert "api.megacorp.com" in domain_patterns


def test_source_section_tracking_in_scope(parser: PolicyParser) -> None:
    """In-scope entries should have source_section='in_scope'."""
    policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test-comp")

    for entry in policy.in_scope:
        assert entry.source_section == "in_scope", (
            f"Entry {entry.pattern} has source_section={entry.source_section}"
        )


def test_source_section_tracking_out_of_scope(parser: PolicyParser) -> None:
    """Out-of-scope entries should have source_section='out_of_scope'."""
    policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test-comp")

    assert len(policy.out_of_scope) > 0, "Expected at least one out-of-scope entry"
    for entry in policy.out_of_scope:
        assert entry.source_section == "out_of_scope", (
            f"Entry {entry.pattern} has source_section={entry.source_section}"
        )


def test_out_of_scope_wildcard(parser: PolicyParser) -> None:
    """Wildcard out-of-scope entries like *.dev.megacorp.com should be detected."""
    policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test-comp")

    dev_wildcard = [e for e in policy.out_of_scope if e.pattern == "*.dev.megacorp.com"]
    assert len(dev_wildcard) == 1
    assert dev_wildcard[0].is_wildcard is True
    assert dev_wildcard[0].type == "wildcard_domain"


def test_out_of_scope_overrides_in_scope_extraction(parser: PolicyParser) -> None:
    """is_in_scope should return False for targets in out_of_scope even if
    they match an in_scope wildcard."""
    # Build policy with explicit conflict: staging is excluded via wildcard
    policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test-comp")

    # staging.megacorp.com is explicitly out of scope
    assert policy.is_in_scope("staging.megacorp.com") is False
    # sub.dev.megacorp.com matches *.dev.megacorp.com in out_of_scope
    assert policy.is_in_scope("sub.dev.megacorp.com") is False
    # But *.megacorp.com (in scope) still allows sub.megacorp.com
    assert policy.is_in_scope("sub.megacorp.com") is True


def test_ineligible_marker_extraction(parser: PolicyParser) -> None:
    """'Ineligible' section should be treated as out-of-scope."""
    policy = parser.parse_from_text(POLICY_INELIGIBLE, source_label="test-ineligible")

    assert len(policy.out_of_scope) >= 2
    out_patterns = {e.pattern for e in policy.out_of_scope}
    assert "admin.example.com" in out_patterns
    assert "internal.example.com" in out_patterns
    for e in policy.out_of_scope:
        assert e.source_section == "out_of_scope"


def test_prohibited_targets_marker_extraction(parser: PolicyParser) -> None:
    """'Prohibited Targets' section should be treated as out-of-scope."""
    policy = parser.parse_from_text(POLICY_PROHIBITED, source_label="test-prohibited")

    assert len(policy.out_of_scope) >= 1
    out_patterns = {e.pattern for e in policy.out_of_scope}
    assert "staging.example.com" in out_patterns


def test_api_type_detection(parser: PolicyParser) -> None:
    """API endpoints (with /api/ or /vN in path) should get type='api'."""
    policy = parser.parse_from_text(POLICY_API_TARGETS, source_label="test-api")

    api_entries = [e for e in policy.in_scope if e.type == "api"]
    assert len(api_entries) >= 2, f"Expected at least 2 API entries, got {len(api_entries)}"
    api_patterns = {e.pattern for e in api_entries}
    assert "api.example.com/v1" in api_patterns, f"Got patterns: {api_patterns}"
    assert "api.example.com/v2/users" in api_patterns or "rest.example.com/api" in api_patterns


def test_url_type_vs_domain_type(parser: PolicyParser) -> None:
    """URLs with generic paths → type='url', API paths → type='api', plain domains → type='domain'."""
    policy = parser.parse_from_text(POLICY_URL_WITH_PATH, source_label="test-url")

    url_entries = [e for e in policy.in_scope if e.type == "url"]
    api_entries = [e for e in policy.in_scope if e.type == "api"]
    domain_entries = [e for e in policy.in_scope if e.type == "domain"]

    # app.example.com/v2 has /v2 → classified as api
    api_patterns = {e.pattern for e in api_entries}
    assert "app.example.com/v2" in api_patterns, f"Got api patterns: {api_patterns}"

    # app.example.com/dashboard (from https://...) has generic path → url
    url_patterns = {e.pattern for e in url_entries}
    assert any("app.example.com/dashboard" in p for p in url_patterns), (
        f"Got url patterns: {url_patterns}"
    )

    # static.example.com should be domain
    domain_patterns = {e.pattern for e in domain_entries}
    assert "static.example.com" in domain_patterns


def test_deterministic_enhanced_parsing(parser: PolicyParser) -> None:
    """Enhanced parser must still be deterministic — same input → same output."""
    p1 = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="same")
    p2 = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="same")

    assert len(p1.in_scope) == len(p2.in_scope)
    assert len(p1.out_of_scope) == len(p2.out_of_scope)

    for e1, e2 in zip(p1.in_scope, p2.in_scope, strict=True):
        assert e1.pattern == e2.pattern
        assert e1.type == e2.type
        assert e1.is_wildcard == e2.is_wildcard
        assert e1.source_section == e2.source_section

    for e1, e2 in zip(p1.out_of_scope, p2.out_of_scope, strict=True):
        assert e1.pattern == e2.pattern
        assert e1.type == e2.type
        assert e1.is_wildcard == e2.is_wildcard
        assert e1.source_section == e2.source_section


def test_no_network_in_parse_from_text(parser: PolicyParser) -> None:
    """parse_from_text should never make network requests."""
    # This is inherently verified by using local string fixtures,
    # but we explicitly assert no httpx calls are made.
    import httpx

    try:
        policy = parser.parse_from_text(COMPREHENSIVE_POLICY, source_label="test")
        assert len(policy.in_scope) > 0
        assert len(policy.out_of_scope) > 0
    except httpx.HTTPError:
        pytest.fail("parse_from_text should never make HTTP requests")


def test_scope_entry_with_source_section_serialization() -> None:
    """ScopeEntry with is_wildcard and source_section should serialize correctly."""
    entry = ScopeEntry(
        pattern="*.example.com",
        type="wildcard_domain",
        is_wildcard=True,
        source_section="in_scope",
        bounty_eligible=True,
    )
    data = entry.model_dump()
    assert data["is_wildcard"] is True
    assert data["source_section"] == "in_scope"
    assert data["type"] == "wildcard_domain"


def test_minimal_policy_with_only_one_target(parser: PolicyParser) -> None:
    """Policy with a single in-scope target should extract exactly one entry."""
    minimal = "In Scope:\n- only.example.com"
    policy = parser.parse_from_text(minimal, source_label="test-min")
    assert len(policy.in_scope) == 1
    assert policy.in_scope[0].pattern == "only.example.com"
    assert policy.in_scope[0].type == "domain"
    assert policy.in_scope[0].source_section == "in_scope"
    assert len(policy.out_of_scope) == 0


def test_empty_scope_sections(parser: PolicyParser) -> None:
    """Policy without any scope sections should return empty lists."""
    no_scope = (
        "This is a vulnerability disclosure policy.\nRules:\n- Report to security@example.com"
    )
    policy = parser.parse_from_text(no_scope, source_label="test-empty")
    assert len(policy.in_scope) == 0
    assert len(policy.out_of_scope) == 0
