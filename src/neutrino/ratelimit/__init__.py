"""RateLimit Enforcement — deterministic, local per-target rate-limit enforcement.

This package provides the RateLimitEnforcer that evaluates request intents
against a ScopePolicy's rate_limits and a local RateLimitState, producing
immutable RateLimitDecision records. All checks are local and deterministic;
no network requests, DNS resolution, sleep, or persistent audit logs.
"""

from neutrino.ratelimit.enforcer import RateLimitEnforcer
from neutrino.ratelimit.models import (
    RateLimitDecision,
    RateLimitDecisionStatus,
    RateLimitReason,
    RateLimitRequest,
    RateLimitState,
    RateLimitViolation,
)

__all__ = [
    "RateLimitEnforcer",
    "RateLimitDecision",
    "RateLimitDecisionStatus",
    "RateLimitReason",
    "RateLimitRequest",
    "RateLimitState",
    "RateLimitViolation",
]
