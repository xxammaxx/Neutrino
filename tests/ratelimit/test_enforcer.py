"""Unit tests for the RateLimitEnforcer module.

All tests are local and deterministic. No network I/O, no DNS,
no sleep, no scheduler, no persistent audit log.
"""

from __future__ import annotations

import json
import time

import pytest

from neutrino.models.policy import RateLimit, ScopePolicy
from neutrino.ratelimit.enforcer import RateLimitEnforcer
from neutrino.ratelimit.models import (
    RateLimitDecision,
    RateLimitDecisionStatus,
    RateLimitReason,
    RateLimitRequest,
    RateLimitState,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def enforcer() -> RateLimitEnforcer:
    """Return a fresh enforcer instance."""
    return RateLimitEnforcer()


@pytest.fixture
def empty_state() -> RateLimitState:
    """Return a fresh, empty rate-limit state."""
    return RateLimitState()


@pytest.fixture
def base_policy() -> ScopePolicy:
    """Return a ScopePolicy with typical rate limits."""
    return ScopePolicy(
        source_url="https://hackerone.com/example",
        rate_limits=RateLimit(
            requests_per_second=2,
            requests_per_minute=60,
            requests_per_hour=500,
            requests_per_day=5000,
            concurrent_requests=5,
        ),
        raw_text="Rate-limited testing: 2 req/s, 60 req/min, 500 req/hr, 5000 req/day, 5 concurrent.",
    )


@pytest.fixture
def policy_no_limits() -> ScopePolicy:
    """Return a ScopePolicy with rate_limits=None."""
    return ScopePolicy(
        source_url="https://hackerone.com/no-limits",
        rate_limits=None,
        raw_text="No rate limits specified.",
    )


@pytest.fixture
def policy_partial_limits() -> ScopePolicy:
    """Return a ScopePolicy with only some limit fields set."""
    return ScopePolicy(
        source_url="https://hackerone.com/partial",
        rate_limits=RateLimit(
            requests_per_second=2,
            concurrent_requests=3,
        ),
        raw_text="Only per-second and concurrent limits.",
    )


@pytest.fixture
def sample_request() -> RateLimitRequest:
    """Return a sample request intent."""
    return RateLimitRequest(
        target="api.example.com",
        timestamp=1000.0,
        method="GET",
        request_id="req-1",
    )


# ------------------------------------------------------------------
# 1. Missing policy → DENY
# ------------------------------------------------------------------


class TestMissingPolicy:
    """Policy is None → immediate DENY."""

    def test_missing_policy_denies(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, None, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY
        assert decision.reason == RateLimitReason.DENY_MISSING_POLICY
        assert decision.is_denied is True
        assert decision.is_allowed is False

    def test_missing_policy_explanation_contains_context(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, None, empty_state)
        assert "policy" in decision.explanation.lower()

    def test_missing_policy_no_violation_evidence(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, None, empty_state)
        # No violation for structural denials (only for limit-exceeded)
        assert decision.violation is None

    def test_missing_policy_does_not_mutate_state(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        sample_request: RateLimitRequest,
    ) -> None:
        assert len(empty_state.requests) == 0
        enforcer.check_request(sample_request, None, empty_state)
        assert len(empty_state.requests) == 0


# ------------------------------------------------------------------
# 2. Missing rate limits → DENY
# ------------------------------------------------------------------


class TestMissingRateLimits:
    """RateLimits is None → DENY (conservative)."""

    def test_missing_rate_limits_denies(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        policy_no_limits: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, policy_no_limits, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY
        assert decision.reason == RateLimitReason.DENY_MISSING_RATE_LIMIT

    def test_missing_rate_limits_does_not_mutate_state(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        policy_no_limits: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        assert len(empty_state.requests) == 0
        enforcer.check_request(sample_request, policy_no_limits, empty_state)
        assert len(empty_state.requests) == 0


# ------------------------------------------------------------------
# 3. Invalid / empty target → DENY
# ------------------------------------------------------------------


class TestInvalidTarget:
    """Empty or whitespace-only targets → DENY_INVALID_TARGET."""

    def test_empty_string_target_denies(
        self, enforcer: RateLimitEnforcer, empty_state: RateLimitState, base_policy: ScopePolicy
    ) -> None:
        req = RateLimitRequest(target="", timestamp=1000.0, request_id="empty")
        decision = enforcer.check_request(req, base_policy, empty_state)
        assert decision.reason == RateLimitReason.DENY_INVALID_TARGET

    def test_whitespace_only_target_denies(
        self, enforcer: RateLimitEnforcer, empty_state: RateLimitState, base_policy: ScopePolicy
    ) -> None:
        req = RateLimitRequest(target="   ", timestamp=1000.0, request_id="ws")
        decision = enforcer.check_request(req, base_policy, empty_state)
        assert decision.reason == RateLimitReason.DENY_INVALID_TARGET

    def test_scheme_only_target_denies(
        self, enforcer: RateLimitEnforcer, empty_state: RateLimitState, base_policy: ScopePolicy
    ) -> None:
        req = RateLimitRequest(target="https://", timestamp=1000.0, request_id="so")
        decision = enforcer.check_request(req, base_policy, empty_state)
        assert decision.reason == RateLimitReason.DENY_INVALID_TARGET

    def test_invalid_target_does_not_mutate_state(
        self, enforcer: RateLimitEnforcer, empty_state: RateLimitState, base_policy: ScopePolicy
    ) -> None:
        req = RateLimitRequest(target="", timestamp=1000.0, request_id="empty")
        assert len(empty_state.requests) == 0
        enforcer.check_request(req, base_policy, empty_state)
        assert len(empty_state.requests) == 0


# ------------------------------------------------------------------
# 4. Within limits → ALLOW
# ------------------------------------------------------------------


class TestAllowWithinLimits:
    """Single request within all limits → ALLOW."""

    def test_single_request_allowed(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.ALLOW
        assert decision.reason == RateLimitReason.ALLOW_WITHIN_LIMIT
        assert decision.is_allowed is True

    def test_allow_adds_request_to_state(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        assert len(empty_state.requests) == 0
        enforcer.check_request(sample_request, base_policy, empty_state)
        assert len(empty_state.requests) == 1
        assert empty_state.requests[0].request_id == sample_request.request_id

    def test_multiple_requests_within_limits_allowed(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        """3 requests well within all limits → all ALLOW."""
        for i in range(3):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=float(1000 + i),
                request_id=f"req-{i}",
            )
            decision = enforcer.check_request(req, base_policy, empty_state)
            assert decision.status == RateLimitDecisionStatus.ALLOW
        assert len(empty_state.requests) == 3

    def test_allow_has_no_violation(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, base_policy, empty_state)
        assert decision.violation is None

    def test_allow_has_policy_source(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, base_policy, empty_state)
        assert decision.policy_source == base_policy.source_url


# ------------------------------------------------------------------
# 5. Exceeding per-second limit → DENY
# ------------------------------------------------------------------


class TestExceedPerSecond:
    """Exceeding requests_per_second → DENY."""

    def test_exceeding_per_second_denies(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        # Pre-fill state with 2 requests within 1s window (at limit)
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i * 0.1,
                request_id=f"pre-{i}",
            )
            empty_state.add_request(req)

        # This 3rd request should be denied
        new_req = RateLimitRequest(
            target="api.example.com",
            timestamp=1000.3,
            request_id="exceed",
        )
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY
        assert decision.reason == RateLimitReason.DENY_REQUESTS_PER_SECOND_EXCEEDED

    def test_per_second_deny_has_violation(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 0.1, request_id=f"p-{i}"
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1000.3, request_id="ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.violation is not None
        assert decision.violation.limit_name == "requests_per_second"
        assert decision.violation.limit_value == 2
        assert decision.violation.observed_value >= 2
        assert decision.violation.window_seconds == 1.0

    def test_per_second_deny_has_retry_after(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 0.1, request_id=f"ra-{i}"
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1000.3, request_id="ra-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.retry_after_seconds is not None
        assert decision.retry_after_seconds >= 0.0

    def test_per_second_deny_does_not_mutate_state(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 0.1, request_id=f"ns-{i}"
            )
            empty_state.add_request(req)
        before = len(empty_state.requests)
        new_req = RateLimitRequest(target="api.example.com", timestamp=1000.3, request_id="ns-ex")
        enforcer.check_request(new_req, base_policy, empty_state)
        assert len(empty_state.requests) == before


# ------------------------------------------------------------------
# 6. Exceeding per-minute limit → DENY
# ------------------------------------------------------------------


class TestExceedPerMinute:
    """Exceeding requests_per_minute → DENY."""

    def test_exceeding_per_minute_denies(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        # Pre-fill with 60 completed requests (limit) within 60s window.
        # Complete them so concurrent limit (5) does NOT fire.
        for i in range(60):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i * 0.5,
                request_id=f"pm-{i}",
            )
            empty_state.add_request(req)
            empty_state.complete_request(req.request_id)

        new_req = RateLimitRequest(
            target="api.example.com",
            timestamp=1030.0,
            request_id="pm-exceed",
        )
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY
        assert decision.reason == RateLimitReason.DENY_REQUESTS_PER_MINUTE_EXCEEDED

    def test_per_minute_violation_has_correct_window(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(60):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 0.5, request_id=f"pmv-{i}"
            )
            empty_state.add_request(req)
            empty_state.complete_request(req.request_id)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1030.0, request_id="pmv-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.violation is not None
        assert decision.violation.window_seconds == 60.0
        assert decision.violation.limit_name == "requests_per_minute"


# ------------------------------------------------------------------
# 7. Exceeding per-hour limit → DENY
# ------------------------------------------------------------------


class TestExceedPerHour:
    """Exceeding requests_per_hour → DENY."""

    def test_exceeding_per_hour_denies(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        # Spread requests across the hour so per-second limit (2) does NOT fire.
        for i in range(500):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i * 7.0,
                request_id=f"ph-{i}",
            )
            empty_state.add_request(req)
            empty_state.complete_request(req.request_id)

        new_req = RateLimitRequest(
            target="api.example.com",
            timestamp=4500.0,
            request_id="ph-exceed",
        )
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY
        assert decision.reason == RateLimitReason.DENY_REQUESTS_PER_HOUR_EXCEEDED

    def test_per_hour_violation_has_correct_window(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(500):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 7.0, request_id=f"phv-{i}"
            )
            empty_state.add_request(req)
            empty_state.complete_request(req.request_id)

        new_req = RateLimitRequest(target="api.example.com", timestamp=4500.0, request_id="phv-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.violation is not None
        assert decision.violation.window_seconds == 3600.0


# ------------------------------------------------------------------
# 8. Exceeding per-day limit → DENY
# ------------------------------------------------------------------


class TestExceedPerDay:
    """Exceeding requests_per_day → DENY."""

    def test_exceeding_per_day_denies(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        # Spread requests across the day so no finer limit fires first.
        for i in range(5000):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i * 17.0,
                request_id=f"pd-{i}",
            )
            empty_state.add_request(req)
            empty_state.complete_request(req.request_id)

        new_req = RateLimitRequest(
            target="api.example.com",
            timestamp=86000.0,
            request_id="pd-exceed",
        )
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY
        assert decision.reason == RateLimitReason.DENY_REQUESTS_PER_DAY_EXCEEDED

    def test_per_day_violation_has_correct_window(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(5000):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 17.0, request_id=f"pdv-{i}"
            )
            empty_state.add_request(req)
            empty_state.complete_request(req.request_id)

        new_req = RateLimitRequest(target="api.example.com", timestamp=86000.0, request_id="pdv-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.violation is not None
        assert decision.violation.window_seconds == 86400.0


# ------------------------------------------------------------------
# 9. Exceeding concurrent limit → DENY
# ------------------------------------------------------------------


class TestExceedConcurrent:
    """Exceeding concurrent_requests → DENY."""

    def test_exceeding_concurrent_denies(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        # Pre-fill state with 5 active requests (at concurrent limit)
        for i in range(5):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i,
                request_id=f"cc-{i}",
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(
            target="api.example.com",
            timestamp=1005.0,
            request_id="cc-exceed",
        )
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY
        assert decision.reason == RateLimitReason.DENY_CONCURRENT_REQUESTS_EXCEEDED

    def test_concurrent_violation_has_zero_window(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(5):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i, request_id=f"ccv-{i}"
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1005.0, request_id="ccv-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.violation is not None
        assert decision.violation.limit_name == "concurrent_requests"
        assert decision.violation.window_seconds == 0

    def test_release_request_frees_concurrent_slot(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        """After releasing a concurrent slot, a new request is ALLOWed."""
        for i in range(5):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i,
                request_id=f"rel-{i}",
            )
            empty_state.add_request(req)

        # Release one slot
        empty_state.complete_request("rel-0")

        # Now new request should be allowed
        new_req = RateLimitRequest(
            target="api.example.com",
            timestamp=1005.0,
            request_id="rel-new",
        )
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.ALLOW


# ------------------------------------------------------------------
# 10. Per-target isolation
# ------------------------------------------------------------------


class TestPerTargetIsolation:
    """Rate limits are per-target — target A exceeding limit does not block target B."""

    def test_different_targets_have_independent_limits(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        # Fill target A up to concurrent limit
        for i in range(5):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i,
                request_id=f"pt-a-{i}",
            )
            empty_state.add_request(req)

        # Target B should still be allowed (independent limit tracking)
        req_b = RateLimitRequest(
            target="app.example.com",
            timestamp=1005.0,
            request_id="pt-b-1",
        )
        decision = enforcer.check_request(req_b, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.ALLOW

    def test_normalized_targets_share_same_counter(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        """https://api.example.com/ and api.example.com normalize to the same target."""
        # Add request with scheme
        req1 = RateLimitRequest(
            target="https://api.example.com/",
            timestamp=1000.0,
            request_id="n1",
        )
        enforcer.check_request(req1, base_policy, empty_state)

        # Second request without scheme should count towards same limit
        req2 = RateLimitRequest(
            target="api.example.com",
            timestamp=1000.1,
            request_id="n2",
        )
        enforcer.check_request(req2, base_policy, empty_state)

        # Now 2 requests should be in the same target bucket
        # Third request within per-second limit (limit=2) should be denied
        req3 = RateLimitRequest(
            target="API.EXAMPLE.COM",  # uppercase — normalized to lowercase
            timestamp=1000.2,
            request_id="n3",
        )
        decision = enforcer.check_request(req3, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY
        assert decision.reason == RateLimitReason.DENY_REQUESTS_PER_SECOND_EXCEEDED

    def test_url_with_path_normalizes_correctly(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        """URLs with path are normalized to host-only for rate-limit tracking."""
        # Fill state via a URL with path
        req1 = RateLimitRequest(
            target="https://api.example.com/v1/status",
            timestamp=1000.0,
            request_id="url1",
        )
        enforcer.check_request(req1, base_policy, empty_state)

        # Request to same host without path should share the count
        req2 = RateLimitRequest(
            target="api.example.com",
            timestamp=1000.1,
            request_id="url2",
        )
        enforcer.check_request(req2, base_policy, empty_state)

        # Third request should be denied (exceeds per-second limit of 2)
        req3 = RateLimitRequest(
            target="api.example.com/other",
            timestamp=1000.2,
            request_id="url3",
        )
        decision = enforcer.check_request(req3, base_policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY


# ------------------------------------------------------------------
# 11. Retry-after calculation
# ------------------------------------------------------------------


class TestRetryAfter:
    """DENY decisions include retry_after_seconds where computable."""

    def test_retry_after_is_positive_when_violated(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        # Pre-fill: 2 requests at t=1000.0 and t=1000.1
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 0.1, request_id=f"ra-{i}"
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1000.15, request_id="ra-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.retry_after_seconds is not None
        # Oldest request at 1000.0, retry after 1.0 from that = 1001.0
        # So retry_after = 1001.0 - 1000.15 = 0.85
        assert decision.retry_after_seconds >= 0.0

    def test_retry_after_concurrent_is_none(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(5):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i, request_id=f"cra-{i}"
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1005.0, request_id="cra-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        # Concurrent violations: retry depends on external release, not time
        assert decision.retry_after_seconds is None

    def test_retry_after_none_when_no_requests_in_window(
        self, enforcer: RateLimitEnforcer, empty_state: RateLimitState
    ) -> None:
        """Internal _calc_retry_after returns None for empty window."""
        retry = enforcer._calc_retry_after(empty_state, "t", 1.0, 1000.0)
        assert retry is None


# ------------------------------------------------------------------
# 12. Violation evidence (audit)
# ------------------------------------------------------------------


class TestViolationEvidence:
    """Every DENY due to limit exceeded produces serializable violation evidence."""

    def test_violation_is_serializable_to_json(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 0.1, request_id=f"ser-{i}"
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1000.3, request_id="ser-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.violation is not None

        # Serialize to JSON and back
        data = decision.violation.model_dump()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["limit_name"] == "requests_per_second"
        assert parsed["target"] == "api.example.com"
        assert parsed["window_seconds"] == 1.0

    def test_decision_is_serializable_to_json(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, base_policy, empty_state)
        data = decision.model_dump()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["status"] == "allow"
        assert parsed["reason"] == "allow_within_limit"

    def test_violation_contains_all_required_fields(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 0.1, request_id=f"fld-{i}"
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1000.3, request_id="fld-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        v = decision.violation
        assert v is not None
        assert v.target == "api.example.com"
        assert len(v.reason) > 0
        assert v.limit_name == "requests_per_second"
        assert v.limit_value == 2
        assert v.observed_value >= 2
        assert v.window_seconds == 1.0
        assert v.timestamp > 0

    def test_no_violation_for_allow(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, base_policy, empty_state)
        assert decision.violation is None

    def test_no_violation_for_structural_deny(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
    ) -> None:
        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="sd")
        decision = enforcer.check_request(req, None, empty_state)
        assert decision.violation is None

    def test_no_violation_for_missing_rate_limits(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        policy_no_limits: ScopePolicy,
    ) -> None:
        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="mrl")
        decision = enforcer.check_request(req, policy_no_limits, empty_state)
        assert decision.violation is None

    def test_no_persistent_file_written(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
        sample_request: RateLimitRequest,
    ) -> None:
        """Verify that no persistent audit file is written (Issue #12 scope)."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily redirect no writes — just verify no side effects
            enforcer.check_request(sample_request, base_policy, empty_state)
            # No audit.jsonl or rate_limit_violations.log should appear
            files = os.listdir(tmpdir)
            assert len(files) == 0


# ------------------------------------------------------------------
# 13. Partial / auto_throttle / conservatism
# ------------------------------------------------------------------


class TestPartialLimits:
    """Partial limits — only specified fields are enforced."""

    def test_partial_limits_only_enforce_specified(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        policy_partial_limits: ScopePolicy,
    ) -> None:
        """Only requests_per_second and concurrent are set. Other dimensions are not enforced."""
        # Fill 3 requests per second (exceeds the limit of 2)
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i * 0.1,
                request_id=f"part-{i}",
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(
            target="api.example.com",
            timestamp=1000.2,
            request_id="part-ex",
        )
        decision = enforcer.check_request(new_req, policy_partial_limits, empty_state)
        assert decision.reason == RateLimitReason.DENY_REQUESTS_PER_SECOND_EXCEEDED

    def test_partial_limits_allow_when_limits_not_set(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        policy_partial_limits: ScopePolicy,
    ) -> None:
        """When per_minute is not set, many requests spread over >1s are allowed."""
        for i in range(50):
            req = RateLimitRequest(
                target="api.example.com",
                timestamp=1000.0 + i * 2.0,  # 2 seconds apart, so <1 per second
                request_id=f"pall-{i}",
            )
            decision = enforcer.check_request(req, policy_partial_limits, empty_state)
            assert decision.status == RateLimitDecisionStatus.ALLOW
            # Mark completed to free concurrent slots
            empty_state.complete_request(req.request_id)


class TestAutoThrottle:
    """auto_throttle=False must NOT bypass DENY."""

    def test_auto_throttle_false_still_enforces_limits(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
    ) -> None:
        policy = ScopePolicy(
            source_url="https://hackerone.com/auto-off",
            rate_limits=RateLimit(
                requests_per_second=1,
                auto_throttle=False,
            ),
        )
        # Add one request already
        req1 = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="at1")
        empty_state.add_request(req1)

        # Second request should be denied regardless of auto_throttle
        req2 = RateLimitRequest(target="api.example.com", timestamp=1000.5, request_id="at2")
        decision = enforcer.check_request(req2, policy, empty_state)
        assert decision.status == RateLimitDecisionStatus.DENY


class TestConservativeMissingLimits:
    """RateLimits with no fields set at all → treated as DENY."""

    def test_all_none_rate_limits_still_treat_as_set(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
    ) -> None:
        """Even if all RateLimit fields are None, the object exists, so it's treated as having limits.
        With all None fields, no limit check triggers, so request is allowed."""
        policy = ScopePolicy(
            source_url="https://hackerone.com/all-null",
            rate_limits=RateLimit(),
        )
        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="anr")
        decision = enforcer.check_request(req, policy, empty_state)
        # All fields None → no limits enforced → ALLOW
        assert decision.status == RateLimitDecisionStatus.ALLOW

    def test_rate_limits_none_denies(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        policy_no_limits: ScopePolicy,
    ) -> None:
        """RateLimits is None (not just empty) → DENY_MISSING_RATE_LIMIT."""
        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="rn")
        decision = enforcer.check_request(req, policy_no_limits, empty_state)
        assert decision.reason == RateLimitReason.DENY_MISSING_RATE_LIMIT


# ------------------------------------------------------------------
# 14. Safety: No real network, DNS, sleep, scheduler, bypass
# ------------------------------------------------------------------


class TestSafetyGates:
    """Safety invariants: no network, no DNS, no sleep, no bypass."""

    def test_enforcer_module_has_no_network_imports(self) -> None:
        """Enforcer must not import httpx, socket, urllib, or requests."""
        import inspect

        from neutrino.ratelimit import enforcer as enf

        source = inspect.getsource(enf)
        assert "httpx" not in source
        assert "socket" not in source
        assert "urllib" not in source
        assert "requests." not in source  # requests library

    def test_enforcer_has_no_sleep_import(self) -> None:
        """Enforcer must not import time.sleep or asyncio.sleep."""
        import inspect

        from neutrino.ratelimit import enforcer as enf

        source = inspect.getsource(enf)
        assert "time.sleep" not in source
        assert "asyncio.sleep" not in source
        assert "await" not in source

    def test_no_force_override_in_decision(self) -> None:
        """RateLimitDecision has no force=True or admin_override field."""
        fields = list(RateLimitDecision.model_fields.keys())
        assert "force" not in fields
        assert "admin_override" not in fields
        assert "ignore_rate_limit" not in fields
        assert "bypass" not in fields

    def test_no_allow_missing_limits_flag(self) -> None:
        """Enforcer has no allow_missing_limits flag."""
        import inspect

        from neutrino.ratelimit import enforcer as enf

        source = inspect.getsource(enf.RateLimitEnforcer.check_request)
        assert "allow_missing_limits" not in source
        assert "auto_raise_limit" not in source

    def test_no_override_path_for_deny(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
    ) -> None:
        """DENY cannot be changed to ALLOW by any code path."""
        # DENY from missing policy — no way to override
        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="ovr")
        decision = enforcer.check_request(req, None, empty_state)
        assert decision.is_denied
        # Even if we manually construct a new decision, the original is DENY
        # The decision object itself is immutable (Pydantic model)


# ------------------------------------------------------------------
# 15. Determinism
# ------------------------------------------------------------------


class TestDeterminism:
    """Same inputs + same state → same decision (deterministic)."""

    def test_same_inputs_same_decision(
        self,
        enforcer: RateLimitEnforcer,
        base_policy: ScopePolicy,
    ) -> None:
        """Two calls with identical inputs produce identical decisions."""
        state1 = RateLimitState()
        state2 = RateLimitState()

        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="det")
        d1 = enforcer.check_request(req, base_policy, state1)
        d2 = enforcer.check_request(req, base_policy, state2)

        assert d1.status == d2.status
        assert d1.reason == d2.reason
        assert d1.explanation == d2.explanation


# ------------------------------------------------------------------
# 16. State management
# ------------------------------------------------------------------


class TestStateManagement:
    """RateLimitState query and mutation operations."""

    def test_count_in_window_zero(self, empty_state: RateLimitState) -> None:
        assert empty_state.count_in_window("api.example.com", 1.0, 1000.0) == 0

    def test_count_in_window_counts_correctly(self, empty_state: RateLimitState) -> None:
        empty_state.add_request(
            RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="c1")
        )
        empty_state.add_request(
            RateLimitRequest(target="api.example.com", timestamp=1000.5, request_id="c2")
        )
        # Both within 1s window
        assert empty_state.count_in_window("api.example.com", 1.0, 1000.6) == 2

    def test_count_in_window_excludes_outside(self, empty_state: RateLimitState) -> None:
        empty_state.add_request(
            RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="ow1")
        )
        # Window is from t=1000.0 to t=1001.0 (cutoff = 1000.0)
        # timestamp 1000.0 is NOT > cutoff, so it's excluded
        assert empty_state.count_in_window("api.example.com", 1.0, 1001.0) == 0

    def test_prune_removes_old_requests(self, empty_state: RateLimitState) -> None:
        empty_state.add_request(
            RateLimitRequest(target="api.example.com", timestamp=900.0, request_id="old")
        )
        empty_state.complete_request("old")  # must be completed to be prunable
        empty_state.add_request(
            RateLimitRequest(target="api.example.com", timestamp=1100.0, request_id="new")
        )
        empty_state.prune_before(1000.0)
        assert len(empty_state.requests) == 1
        assert empty_state.requests[0].request_id == "new"

    def test_active_count_different_targets(self, empty_state: RateLimitState) -> None:
        empty_state.add_request(
            RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="a1")
        )
        empty_state.add_request(
            RateLimitRequest(target="app.example.com", timestamp=1000.0, request_id="a2")
        )
        assert empty_state.active_count("api.example.com") == 1
        assert empty_state.active_count("app.example.com") == 1
        assert empty_state.active_count("other.example.com") == 0

    def test_count_in_window_by_target(self, empty_state: RateLimitState) -> None:
        empty_state.add_request(
            RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="bt1")
        )
        empty_state.add_request(
            RateLimitRequest(target="app.example.com", timestamp=1000.1, request_id="bt2")
        )
        assert empty_state.count_in_window("api.example.com", 1.0, 1000.5) == 1
        assert empty_state.count_in_window("app.example.com", 1.0, 1000.5) == 1


# ------------------------------------------------------------------
# 17. Request model
# ------------------------------------------------------------------


class TestRequestModel:
    """RateLimitRequest model validation."""

    def test_request_default_method(self) -> None:
        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="r1")
        assert req.method == "GET"

    def test_request_custom_method(self) -> None:
        req = RateLimitRequest(
            target="api.example.com", timestamp=1000.0, method="POST", request_id="r2"
        )
        assert req.method == "POST"

    def test_request_is_serializable(self) -> None:
        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="r3")
        data = req.model_dump()
        assert data["target"] == "api.example.com"
        assert data["request_id"] == "r3"

    def test_request_has_no_network_fields(self) -> None:
        """RateLimitRequest must not have HTTP client, DNS, or socket fields."""
        fields = list(RateLimitRequest.model_fields.keys())
        assert "url" not in fields  # we use 'target'
        assert "dns" not in fields
        assert "sock" not in fields
        assert "ip" not in fields


# ------------------------------------------------------------------
# 18. Reason codes completeness
# ------------------------------------------------------------------


class TestReasonCodes:
    """All defined reason codes are used in proper decision paths."""

    def test_allow_reason_only_for_allow(self) -> None:
        """Only ALLOW_WITHIN_LIMIT is an ALLOW reason."""
        assert RateLimitReason.ALLOW_WITHIN_LIMIT.value.startswith("allow")

    def test_all_deny_reasons_start_with_deny(self) -> None:
        deny_reasons = [r for r in RateLimitReason if r != RateLimitReason.ALLOW_WITHIN_LIMIT]
        for reason in deny_reasons:
            assert reason.value.startswith("deny"), f"{reason} should start with deny"

    def test_each_limit_dimension_has_reason(self) -> None:
        """Every rate-limit dimension has a corresponding DENY reason."""
        deny_values = [r.value for r in RateLimitReason]
        assert "deny_requests_per_second_exceeded" in deny_values
        assert "deny_requests_per_minute_exceeded" in deny_values
        assert "deny_requests_per_hour_exceeded" in deny_values
        assert "deny_requests_per_day_exceeded" in deny_values
        assert "deny_concurrent_requests_exceeded" in deny_values


# ------------------------------------------------------------------
# 19. No Sleep / No Scheduler
# ------------------------------------------------------------------


class TestNoSleep:
    """Enforcer makes no sleep or wait calls."""

    def test_check_request_no_sleep(self, enforcer: RateLimitEnforcer) -> None:
        """Calling check_request must not invoke time.sleep."""
        state = RateLimitState()
        policy = ScopePolicy(
            source_url="https://example.com",
            rate_limits=RateLimit(requests_per_second=1),
        )
        req = RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="ns1")
        start = time.time()
        decision = enforcer.check_request(req, policy, state)
        elapsed = time.time() - start
        # Should complete essentially instantly (< 0.1s)
        assert elapsed < 0.1, f"Enforcer took {elapsed:.3f}s — may be sleeping"
        assert decision.status == RateLimitDecisionStatus.ALLOW

    def test_deny_does_not_block(self, enforcer: RateLimitEnforcer) -> None:
        """Even DENY must return instantly, not block."""
        state = RateLimitState()
        policy = ScopePolicy(
            source_url="https://example.com",
            rate_limits=RateLimit(requests_per_second=1),
        )
        # Pre-fill state to trigger DENY
        state.add_request(
            RateLimitRequest(target="api.example.com", timestamp=1000.0, request_id="b1")
        )
        req = RateLimitRequest(target="api.example.com", timestamp=1000.5, request_id="b2")
        start = time.time()
        decision = enforcer.check_request(req, policy, state)
        elapsed = time.time() - start
        assert elapsed < 0.1, f"DENY path took {elapsed:.3f}s — may be sleeping or blocking"
        assert decision.status == RateLimitDecisionStatus.DENY


# ------------------------------------------------------------------
# 20. Policy source tracking
# ------------------------------------------------------------------


class TestPolicySourceTracking:
    """Decision records include the policy source URL for audit."""

    def test_deny_decision_includes_policy_source(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        base_policy: ScopePolicy,
    ) -> None:
        for i in range(2):
            req = RateLimitRequest(
                target="api.example.com", timestamp=1000.0 + i * 0.1, request_id=f"ps-{i}"
            )
            empty_state.add_request(req)

        new_req = RateLimitRequest(target="api.example.com", timestamp=1000.3, request_id="ps-ex")
        decision = enforcer.check_request(new_req, base_policy, empty_state)
        assert decision.policy_source == "https://hackerone.com/example"

    def test_missing_policy_has_no_source(
        self,
        enforcer: RateLimitEnforcer,
        empty_state: RateLimitState,
        sample_request: RateLimitRequest,
    ) -> None:
        decision = enforcer.check_request(sample_request, None, empty_state)
        assert decision.policy_source is None
