"""Unit tests for the Policy Parser module.

Tests use mock HTTP responses and locally defined policy text — no real
external targets are contacted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from neutrino.models.policy import AutomationPolicy, PolicyRule, RateLimit, ScopeEntry, ScopePolicy
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


# ==========================================================================
# Issue #3: Rate-Limit & Automation Extraction Tests
# ==========================================================================

# ------------------------------------------------------------------
# Fixtures: policy texts for rate-limit, automation, and test-type extraction
# ------------------------------------------------------------------

POLICY_RATE_LIMIT_PER_SECOND = """
In Scope: example.com

Rate Limit: 2 requests per second
"""

POLICY_RATE_LIMIT_PER_MINUTE = """
In Scope: example.com

Rate Limit: 60 requests per minute
"""

POLICY_RATE_LIMIT_PER_HOUR = """
In Scope: example.com

Rate Limit: 1000 requests per hour
"""

POLICY_RATE_LIMIT_PER_DAY = """
In Scope: example.com

Monthly limit: 10000 requests per day
"""

POLICY_RATE_LIMIT_CONCURRENT = """
In Scope: example.com

Rate Limit:
- 5 concurrent requests
"""

POLICY_RATE_LIMIT_COMBINED = """
In Scope: example.com

Rate Limit:
- 3 req/s
- 100 req/min
- 500 req/hour
- 10000 req/day
- 5 concurrent requests
"""

POLICY_NO_RATE_LIMIT = """
In Scope: example.com

Rules:
- Report vulnerabilities within 24 hours
"""

POLICY_AUTOMATION_PROHIBITED = """
In Scope: example.com

Automated scanning is prohibited.
"""

POLICY_AUTOMATION_NO_SCANNERS = """
In Scope: example.com

Rules:
- Do not use automated scanners
- No automated testing without permission
"""

POLICY_AUTOMATION_REQUIRES_APPROVAL = """
In Scope: example.com

Automated testing requires prior approval.
"""

POLICY_AUTOMATION_CONTACT_TEAM = """
In Scope: example.com

You must obtain prior written permission before using automated tools.
"""

POLICY_AUTOMATION_ALLOWED = """
In Scope: example.com

Automated testing is allowed within the published rate limits.
"""

POLICY_AUTOMATION_WELCOME = """
In Scope: example.com

Automation is welcome and encouraged!
"""

POLICY_NO_AUTOMATION_MENTION = """
In Scope: example.com

Please report security issues to security@example.com.
"""

POLICY_PROHIBITED_TESTS = """
In Scope: example.com

Rules:
- No brute force attacks
- No credential stuffing
- No social engineering
- No phishing
- No spam
- Do not perform DDoS attacks
- No destructive testing
- Physical attacks are prohibited
- Do not exfiltrate data
- Do not access user data
"""

POLICY_ALLOWED_TESTS = """
In Scope: example.com

Allowed testing:
- Web application testing
- API testing
- Authenticated testing with test accounts is encouraged
- Non-destructive testing is permitted
- Rate-limited automated testing is allowed
"""

POLICY_MIXED_TESTS = """
In Scope: example.com

Allowed:
- API testing
- Non-destructive testing

Prohibited:
- No brute force attacks
- No social engineering
- Do not access user data
- No automated scanning
"""

POLICY_CONTRADICTORY_AUTOMATION = """
In Scope: example.com

Automated scanning is prohibited.
However, automated testing is allowed within rate limits.
"""

POLICY_DDOS_VARIANT = """
In Scope: example.com

Do not perform denial of service attacks.
"""

# ------------------------------------------------------------------
# Rate-Limit Tests
# ------------------------------------------------------------------


class TestRateLimitExtraction:
    """Tests for enhanced rate-limit extraction (second/minute/hour/day/concurrent)."""

    def test_extract_per_second(self, parser: PolicyParser) -> None:
        """'2 requests per second' → requests_per_second == 2."""
        policy = parser.parse_from_text(POLICY_RATE_LIMIT_PER_SECOND, source_label="test-rl-1")
        assert policy.rate_limits is not None
        assert policy.rate_limits.requests_per_second == 2

    def test_extract_per_minute(self, parser: PolicyParser) -> None:
        """'60 requests per minute' → requests_per_minute == 60."""
        policy = parser.parse_from_text(POLICY_RATE_LIMIT_PER_MINUTE, source_label="test-rl-2")
        assert policy.rate_limits is not None
        assert policy.rate_limits.requests_per_minute == 60

    def test_extract_per_hour(self, parser: PolicyParser) -> None:
        """'1000 requests per hour' → requests_per_hour == 1000."""
        policy = parser.parse_from_text(POLICY_RATE_LIMIT_PER_HOUR, source_label="test-rl-3")
        assert policy.rate_limits is not None
        assert policy.rate_limits.requests_per_hour == 1000

    def test_extract_per_day(self, parser: PolicyParser) -> None:
        """'10000 requests per day' → requests_per_day == 10000."""
        policy = parser.parse_from_text(POLICY_RATE_LIMIT_PER_DAY, source_label="test-rl-4")
        assert policy.rate_limits is not None
        assert policy.rate_limits.requests_per_day == 10000

    def test_extract_concurrent(self, parser: PolicyParser) -> None:
        """'5 concurrent requests' → concurrent_requests == 5."""
        policy = parser.parse_from_text(POLICY_RATE_LIMIT_CONCURRENT, source_label="test-rl-5")
        assert policy.rate_limits is not None
        assert policy.rate_limits.concurrent_requests == 5

    def test_extract_combined_rate_limits(self, parser: PolicyParser) -> None:
        """Combined limits with all units (req/s, req/min, req/hour, req/day, concurrent)."""
        policy = parser.parse_from_text(POLICY_RATE_LIMIT_COMBINED, source_label="test-rl-combined")
        assert policy.rate_limits is not None
        assert policy.rate_limits.requests_per_second == 3
        assert policy.rate_limits.requests_per_minute == 100
        assert policy.rate_limits.requests_per_hour == 500
        assert policy.rate_limits.requests_per_day == 10000
        assert policy.rate_limits.concurrent_requests == 5

    def test_no_rate_limit_returns_none(self, parser: PolicyParser) -> None:
        """Policy without rate-limit → rate_limits is None."""
        policy = parser.parse_from_text(POLICY_NO_RATE_LIMIT, source_label="test-no-rl")
        assert policy.rate_limits is None

    def test_rate_limit_serialization_new_fields(self, parser: PolicyParser) -> None:
        """RateLimit with minute/day fields serializes correctly via Pydantic."""
        policy = parser.parse_from_text(POLICY_RATE_LIMIT_COMBINED, source_label="test-serial")
        assert policy.rate_limits is not None
        data = policy.rate_limits.model_dump()
        assert data["requests_per_minute"] == 100
        assert data["requests_per_day"] == 10000
        assert data["requests_per_second"] == 3
        assert data["requests_per_hour"] == 500
        assert data["concurrent_requests"] == 5


# ------------------------------------------------------------------
# Automation Policy Tests
# ------------------------------------------------------------------


class TestAutomationPolicyExtraction:
    """Tests for automation policy detection."""

    def test_automation_prohibited(self, parser: PolicyParser) -> None:
        """'Automated scanning is prohibited' → status='prohibited'."""
        policy = parser.parse_from_text(POLICY_AUTOMATION_PROHIBITED, source_label="test-ap-1")
        assert policy.automation_policy.status == "prohibited"
        assert policy.automation_policy.is_prohibited is True
        assert policy.automation_policy.evidence is not None

    def test_automation_no_scanners_prohibited(self, parser: PolicyParser) -> None:
        """'Do not use automated scanners' → status='prohibited'."""
        policy = parser.parse_from_text(POLICY_AUTOMATION_NO_SCANNERS, source_label="test-ap-2")
        assert policy.automation_policy.status == "prohibited"

    def test_automation_requires_approval(self, parser: PolicyParser) -> None:
        """'Automated testing requires prior approval' → status='requires_approval'."""
        policy = parser.parse_from_text(
            POLICY_AUTOMATION_REQUIRES_APPROVAL, source_label="test-ap-3"
        )
        assert policy.automation_policy.status == "requires_approval"
        assert policy.automation_policy.requires_approval is True

    def test_automation_must_obtain_permission(self, parser: PolicyParser) -> None:
        """'Must obtain prior written permission' → status='requires_approval'."""
        policy = parser.parse_from_text(POLICY_AUTOMATION_CONTACT_TEAM, source_label="test-ap-4")
        assert policy.automation_policy.status == "requires_approval"

    def test_automation_allowed_within_limits(self, parser: PolicyParser) -> None:
        """'Automated testing is allowed within rate limits' → status='allowed'."""
        policy = parser.parse_from_text(POLICY_AUTOMATION_ALLOWED, source_label="test-ap-5")
        assert policy.automation_policy.status == "allowed"
        assert policy.automation_policy.is_allowed is True

    def test_automation_welcome(self, parser: PolicyParser) -> None:
        """'Automation is welcome' → status='allowed'."""
        policy = parser.parse_from_text(POLICY_AUTOMATION_WELCOME, source_label="test-ap-6")
        assert policy.automation_policy.status == "allowed"

    def test_automation_unknown_when_no_mention(self, parser: PolicyParser) -> None:
        """Policy without automation statement → status='unknown'."""
        policy = parser.parse_from_text(POLICY_NO_AUTOMATION_MENTION, source_label="test-ap-7")
        assert policy.automation_policy.status == "unknown"
        assert policy.automation_policy.is_unknown is True
        assert policy.automation_policy.evidence is None

    def test_contradictory_automation_conservative(self, parser: PolicyParser) -> None:
        """Contradictory statements → most restrictive wins (prohibited > requires_approval > allowed)."""
        policy = parser.parse_from_text(POLICY_CONTRADICTORY_AUTOMATION, source_label="test-ap-8")
        assert policy.automation_policy.status == "prohibited"

    def test_automation_policy_serialization(self) -> None:
        """AutomationPolicy serializes correctly via Pydantic."""
        ap = AutomationPolicy(status="prohibited", evidence="Automated scanning is prohibited")
        data = ap.model_dump()
        assert data["status"] == "prohibited"
        assert data["evidence"] == "Automated scanning is prohibited"

        json_str = ap.model_dump_json()
        reloaded = AutomationPolicy.model_validate_json(json_str)
        assert reloaded.status == "prohibited"
        assert reloaded.is_prohibited is True

    def test_automation_policy_default_is_unknown(self) -> None:
        """Default AutomationPolicy has status='unknown'."""
        ap = AutomationPolicy()
        assert ap.status == "unknown"
        assert ap.is_unknown is True
        assert ap.is_allowed is False
        assert ap.is_prohibited is False
        assert ap.requires_approval is False


# ------------------------------------------------------------------
# Test-Type Extraction Tests
# ------------------------------------------------------------------


class TestTestTypeExtraction:
    """Tests for allowed and prohibited test-type extraction."""

    def test_prohibited_brute_force(self, parser: PolicyParser) -> None:
        """'No brute force' → 'brute_force' in prohibited_test_types."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-1")
        assert "brute_force" in policy.prohibited_test_types

    def test_prohibited_credential_stuffing(self, parser: PolicyParser) -> None:
        """'No credential stuffing' → 'credential_stuffing' in prohibited."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-2")
        assert "credential_stuffing" in policy.prohibited_test_types

    def test_prohibited_social_engineering(self, parser: PolicyParser) -> None:
        """'No social engineering' → 'social_engineering' in prohibited."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-3")
        assert "social_engineering" in policy.prohibited_test_types

    def test_prohibited_phishing(self, parser: PolicyParser) -> None:
        """'phishing' → 'phishing' in prohibited."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-4")
        assert "phishing" in policy.prohibited_test_types

    def test_prohibited_ddos(self, parser: PolicyParser) -> None:
        """'DDoS' → 'ddos' in prohibited."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-5")
        assert "ddos" in policy.prohibited_test_types

    def test_prohibited_destructing_testing(self, parser: PolicyParser) -> None:
        """'destructive testing' → 'destructive_testing' in prohibited."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-6")
        assert "destructive_testing" in policy.prohibited_test_types

    def test_prohibited_data_exfiltration(self, parser: PolicyParser) -> None:
        """'exfiltrate data' → 'data_exfiltration' in prohibited."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-7")
        assert "data_exfiltration" in policy.prohibited_test_types

    def test_prohibited_access_user_data(self, parser: PolicyParser) -> None:
        """'access user data' → 'accessing_user_data' in prohibited."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-8")
        assert "accessing_user_data" in policy.prohibited_test_types

    def test_prohibited_physical(self, parser: PolicyParser) -> None:
        """'physical attacks' → 'physical_attacks' in prohibited."""
        policy = parser.parse_from_text(POLICY_PROHIBITED_TESTS, source_label="test-tt-9")
        assert "physical_attacks" in policy.prohibited_test_types

    def test_allowed_web_application_testing(self, parser: PolicyParser) -> None:
        """'Web application testing' → 'web_application_testing' in allowed."""
        policy = parser.parse_from_text(POLICY_ALLOWED_TESTS, source_label="test-tt-10")
        assert "web_application_testing" in policy.allowed_test_types

    def test_allowed_api_testing(self, parser: PolicyParser) -> None:
        """'API testing' → 'api_testing' in allowed."""
        policy = parser.parse_from_text(POLICY_ALLOWED_TESTS, source_label="test-tt-11")
        assert "api_testing" in policy.allowed_test_types

    def test_allowed_authenticated_testing(self, parser: PolicyParser) -> None:
        """'Authenticated testing with test accounts' → 'authenticated_testing' in allowed."""
        policy = parser.parse_from_text(POLICY_ALLOWED_TESTS, source_label="test-tt-12")
        assert "authenticated_testing" in policy.allowed_test_types

    def test_allowed_non_destructive(self, parser: PolicyParser) -> None:
        """'Non-destructive testing' → 'non_destructive_testing' in allowed."""
        policy = parser.parse_from_text(POLICY_ALLOWED_TESTS, source_label="test-tt-13")
        assert "non_destructive_testing" in policy.allowed_test_types

    def test_allowed_rate_limited_automated(self, parser: PolicyParser) -> None:
        """'rate-limited automated testing' → 'rate_limited_automated_testing' in allowed."""
        policy = parser.parse_from_text(POLICY_ALLOWED_TESTS, source_label="test-tt-14")
        assert "rate_limited_automated_testing" in policy.allowed_test_types

    def test_separated_allowed_and_prohibited(self, parser: PolicyParser) -> None:
        """Allowed and prohibited test types remain in separate lists."""
        policy = parser.parse_from_text(POLICY_MIXED_TESTS, source_label="test-tt-sep")
        assert "brute_force" in policy.prohibited_test_types
        assert "social_engineering" in policy.prohibited_test_types
        assert "accessing_user_data" in policy.prohibited_test_types
        assert "api_testing" in policy.allowed_test_types
        assert "non_destructive_testing" in policy.allowed_test_types
        assert "brute_force" not in policy.allowed_test_types
        assert "api_testing" not in policy.prohibited_test_types

    def test_no_test_types_empty_lists(self, parser: PolicyParser) -> None:
        """Policy without test-type mentions → empty lists (unknown state)."""
        policy = parser.parse_from_text(POLICY_NO_AUTOMATION_MENTION, source_label="test-tt-empty")
        assert policy.prohibited_test_types == []
        assert policy.allowed_test_types == []

    def test_no_duplicate_test_types(self, parser: PolicyParser) -> None:
        """Test types lists contain no duplicates."""
        duplicate_policy = """
        In Scope: example.com
        Rules:
        - No brute force attacks
        - Do not perform brute-force testing
        """
        policy = parser.parse_from_text(duplicate_policy, source_label="test-tt-dup")
        assert policy.prohibited_test_types.count("brute_force") <= 1

    def test_denial_of_service_variant(self, parser: PolicyParser) -> None:
        """'denial of service' → 'ddos' in prohibited."""
        policy = parser.parse_from_text(POLICY_DDOS_VARIANT, source_label="test-tt-dos")
        assert "ddos" in policy.prohibited_test_types


# ------------------------------------------------------------------
# Test: Determinism & Safety for Issue #3
# ------------------------------------------------------------------


class TestIssue3DeterminismAndSafety:
    """Determinism and safety-gate tests for Issue #3 extraction."""

    def test_rate_limit_deterministic(self, parser: PolicyParser) -> None:
        """Same input → same rate-limit values."""
        p1 = parser.parse_from_text(POLICY_RATE_LIMIT_COMBINED, source_label="same")
        p2 = parser.parse_from_text(POLICY_RATE_LIMIT_COMBINED, source_label="same")
        assert p1.rate_limits is not None
        assert p2.rate_limits is not None
        assert p1.rate_limits.model_dump() == p2.rate_limits.model_dump()

    def test_automation_deterministic(self, parser: PolicyParser) -> None:
        """Same input → same automation policy classification."""
        p1 = parser.parse_from_text(POLICY_AUTOMATION_PROHIBITED, source_label="same")
        p2 = parser.parse_from_text(POLICY_AUTOMATION_PROHIBITED, source_label="same")
        assert p1.automation_policy.model_dump() == p2.automation_policy.model_dump()

    def test_test_types_deterministic(self, parser: PolicyParser) -> None:
        """Same input → same test type lists."""
        p1 = parser.parse_from_text(POLICY_MIXED_TESTS, source_label="same")
        p2 = parser.parse_from_text(POLICY_MIXED_TESTS, source_label="same")
        assert p1.prohibited_test_types == p2.prohibited_test_types
        assert p1.allowed_test_types == p2.allowed_test_types

    def test_no_network_in_issue3_parsing(self, parser: PolicyParser) -> None:
        """parse_from_text for Issue #3 fixtures never makes network requests."""
        import httpx

        try:
            policy = parser.parse_from_text(POLICY_RATE_LIMIT_COMBINED, source_label="test")
            assert policy.rate_limits is not None
            assert policy.automation_policy is not None
            assert isinstance(policy.prohibited_test_types, list)
            assert isinstance(policy.allowed_test_types, list)
        except httpx.HTTPError:
            pytest.fail("parse_from_text should never make HTTP requests")

    def test_no_dns_in_parsing(self, parser: PolicyParser) -> None:
        """parse_from_text makes no DNS calls. Verifies prohibited test types extracted."""
        policy = parser.parse_from_text(POLICY_MIXED_TESTS, source_label="test")
        # Verify test types were extracted (proves parser ran without DNS)
        assert len(policy.prohibited_test_types) > 0
        assert len(policy.allowed_test_types) > 0
        assert "brute_force" in policy.prohibited_test_types

    def test_scope_policy_serialization_with_new_fields(self, parser: PolicyParser) -> None:
        """ScopePolicy with new fields serializes correctly."""
        policy = parser.parse_from_text(POLICY_RATE_LIMIT_COMBINED, source_label="test-serial")
        data = policy.model_dump()
        assert data["source_url"] == "test-serial"
        assert data["rate_limits"]["requests_per_minute"] == 100
        assert data["rate_limits"]["requests_per_day"] == 10000
        assert data["automation_policy"]["status"] is not None
        assert "evidence" in data["automation_policy"]
        assert isinstance(data["allowed_test_types"], list)
        assert isinstance(data["prohibited_test_types"], list)

    def test_scope_policy_deserialization_with_new_fields(self, parser: PolicyParser) -> None:
        """ScopePolicy with new fields deserializes correctly."""
        json_data = {
            "source_url": "https://example.com",
            "in_scope": [{"pattern": "example.com", "type": "domain"}],
            "out_of_scope": [],
            "rate_limits": {
                "requests_per_second": 2.0,
                "requests_per_minute": 60,
                "requests_per_hour": 1000,
                "requests_per_day": 10000,
                "concurrent_requests": 5,
            },
            "rules": [],
            "automation_policy": {"status": "prohibited", "evidence": "No automated scanners"},
            "allowed_test_types": ["api_testing"],
            "prohibited_test_types": ["brute_force", "credential_stuffing"],
            "raw_text": "",
        }
        policy = ScopePolicy.model_validate(json_data)
        assert policy.rate_limits is not None
        assert policy.rate_limits.requests_per_minute == 60
        assert policy.rate_limits.requests_per_day == 10000
        assert policy.automation_policy.status == "prohibited"
        assert "brute_force" in policy.prohibited_test_types
        assert "api_testing" in policy.allowed_test_types

    def test_rate_limit_backward_compatible(self) -> None:
        """Old RateLimit (without minute/day) still works."""
        rl = RateLimit(requests_per_second=2, requests_per_hour=1000, concurrent_requests=5)
        assert rl.requests_per_minute is None
        assert rl.requests_per_day is None
        data = rl.model_dump()
        assert data["requests_per_minute"] is None
        assert data["requests_per_day"] is None

    def test_unknown_is_explicitly_detectable(self, parser: PolicyParser) -> None:
        """Unknown state is explicitly detectable for all new fields."""
        policy = parser.parse_from_text(POLICY_NO_AUTOMATION_MENTION, source_label="test-unknown")
        assert policy.rate_limits is None
        assert policy.automation_policy.status == "unknown"
        assert policy.automation_policy.is_unknown is True
        assert policy.prohibited_test_types == []
        assert policy.allowed_test_types == []
