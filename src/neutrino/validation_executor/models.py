"""Validation Executor domain models — Issue #19.

This module defines all data models for the ValidationRecipeExecutor:
execution requests, per-step results, and overall execution results.

Key invariants:
    - ALL models use ``extra="forbid"`` (no bypass fields).
    - ALL models are ``frozen=True`` (immutable).
    - No ``force``, ``skip_gate``, ``skip_scopeguard``, ``skip_approval``,
      ``allow_external``, or ``unsafe`` override fields exist.
    - ``dry_run`` defaults to ``True``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Runtime imports needed for Pydantic field types
# ruff: noqa: TC001
from neutrino.active_validation import ActiveValidationGateDecision
from neutrino.validation_recipe import ValidationRecipe, ValidationStepType

# ------------------------------------------------------------------
# Status Enums
# ------------------------------------------------------------------


class StepExecutionStatus(StrEnum):
    """Per-step execution outcome."""

    PLANNED = "PLANNED"
    """Step was planned but will require manual execution."""

    BLOCKED = "BLOCKED"
    """Step was blocked by a safety gate (gate DENY, ScopeGuard DENY, etc.)."""

    SKIPPED_DRY_RUN = "SKIPPED_DRY_RUN"
    """Step was allowed by the gate but skipped because dry_run=True."""

    EXECUTED = "EXECUTED"
    """Step passed all gates and was executed by its handler."""

    ERROR = "ERROR"
    """Step execution failed with an unexpected error."""


class ExecutionStatus(StrEnum):
    """Overall execution outcome for a recipe run."""

    COMPLETED = "COMPLETED"
    """All steps completed successfully (PLANNED, SKIPPED_DRY_RUN, or EXECUTED)."""

    BLOCKED = "BLOCKED"
    """At least one step was BLOCKED. No ERROR steps."""

    ERROR = "ERROR"
    """At least one step resulted in ERROR."""


# ------------------------------------------------------------------
# Request Model
# ------------------------------------------------------------------


class ValidationExecutionRequest(BaseModel):
    """Request to execute or plan a validated ValidationRecipe.

    Safety defaults:
        - ``dry_run`` defaults to ``True`` (no real execution by default).
        - ``extra="forbid"`` blocks unknown bypass fields.
        - ``approval_request_ids_by_step`` is required because
          ``ValidationStep`` does not carry an approval request ID.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1)
    """Unique identifier for this execution request."""

    recipe: ValidationRecipe
    """The validated recipe to execute."""

    dry_run: bool = True
    """If True (default), steps are planned but not executed."""

    allowed_fixture_dir: str | None = None
    """Base directory for local_fixture_check reads. Required for fixture steps."""

    actor: str = Field(default="validation_recipe_executor", min_length=1)
    """Identifier for the actor proposing this execution."""

    approval_request_ids_by_step: dict[str, str] = Field(default_factory=dict)
    """Mapping from step.id to approval_request_id. Every active step needs one."""

    evidence_context: dict[str, Any] = Field(default_factory=dict)
    """Local in-memory evidence for evidence_check steps."""


# ------------------------------------------------------------------
# Result Models
# ------------------------------------------------------------------


class ValidationStepResult(BaseModel):
    """Per-step execution result.

    Captures what happened to a single step: its status, the gate
    decision that governed it, any audit event, and collected evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    """The step's unique identifier."""

    step_type: ValidationStepType
    """The type of validation step."""

    status: StepExecutionStatus
    """The outcome of this step."""

    gate_decision: ActiveValidationGateDecision | None = None
    """The gate decision for this step (None if step never reached the gate)."""

    audit_event_id: str | None = None
    """The ID of the audit event recorded for this step."""

    error_message: str | None = None
    """Human-readable error description (only set when status is ERROR or BLOCKED)."""

    evidence: dict[str, Any] = Field(default_factory=dict)
    """Evidence collected during step execution (handler output)."""


class ValidationExecutionResult(BaseModel):
    """Overall execution result for a recipe run.

    Aggregates all per-step results, audit trail, and an overall status.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    """The request that produced this result."""

    recipe_id: str | None
    """The ID of the executed recipe (None if recipe was invalid)."""

    overall_status: ExecutionStatus
    """Aggregate status: COMPLETED, BLOCKED, or ERROR."""

    step_results: list[ValidationStepResult]
    """Per-step results in recipe order."""

    audit_trail: list[str] = Field(default_factory=list)
    """Ordered list of audit event IDs recorded during this execution."""
