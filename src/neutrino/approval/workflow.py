"""ApprovalWorkflow — the core Human Authorization Workflow service.

This module implements the #4 Human Authorization Workflow as a
deterministic, local service. It manages:

    1. ``create_request()`` — Create a new ApprovalRequest as PENDING.
    2. ``record_decision()`` — Record a human's explicit APPROVE/REJECT.
    3. ``check_approval()`` — Check the gate result for a given request.

Key invariants:
    - All requests start as PENDING.
    - Only explicit human APPROVE yields ALLOW_APPROVED.
    - REJECTED remains permanently blocked.
    - No auto-approval, no LLM approval, no time-based approval.
    - Every state change is audited.

Uses the existing ``HumanApprovalRepository`` for persistence and
``AuditEventRepository`` / ``AuditLogWriter`` for audit trails.
All dependencies are injected — no global state.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from neutrino.approval.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    DecisionType,
    GateResult,
    HumanDecision,
)

if TYPE_CHECKING:
    from neutrino.audit.models import AuditLogEvent
    from neutrino.audit.writer import AuditLogWriter
    from neutrino.models.entities import (
        AuditEventCreate,
        HumanApprovalCreate,
        HumanApprovalUpdate,
    )
    from neutrino.storage.repositories.audit_events import AuditEventRepository
    from neutrino.storage.repositories.human_approvals import HumanApprovalRepository


# ------------------------------------------------------------------
# ApprovalWorkflow
# ------------------------------------------------------------------


class ApprovalWorkflow:
    """Core Human Authorization Workflow service.

    Orchestrates the creation, decision, and gate-check of approval
    requests. All operations are deterministic — no randomness, no
    auto-approval, no time-based logic inside the core.

    Args:
        approval_repo: Repository for persisting ApprovalRequests
            (via the existing HumanApproval model).
        audit_repo: Optional SQLite AuditEventRepository for structured
            audit events.
        audit_writer: Optional JSONL AuditLogWriter for file-based
            audit events.
    """

    def __init__(
        self,
        approval_repo: HumanApprovalRepository,
        audit_repo: AuditEventRepository | None = None,
        audit_writer: AuditLogWriter | None = None,
    ) -> None:
        self._approval_repo = approval_repo
        self._audit_repo = audit_repo
        self._audit_writer = audit_writer

    # ------------------------------------------------------------------
    # 1. Create Request
    # ------------------------------------------------------------------

    def create_request(
        self,
        actor: str,
        action: str,
        target: str,
        scope_reference: str,
        test_type: str,
        risk_summary: str,
        *,
        request_id: str | None = None,
        timestamp: str | None = None,
    ) -> ApprovalRequest:
        """Create a new ApprovalRequest in PENDING status.

        Args:
            actor: Who or what is requesting the action.
            action: The planned action description.
            target: The target of the action.
            scope_reference: Scope policy reference.
            test_type: Planned test type.
            risk_summary: Risk assessment summary.
            request_id: Optional request UUID (auto-generated if None).
            timestamp: Optional ISO 8601 timestamp (auto-generated if None).

        Returns:
            The created ApprovalRequest.

        Raises:
            ValueError: If required fields are empty.
        """
        if request_id is None:
            request_id = str(uuid.uuid4())
        if timestamp is None:
            timestamp = datetime.now(UTC).isoformat()

        # Validate via the domain model
        request = ApprovalRequest(
            id=request_id,
            actor=actor,
            action=action,
            target=target,
            scope_reference=scope_reference,
            test_type=test_type,
            risk_summary=risk_summary,
            created_at=timestamp,
            status=ApprovalStatus.PENDING,
        )

        # Persist via HumanApprovalRepository
        create_data: HumanApprovalCreate = self._build_create_data(request)
        self._approval_repo.create(create_data)

        # Audit: request created
        self._audit(
            actor="approval_workflow",
            action="approval_request_created",
            target=request_id,
            decision="pending",
            event_data={
                "actor": actor,
                "action": action,
                "target": target,
                "scope_reference": scope_reference,
                "test_type": test_type,
                "risk_summary": risk_summary,
                "request_id": request_id,
            },
            timestamp=timestamp,
        )

        return request

    # ------------------------------------------------------------------
    # 2. Record Decision
    # ------------------------------------------------------------------

    def record_decision(
        self,
        request_id: str,
        decider: str,
        decision: DecisionType,
        reason: str,
        *,
        timestamp: str | None = None,
    ) -> HumanDecision:
        """Record a human's explicit decision on an approval request.

        Args:
            request_id: The ID of the ApprovalRequest being decided.
            decider: Identity of the human who made the decision.
            decision: APPROVE or REJECT (must be a valid DecisionType).
            reason: Explanation for the decision (must be non-empty).
            timestamp: Optional ISO 8601 timestamp (auto-generated if None).

        Returns:
            The recorded HumanDecision.

        Raises:
            ValueError: If the request does not exist, the request is
                not in PENDING status, or the decision is invalid.
            EntityNotFound: If ``request_id`` does not exist.
        """
        if timestamp is None:
            timestamp = datetime.now(UTC).isoformat()

        # Validate decision type (paranoid check — the enum already does this)
        if decision not in (DecisionType.APPROVE, DecisionType.REJECT):
            raise ValueError(f"Invalid decision '{decision}'. Only APPROVE and REJECT are allowed.")

        # Load existing request
        existing = self._approval_repo.get(request_id)
        if existing is None:
            self._audit(
                actor="approval_workflow",
                action="approval_decision_blocked",
                target=request_id,
                decision="block_missing_request",
                event_data={
                    "decider": decider,
                    "decision": decision.value,
                    "reason": reason,
                },
                timestamp=timestamp,
            )
            raise ValueError(f"ApprovalRequest '{request_id}' not found")

        # Only PENDING requests can be decided
        if existing.decision != ApprovalStatus.PENDING.value:
            self._audit(
                actor="approval_workflow",
                action="approval_decision_blocked",
                target=request_id,
                decision="block_not_pending",
                event_data={
                    "current_status": existing.decision,
                    "decider": decider,
                    "decision": decision.value,
                    "reason": reason,
                },
                timestamp=timestamp,
            )
            raise ValueError(
                f"ApprovalRequest '{request_id}' is not PENDING (status: {existing.decision})"
            )

        # Map decision to status
        new_status = (
            ApprovalStatus.APPROVED if decision == DecisionType.APPROVE else ApprovalStatus.REJECTED
        )

        # Update via repository
        update_data: HumanApprovalUpdate = _build_update_data(
            decision=new_status.value, reason=reason, actor=decider
        )
        self._approval_repo.update(request_id, update_data)

        human_decision = HumanDecision(
            request_id=request_id,
            decider=decider,
            decision=decision,
            reason=reason,
            decided_at=timestamp,
        )

        # Audit: decision recorded
        self._audit(
            actor="approval_workflow",
            action="approval_decision_recorded",
            target=request_id,
            decision=new_status.value,
            event_data={
                "decider": decider,
                "decision": decision.value,
                "reason": reason,
                "status": new_status.value,
            },
            timestamp=timestamp,
        )

        return human_decision

    # ------------------------------------------------------------------
    # 3. Check Approval (Gate)
    # ------------------------------------------------------------------

    def check_approval(
        self,
        request_id: str,
        *,
        timestamp: str | None = None,
    ) -> ApprovalDecision:
        """Check the gate result for a given approval request.

        This is the core gate function. It returns an ``ApprovalDecision``
        with a binary ``allow`` flag and a categorical ``gate_result``.

        Default-Deny: Only an explicit human APPROVE yields allow=True.
        PENDING, REJECTED, missing, invalid, and EXPIRED all block.

        Args:
            request_id: The ID of the ApprovalRequest to check.
            timestamp: Optional ISO 8601 timestamp (auto-generated if None).

        Returns:
            An ApprovalDecision with allow=True only for APPROVED requests.
        """
        if timestamp is None:
            timestamp = datetime.now(UTC).isoformat()

        existing = self._approval_repo.get(request_id)

        # Missing request
        if existing is None:
            result = self._block(
                GateResult.BLOCK_MISSING_APPROVAL,
                request_id,
                f"ApprovalRequest '{request_id}' not found",
                timestamp=timestamp,
            )
            return result

        status = existing.decision

        # APPROVED
        if status == ApprovalStatus.APPROVED.value:
            result = ApprovalDecision(
                gate_result=GateResult.ALLOW_APPROVED,
                allow=True,
                request_id=request_id,
                decision_id=existing.id,
                explanation=(
                    f"ApprovalRequest '{request_id}' has been APPROVED by '{existing.actor}'"
                ),
            )
            self._audit(
                actor="approval_workflow",
                action="approval_gate_check",
                target=request_id,
                decision="allow",
                event_data={
                    "gate_result": GateResult.ALLOW_APPROVED.value,
                    "status": status,
                },
                timestamp=timestamp,
            )
            return result

        # PENDING
        if status == ApprovalStatus.PENDING.value:
            return self._block(
                GateResult.BLOCK_PENDING_APPROVAL,
                request_id,
                f"ApprovalRequest '{request_id}' is still PENDING",
                timestamp=timestamp,
            )

        # REJECTED
        if status == ApprovalStatus.REJECTED.value:
            return self._block(
                GateResult.BLOCK_REJECTED,
                request_id,
                f"ApprovalRequest '{request_id}' has been REJECTED",
                timestamp=timestamp,
            )

        # EXPIRED
        if status == ApprovalStatus.EXPIRED.value:
            return self._block(
                GateResult.BLOCK_EXPIRED_APPROVAL,
                request_id,
                f"ApprovalRequest '{request_id}' has EXPIRED",
                timestamp=timestamp,
            )

        # Unknown / invalid — BLOCK_INVALID_REQUEST
        return self._block(
            GateResult.BLOCK_INVALID_REQUEST,
            request_id,
            f"ApprovalRequest '{request_id}' has unknown status '{status}'",
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _block(
        self,
        gate_result: GateResult,
        request_id: str | None,
        explanation: str,
        *,
        timestamp: str,
    ) -> ApprovalDecision:
        """Create a blocking ApprovalDecision and audit the block."""
        decision = ApprovalDecision(
            gate_result=gate_result,
            allow=False,
            request_id=request_id,
            explanation=explanation,
        )
        self._audit(
            actor="approval_workflow",
            action="approval_gate_check",
            target=request_id or "unknown",
            decision="block",
            event_data={
                "gate_result": gate_result.value,
                "explanation": explanation,
            },
            timestamp=timestamp,
        )
        return decision

    def _build_create_data(self, request: ApprovalRequest) -> HumanApprovalCreate:
        """Build a ``HumanApprovalCreate`` from an ``ApprovalRequest``."""
        from neutrino.models.entities import HumanApprovalCreate

        return HumanApprovalCreate(
            id=request.id,
            actor=request.actor,
            decision=request.status.value,
            reason=json.dumps(
                {
                    "action": request.action,
                    "target": request.target,
                    "scope_reference": request.scope_reference,
                    "test_type": request.test_type,
                    "risk_summary": request.risk_summary,
                }
            ),
            action=request.action,
            target=request.target,
            scope_reference=request.scope_reference,
            test_type=request.test_type,
            risk_summary=request.risk_summary,
        )

    def _audit(
        self,
        actor: str,
        action: str,
        target: str,
        decision: str,
        event_data: dict,
        timestamp: str,
    ) -> None:
        """Record an audit event via both SQLite and JSONL if available."""
        # SQLite AuditEventRepository
        if self._audit_repo is not None:
            audit_id = str(uuid.uuid4())
            audit_create = _make_audit_event_create(
                event_id=audit_id,
                actor=actor,
                action=action,
                target=target,
                decision=decision,
                event_data=event_data,
                timestamp=timestamp,
            )
            self._audit_repo.append(audit_create)

        # JSONL AuditLogWriter
        if self._audit_writer is not None:
            audit_event = _make_audit_log_event(
                actor=actor,
                action=action,
                target=target,
                decision=decision,
                event_data=event_data,
                timestamp=timestamp,
            )
            self._audit_writer.append(audit_event)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _make_audit_event_create(
    event_id: str,
    actor: str,
    action: str,
    target: str,
    decision: str,
    event_data: dict,
    timestamp: str,
) -> AuditEventCreate:
    """Build an ``AuditEventCreate`` for the SQLite audit repository."""
    from neutrino.models.entities import AuditEventCreate

    return AuditEventCreate(
        id=event_id,
        actor=actor,
        action=action,
        target=target,
        decision=decision,
        event_json=json.dumps(event_data),
        timestamp=timestamp,
    )


def _make_audit_log_event(
    actor: str,
    action: str,
    target: str,
    decision: str,
    event_data: dict,
    timestamp: str,
) -> AuditLogEvent:
    """Build an ``AuditLogEvent`` for the JSONL writer."""
    from neutrino.audit.models import AuditLogEvent

    return AuditLogEvent(
        actor=actor,
        action=action,
        target=target,
        decision=decision,
        timestamp=timestamp,
        event=event_data,
    )


def _build_update_data(
    decision: str,
    reason: str,
    actor: str,
) -> HumanApprovalUpdate:
    """Build a ``HumanApprovalUpdate`` with the given decision and reason."""
    from neutrino.models.entities import HumanApprovalUpdate

    return HumanApprovalUpdate(
        decision=decision,
        reason=reason,
        actor=actor,
    )
