"""Program Policy Prohibition Enforcement — deterministic, local enforcement.

This package provides the ``ProgramPolicyEnforcer`` decision engine that
evaluates ``ProgramPolicyIntent`` against ``ScopePolicy`` prohibition rules:
prohibited test types, automation policies, and blocking ``PolicyRule``
entries.

All checks are local and deterministic; no network requests, DNS resolution,
scheduler, or persistent audit log.
"""

from neutrino.policy_enforcement.enforcer import ProgramPolicyEnforcer
from neutrino.policy_enforcement.models import (
    ProgramPolicyDecision,
    ProgramPolicyDecisionStatus,
    ProgramPolicyIntent,
    ProgramPolicyReason,
    ProgramPolicyViolation,
)

__all__ = [
    "ProgramPolicyEnforcer",
    "ProgramPolicyDecision",
    "ProgramPolicyDecisionStatus",
    "ProgramPolicyIntent",
    "ProgramPolicyReason",
    "ProgramPolicyViolation",
]
