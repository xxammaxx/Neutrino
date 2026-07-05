"""Decision models for Program Policy Prohibition Enforcement.

Every program-specific prohibition decision is captured as an immutable
``ProgramPolicyDecision`` that records the target, outcome, reason code,
and optional violation evidence. Designed for serialization and later
audit trail consumption.

No network I/O. No DNS. No scheduler. No persistent audit log.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ProgramPolicyDecisionStatus(StrEnum):
    """Binary outcome of a ProgramPolicyEnforcer evaluation.

    Only two states exist. There is no UNKNOWN — if a determination
    cannot be made with certainty, the result is DENY.
    """

    ALLOW = "allow"
    DENY = "deny"


class ProgramPolicyReason(StrEnum):
    """Deterministic reason code explaining WHY a program-policy decision was made.

    Each code maps to exactly one evaluation path in the enforcer.
    There is no generic or fallback code — every path is explicit.

    ALLOW codes:
        ALLOW_POLICY_PERMITS_TEST_TYPE:
            Test type is explicitly allowed and no blocking rule applies.

    DENY codes — prohibited test types:
        DENY_PROHIBITED_TEST_TYPE:
            Test type is in the policy's ``prohibited_test_types`` list.

    DENY codes — automation policies:
        DENY_AUTOMATION_PROHIBITED:
            Automation is explicitly prohibited by the policy.
        DENY_AUTOMATION_REQUIRES_APPROVAL:
            Automation requires explicit prior approval.
        DENY_AUTOMATION_UNKNOWN:
            Automation policy status is unknown (conservative default).

    DENY codes — blocking rules:
        DENY_BLOCKING_POLICY_RULE:
            A blocking ``PolicyRule`` matched the test type.

    DENY codes — structural / unknown:
        DENY_UNKNOWN_TEST_TYPE:
            Test type is not in allowed_test_types (default deny).
        DENY_MISSING_POLICY:
            No ScopePolicy was provided.
        DENY_INVALID_INTENT:
            Test type is empty or structurally invalid.
    """

    ALLOW_POLICY_PERMITS_TEST_TYPE = "allow_policy_permits_test_type"

    DENY_PROHIBITED_TEST_TYPE = "deny_prohibited_test_type"
    DENY_AUTOMATION_PROHIBITED = "deny_automation_prohibited"
    DENY_AUTOMATION_REQUIRES_APPROVAL = "deny_automation_requires_approval"
    DENY_AUTOMATION_UNKNOWN = "deny_automation_unknown"
    DENY_BLOCKING_POLICY_RULE = "deny_blocking_policy_rule"
    DENY_UNKNOWN_TEST_TYPE = "deny_unknown_test_type"
    DENY_MISSING_POLICY = "deny_missing_policy"
    DENY_INVALID_INTENT = "deny_invalid_intent"


class ProgramPolicyViolation(BaseModel):
    """Serializable evidence for an audit-relevant policy prohibition violation.

    Captures what was denied, why, and which policy item triggered the
    denial. Designed for consumption by an AuditLog but does NOT persist
    anything itself (no file/DB writes).
    """

    target: str = Field(description="The target that was evaluated")
    test_type: str = Field(description="The (normalized) test type that was denied")
    automation: bool = Field(description="Whether the intent requested automation")
    reason: str = Field(description="Human-readable reason code for the denial")
    matched_policy_item: str | None = Field(
        default=None,
        description="The specific policy item that matched (prohibited type, rule description, etc.)",
    )
    policy_source: str | None = Field(
        default=None,
        description="Source URL of the policy used for this decision",
    )
    explanation: str = Field(
        default="",
        description="Human-readable explanation of why the violation occurred",
    )


class ProgramPolicyIntent(BaseModel):
    """Local, non-executing intent descriptor for a program-policy check.

    Describes a testing intent that would be evaluated against a ScopePolicy.
    Does NOT perform any network I/O, DNS resolution, or HTTP communication.
    """

    target: str = Field(description="The target being tested (domain, host, identifier)")
    test_type: str = Field(
        description="The type of test being requested (e.g. 'api_testing', 'brute_force')"
    )
    automation: bool = Field(
        default=False,
        description="Whether this intent involves automated testing",
    )
    method: str = Field(
        default="GET",
        description="HTTP method or action identifier",
    )
    source: str = Field(
        default="local-test",
        description="Origin of the test intent (e.g. 'local-test', 'manual')",
    )


class ProgramPolicyDecision(BaseModel):
    """Immutable record of a single ProgramPolicyEnforcer evaluation.

    Attributes:
        target: The target that was evaluated.
        status: ALLOW or DENY.
        reason: Deterministic reason code explaining the outcome.
        test_type: The (normalized) test type that was evaluated.
        explanation: Human-readable description of why the decision was made.
        policy_source: Source URL of the policy used, if any.
        violation: Violation evidence for denied intents (serializable audit trail).
    """

    target: str = Field(description="The evaluated target")
    status: ProgramPolicyDecisionStatus = Field(description="ALLOW or DENY")
    reason: ProgramPolicyReason = Field(description="Deterministic reason code")
    test_type: str = Field(description="The (normalized) test type evaluated")
    explanation: str = Field(
        default="",
        description="Human-readable explanation of the decision",
    )
    policy_source: str | None = Field(
        default=None,
        description="Source URL of the policy used for this decision",
    )
    violation: ProgramPolicyViolation | None = Field(
        default=None,
        description="Violation evidence for denied intents (serializable audit trail)",
    )

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def is_allowed(self) -> bool:
        """True if the decision is ALLOW."""
        return self.status == ProgramPolicyDecisionStatus.ALLOW

    @property
    def is_denied(self) -> bool:
        """True if the decision is DENY."""
        return self.status == ProgramPolicyDecisionStatus.DENY
