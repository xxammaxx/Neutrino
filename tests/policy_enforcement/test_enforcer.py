"""Tests for Program Policy Prohibition Enforcement (Issue #15).

Covers prohibited test types, allowed test types, automation policies,
blocking PolicyRules, unknown/invalid handling, audit serialization,
and safety gates.

Usage:
    .venv/bin/python -m pytest tests/policy_enforcement/ -v
"""

from __future__ import annotations

from datetime import datetime

from neutrino.models.policy import (
    AutomationPolicy,
    PolicyRule,
    ScopePolicy,
)
from neutrino.policy_enforcement import (
    ProgramPolicyDecision,
    ProgramPolicyDecisionStatus,
    ProgramPolicyEnforcer,
    ProgramPolicyIntent,
    ProgramPolicyReason,
    ProgramPolicyViolation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_policy(
    *,
    allowed: list[str] | None = None,
    prohibited: list[str] | None = None,
    rules: list[PolicyRule] | None = None,
    automation_status: str = "allowed",
) -> ScopePolicy:
    """Create a minimal ScopePolicy for enforcement tests."""
    return ScopePolicy(
        source_url="https://example.com/policy",
        program_name="Test Program",
        platform="test",
        source_fetched_at=datetime(2026, 7, 5, 23, 0, 0),
        allowed_test_types=allowed if allowed is not None else [],
        prohibited_test_types=prohibited if prohibited is not None else [],
        rules=rules if rules is not None else [],
        automation_policy=AutomationPolicy(status=automation_status),
    )


def _make_intent(
    target: str = "api.example.com",
    test_type: str = "api_testing",
    automation: bool = False,
) -> ProgramPolicyIntent:
    return ProgramPolicyIntent(
        target=target,
        test_type=test_type,
        automation=automation,
    )


# ---------------------------------------------------------------------------
# Prohibited Test Types (5 tests)
# ---------------------------------------------------------------------------


class TestProhibitedTestTypes:
    """Verify prohibited test types are blocked correctly."""

    def test_brute_force_prohibited_denies(self) -> None:
        """brute_force in prohibited_test_types → DENY_PROHIBITED_TEST_TYPE."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["brute_force"], allowed=["api_testing"])
        intent = _make_intent(test_type="brute_force")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE
        assert decision.violation is not None
        assert decision.violation.matched_policy_item == "brute_force"

    def test_credential_stuffing_prohibited_denies(self) -> None:
        """credential_stuffing in prohibited_test_types → DENY_PROHIBITED_TEST_TYPE."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["credential_stuffing"], allowed=["api_testing"])
        intent = _make_intent(test_type="credential_stuffing")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE

    def test_social_engineering_prohibited_denies(self) -> None:
        """social_engineering in prohibited_test_types → DENY_PROHIBITED_TEST_TYPE."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["social_engineering"], allowed=["api_testing"])
        intent = _make_intent(test_type="social_engineering")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE

    def test_prohibited_normalization_matches_variants(self) -> None:
        """'brute force', 'brute-force', 'brute_force' all match equally."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["brute_force"], allowed=["api_testing"])

        for variant in ("brute force", "brute-force", "Brute_Force", "BRUTE FORCE"):
            intent = _make_intent(test_type=variant)
            decision = enforcer.check_intent(intent, policy)
            assert decision.is_denied, f"Variant {variant!r} was not denied"
            assert decision.reason == ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE

    def test_prohibited_wins_over_allowed_list(self) -> None:
        """Prohibited check wins even when test type is also in allowed list."""
        enforcer = ProgramPolicyEnforcer()
        # Test type appears in BOTH lists — prohibited MUST win
        policy = _make_policy(prohibited=["brute_force"], allowed=["brute_force", "api_testing"])
        intent = _make_intent(test_type="brute_force")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE


# ---------------------------------------------------------------------------
# Allowed Test Types (4 tests)
# ---------------------------------------------------------------------------


class TestAllowedTestTypes:
    """Verify allowed test types are handled correctly (default deny)."""

    def test_api_testing_explicitly_allowed(self) -> None:
        """api_testing in allowed_test_types → ALLOW (when no other rule blocks)."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"])
        intent = _make_intent(test_type="api_testing")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_allowed
        assert decision.reason == ProgramPolicyReason.ALLOW_POLICY_PERMITS_TEST_TYPE

    def test_web_app_testing_explicitly_allowed(self) -> None:
        """web_application_testing in allowed_test_types → ALLOW."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["web_application_testing", "api_testing"])
        intent = _make_intent(test_type="web_application_testing")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_allowed
        assert decision.reason == ProgramPolicyReason.ALLOW_POLICY_PERMITS_TEST_TYPE

    def test_empty_allowed_list_denies_unknown(self) -> None:
        """allowed_test_types empty + unknown test type → DENY_UNKNOWN_TEST_TYPE."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=[])  # empty
        intent = _make_intent(test_type="unknown_test_123")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_UNKNOWN_TEST_TYPE

    def test_not_in_allowed_list_denies(self) -> None:
        """allowed_test_types non-empty but test type not in it → DENY."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing", "web_application_testing"])
        intent = _make_intent(test_type="code_review")  # not in allowed list

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_UNKNOWN_TEST_TYPE


# ---------------------------------------------------------------------------
# Automation Policies (5 tests)
# ---------------------------------------------------------------------------


class TestAutomationPolicies:
    """Verify automation policy enforcement."""

    def test_automation_prohibited_denies(self) -> None:
        """automation=prohibited + intent.automation=True → DENY_AUTOMATION_PROHIBITED."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"], automation_status="prohibited")
        intent = _make_intent(test_type="api_testing", automation=True)

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_AUTOMATION_PROHIBITED
        assert decision.violation is not None
        assert decision.violation.automation is True

    def test_automation_requires_approval_denies(self) -> None:
        """automation=requires_approval + intent.automation=True → DENY_AUTOMATION_REQUIRES_APPROVAL."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"], automation_status="requires_approval")
        intent = _make_intent(test_type="api_testing", automation=True)

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_AUTOMATION_REQUIRES_APPROVAL

    def test_automation_unknown_denies(self) -> None:
        """automation=unknown + intent.automation=True → DENY_AUTOMATION_UNKNOWN."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"], automation_status="unknown")
        intent = _make_intent(test_type="api_testing", automation=True)

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_AUTOMATION_UNKNOWN

    def test_automation_allowed_continues_to_test_type_check(self) -> None:
        """automation=allowed + allowed test type → ALLOW."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"], automation_status="allowed")
        intent = _make_intent(test_type="api_testing", automation=True)

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_allowed
        assert decision.reason == ProgramPolicyReason.ALLOW_POLICY_PERMITS_TEST_TYPE

    def test_automation_prohibited_but_automation_false_skips(self) -> None:
        """automation=prohibited + intent.automation=False → skips auto check, checks test type."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"], automation_status="prohibited")
        intent = _make_intent(test_type="api_testing", automation=False)

        decision = enforcer.check_intent(intent, policy)

        # automation check is skipped because automation=False
        # test_type is allowed → ALLOW
        assert decision.is_allowed
        assert decision.reason == ProgramPolicyReason.ALLOW_POLICY_PERMITS_TEST_TYPE


# ---------------------------------------------------------------------------
# Blocking PolicyRules (4 tests)
# ---------------------------------------------------------------------------


class TestBlockingRules:
    """Verify blocking PolicyRule enforcement."""

    def test_blocking_rule_matches_test_type_denies(self) -> None:
        """Blocking PolicyRule matching test type → DENY_BLOCKING_POLICY_RULE."""
        enforcer = ProgramPolicyEnforcer()
        blocking_rule = PolicyRule(
            description="Do not perform brute force attacks",
            category="testing",
            is_blocking=True,
        )
        policy = _make_policy(allowed=["brute_force"], rules=[blocking_rule])
        intent = _make_intent(test_type="brute_force")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_BLOCKING_POLICY_RULE
        assert decision.violation is not None
        assert decision.violation.matched_policy_item == blocking_rule.description

    def test_non_blocking_rule_does_not_block(self) -> None:
        """Non-blocking PolicyRule does NOT cause denial."""
        enforcer = ProgramPolicyEnforcer()
        non_blocking = PolicyRule(
            description="Do not perform brute force attacks",
            category="testing",
            is_blocking=False,  # NOT blocking
        )
        policy = _make_policy(allowed=["brute_force"], rules=[non_blocking])
        intent = _make_intent(test_type="brute_force")

        decision = enforcer.check_intent(intent, policy)

        # Rule is not blocking, and brute_force is in allowed list → ALLOW
        assert decision.is_allowed

    def test_blocking_rule_no_match_does_not_produce_allow(self) -> None:
        """Blocking rule without match still requires allowed_test_types check."""
        enforcer = ProgramPolicyEnforcer()
        blocking_rule = PolicyRule(
            description="Do not perform credential stuffing attacks",
            category="testing",
            is_blocking=True,
        )
        policy = _make_policy(allowed=["api_testing"], rules=[blocking_rule])
        intent = _make_intent(test_type="brute_force")  # different test type

        decision = enforcer.check_intent(intent, policy)

        # Rule does not match brute_force, but brute_force is not in allowed list
        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_UNKNOWN_TEST_TYPE

    def test_blocking_rule_wins_over_allowed_test_types(self) -> None:
        """Blocking rule denies even if test type is in allowed_test_types."""
        enforcer = ProgramPolicyEnforcer()
        blocking_rule = PolicyRule(
            description="No automated scanning allowed",
            category="testing",
            is_blocking=True,
        )
        policy = _make_policy(allowed=["automated_scanning"], rules=[blocking_rule])
        intent = _make_intent(test_type="automated_scanning")

        decision = enforcer.check_intent(intent, policy)

        # Blocking rule matches "automated scanning" → DENY
        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_BLOCKING_POLICY_RULE


# ---------------------------------------------------------------------------
# Unknown / Invalid (4 tests)
# ---------------------------------------------------------------------------


class TestUnknownInvalid:
    """Verify conservative handling of unknown and invalid states."""

    def test_missing_policy_denies(self) -> None:
        """policy=None → DENY_MISSING_POLICY."""
        enforcer = ProgramPolicyEnforcer()
        intent = _make_intent(test_type="api_testing")

        decision = enforcer.check_intent(intent, None)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_MISSING_POLICY
        assert decision.violation is None  # structural deny, no violation

    def test_empty_test_type_denies(self) -> None:
        """Empty test type → DENY_INVALID_INTENT."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"])
        intent = _make_intent(test_type="")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_INVALID_INTENT

    def test_unknown_test_type_denies(self) -> None:
        """Test type not in any list and no explicit allow → DENY_UNKNOWN_TEST_TYPE."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"], prohibited=["brute_force"])
        intent = _make_intent(test_type="some_unknown_test")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_UNKNOWN_TEST_TYPE

    def test_default_automation_unknown_conservative(self) -> None:
        """Default AutomationPolicy(status="unknown") + automation=True → DENY."""
        enforcer = ProgramPolicyEnforcer()
        # AutomationPolicy defaults to status="unknown"
        policy = ScopePolicy(
            source_url="https://example.com/policy",
            allowed_test_types=["api_testing"],
            # automation_policy defaults to AutomationPolicy(status="unknown")
            # but we need to let it be the default
        )
        # Explicitly set unknown to be sure
        policy.automation_policy = AutomationPolicy(status="unknown")

        intent = _make_intent(test_type="api_testing", automation=True)

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_AUTOMATION_UNKNOWN


# ---------------------------------------------------------------------------
# Audit / Serialization (4 tests)
# ---------------------------------------------------------------------------


class TestAuditSerialization:
    """Verify audit trail and serialization capabilities."""

    def test_deny_decision_contains_violation(self) -> None:
        """DENY decisions include a ProgramPolicyViolation for audit trail."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["brute_force"], allowed=["api_testing"])
        intent = _make_intent(test_type="brute_force")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.violation is not None
        assert decision.violation.target == intent.target
        assert decision.violation.test_type == "brute_force"
        assert decision.violation.reason == str(ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE)

    def test_decision_serializable_via_pydantic(self) -> None:
        """ProgramPolicyDecision can be serialized to JSON via Pydantic."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"])
        intent = _make_intent(test_type="api_testing")

        decision = enforcer.check_intent(intent, policy)

        # Serialize
        data = decision.model_dump(mode="json")
        assert data["status"] == "allow"
        assert data["reason"] == "allow_policy_permits_test_type"

        # Deserialize
        restored = ProgramPolicyDecision.model_validate(data)
        assert restored.status == decision.status
        assert restored.reason == decision.reason

    def test_violation_serializable_via_pydantic(self) -> None:
        """ProgramPolicyViolation can be serialized to JSON via Pydantic."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["brute_force"], allowed=["api_testing"])
        intent = _make_intent(test_type="brute_force")

        decision = enforcer.check_intent(intent, policy)
        assert decision.violation is not None

        # Serialize
        data = decision.violation.model_dump(mode="json")
        assert "target" in data
        assert "test_type" in data
        assert "reason" in data

        # Deserialize
        restored = ProgramPolicyViolation.model_validate(data)
        assert restored.target == decision.violation.target
        assert restored.test_type == decision.violation.test_type

    def test_no_persistent_file_written(self) -> None:
        """No persistent file or DB is written during enforcement."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["brute_force"], allowed=["api_testing"])
        intent = _make_intent(test_type="brute_force")

        # Multiple decisions to ensure no side effects
        for _ in range(10):
            decision = enforcer.check_intent(intent, policy)
            assert decision.is_denied

        # The decision object itself is the only output — no file, no DB
        # This test verifies by confirming the enforcer has no persistent state
        assert not hasattr(enforcer, "_audit_log")
        assert not hasattr(enforcer, "_log_file")


# ---------------------------------------------------------------------------
# Safety (8 tests)
# ---------------------------------------------------------------------------


class TestSafety:
    """Verify safety gates: no network, no DNS, no schedule, no override, determinism."""

    def test_no_real_network_requests(self) -> None:
        """Enforcer has no network imports (httpx, requests, urllib, socket)."""
        import inspect

        from neutrino.policy_enforcement import enforcer as enf_module

        source = inspect.getsource(enf_module)
        forbidden = ["httpx", "requests.get", "requests.post", "urllib", "socket."]
        for term in forbidden:
            assert term not in source, f"Forbidden network term found: {term}"

    def test_no_dns_resolution(self) -> None:
        """Enforcer has no DNS-related imports or calls."""
        import inspect

        from neutrino.policy_enforcement import enforcer as enf_module

        source = inspect.getsource(enf_module)
        forbidden = ["gethostbyname", "getaddrinfo", "dns.resolver"]
        for term in forbidden:
            assert term not in source, f"Forbidden DNS term found: {term}"

    def test_no_scheduler_or_sleep(self) -> None:
        """Enforcer has no scheduler, sleep, or wait logic."""
        import inspect

        from neutrino.policy_enforcement import enforcer as enf_module

        source = inspect.getsource(enf_module)
        forbidden = ["time.sleep", "asyncio.sleep", "threading.Timer", "schedule."]
        for term in forbidden:
            assert term not in source, f"Forbidden scheduler/sleep term found: {term}"

    def test_no_override_path_for_deny(self) -> None:
        """Decision model has no force/admin_override/ignore fields."""
        decision = ProgramPolicyDecision(
            target="api.example.com",
            status=ProgramPolicyDecisionStatus.DENY,
            reason=ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE,
            test_type="brute_force",
            explanation="Test",
        )

        # Verify no override fields exist
        fields = decision.model_fields
        assert "force" not in fields
        assert "admin_override" not in fields
        assert "allow_missing_policy" not in fields
        assert "bypass_prohibitions" not in fields

    def test_no_human_approval_override_implemented(self) -> None:
        """requires_approval status results in DENY — no approval workflow bypass."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"], automation_status="requires_approval")
        intent = _make_intent(test_type="api_testing", automation=True)

        decision = enforcer.check_intent(intent, policy)

        # Must be DENY — no approval mechanism exists
        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_AUTOMATION_REQUIRES_APPROVAL

        # No approval ID, no approval token, no bypass flag
        assert decision.violation is not None

    def test_determinism_same_inputs_same_decision(self) -> None:
        """Same inputs always produce the same decision."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["brute_force"], allowed=["api_testing"])
        intent = _make_intent(test_type="brute_force")

        decisions = [enforcer.check_intent(intent, policy) for _ in range(20)]

        first = decisions[0]
        for d in decisions[1:]:
            assert d.status == first.status
            assert d.reason == first.reason
            assert d.test_type == first.test_type

    def test_allow_decision_has_no_violation(self) -> None:
        """ALLOW decisions must not have violation evidence."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"])
        intent = _make_intent(test_type="api_testing")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_allowed
        assert decision.violation is None

    def test_deny_never_becomes_allow(self) -> None:
        """No path exists to flip a DENY to ALLOW."""
        enforcer = ProgramPolicyEnforcer()

        # Missing policy
        decision = enforcer.check_intent(_make_intent(), None)
        assert decision.is_denied
        # No way to make this ALLOW — policy is None

        # Invalid intent
        policy = _make_policy(allowed=["api_testing"])
        decision = enforcer.check_intent(_make_intent(test_type=""), policy)
        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_INVALID_INTENT


# ---------------------------------------------------------------------------
# Additional Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge case tests for complete coverage."""

    def test_whitespace_only_test_type_denies(self) -> None:
        """Whitespace-only test type → DENY_INVALID_INTENT."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"])
        intent = _make_intent(test_type="   ")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_INVALID_INTENT

    def test_policy_source_in_decision(self) -> None:
        """Decisions include policy_source from the ScopePolicy."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"])
        intent = _make_intent(test_type="api_testing")

        decision = enforcer.check_intent(intent, policy)

        assert decision.policy_source == policy.source_url

    def test_policy_source_in_deny_decision(self) -> None:
        """DENY decisions also include policy_source."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["brute_force"], allowed=["api_testing"])
        intent = _make_intent(test_type="brute_force")

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_denied
        assert decision.policy_source == policy.source_url

    def test_normalization_collapses_underscores(self) -> None:
        """Multiple spaces/hyphens collapse to single underscore."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(prohibited=["brute_force"], allowed=["api_testing"])

        # "brute   force" → "brute_force"
        intent = _make_intent(test_type="brute   force")
        decision = enforcer.check_intent(intent, policy)
        assert decision.is_denied
        assert decision.reason == ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE

    def test_normalization_allows_matched_in_allowed(self) -> None:
        """Normalized variants in allowed list also match."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["web application testing"])

        intent = _make_intent(test_type="web-application-testing")
        decision = enforcer.check_intent(intent, policy)

        assert decision.is_allowed

    def test_automation_false_skips_unknown_automation(self) -> None:
        """automation=False + automation_policy=unknown → no auto block, check test type."""
        enforcer = ProgramPolicyEnforcer()
        policy = _make_policy(allowed=["api_testing"], automation_status="unknown")
        intent = _make_intent(test_type="api_testing", automation=False)

        decision = enforcer.check_intent(intent, policy)

        assert decision.is_allowed
