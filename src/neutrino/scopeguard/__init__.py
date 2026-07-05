"""ScopeGuard — deterministic, local request-gating against a ScopePolicy.

This package provides the ScopeGuard decision engine that evaluates
targets (domains, IPs, URLs) against a loaded ScopePolicy and returns
an immutable ScopeDecision. All checks are local and deterministic;
no network requests, DNS resolution, or redirect handling is used.
"""

from neutrino.scopeguard.guard import ScopeGuard
from neutrino.scopeguard.models import ScopeDecision, ScopeDecisionStatus, ScopeReason

__all__ = [
    "ScopeGuard",
    "ScopeDecision",
    "ScopeDecisionStatus",
    "ScopeReason",
]
