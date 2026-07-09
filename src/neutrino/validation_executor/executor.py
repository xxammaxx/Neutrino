"""Validation Recipe Executor — Issue #19.

Deterministic, fail-closed executor for validated ``ValidationRecipe``
objects. Orchestrates safety gates (ActiveValidationGate, ScopeGuard,
Human Approval, Audit) and delegates to safe local-only step handlers.

Safety invariants:
    - Dry-run is the default (``dry_run=True`` in ``ValidationExecutionRequest``).
    - Recipe is re-validated with ``validate_recipe()`` before any step.
    - Every step passes through ``ActiveValidationGate.evaluate()``.
    - Gate DENY → step is BLOCKED and audited (never executed).
    - Gate ALLOW + dry_run → step is SKIPPED_DRY_RUN and audited.
    - Gate ALLOW + not dry_run → handler is dispatched.
    - Every step outcome is audited.
    - Audit failure → BLOCKED (fail-closed, never allow).
    - No ``force``, ``skip_gate``, ``skip_scopeguard``, ``skip_approval``,
      ``allow_external``, or ``unsafe`` override fields exist.
    - No shell, subprocess, DNS, external HTTP, or socket imports.
    - Deterministic: same inputs → same results.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from neutrino.active_validation import (
    ActiveValidationGate,
    ActiveValidationIntent,
)
from neutrino.audit import AuditLogEvent, AuditLogWriter
from neutrino.validation_executor.handlers import get_handler
from neutrino.validation_executor.models import (
    ExecutionStatus,
    StepExecutionStatus,
    ValidationExecutionRequest,
    ValidationExecutionResult,
    ValidationStepResult,
)
from neutrino.validation_recipe import (
    ValidationStep,
    validate_recipe,
)

if TYPE_CHECKING:
    from neutrino.approval import ApprovalWorkflow
    from neutrino.models.policy import ScopePolicy
    from neutrino.scopeguard import ScopeGuard


class ValidationRecipeExecutor:
    """Deterministic, fail-closed executor for ``ValidationRecipe``.

    This class orchestrates safety gates and step handlers. It does NOT
    replace ``ActiveValidationGate``, ``ScopeGuard``, ``ApprovalWorkflow``,
    or ``AuditLogWriter`` — it composes them.

    Usage::

        executor = ValidationRecipeExecutor(
            active_validation_gate=gate,
            scope_guard=scope_guard,
            scope_policy=policy,
            approval_workflow=approval,
            audit_writer=audit_writer,
        )

        request = ValidationExecutionRequest(
            request_id="req-001",
            recipe=recipe,
            approval_request_ids_by_step={...},
        )

        result = executor.execute(request)

    Constructor args:
        active_validation_gate: The gate from #14.
        scope_guard: ScopeGuard instance.
        scope_policy: The ScopePolicy to validate against.
        approval_workflow: The ApprovalWorkflow from #4.
        audit_writer: The AuditLogWriter for immutable audit trails.
    """

    def __init__(
        self,
        active_validation_gate: ActiveValidationGate,
        scope_guard: ScopeGuard,
        scope_policy: ScopePolicy,
        approval_workflow: ApprovalWorkflow,
        audit_writer: AuditLogWriter,
    ) -> None:
        self._gate = active_validation_gate
        self._scope_guard = scope_guard
        self._scope_policy = scope_policy
        self._approval_workflow = approval_workflow
        self._audit_writer = audit_writer

    # --------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------

    def execute(
        self,
        request: ValidationExecutionRequest,
    ) -> ValidationExecutionResult:
        """Execute or plan a validation recipe.

        Fail-closed rules:
            - Invalid recipe (``validate_recipe`` fails) → entire execution BLOCKED.
            - Missing ``approval_request_id`` for a step → step BLOCKED.
            - ``gate.allow == False`` → step BLOCKED.
            - Unknown/unregistered step type → step BLOCKED (handler lookup raises).
            - Audit failure → fail-closed (exception propagates; caller must treat
              as execution failure).

        Args:
            request: The execution request with recipe and configuration.

        Returns:
            ``ValidationExecutionResult`` with per-step results and audit trail.
        """
        audit_trail: list[str] = []
        step_results: list[ValidationStepResult] = []

        # --- Phase 1: Recipe Validation ---
        validation = validate_recipe(request.recipe)

        if not validation.valid:
            audit_event_id = self._audit(
                actor="validation_recipe_executor",
                action="validate_recipe",
                target=validation.recipe_id or request.recipe.id,
                decision="blocked_invalid_recipe",
                payload={
                    "request_id": request.request_id,
                    "recipe_id": validation.recipe_id,
                    "reasons": [reason.value for reason in validation.reasons],
                    "errors": validation.errors,
                },
            )
            audit_trail.append(audit_event_id)

            return ValidationExecutionResult(
                request_id=request.request_id,
                recipe_id=validation.recipe_id,
                overall_status=ExecutionStatus.BLOCKED,
                step_results=[],
                audit_trail=audit_trail,
            )

        # --- Phase 2: Per-Step Execution ---
        for step in request.recipe.steps:
            try:
                step_result = self._execute_step(request, step)
            except Exception as exc:
                # Catch-all: any unhandled exception results in ERROR.
                # Attempt to audit the exception. If audit itself fails,
                # the step is still ERROR — audit_event_id remains None.
                error_audit_id = self._audit_safe(
                    request=request,
                    step=step,
                    status=StepExecutionStatus.ERROR,
                    decision="error_unhandled_exception",
                    payload={"error": str(exc)},
                )

                step_result = ValidationStepResult(
                    step_id=step.id,
                    step_type=step.step_type,
                    status=StepExecutionStatus.ERROR,
                    audit_event_id=error_audit_id,
                    error_message=str(exc),
                    evidence={},
                )

            if step_result.audit_event_id is not None:
                audit_trail.append(step_result.audit_event_id)
            step_results.append(step_result)

        # --- Phase 3: Aggregate ---
        overall_status = self._derive_overall_status(step_results)

        return ValidationExecutionResult(
            request_id=request.request_id,
            recipe_id=request.recipe.id,
            overall_status=overall_status,
            step_results=step_results,
            audit_trail=audit_trail,
        )

    # --------------------------------------------------------------
    # Internal: Step Execution
    # --------------------------------------------------------------

    def _execute_step(
        self,
        request: ValidationExecutionRequest,
        step: ValidationStep,
    ) -> ValidationStepResult:
        """Execute a single step through all safety gates."""

        # --- Gate 1: Approval Request ID ---
        approval_request_id = request.approval_request_ids_by_step.get(step.id)

        if not approval_request_id:
            audit_event_id = self._audit(
                actor="validation_recipe_executor",
                action="execute_step",
                target=step.target,
                decision="blocked_missing_approval_request_id",
                payload={
                    "request_id": request.request_id,
                    "recipe_id": request.recipe.id,
                    "step_id": step.id,
                    "step_type": step.step_type.value,
                },
            )

            return ValidationStepResult(
                step_id=step.id,
                step_type=step.step_type,
                status=StepExecutionStatus.BLOCKED,
                gate_decision=None,
                audit_event_id=audit_event_id,
                error_message="Missing approval_request_id for step",
                evidence={},
            )

        # --- Gate 2: Build Intent + ActiveValidationGate ---
        intent = self._build_intent(
            request=request,
            step=step,
            approval_request_id=approval_request_id,
        )

        gate_decision = self._gate.evaluate(intent)

        if gate_decision.allow is False:
            audit_event_id = self._audit(
                actor="validation_recipe_executor",
                action="execute_step",
                target=step.target,
                decision="blocked_by_active_validation_gate",
                payload={
                    "request_id": request.request_id,
                    "recipe_id": request.recipe.id,
                    "step_id": step.id,
                    "step_type": step.step_type.value,
                    "gate_reason": gate_decision.reason.value,
                    "gate_audit_event_id": gate_decision.audit_event_id,
                    "gate_explanation": gate_decision.explanation,
                },
            )

            return ValidationStepResult(
                step_id=step.id,
                step_type=step.step_type,
                status=StepExecutionStatus.BLOCKED,
                gate_decision=gate_decision,
                audit_event_id=audit_event_id,
                error_message=gate_decision.explanation,
                evidence={},
            )

        # --- Gate 3: Dry-Run Check ---
        if request.dry_run:
            audit_event_id = self._audit(
                actor="validation_recipe_executor",
                action="execute_step",
                target=step.target,
                decision="skipped_dry_run",
                payload={
                    "request_id": request.request_id,
                    "recipe_id": request.recipe.id,
                    "step_id": step.id,
                    "step_type": step.step_type.value,
                    "gate_reason": gate_decision.reason.value,
                    "gate_audit_event_id": gate_decision.audit_event_id,
                },
            )

            return ValidationStepResult(
                step_id=step.id,
                step_type=step.step_type,
                status=StepExecutionStatus.SKIPPED_DRY_RUN,
                gate_decision=gate_decision,
                audit_event_id=audit_event_id,
                evidence={"planned": True, "dry_run": True},
            )

        # --- Phase 4: Handler Dispatch ---
        try:
            handler = get_handler(step.step_type)
        except ValueError as exc:
            # Unknown step type → BLOCKED
            audit_event_id = self._audit(
                actor="validation_recipe_executor",
                action="execute_step",
                target=step.target,
                decision="blocked_unknown_step_type",
                payload={
                    "request_id": request.request_id,
                    "recipe_id": request.recipe.id,
                    "step_id": step.id,
                    "step_type": step.step_type.value,
                    "error": str(exc),
                },
            )

            return ValidationStepResult(
                step_id=step.id,
                step_type=step.step_type,
                status=StepExecutionStatus.BLOCKED,
                gate_decision=gate_decision,
                audit_event_id=audit_event_id,
                error_message=str(exc),
                evidence={},
            )

        status, evidence, error_message = handler.execute(
            step,
            allowed_fixture_dir=request.allowed_fixture_dir,
            evidence_context=request.evidence_context,
        )

        # --- Audit handler outcome ---
        audit_event_id = self._audit(
            actor="validation_recipe_executor",
            action="execute_step",
            target=step.target,
            decision=status.value.lower(),
            payload={
                "request_id": request.request_id,
                "recipe_id": request.recipe.id,
                "step_id": step.id,
                "step_type": step.step_type.value,
                "gate_reason": gate_decision.reason.value,
                "gate_audit_event_id": gate_decision.audit_event_id,
                "evidence_keys": sorted(evidence.keys()),
                "error_message": error_message,
            },
        )

        return ValidationStepResult(
            step_id=step.id,
            step_type=step.step_type,
            status=status,
            gate_decision=gate_decision,
            audit_event_id=audit_event_id,
            error_message=error_message,
            evidence=evidence,
        )

    # --------------------------------------------------------------
    # Internal: Helpers
    # --------------------------------------------------------------

    def _build_intent(
        self,
        *,
        request: ValidationExecutionRequest,
        step: ValidationStep,
        approval_request_id: str,
    ) -> ActiveValidationIntent:
        """Build an ``ActiveValidationIntent`` from a recipe step.

        The intent ID is deterministic (UUID v5) so that the same
        recipe step in the same request always produces the same ID.
        """
        namespace = uuid.NAMESPACE_URL
        name = f"{request.request_id}:{request.recipe.id}:{step.id}"
        intent_id = str(uuid.uuid5(namespace, name))

        return ActiveValidationIntent(
            id=intent_id,
            actor=request.actor,
            action=f"validation_recipe.{step.step_type.value}",
            target=step.target,
            scope_reference=step.scope_reference,
            test_type=step.step_type.value,
            risk_summary=(
                f"Non-destructive validation step '{step.id}' from recipe '{request.recipe.id}'"
            ),
            approval_request_id=approval_request_id,
            created_at=datetime.now(UTC).isoformat(),
        )

    def _audit(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        decision: str,
        payload: dict[str, Any],
    ) -> str:
        """Write an audit event and return its ID.

        This method MUST succeed. If the audit writer is unavailable
        (disk full, permission error, etc.), an exception propagates
        and the caller must fail closed.
        """
        event = AuditLogEvent(
            actor=actor,
            action=action,
            target=target,
            decision=decision,
            event=payload,
        )
        written = self._audit_writer.append(event)
        return written.id

    def _audit_safe(
        self,
        *,
        request: ValidationExecutionRequest,
        step: ValidationStep,
        status: StepExecutionStatus,
        decision: str,
        payload: dict[str, Any],
    ) -> str | None:
        """Best-effort audit for exception paths.

        If this audit also fails, return ``None``. The step result
        remains ERROR/BLOCKED regardless.
        """
        try:
            return self._audit(
                actor="validation_recipe_executor",
                action="execute_step",
                target=step.target,
                decision=decision,
                payload={
                    "request_id": request.request_id,
                    "recipe_id": request.recipe.id,
                    "step_id": step.id,
                    "step_type": step.step_type.value,
                    "status": status.value,
                    **payload,
                },
            )
        except Exception:
            return None

    def _derive_overall_status(
        self,
        step_results: list[ValidationStepResult],
    ) -> ExecutionStatus:
        """Aggregate per-step results into an overall execution status.

        Rules:
            - Any ERROR → overall ERROR
            - Any BLOCKED → overall BLOCKED
            - Otherwise → COMPLETED
        """
        has_error = any(result.status == StepExecutionStatus.ERROR for result in step_results)
        if has_error:
            return ExecutionStatus.ERROR

        has_blocked = any(result.status == StepExecutionStatus.BLOCKED for result in step_results)
        if has_blocked:
            return ExecutionStatus.BLOCKED

        return ExecutionStatus.COMPLETED
