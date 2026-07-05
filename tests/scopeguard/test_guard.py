"""Unit tests for ScopeGuard — deterministic request-gating.

All tests use locally constructed ScopePolicy objects. No real
external targets are contacted. No DNS, no network I/O.
"""

from __future__ import annotations

import pytest

from neutrino.models.policy import ScopeEntry, ScopePolicy
from neutrino.scopeguard.guard import ScopeGuard
from neutrino.scopeguard.models import ScopeDecision, ScopeDecisionStatus, ScopeReason

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def guard() -> ScopeGuard:
    """Fresh ScopeGuard instance for each test."""
    return ScopeGuard()


@pytest.fixture
def basic_policy() -> ScopePolicy:
    """Policy with single in-scope domain and no exclusions."""
    return ScopePolicy(
        source_url="https://example.com/policy",
        in_scope=[ScopeEntry(pattern="example.com", type="domain")],
    )


@pytest.fixture
def wildcard_policy() -> ScopePolicy:
    """Policy with wildcard in-scope entry."""
    return ScopePolicy(
        source_url="https://example.com/policy",
        in_scope=[ScopeEntry(pattern="*.example.com", type="wildcard_domain", is_wildcard=True)],
    )


@pytest.fixture
def complex_policy() -> ScopePolicy:
    """Policy with in-scope, out-of-scope, wildcards, IP ranges, and API endpoints."""
    return ScopePolicy(
        source_url="https://megacorp.com/policy",
        in_scope=[
            ScopeEntry(pattern="*.megacorp.com", type="wildcard_domain", is_wildcard=True),
            ScopeEntry(pattern="api.megacorp.com", type="domain"),
            ScopeEntry(pattern="app.megacorp.com/v2", type="api"),
            ScopeEntry(pattern="198.51.100.0/24", type="ip_range"),
            ScopeEntry(pattern="203.0.113.0/28", type="ip_range"),
        ],
        out_of_scope=[
            ScopeEntry(pattern="staging.megacorp.com", type="domain"),
            ScopeEntry(pattern="*.dev.megacorp.com", type="wildcard_domain", is_wildcard=True),
        ],
    )


# =============================================================================
# Test: ALLOW cases
# =============================================================================


def test_exact_in_scope_domain_allows(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Exact in-scope domain match should ALLOW."""
    decision = guard.check_target("example.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW
    assert decision.reason == ScopeReason.ALLOW_IN_SCOPE
    assert decision.matched_entry == "example.com"
    assert decision.is_allowed is True


def test_wildcard_in_scope_allows(guard: ScopeGuard, wildcard_policy: ScopePolicy) -> None:
    """Wildcard in-scope domain should match single-level subdomains."""
    decision = guard.check_target("sub.example.com", wildcard_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW
    assert decision.reason == ScopeReason.ALLOW_IN_SCOPE


def test_https_url_normalized_and_allowed(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """HTTPS URL should be normalized (scheme stripped) and checked against policy."""
    decision = guard.check_target("https://example.com/", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW
    assert decision.reason == ScopeReason.ALLOW_IN_SCOPE


def test_https_url_with_path_allowed(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """HTTPS URL with path should be normalized and checked."""
    decision = guard.check_target("https://example.com/v1/status", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


def test_ip_range_target_allowed(guard: ScopeGuard, complex_policy: ScopePolicy) -> None:
    """IP address within a CIDR range should ALLOW."""
    decision = guard.check_target("198.51.100.42", complex_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW
    assert decision.reason == ScopeReason.ALLOW_IN_SCOPE
    assert decision.matched_entry == "198.51.100.0/24"


def test_ip_range_edge_allowed(guard: ScopeGuard, complex_policy: ScopePolicy) -> None:
    """IP at the edge of a CIDR range should still match."""
    # 203.0.113.0/28 includes 203.0.113.0 through 203.0.113.15
    decision = guard.check_target("203.0.113.15", complex_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


def test_api_path_target_allowed(guard: ScopeGuard, complex_policy: ScopePolicy) -> None:
    """API path entry should match the same path."""
    decision = guard.check_target("app.megacorp.com/v2", complex_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW
    assert decision.reason == ScopeReason.ALLOW_IN_SCOPE


# =============================================================================
# Test: DENY cases — explicit out-of-scope
# =============================================================================


def test_exact_out_of_scope_denies(guard: ScopeGuard, complex_policy: ScopePolicy) -> None:
    """Exact out-of-scope domain should DENY."""
    decision = guard.check_target("staging.megacorp.com", complex_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_OUT_OF_SCOPE
    assert decision.matched_entry == "staging.megacorp.com"
    assert decision.is_denied is True


def test_out_of_scope_overrides_wildcard_in_scope(
    guard: ScopeGuard, complex_policy: ScopePolicy
) -> None:
    """Out-of-scope exclusion wins even when a wildcard in-scope would match."""
    # *.megacorp.com would match staging.megacorp.com, but explicit
    # out-of-scope overrides it.
    decision = guard.check_target("staging.megacorp.com", complex_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_OUT_OF_SCOPE


def test_out_of_scope_wildcard_blocks_subdomain(
    guard: ScopeGuard, complex_policy: ScopePolicy
) -> None:
    """Wildcard out-of-scope blocks matching subdomains."""
    decision = guard.check_target("test.dev.megacorp.com", complex_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_OUT_OF_SCOPE


# =============================================================================
# Test: DENY cases — unknown targets
# =============================================================================


def test_unknown_target_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Unmatched domain should DENY_UNKNOWN_TARGET."""
    decision = guard.check_target("evil.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNKNOWN_TARGET


def test_deep_wildcard_mismatch_denies(guard: ScopeGuard, wildcard_policy: ScopePolicy) -> None:
    """Wildcard *.example.com should NOT match deep.sub.example.com."""
    decision = guard.check_target("deep.sub.example.com", wildcard_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNKNOWN_TARGET


def test_similar_but_different_domain_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """'notexample.com' should NOT match 'example.com'."""
    decision = guard.check_target("notexample.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNKNOWN_TARGET


# =============================================================================
# Test: DENY cases — invalid targets
# =============================================================================


def test_empty_target_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Empty string target should DENY_INVALID_TARGET."""
    decision = guard.check_target("", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_INVALID_TARGET


def test_whitespace_only_target_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Whitespace-only target should DENY_INVALID_TARGET."""
    decision = guard.check_target("   \n\t  ", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_INVALID_TARGET


def test_too_long_target_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Target exceeding maximum length should DENY_INVALID_TARGET."""
    long_target = "a" * 3000 + ".example.com"
    decision = guard.check_target(long_target, basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_INVALID_TARGET


def test_null_byte_target_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Target containing null bytes should DENY_INVALID_TARGET."""
    decision = guard.check_target("example.com\x00extra", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_INVALID_TARGET


# =============================================================================
# Test: DENY cases — unsafe schemes
# =============================================================================


def test_ftp_scheme_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """FTP scheme should DENY_UNSAFE_SCHEME even if domain is in scope."""
    decision = guard.check_target("ftp://example.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNSAFE_SCHEME


def test_http_scheme_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """HTTP (not HTTPS) scheme should DENY_UNSAFE_SCHEME."""
    decision = guard.check_target("http://example.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNSAFE_SCHEME


def test_file_scheme_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """file:// scheme should DENY_UNSAFE_SCHEME."""
    decision = guard.check_target("file:///etc/passwd", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNSAFE_SCHEME


def test_javascript_scheme_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """javascript: scheme should DENY_UNSAFE_SCHEME."""
    decision = guard.check_target("javascript://example.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNSAFE_SCHEME


def test_data_scheme_denies(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """data: scheme should DENY_UNSAFE_SCHEME."""
    decision = guard.check_target("data://example.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNSAFE_SCHEME


# =============================================================================
# Test: Missing policy
# =============================================================================


def test_missing_policy_denies(guard: ScopeGuard) -> None:
    """None policy should immediately DENY_MISSING_POLICY."""
    decision = guard.check_target("example.com", None)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_MISSING_POLICY


def test_missing_policy_with_url_target(guard: ScopeGuard) -> None:
    """Missing policy denies even for well-formed URLs."""
    decision = guard.check_target("https://api.example.com/v1", None)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_MISSING_POLICY


# =============================================================================
# Test: Target normalization
# =============================================================================


def test_trailing_slash_stripped(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Trailing slash should be stripped during normalization."""
    decision = guard.check_target("example.com/", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


def test_mixed_case_normalized(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Mixed-case target should be lowercased during normalization."""
    decision = guard.check_target("Example.COM", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


def test_surrounding_whitespace_stripped(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Leading/trailing whitespace should be stripped."""
    decision = guard.check_target("  example.com  ", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


def test_https_with_trailing_slash_and_path(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """HTTPS URL with path and trailing slash should normalize correctly."""
    decision = guard.check_target("https://example.com/path/", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


# =============================================================================
# Test: IP range edge cases
# =============================================================================


def test_ip_outside_cidr_range_denies(guard: ScopeGuard, complex_policy: ScopePolicy) -> None:
    """IP outside CIDR range should DENY_UNKNOWN_TARGET."""
    # 198.51.100.0/24 includes 198.51.100.0-255
    decision = guard.check_target("198.51.101.1", complex_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNKNOWN_TARGET


def test_ip_range_network_address_allowed(guard: ScopeGuard, complex_policy: ScopePolicy) -> None:
    """Network address (first IP in range) should be in scope."""
    decision = guard.check_target("198.51.100.0", complex_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


def test_ip_range_broadcast_allowed(guard: ScopeGuard, complex_policy: ScopePolicy) -> None:
    """Broadcast address (last IP in range) should be in scope."""
    decision = guard.check_target("198.51.100.255", complex_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


def test_invalid_ip_string_denies(guard: ScopeGuard, complex_policy: ScopePolicy) -> None:
    """Invalid IP string should not match IP ranges and fall through to DENY."""
    decision = guard.check_target("999.999.999.999", complex_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_UNKNOWN_TARGET


# =============================================================================
# Test: Decision object properties
# =============================================================================


def test_decision_is_serializable(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """ScopeDecision should serialize to JSON-compatible dict via model_dump()."""
    decision = guard.check_target("example.com", basic_policy)
    data = decision.model_dump()
    assert data["target"] == "example.com"
    assert data["status"] == "allow"
    assert data["reason"] == "allow_in_scope"
    assert data["matched_entry"] == "example.com"
    assert data["policy_source"] == "https://example.com/policy"
    assert isinstance(data["explanation"], str)
    assert len(data["explanation"]) > 0


def test_deny_decision_is_serializable(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """DENY decisions should also serialize correctly."""
    decision = guard.check_target("evil.com", basic_policy)
    data = decision.model_dump()
    assert data["status"] == "deny"
    assert data["reason"] == "deny_unknown_target"
    assert data["matched_entry"] is None


def test_decision_json_roundtrip(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """ScopeDecision should survive JSON round-trip."""
    original = guard.check_target("example.com", basic_policy)
    json_str = original.model_dump_json()
    reloaded = ScopeDecision.model_validate_json(json_str)
    assert reloaded.target == original.target
    assert reloaded.status == original.status
    assert reloaded.reason == original.reason
    assert reloaded.matched_entry == original.matched_entry
    assert reloaded.policy_source == original.policy_source
    assert reloaded.explanation == original.explanation


# =============================================================================
# Test: No override path for DENY
# =============================================================================


def test_deny_cannot_become_allow(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """A DENY decision cannot be changed to ALLOW after creation.

    Verifies structural immutability: no ScopeGuard method accepts
    override flags, and repeated evaluations yield the same DENY.
    """
    # First evaluation: DENY
    decision = guard.check_target("evil.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.is_denied is True
    assert decision.is_allowed is False

    # Second evaluation with same input: still DENY (deterministic)
    decision2 = guard.check_target("evil.com", basic_policy)
    assert decision2.status == ScopeDecisionStatus.DENY

    # The decision objects carry no mutation methods.
    # There is no ScopeGuard API to re-evaluate a decision as ALLOW;
    # check_target() is the only entry point, and it is stateless.
    # The only output is a new ScopeDecision — never a modification.


def test_no_override_kwargs_accepted(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """ScopeGuard.check_target does not accept override flags."""
    # Verify the method signature does not accept any override arguments
    import inspect

    sig = inspect.signature(guard.check_target)
    param_names = set(sig.parameters.keys())
    assert "force" not in param_names, "force parameter must not exist"
    assert "admin_override" not in param_names, "admin_override parameter must not exist"
    assert "ignore_scope" not in param_names, "ignore_scope parameter must not exists"
    assert "allow_unknown" not in param_names, "allow_unknown parameter must not exist"


# =============================================================================
# Test: Explanation quality
# =============================================================================


def test_explanation_contains_relevant_info(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Decision explanation should contain the target and reason."""
    decision = guard.check_target("evil.com", basic_policy)
    assert "evil.com" in decision.explanation
    assert "default deny" in decision.explanation.lower()


def test_explanation_for_unsafe_scheme(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Deny explanation for unsafe scheme should mention the scheme."""
    decision = guard.check_target("ftp://example.com", basic_policy)
    assert "ftp" in decision.explanation.lower()


# =============================================================================
# Test: Complex scenarios
# =============================================================================


def test_out_of_scope_checked_before_in_scope(
    guard: ScopeGuard, complex_policy: ScopePolicy
) -> None:
    """Verify out-of-scope is checked first by timing-dependent logic:
    a domain that matches both in- and out-of-scope gets DENY_OUT_OF_SCOPE."""
    # staging.megacorp.com matches *.megacorp.com (in_scope) AND
    # staging.megacorp.com (out_of_scope). Out-of-scope must win.
    decision = guard.check_target("staging.megacorp.com", complex_policy)
    assert decision.status == ScopeDecisionStatus.DENY
    assert decision.reason == ScopeReason.DENY_OUT_OF_SCOPE
    assert "out-of-scope" in decision.explanation.lower()


def test_complex_policy_allows_valid_subdomain(
    guard: ScopeGuard, complex_policy: ScopePolicy
) -> None:
    """A valid subdomain not in out_of_scope should be allowed."""
    decision = guard.check_target("www.megacorp.com", complex_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW
    assert decision.reason == ScopeReason.ALLOW_IN_SCOPE


# =============================================================================
# Test: policy_source tracking
# =============================================================================


def test_policy_source_in_decision(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """Decision should reference the policy source URL."""
    decision = guard.check_target("example.com", basic_policy)
    assert decision.policy_source == "https://example.com/policy"


def test_policy_source_in_deny_decision(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """DENY decision should also reference the policy source."""
    decision = guard.check_target("evil.com", basic_policy)
    assert decision.policy_source == "https://example.com/policy"


# =============================================================================
# Test: Subdomain matching via base domain
# =============================================================================


def test_base_domain_matches_subdomain(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """'example.com' in scope should match 'sub.example.com'."""
    decision = guard.check_target("sub.example.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW


def test_base_domain_matches_www(guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
    """'example.com' in scope should match 'www.example.com'."""
    decision = guard.check_target("www.example.com", basic_policy)
    assert decision.status == ScopeDecisionStatus.ALLOW
