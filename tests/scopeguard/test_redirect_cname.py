"""Unit tests for Redirect/CNAME/DNS evasion-prevention — Issue #6.

All tests use locally constructed data and FakeResolver / mock objects.
NO REAL DNS or HTTP requests are made.
"""

from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path

import pytest

from neutrino.models.policy import ScopeEntry, ScopePolicy
from neutrino.scopeguard.dns import (
    FakeCnameResolver,
    check_cname_chain,
)
from neutrino.scopeguard.evasion import build_evasion_result
from neutrino.scopeguard.guard import ScopeGuard
from neutrino.scopeguard.models import (
    DnsTrace,
    RedirectTrace,
    ScopeDecisionStatus,
    ScopeReason,
)
from neutrino.scopeguard.redirects import RedirectHop, check_redirect_chain

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def guard() -> ScopeGuard:
    """Fresh ScopeGuard instance for each test."""
    return ScopeGuard()


@pytest.fixture
def basic_policy() -> ScopePolicy:
    """Policy with single in-scope domain (example.com)."""
    return ScopePolicy(
        source_url="https://example.com/policy",
        in_scope=[ScopeEntry(pattern="example.com", type="domain")],
    )


@pytest.fixture
def multi_domain_policy() -> ScopePolicy:
    """Policy with multiple in-scope domains for chain testing."""
    return ScopePolicy(
        source_url="https://multi.example/policy",
        in_scope=[
            ScopeEntry(pattern="app.example.com", type="domain"),
            ScopeEntry(pattern="api.example.com", type="domain"),
            ScopeEntry(pattern="cdn.trusted.net", type="domain"),
            ScopeEntry(pattern="final.dashboard.example.com", type="domain"),
        ],
        out_of_scope=[
            ScopeEntry(pattern="evil.example.net", type="domain"),
        ],
    )


@pytest.fixture
def wildcard_policy() -> ScopePolicy:
    """Policy with a single-level wildcard entry."""
    return ScopePolicy(
        source_url="https://wildcard.example/policy",
        in_scope=[
            ScopeEntry(
                pattern="*.example.com",
                type="wildcard_domain",
                is_wildcard=True,
            ),
        ],
    )


@pytest.fixture
def cname_resolver() -> FakeCnameResolver:
    """Fake resolver with an in-scope CNAME chain."""
    return FakeCnameResolver(
        {
            "app.example.com": ["api.example.com"],
            "api.example.com": ["cdn.trusted.net"],
        }
    )


@pytest.fixture
def cname_resolver_out_of_scope() -> FakeCnameResolver:
    """Fake resolver with a CNAME that points out of scope."""
    return FakeCnameResolver(
        {
            "app.example.com": ["evil.example.net"],
        }
    )


@pytest.fixture
def cname_resolver_unknown() -> FakeCnameResolver:
    """Fake resolver with a CNAME that points to an unknown domain."""
    return FakeCnameResolver(
        {
            "app.example.com": ["unknown.example.org"],
        }
    )


@pytest.fixture
def cname_resolver_long_chain() -> FakeCnameResolver:
    """Fake resolver with 12-hop chain starting from in-scope target."""
    mapping: dict[str, list[str]] = {
        "app.example.com": ["hop0.example.com"],
    }
    for i in range(11):
        mapping[f"hop{i}.example.com"] = [f"hop{i + 1}.example.com"]
    # Make the final hop also in-scope
    mapping["hop11.example.com"] = ["api.example.com"]
    return FakeCnameResolver(mapping)


@pytest.fixture
def cname_resolver_loop() -> FakeCnameResolver:
    """Fake resolver with a CNAME loop: A → B → A."""
    return FakeCnameResolver(
        {
            "app.example.com": ["cdn.trusted.net"],
            "cdn.trusted.net": ["app.example.com"],
        }
    )


@pytest.fixture
def cname_resolver_empty_answer() -> FakeCnameResolver:
    """Fake resolver that returns an empty answer list."""
    return FakeCnameResolver(
        {
            "app.example.com": [],
        }
    )


# ------------------------------------------------------------------
# Redirect Tests
# ------------------------------------------------------------------


class TestRedirectBasic:
    """Basic redirect chain checks."""

    def test_redirect_in_scope_all_allowed(
        self, guard: ScopeGuard, multi_domain_policy: ScopePolicy
    ) -> None:
        """All redirect targets in-scope → no blocking reason."""
        chain = [
            RedirectHop("app.example.com", "api.example.com", 302),
            RedirectHop("api.example.com", "cdn.trusted.net", 301),
        ]
        traces, reason = check_redirect_chain(
            "app.example.com", chain, multi_domain_policy, guard=guard
        )
        assert reason is None
        assert len(traces) == 2

    def test_redirect_out_of_scope_denies(
        self, guard: ScopeGuard, multi_domain_policy: ScopePolicy
    ) -> None:
        """Redirect to out-of-scope domain → DENY_REDIRECT_OUT_OF_SCOPE."""
        chain = [
            RedirectHop("app.example.com", "evil.example.net", 302),
        ]
        traces, reason = check_redirect_chain(
            "app.example.com", chain, multi_domain_policy, guard=guard
        )
        assert reason == ScopeReason.DENY_REDIRECT_OUT_OF_SCOPE
        assert len(traces) == 1

    def test_redirect_unknown_denies(self, guard: ScopeGuard, basic_policy: ScopePolicy) -> None:
        """Redirect to unknown target → DENY_REDIRECT_UNKNOWN."""
        chain = [
            RedirectHop("example.com", "unknown.example.org", 302),
        ]
        traces, reason = check_redirect_chain("example.com", chain, basic_policy, guard=guard)
        assert reason == ScopeReason.DENY_REDIRECT_UNKNOWN

    def test_redirect_multi_hop_in_scope_all_allowed(
        self, guard: ScopeGuard, multi_domain_policy: ScopePolicy
    ) -> None:
        """Multiple in-scope hops → all allowed."""
        chain = [
            RedirectHop("app.example.com", "api.example.com", 307),
            RedirectHop("api.example.com", "final.dashboard.example.com", 302),
        ]
        traces, reason = check_redirect_chain(
            "app.example.com", chain, multi_domain_policy, guard=guard
        )
        assert reason is None
        assert len(traces) == 2
        assert all(t.decision.startswith("allow") for t in traces)

    def test_redirect_hop_limit_exceeded(
        self, guard: ScopeGuard, multi_domain_policy: ScopePolicy
    ) -> None:
        """Chain exceeding max_hops → DENY_REDIRECT_LIMIT_EXCEEDED."""
        chain = [
            RedirectHop(f"hop{i}.com", f"hop{i + 1}.com", 302)
            for i in range(10)  # default limit is 5
        ]
        traces, reason = check_redirect_chain(
            "app.example.com", chain, multi_domain_policy, guard=guard
        )
        assert reason == ScopeReason.DENY_REDIRECT_LIMIT_EXCEEDED

    def test_redirect_empty_location_denies(
        self, guard: ScopeGuard, basic_policy: ScopePolicy
    ) -> None:
        """Empty Location header → DENY_INVALID_REDIRECT."""
        chain = [
            RedirectHop("example.com", "", 302),
        ]
        traces, reason = check_redirect_chain("example.com", chain, basic_policy, guard=guard)
        assert reason == ScopeReason.DENY_INVALID_REDIRECT
        assert len(traces) == 1

    def test_redirect_whitespace_only_location_denies(
        self, guard: ScopeGuard, basic_policy: ScopePolicy
    ) -> None:
        """Whitespace-only Location → DENY_INVALID_REDIRECT."""
        chain = [
            RedirectHop("example.com", "   ", 302),
        ]
        traces, reason = check_redirect_chain("example.com", chain, basic_policy, guard=guard)
        assert reason == ScopeReason.DENY_INVALID_REDIRECT

    def test_redirect_unsafe_scheme_target_blocked(
        self, guard: ScopeGuard, basic_policy: ScopePolicy
    ) -> None:
        """Redirect to http://example.com → blocked (http is unsafe scheme)."""
        chain = [
            RedirectHop("https://example.com", "http://example.com", 302),
        ]
        traces, reason = check_redirect_chain(
            "https://example.com", chain, basic_policy, guard=guard
        )
        assert reason == ScopeReason.DENY_INVALID_REDIRECT

    def test_redirect_must_be_independently_in_scope(
        self, guard: ScopeGuard, wildcard_policy: ScopePolicy
    ) -> None:
        """Redirect target must be independently in scope — wildcard is not inherited."""
        # *.example.com allows sub.example.com but the redirect target
        # "other.org" is not covered.
        chain = [
            RedirectHop("sub.example.com", "other.org", 302),
        ]
        traces, reason = check_redirect_chain(
            "sub.example.com", chain, wildcard_policy, guard=guard
        )
        assert reason == ScopeReason.DENY_REDIRECT_UNKNOWN

    def test_initial_target_deny_blocks_redirect(
        self, guard: ScopeGuard, basic_policy: ScopePolicy
    ) -> None:
        """If initial target is DENY, redirect chain is not checked at all."""
        chain = [
            RedirectHop("evil.com", "example.com", 302),
        ]
        traces, reason = check_redirect_chain("evil.com", chain, basic_policy, guard=guard)
        assert reason == ScopeReason.DENY_UNKNOWN_TARGET
        assert len(traces) == 0  # No redirect traces when initial fails


class TestRedirectSafety:
    """Safety-gate tests for redirect checking."""

    def test_no_override_kwargs_in_check_redirect_chain(self) -> None:
        """verify check_redirect_chain has no override parameters."""
        import inspect

        sig = inspect.signature(check_redirect_chain)
        param_names = set(sig.parameters.keys())
        for forbidden in ("force", "admin_override", "ignore_scope", "allow_unknown"):
            assert forbidden not in param_names, (
                f"{forbidden} must not exist in check_redirect_chain"
            )

    def test_evil_domain_mid_chain_blocks_everything(
        self, guard: ScopeGuard, multi_domain_policy: ScopePolicy
    ) -> None:
        """Single evil hop blocks entire chain, even if later hops are good."""
        chain = [
            RedirectHop("app.example.com", "api.example.com", 302),
            RedirectHop("api.example.com", "evil.example.net", 302),
            RedirectHop("evil.example.net", "cdn.trusted.net", 302),
        ]
        traces, reason = check_redirect_chain(
            "app.example.com", chain, multi_domain_policy, guard=guard
        )
        assert reason == ScopeReason.DENY_REDIRECT_OUT_OF_SCOPE
        # Only the first two hops are traced; the third is never reached
        assert len(traces) == 2


# ------------------------------------------------------------------
# CNAME Tests
# ------------------------------------------------------------------


class TestCnameBasic:
    """Basic CNAME chain checks."""

    def test_cname_in_scope_chain_allowed(
        self,
        guard: ScopeGuard,
        multi_domain_policy: ScopePolicy,
        cname_resolver: FakeCnameResolver,
    ) -> None:
        """CNAME chain with all in-scope targets → allowed."""
        traces, reason = check_cname_chain(
            "app.example.com",
            multi_domain_policy,
            resolver=cname_resolver,
            guard=guard,
        )
        assert reason is None

    def test_cname_out_of_scope_denies(
        self,
        guard: ScopeGuard,
        multi_domain_policy: ScopePolicy,
        cname_resolver_out_of_scope: FakeCnameResolver,
    ) -> None:
        """CNAME pointing to out-of-scope → DENY_CNAME_OUT_OF_SCOPE."""
        traces, reason = check_cname_chain(
            "app.example.com",
            multi_domain_policy,
            resolver=cname_resolver_out_of_scope,
            guard=guard,
        )
        assert reason == ScopeReason.DENY_CNAME_OUT_OF_SCOPE

    def test_cname_unknown_denies(
        self,
        guard: ScopeGuard,
        basic_policy: ScopePolicy,
        cname_resolver_unknown: FakeCnameResolver,
    ) -> None:
        """CNAME pointing to unknown domain → DENY_CNAME_UNKNOWN."""
        traces, reason = check_cname_chain(
            "app.example.com",
            basic_policy,
            resolver=cname_resolver_unknown,
            guard=guard,
        )
        assert reason == ScopeReason.DENY_CNAME_UNKNOWN

    def test_cname_hop_limit_exceeded(
        self,
        guard: ScopeGuard,
        wildcard_policy: ScopePolicy,
        cname_resolver_long_chain: FakeCnameResolver,
    ) -> None:
        """CNAME chain exceeding hop limit → DENY_CNAME_LIMIT_EXCEEDED."""
        # Use wildcard policy so all *.example.com are in scope
        traces, reason = check_cname_chain(
            "app.example.com",
            wildcard_policy,
            resolver=cname_resolver_long_chain,
            guard=guard,
        )
        assert reason == ScopeReason.DENY_CNAME_LIMIT_EXCEEDED

    def test_cname_loop_denies(
        self,
        guard: ScopeGuard,
        multi_domain_policy: ScopePolicy,
        cname_resolver_loop: FakeCnameResolver,
    ) -> None:
        """CNAME loop A → B → A → DENY_CNAME_LOOP."""
        traces, reason = check_cname_chain(
            "app.example.com",
            multi_domain_policy,
            resolver=cname_resolver_loop,
            guard=guard,
        )
        assert reason == ScopeReason.DENY_CNAME_LOOP

    def test_empty_cname_answer_denies(
        self,
        guard: ScopeGuard,
        basic_policy: ScopePolicy,
        cname_resolver_empty_answer: FakeCnameResolver,
    ) -> None:
        """Empty CNAME answer → DENY_DNS_UNKNOWN."""
        traces, reason = check_cname_chain(
            "app.example.com",
            basic_policy,
            resolver=cname_resolver_empty_answer,
            guard=guard,
        )
        assert reason == ScopeReason.DENY_DNS_UNKNOWN

    def test_no_cname_answer_allowed_if_initial_ok(
        self, guard: ScopeGuard, basic_policy: ScopePolicy
    ) -> None:
        """No CNAME record found → chain ends naturally, initial target is in-scope."""
        resolver = FakeCnameResolver({})  # No mapping means None answer
        traces, reason = check_cname_chain(
            "example.com",
            basic_policy,
            resolver=resolver,
            guard=guard,
        )
        assert reason is None
        # Should have initial trace + "no CNAME" trace
        assert len(traces) >= 2


class TestCnameWildcard:
    """CNAME + wildcard handling tests."""

    def test_wildcard_allows_single_level_cname(
        self, guard: ScopeGuard, wildcard_policy: ScopePolicy
    ) -> None:
        """Single-level wildcard *.example.com allows sub.example.com CNAME."""
        resolver = FakeCnameResolver(
            {
                "sub.example.com": ["other.example.com"],
            }
        )
        traces, reason = check_cname_chain(
            "sub.example.com", wildcard_policy, resolver=resolver, guard=guard
        )
        assert reason is None

    def test_wildcard_does_not_deep_match_cname(
        self, guard: ScopeGuard, wildcard_policy: ScopePolicy
    ) -> None:
        """*.example.com does NOT match deep.sub.example.com."""
        resolver = FakeCnameResolver(
            {
                "deep.sub.example.com": ["other.example.com"],
            }
        )
        traces, reason = check_cname_chain(
            "deep.sub.example.com",
            wildcard_policy,
            resolver=resolver,
            guard=guard,
        )
        # Initial target deep.sub.example.com is DENY_UNKNOWN_TARGET
        assert reason == ScopeReason.DENY_UNKNOWN_TARGET

    def test_cname_target_not_auto_allowed_by_origin_scope(
        self, guard: ScopeGuard, wildcard_policy: ScopePolicy
    ) -> None:
        """CNAME target must pass its own scope check; origin scope is not inherited."""
        # *.example.com allows sub.example.com, but the CNAME target
        # vendor.example.net is NOT covered.
        resolver = FakeCnameResolver(
            {
                "sub.example.com": ["vendor.example.net"],
            }
        )
        traces, reason = check_cname_chain(
            "sub.example.com", wildcard_policy, resolver=resolver, guard=guard
        )
        assert reason == ScopeReason.DENY_CNAME_UNKNOWN


class TestCnameSafety:
    """Safety-gate tests for CNAME checking."""

    def test_no_override_kwargs_in_check_cname_chain(self) -> None:
        """verify check_cname_chain has no override parameters."""
        import inspect

        sig = inspect.signature(check_cname_chain)
        param_names = set(sig.parameters.keys())
        for forbidden in ("force", "admin_override", "ignore_scope", "allow_unknown"):
            assert forbidden not in param_names, f"{forbidden} must not exist in check_cname_chain"

    def test_initial_target_deny_blocks_cname_check(
        self,
        guard: ScopeGuard,
        basic_policy: ScopePolicy,
        cname_resolver: FakeCnameResolver,
    ) -> None:
        """If initial target is DENY, CNAME chain is not followed."""
        traces, reason = check_cname_chain(
            "evil.com",
            basic_policy,
            resolver=cname_resolver,
            guard=guard,
        )
        assert reason == ScopeReason.DENY_UNKNOWN_TARGET
        # Only initial trace — no CNAME traces
        cname_traces = [t for t in traces if t.record_type == "CNAME"]
        assert len(cname_traces) == 0


# ------------------------------------------------------------------
# DNS Trace / Serialization Tests
# ------------------------------------------------------------------


class TestDnsTrace:
    """DNS Trace serialization and content checks."""

    def test_dns_trace_is_serializable(self) -> None:
        """DnsTrace should be serializable via model_dump()."""
        trace = DnsTrace(
            queried_name="example.com",
            record_type="CNAME",
            answers=["cname.example.net"],
            source="fake_resolver",
            decision="allow_in_scope",
        )
        data = trace.model_dump()
        assert data["queried_name"] == "example.com"
        assert data["record_type"] == "CNAME"
        assert data["answers"] == ["cname.example.net"]
        assert data["source"] == "fake_resolver"
        assert data["decision"] == "allow_in_scope"

    def test_dns_trace_json_roundtrip(self) -> None:
        """DnsTrace should survive JSON round-trip."""
        trace = DnsTrace(
            queried_name="example.com",
            record_type="CNAME",
            answers=["target.example.org"],
            source="fake_resolver",
            decision="deny_cname_unknown",
        )
        json_str = trace.model_dump_json()
        reloaded = DnsTrace.model_validate_json(json_str)
        assert reloaded.queried_name == trace.queried_name
        assert reloaded.record_type == trace.record_type
        assert reloaded.answers == trace.answers
        assert reloaded.decision == trace.decision

    def test_redirect_trace_is_serializable(self) -> None:
        """RedirectTrace should be serializable."""
        trace = RedirectTrace(
            from_url="https://app.example.com",
            to_url="https://api.example.com",
            status_code=302,
            decision="allow_in_scope",
        )
        data = trace.model_dump()
        assert data["from_url"] == "https://app.example.com"
        assert data["to_url"] == "https://api.example.com"
        assert data["status_code"] == 302
        assert data["decision"] == "allow_in_scope"

    def test_evasion_result_is_serializable(
        self, guard: ScopeGuard, multi_domain_policy: ScopePolicy
    ) -> None:
        """EvasionResult should be serializable via model_dump()."""
        result = build_evasion_result(
            "app.example.com",
            multi_domain_policy,
        )
        data = result.model_dump()
        assert data["initial_target"] == "app.example.com"
        assert "initial_decision" in data
        assert "redirect_traces" in data
        assert "dns_traces" in data
        assert data["final_decision"] == "allow"
        assert data["final_reason"] == "allow_in_scope"


# ------------------------------------------------------------------
# EvasionResult orchestration tests
# ------------------------------------------------------------------


class TestEvasionOrchestration:
    """Tests for the combined build_evasion_result pipeline."""

    def test_pure_allow_passes(self, guard: ScopeGuard, multi_domain_policy: ScopePolicy) -> None:
        """In-scope target with no redirects or CNAMEs → clean ALLOW."""
        result = build_evasion_result("app.example.com", multi_domain_policy)
        assert result.final_decision == ScopeDecisionStatus.ALLOW
        assert result.final_reason == ScopeReason.ALLOW_IN_SCOPE

    def test_redirect_block_propagates(
        self, guard: ScopeGuard, multi_domain_policy: ScopePolicy
    ) -> None:
        """Redirect to out-of-scope makes final_decision DENY."""
        chain = [RedirectHop("app.example.com", "evil.example.net", 302)]
        result = build_evasion_result(
            "app.example.com",
            multi_domain_policy,
            redirect_chain=chain,
        )
        assert result.final_decision == ScopeDecisionStatus.DENY
        assert result.final_reason == ScopeReason.DENY_REDIRECT_OUT_OF_SCOPE
        assert len(result.redirect_traces) == 1

    def test_cname_block_propagates(
        self,
        guard: ScopeGuard,
        multi_domain_policy: ScopePolicy,
        cname_resolver_out_of_scope: FakeCnameResolver,
    ) -> None:
        """CNAME to out-of-scope makes final_decision DENY."""
        result = build_evasion_result(
            "app.example.com",
            multi_domain_policy,
            cname_resolver=cname_resolver_out_of_scope,
        )
        assert result.final_decision == ScopeDecisionStatus.DENY
        assert result.final_reason == ScopeReason.DENY_CNAME_OUT_OF_SCOPE

    def test_combined_redirect_and_cname_all_allowed(
        self,
        guard: ScopeGuard,
        multi_domain_policy: ScopePolicy,
        cname_resolver: FakeCnameResolver,
    ) -> None:
        """Both redirect and CNAME chains in-scope → final ALLOW."""
        chain = [
            RedirectHop("app.example.com", "api.example.com", 302),
        ]
        result = build_evasion_result(
            "app.example.com",
            multi_domain_policy,
            redirect_chain=chain,
            cname_resolver=cname_resolver,
        )
        assert result.final_decision == ScopeDecisionStatus.ALLOW

    def test_no_cname_no_redirect_should_not_log_persistent_audit(
        self, guard: ScopeGuard, basic_policy: ScopePolicy
    ) -> None:
        """build_evasion_result creates no persistent AuditLog files."""
        # Verify no audit log files are created
        result = build_evasion_result("example.com", basic_policy)
        # The result itself is in-memory only; no file is written
        assert result.final_decision == ScopeDecisionStatus.ALLOW
        # Assert no .jsonl or audit files are created in the workspace
        cwd = os.getcwd()
        audit_files = [f for f in os.listdir(cwd) if f.startswith("audit") and f.endswith(".jsonl")]
        assert len(audit_files) == 0, "No persistent audit log files should be created"


# ------------------------------------------------------------------
# Safety Gates — NO real network requests
# ------------------------------------------------------------------


class TestNoRealNetwork:
    """Verify that no real network requests are made by any module."""

    def test_dns_module_no_network_imports(self) -> None:
        """dns.py imports no network libraries."""
        from neutrino.scopeguard import dns as dns_module

        forbidden = {"dns.resolver", "dnspython", "requests", "httpx", "urllib3"}
        for _name, obj in inspect.getmembers(dns_module):
            if inspect.ismodule(obj):
                mod_name = obj.__name__
                if any(f in mod_name for f in forbidden):
                    raise AssertionError(f"dns.py imported forbidden network module: {mod_name}")

    def test_redirect_module_no_httpx_follow(self) -> None:
        """redirects.py does not import httpx or call .get()."""
        redirect_path = (
            Path(__file__).parents[2] / "src" / "neutrino" / "scopeguard" / "redirects.py"
        )
        source = redirect_path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert "get" not in node.func.attr or "httpx" not in ast.unparse(node), (
                    "redirects.py must not call httpx.get()"
                )

    def test_no_real_dns_in_fake_resolver(self) -> None:
        """FakeCnameResolver.resolve_cname uses a static dict, not real DNS."""
        resolver = FakeCnameResolver({"test.example.com": ["target.example.org"]})
        result = resolver.resolve_cname("test.example.com")
        assert result == ["target.example.org"]
        # No DNS socket or resolver involved
        result_none = resolver.resolve_cname("nonexistent.example.com")
        assert result_none is None
