"""Active Validation Gate domain models for Issue #14.

This module defines the core domain types for the Active-Validation-Gate:

    - ``ActiveValidationIntent``: A serializable intent describing a planned
      active validation action (port scan, HTTP request, etc.). Describes
      ONLY — never executes.
    - ``ReasonCode``: Deterministic reason codes for gate decisions.
    - ``ActiveValidationGateDecision``: The binary gate result — ALLOW or BLOCK
      with a specific reason and mandatory audit trail.

Key invariants:
    - Default is ``allow=False`` (fail-closed).
    - Only ``ALLOW_APPROVED_IN_SCOPE`` yields ``allow=True``.
    - Every decision is auditable.
    - No auto-approval, no LLM approval, no time-based approval.
    - No network I/O, no DNS, no shell, no exploits.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ------------------------------------------------------------------
# ReasonCode
# ------------------------------------------------------------------


class ReasonCode(str, Enum):
    """Deterministic reason codes for ActiveValidationGate decisions.

    Only ``ALLOW_APPROVED_IN_SCOPE`` yields ``allow=True``.
    All other codes yield ``allow=False`` (Default-Deny / fail-closed).

    Codes:
        ALLOW_APPROVED_IN_SCOPE:
            All checks passed: valid approval, scope match, ScopeGuard ALLOW,
            audit success.
        BLOCK_MISSING_APPROVAL:
            The referenced ApprovalRequest does not exist.
        BLOCK_PENDING_APPROVAL:
            The ApprovalRequest exists but is still PENDING.
        BLOCK_REJECTED_APPROVAL:
            The ApprovalRequest has been REJECTED by a human.
        BLOCK_INVALID_APPROVAL:
            The ApprovalRequest has an unknown, expired, or otherwise
            invalid status.
        BLOCK_SCOPE_MISMATCH:
            Scope metadata (target, scope_reference, test_type) does not
            match between the intent and the stored ApprovalRequest.
        BLOCK_SCOPE_DENIED:
            ScopeGuard evaluated the target and returned DENY.
        BLOCK_INVALID_INTENT:
            The ActiveValidationIntent itself is invalid (missing or
            blank required fields).
        BLOCK_AUDIT_FAILED:
            The audit sink (JSONL or SQLite) is unavailable or writing
            failed. The gate blocks to prevent unaudited actions.
    """

    ALLOW_APPROVED_IN_SCOPE = "ALLOW_APPROVED_IN_SCOPE"
    BLOCK_MISSING_APPROVAL = "BLOCK_MISSING_APPROVAL"
    BLOCK_PENDING_APPROVAL = "BLOCK_PENDING_APPROVAL"
    BLOCK_REJECTED_APPROVAL = "BLOCK_REJECTED_APPROVAL"
    BLOCK_INVALID_APPROVAL = "BLOCK_INVALID_APPROVAL"
    BLOCK_SCOPE_MISMATCH = "BLOCK_SCOPE_MISMATCH"
    BLOCK_SCOPE_DENIED = "BLOCK_SCOPE_DENIED"
    BLOCK_INVALID_INTENT = "BLOCK_INVALID_INTENT"
    BLOCK_AUDIT_FAILED = "BLOCK_AUDIT_FAILED"


# ------------------------------------------------------------------
# ActiveValidationIntent
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ActiveValidationIntent:
    """A serializable intent describing a planned active validation action.

    This model is purely descriptive — it does NOT execute anything.
    It MUST be validated before being passed to ``ActiveValidationGate``.

    Fields:
        id: Unique intent identifier (UUID string).
        actor: Who or what is proposing the action (e.g., "researcher",
            "scanner-engine").
        action: The planned action description (e.g., "port_scan",
            "http_request", "dns_lookup").
        target: The target of the action (domain, IP, URL, etc.).
        scope_reference: Reference to the scope policy that permits this
            target. Must be non-empty.
        test_type: The planned test type (e.g., "xss", "sql_injection",
            "port_scan"). Must be non-empty.
        risk_summary: A text summary of the risk assessment. Must be non-empty.
        approval_request_id: Reference to the ApprovalRequest (from #4)
            that authorizes this action. Must be non-empty.
        created_at: ISO 8601 timestamp of intent creation.

    Raises:
        ValueError: If any required field is empty or whitespace-only.
    """

    id: str
    actor: str
    action: str
    target: str
    scope_reference: str
    test_type: str
    risk_summary: str
    approval_request_id: str
    created_at: str

    def __post_init__(self) -> None:
        """Validate that mandatory fields are non-empty.

        Raises:
            ValueError: If any required field is empty or whitespace-only.
        """
        required_fields: dict[str, str] = {
            "id": self.id,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "scope_reference": self.scope_reference,
            "test_type": self.test_type,
            "risk_summary": self.risk_summary,
            "approval_request_id": self.approval_request_id,
            "created_at": self.created_at,
        }
        for field_name, value in required_fields.items():
            if not value or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")


# ------------------------------------------------------------------
# ActiveValidationGateDecision
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ActiveValidationGateDecision:
    """The binary gate result of evaluating an ActiveValidationIntent.

    This is a purely descriptive decision model. It does NOT trigger
    any action. Consumers (e.g. future #19 executor) check ``allow``
    before proceeding with actual validation.

    Fields:
        reason: The deterministic reason code for this decision.
        intent_id: The ID of the evaluated ActiveValidationIntent.
        target: The target that was checked.
        approval_request_id: The referenced ApprovalRequest ID.
        scope_reference: The scope policy reference.
        audit_event_id: Optional ID of the audit event if audited.
        explanation: Human-readable explanation of the decision.
        timestamp: ISO 8601 timestamp of the evaluation.
        allow: Binary flag — only True when reason is
            ``ALLOW_APPROVED_IN_SCOPE`` (fail-closed).

    Invariant:
        ``allow=True`` ONLY when ``reason == ALLOW_APPROVED_IN_SCOPE``.
        Setting ``allow=True`` for any other reason raises ``ValueError``.
    """

    reason: ReasonCode
    intent_id: str
    target: str
    approval_request_id: str
    scope_reference: str
    audit_event_id: str | None = None
    explanation: str = ""
    timestamp: str = ""
    allow: bool = False

    def __post_init__(self) -> None:
        """Enforce the invariant: allow=True only for ALLOW_APPROVED_IN_SCOPE.

        If reason is ALLOW_APPROVED_IN_SCOPE, allow is auto-set to True
        (correcting a possible oversight). For all other reasons,
        allow=True raises ValueError.
        """
        if self.reason == ReasonCode.ALLOW_APPROVED_IN_SCOPE:
            if not self.allow:
                object.__setattr__(self, "allow", True)
        else:
            if self.allow:
                raise ValueError(
                    f"allow=True is only valid for ALLOW_APPROVED_IN_SCOPE, got {self.reason.value}"
                )
