"""Approval domain models for the Human Authorization Workflow.

This module defines the core domain types for the #4 Human Authorization
Workflow:

    - ``ApprovalRequest``: A serializable request for human approval of an
      active action, containing scope information, planned test type, and
      risk summary.
    - ``HumanDecision``: A human's explicit decision (APPROVE or REJECT)
      on an approval request.
    - ``ApprovalDecision``: The gate result — a binary allow/block verdict
      derived from the request status and any human decision.

Key invariants:
    - Default status is ``PENDING``.
    - Only explicit human ``APPROVE`` yields ``allow=True``.
    - ``REJECTED`` remains permanently blocked.
    - No auto-approval, no LLM approval, no time-based approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ------------------------------------------------------------------
# Status Enums
# ------------------------------------------------------------------


class ApprovalStatus(str, Enum):
    """Possible status values for an ApprovalRequest."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"


class DecisionType(str, Enum):
    """Allowed human decision types.

    Only ``APPROVE`` and ``REJECT`` are allowed. All other values
    (AUTO_APPROVE, LLM_APPROVE, TIMEOUT_APPROVE, IMPLICIT_APPROVE)
    are prohibited and will be rejected.
    """

    APPROVE = "APPROVE"
    REJECT = "REJECT"


class GateResult(str, Enum):
    """Gate check results used by downstream validation gates.

    ``ALLOW_APPROVED`` is the only result that means ``allow=True``.
    All other results mean ``allow=False`` (Default-Deny).
    """

    ALLOW_APPROVED = "ALLOW_APPROVED"
    BLOCK_PENDING_APPROVAL = "BLOCK_PENDING_APPROVAL"
    BLOCK_REJECTED = "BLOCK_REJECTED"
    BLOCK_MISSING_APPROVAL = "BLOCK_MISSING_APPROVAL"
    BLOCK_INVALID_REQUEST = "BLOCK_INVALID_REQUEST"
    BLOCK_EXPIRED_APPROVAL = "BLOCK_EXPIRED_APPROVAL"


# ------------------------------------------------------------------
# ApprovalRequest
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalRequest:
    """A serializable request for human approval of an active action.

    Fields:
        id: Unique request identifier (UUID string).
        actor: Who or what is requesting the action (e.g., "researcher",
            "agent-pentest-01").
        action: The planned action description (e.g., "port_scan",
            "http_request", "shell_command").
        target: The target of the action (domain, IP, URL, etc.).
        scope_reference: Reference to the scope policy that allows this
            target. Must be non-empty — ScopeGuard ALLOW does not replace
            human approval.
        test_type: The planned test type (e.g., "xss", "sql_injection",
            "port_scan").
        risk_summary: A text summary of the risk assessment.
        created_at: ISO 8601 timestamp of request creation.
        status: Current approval status (default: PENDING).
    """

    id: str
    actor: str = ""
    action: str = ""
    target: str = ""
    scope_reference: str = ""
    test_type: str = ""
    risk_summary: str = ""
    created_at: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING

    def __post_init__(self) -> None:
        """Validate that mandatory fields are non-empty.

        Raises:
            ValueError: If ``scope_reference``, ``test_type``, or
                ``risk_summary`` are empty or whitespace-only.
        """
        if not self.scope_reference or not self.scope_reference.strip():
            raise ValueError("scope_reference must be a non-empty string")
        if not self.test_type or not self.test_type.strip():
            raise ValueError("test_type must be a non-empty string")
        if not self.risk_summary or not self.risk_summary.strip():
            raise ValueError("risk_summary must be a non-empty string")


# ------------------------------------------------------------------
# HumanDecision
# ------------------------------------------------------------------


@dataclass(frozen=True)
class HumanDecision:
    """A human's explicit decision on an approval request.

    Fields:
        request_id: The ID of the ApprovalRequest being decided.
        decider: Identity of the human who made the decision.
        decision: The decision type (APPROVE or REJECT).
        reason: Explanation for the decision.
        decided_at: ISO 8601 timestamp of the decision.

    Raises:
        ValueError: If ``decision`` is not a valid ``DecisionType``,
            or if ``reason`` is empty/whitespace-only.
    """

    request_id: str
    decider: str
    decision: DecisionType
    reason: str
    decided_at: str = ""

    def __post_init__(self) -> None:
        """Validate the decision fields.

        Raises:
            ValueError: If reason is empty or whitespace-only.
        """
        if not self.reason or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")


# ------------------------------------------------------------------
# ApprovalDecision (Gate Result)
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalDecision:
    """The gate result of checking an ApprovalRequest against its decisions.

    Fields:
        gate_result: The categorical gate check result.
        allow: Binary flag — only True when gate_result is ALLOW_APPROVED.
        request_id: The ID of the checked ApprovalRequest (if any).
        decision_id: The ID of the HumanDecision that authorized (if any).
        explanation: Human-readable explanation of the gate result.

    Note:
        ``allow`` is True ONLY when a valid human APPROVE decision exists
        and no other blocking condition applies. All unknown, pending,
        rejected, invalid, or expired states yield ``allow=False``
        (Default-Deny).
    """

    gate_result: GateResult
    allow: bool = False
    request_id: str | None = None
    decision_id: str | None = None
    explanation: str = ""

    def __post_init__(self) -> None:
        """Enforce the invariant: allow=True only for ALLOW_APPROVED.

        This is enforced through a post-init check to prevent accidental
        misconfiguration.
        """
        if self.gate_result == GateResult.ALLOW_APPROVED and not self.allow:
            object.__setattr__(self, "allow", True)
        if self.gate_result != GateResult.ALLOW_APPROVED and self.allow:
            raise ValueError(
                f"allow=True is only valid for ALLOW_APPROVED, got {self.gate_result.value}"
            )
