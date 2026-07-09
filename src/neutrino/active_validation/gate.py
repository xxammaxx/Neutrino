"""ActiveValidationGate — the core gate engine for Issue #14.

This module implements the Active-Validation-Gate as a deterministic,
fail-closed orchestrator. It evaluates an ``ActiveValidationIntent``
against three mandatory safety checks:

    1. **Human Approval** (from #4): Is there a valid, approved
       ``ApprovalRequest``?
    2. **Scope Match**: Do the intent's scope metadata (target,
       scope_reference, test_type) match the stored approval?
    3. **ScopeGuard**: Does ScopeGuard ALLOW the target?

Only when ALL three checks pass AND auditing succeeds does the gate
return ``ALLOW_APPROVED_IN_SCOPE`` with ``allow=True``.

Key invariants:
    - Default-Deny: ``allow=False`` unless all checks pass.
    - Fail-closed: Unknown states, invalid intents, audit failures → BLOCK.
    - Deterministic: Same inputs always yield the same decision.
    - No execution: The gate decides ONLY. It never performs HTTP, DNS,
      shell, exploits, or any network I/O.
    - No bypass: No force, override, admin, auto-approve, LLM-approve,
      time-approve, or lab-auto-approve paths exist.

Dependencies (all injected — no global state):
    - ``ApprovalWorkflow`` — for ``check_approval()``
    - ``HumanApprovalRepository`` — for loading approval metadata
    - ``ScopeGuard`` — for ``check_target()``
    - ``ScopePolicy`` — for ScopeGuard evaluation
    - ``AuditLogWriter`` — JSONL audit (required)
    - ``AuditEventRepository`` — SQLite audit (required)
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from neutrino.active_validation.models import (
    ActiveValidationGateDecision,
    ActiveValidationIntent,
    ReasonCode,
)
from neutrino.approval.models import (
    ApprovalDecision,
    GateResult,
)

if TYPE_CHECKING:
    from neutrino.approval.workflow import ApprovalWorkflow
    from neutrino.audit.models import AuditLogEvent
    from neutrino.audit.writer import AuditLogWriter
    from neutrino.models.entities import AuditEventCreate
    from neutrino.models.policy import ScopePolicy
    from neutrino.scopeguard.guard import ScopeGuard
    from neutrino.storage.repositories.audit_events import AuditEventRepository
    from neutrino.storage.repositories.human_approvals import HumanApprovalRepository


# ------------------------------------------------------------------
# ActiveValidationGate
# ------------------------------------------------------------------


class ActiveValidationGate:
    """Deterministic, fail-closed gate for active validation actions.

    Evaluates an ``ActiveValidationIntent`` against Human Approval,
    Scope metadata match, and ScopeGuard, and returns a binary
    ``ActiveValidationGateDecision`` with ``allow=True`` only when
    all checks pass.

    Usage::

        gate = ActiveValidationGate(
            approval_workflow=wf,
            approval_repo=repo,
            scope_guard=guard,
            scope_policy=policy,
            audit_writer=jsonl_writer,
            audit_repo=sqlite_repo,
        )
        decision = gate.evaluate(intent)
        if decision.allow:
            ...  # executor may proceed (future #19)
        else:
            ...  # blocked — decision.explanation explains why
    """

    def __init__(
        self,
        approval_workflow: ApprovalWorkflow,
        approval_repo: HumanApprovalRepository,
        scope_guard: ScopeGuard,
        scope_policy: ScopePolicy | None,
        audit_writer: AuditLogWriter | None,
        audit_repo: AuditEventRepository | None,
    ) -> None:
        self._approval_workflow = approval_workflow
        self._approval_repo = approval_repo
        self._scope_guard = scope_guard
        self._scope_policy = scope_policy
        self._audit_writer = audit_writer
        self._audit_repo = audit_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        intent: ActiveValidationIntent,
        *,
        timestamp: str | None = None,
    ) -> ActiveValidationGateDecision:
        """Evaluate an ActiveValidationIntent and return a gate decision.

        Order of checks (fail-closed — first failure blocks immediately):
            1. Intent validation
            2. Approval check (via ``ApprovalWorkflow.check_approval()``)
            3. Scope metadata match (intent vs stored ApprovalRequest)
            4. ScopeGuard check (``ScopeGuard.check_target()``)
            5. Audit all decisions; audit failure → BLOCK_AUDIT_FAILED

        Args:
            intent: The validated ActiveValidationIntent to evaluate.
            timestamp: Optional ISO 8601 timestamp for audit.

        Returns:
            An ActiveValidationGateDecision with ``allow=True`` only
            when ALL checks pass.

        Note:
            This method is purely evaluative. It never:
            - Makes HTTP requests
            - Resolves DNS
            - Executes shell commands
            - Runs attack tooling
            - Modifies any persistent state beyond auditing
        """
        if timestamp is None:
            timestamp = datetime.now(UTC).isoformat()

        approval_request_id = intent.approval_request_id

        # ---------------------------------------------------------------
        # Step 1: Approval check
        # ---------------------------------------------------------------
        approval_decision: ApprovalDecision = self._approval_workflow.check_approval(
            approval_request_id, timestamp=timestamp
        )

        # Map GateResult to ReasonCode
        if approval_decision.gate_result == GateResult.BLOCK_MISSING_APPROVAL:
            return self._block(
                ReasonCode.BLOCK_MISSING_APPROVAL,
                intent,
                f"ApprovalRequest '{approval_request_id}' not found",
                timestamp=timestamp,
            )

        if approval_decision.gate_result == GateResult.BLOCK_PENDING_APPROVAL:
            return self._block(
                ReasonCode.BLOCK_PENDING_APPROVAL,
                intent,
                f"ApprovalRequest '{approval_request_id}' is PENDING",
                timestamp=timestamp,
            )

        if approval_decision.gate_result == GateResult.BLOCK_REJECTED:
            return self._block(
                ReasonCode.BLOCK_REJECTED_APPROVAL,
                intent,
                f"ApprovalRequest '{approval_request_id}' has been REJECTED",
                timestamp=timestamp,
            )

        # BLOCK_EXPIRED_APPROVAL or BLOCK_INVALID_REQUEST
        if approval_decision.gate_result not in (GateResult.ALLOW_APPROVED,):
            return self._block(
                ReasonCode.BLOCK_INVALID_APPROVAL,
                intent,
                f"ApprovalRequest '{approval_request_id}' has status "
                f"'{approval_decision.gate_result.value}'",
                timestamp=timestamp,
            )

        # At this point: approval_decision.gate_result == ALLOW_APPROVED

        # ---------------------------------------------------------------
        # Step 2: Load approval metadata for scope matching
        # ---------------------------------------------------------------
        stored = self._approval_repo.get(approval_request_id)
        if stored is None:
            return self._block(
                ReasonCode.BLOCK_INVALID_APPROVAL,
                intent,
                f"ApprovalRequest '{approval_request_id}' approved but "
                f"metadata not found in repository",
                timestamp=timestamp,
            )

        # ---------------------------------------------------------------
        # Step 3: Scope metadata match
        # ---------------------------------------------------------------
        # Normalize for deterministic comparison
        intent_scope_ref = _normalize(intent.scope_reference)
        stored_scope_ref = _normalize(stored.scope_reference)
        intent_target = _normalize(intent.target)
        stored_target = _normalize(stored.target)
        intent_test_type = _normalize(intent.test_type)
        stored_test_type = _normalize(stored.test_type)

        mismatches: list[str] = []
        if intent_scope_ref != stored_scope_ref:
            mismatches.append(
                f"scope_reference mismatch: intent={intent_scope_ref!r} "
                f"vs stored={stored_scope_ref!r}"
            )
        if intent_target != stored_target:
            mismatches.append(
                f"target mismatch: intent={intent_target!r} vs stored={stored_target!r}"
            )
        if intent_test_type != stored_test_type:
            mismatches.append(
                f"test_type mismatch: intent={intent_test_type!r} vs stored={stored_test_type!r}"
            )

        if mismatches:
            return self._block(
                ReasonCode.BLOCK_SCOPE_MISMATCH,
                intent,
                f"Scope metadata mismatch: {'; '.join(mismatches)}",
                timestamp=timestamp,
            )

        # ---------------------------------------------------------------
        # Step 4: ScopeGuard check
        # ---------------------------------------------------------------
        scope_decision = self._scope_guard.check_target(intent.target, self._scope_policy)

        if not scope_decision.is_allowed:
            return self._block(
                ReasonCode.BLOCK_SCOPE_DENIED,
                intent,
                f"ScopeGuard DENY: {scope_decision.explanation}",
                timestamp=timestamp,
                scope_decision=scope_decision,
            )

        # ---------------------------------------------------------------
        # Step 5: ALLOW — all checks passed
        # ---------------------------------------------------------------
        return self._allow(intent, timestamp=timestamp, scope_decision=scope_decision)

    # ------------------------------------------------------------------
    # Internal: Decision builders (each handles audit)
    # ------------------------------------------------------------------

    def _block(
        self,
        reason: ReasonCode,
        intent: ActiveValidationIntent,
        explanation: str,
        *,
        timestamp: str,
        scope_decision: object | None = None,
    ) -> ActiveValidationGateDecision:
        """Create a blocking decision and audit it.

        If auditing fails, the decision is overridden to
        ``BLOCK_AUDIT_FAILED``.
        """
        decision = ActiveValidationGateDecision(
            reason=reason,
            intent_id=intent.id,
            target=intent.target,
            approval_request_id=intent.approval_request_id,
            scope_reference=intent.scope_reference,
            explanation=explanation,
            timestamp=timestamp,
            allow=False,
        )

        audit_result = self._audit(decision, scope_decision=scope_decision)
        if audit_result is not None:
            # Audit succeeded — attach the audit event ID
            object.__setattr__(decision, "audit_event_id", audit_result)
        else:
            # Audit failed — override to BLOCK_AUDIT_FAILED
            decision = ActiveValidationGateDecision(
                reason=ReasonCode.BLOCK_AUDIT_FAILED,
                intent_id=intent.id,
                target=intent.target,
                approval_request_id=intent.approval_request_id,
                scope_reference=intent.scope_reference,
                explanation=f"Audit failed during BLOCK ({reason.value}): {explanation}",
                timestamp=timestamp,
                allow=False,
            )

        return decision

    def _allow(
        self,
        intent: ActiveValidationIntent,
        *,
        timestamp: str,
        scope_decision: object | None = None,
    ) -> ActiveValidationGateDecision:
        """Create an allow decision and audit it.

        If auditing fails, the decision is overridden to
        ``BLOCK_AUDIT_FAILED``.
        """
        decision = ActiveValidationGateDecision(
            reason=ReasonCode.ALLOW_APPROVED_IN_SCOPE,
            intent_id=intent.id,
            target=intent.target,
            approval_request_id=intent.approval_request_id,
            scope_reference=intent.scope_reference,
            explanation=(
                f"Active validation approved: target={intent.target!r}, "
                f"test_type={intent.test_type!r}, "
                f"approval_request={intent.approval_request_id!r}"
            ),
            timestamp=timestamp,
            allow=True,
        )

        audit_result = self._audit(decision, scope_decision=scope_decision)
        if audit_result is not None:
            object.__setattr__(decision, "audit_event_id", audit_result)
        else:
            decision = ActiveValidationGateDecision(
                reason=ReasonCode.BLOCK_AUDIT_FAILED,
                intent_id=intent.id,
                target=intent.target,
                approval_request_id=intent.approval_request_id,
                scope_reference=intent.scope_reference,
                explanation="Audit failed during ALLOW — action blocked",
                timestamp=timestamp,
                allow=False,
            )

        return decision

    # ------------------------------------------------------------------
    # Internal: Audit
    # ------------------------------------------------------------------

    def _audit(
        self,
        decision: ActiveValidationGateDecision,
        scope_decision: object | None = None,
    ) -> str | None:
        """Audit the gate decision via JSONL and SQLite.

        Returns:
            The audit event ID string if at least one sink succeeded,
            or None if all configured sinks failed (or none configured).

        Note:
            If any configured audit sink fails, the audit is considered
            FAILED and this method returns None, triggering
            ``BLOCK_AUDIT_FAILED``.
            If neither sink is configured, also returns None (block).
        """
        has_any_sink = self._audit_writer is not None or self._audit_repo is not None
        if not has_any_sink:
            return None

        audit_id = str(uuid.uuid4())
        audit_event_data = _build_audit_payload(decision, scope_decision)

        writer_ok = True
        repo_ok = True

        # JSONL
        if self._audit_writer is not None:
            try:
                event = _make_jsonl_event(
                    audit_id=audit_id,
                    decision=decision,
                    event_data=audit_event_data,
                )
                self._audit_writer.append(event)
            except Exception:
                writer_ok = False

        # SQLite
        if self._audit_repo is not None:
            try:
                create_data = _make_sqlite_event(
                    audit_id=audit_id,
                    decision=decision,
                    event_data=audit_event_data,
                )
                self._audit_repo.append(create_data)
            except Exception:
                repo_ok = False

        # If any configured sink failed, audit is FAILED
        if (self._audit_writer is not None and not writer_ok) or (
            self._audit_repo is not None and not repo_ok
        ):
            return None

        return audit_id


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _normalize(value: str) -> str:
    """Normalize a string for deterministic comparison.

    Strips whitespace and lowercases. Does NOT perform DNS, URL parsing,
    or network I/O.
    """
    return value.strip().lower()


def _build_audit_payload(
    decision: ActiveValidationGateDecision,
    scope_decision: object | None = None,
) -> dict[str, object]:
    """Build the audit event payload dictionary."""
    from neutrino.scopeguard.models import ScopeDecision

    payload: dict[str, object] = {
        "intent_id": decision.intent_id,
        "approval_request_id": decision.approval_request_id,
        "target": decision.target,
        "scope_reference": decision.scope_reference,
        "reason": decision.reason.value,
        "allow": decision.allow,
        "explanation": decision.explanation,
    }

    if scope_decision is not None and isinstance(scope_decision, ScopeDecision):
        payload["scope_decision"] = {
            "status": scope_decision.status.value,
            "reason": scope_decision.reason.value,
            "matched_entry": scope_decision.matched_entry,
            "policy_source": scope_decision.policy_source,
            "explanation": scope_decision.explanation,
        }

    return payload


def _make_jsonl_event(
    audit_id: str,
    decision: ActiveValidationGateDecision,
    event_data: dict[str, object],
) -> AuditLogEvent:
    """Build an AuditLogEvent for the JSONL writer."""
    from neutrino.audit.models import AuditLogEvent

    return AuditLogEvent(
        id=audit_id,
        actor="active_validation_gate",
        action="evaluate_active_validation",
        target=decision.target,
        decision="allow" if decision.allow else "block",
        timestamp=decision.timestamp,
        event=event_data,
    )


def _make_sqlite_event(
    audit_id: str,
    decision: ActiveValidationGateDecision,
    event_data: dict[str, object],
) -> AuditEventCreate:
    """Build an AuditEventCreate for the SQLite audit repository."""
    from neutrino.models.entities import AuditEventCreate

    return AuditEventCreate(
        id=audit_id,
        actor="active_validation_gate",
        action="evaluate_active_validation",
        target=decision.target,
        decision="allow" if decision.allow else "block",
        event_json=json.dumps(event_data),
        timestamp=decision.timestamp,
    )
