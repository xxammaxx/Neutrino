"""Decision model for ScopeGuard — immutable, serializable, auditable.

Every ScopeGuard decision is captured as a ScopeDecision that records
the target, outcome, reason code, matched scope entry, and human-readable
explanation. These decisions are designed to be serialized for later
audit trail consumption.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ScopeDecisionStatus(StrEnum):
    """Binary outcome of a ScopeGuard evaluation.

    Only two states exist. There is no UNKNOWN — if a determination
    cannot be made with certainty, the result is DENY.
    """

    ALLOW = "allow"
    DENY = "deny"


class ScopeReason(StrEnum):
    """Deterministic reason code explaining WHY a decision was made.

    Each code maps to exactly one evaluation path in ScopeGuard.
    There is no generic or fallback code — every path is explicit.
    """

    ALLOW_IN_SCOPE = "allow_in_scope"
    DENY_OUT_OF_SCOPE = "deny_out_of_scope"
    DENY_UNKNOWN_TARGET = "deny_unknown_target"
    DENY_INVALID_TARGET = "deny_invalid_target"
    DENY_UNSAFE_SCHEME = "deny_unsafe_scheme"
    DENY_MISSING_POLICY = "deny_missing_policy"


class ScopeDecision(BaseModel):
    """Immutable record of a single ScopeGuard evaluation.

    Attributes:
        target: The original (unmodified) target string that was evaluated.
        status: ALLOW or DENY.
        reason: Determistic reason code explaining the outcome.
        matched_entry: The ScopeEntry pattern that caused the match, if any.
        policy_source: The source URL of the policy used for this decision.
        explanation: Human-readable description of why the decision was made.
    """

    target: str = Field(description="Original target string evaluated")
    status: ScopeDecisionStatus = Field(description="ALLOW or DENY")
    reason: ScopeReason = Field(description="Deterministic reason code")
    matched_entry: str | None = Field(
        default=None,
        description="ScopeEntry pattern that matched (or None)",
    )
    policy_source: str | None = Field(
        default=None,
        description="Source URL of the policy used for this decision",
    )
    explanation: str = Field(
        default="",
        description="Human-readable explanation of the decision",
    )

    @property
    def is_allowed(self) -> bool:
        """Convenience accessor: True if the decision is ALLOW."""
        return self.status == ScopeDecisionStatus.ALLOW

    @property
    def is_denied(self) -> bool:
        """Convenience accessor: True if the decision is DENY."""
        return self.status == ScopeDecisionStatus.DENY
