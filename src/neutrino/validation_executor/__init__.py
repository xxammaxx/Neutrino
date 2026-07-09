"""Validation Executor — Issue #19.

This package implements the ValidationRecipeExecutor: a deterministic,
fail-closed orchestrator that executes validated ``ValidationRecipe``
objects through safety gates before delegating to local-only step
handlers.

Key components:
    - ``ValidationRecipeExecutor`` — Core executor orchestrating gates
      and handlers.
    - ``ValidationExecutionRequest`` — Immutable execution request.
    - ``ValidationExecutionResult`` — Overall execution outcome with
      per-step results and audit trail.
    - ``ValidationStepResult`` — Per-step outcome.
    - ``StepHandler`` — Abstract base for deterministic local handlers.
    - ``get_handler()`` — Default-deny handler registry lookup.

Design invariants:
    - Dry-run is the default.
    - Recipe is re-validated before any step.
    - Every step passes through ``ActiveValidationGate``.
    - Gate DENY → BLOCKED (never executed).
    - All step outcomes are audited.
    - Audit failure → fail-closed.
    - No shell, subprocess, DNS, external HTTP, or socket I/O.
    - No bypass flags exist anywhere in the module.
    - Deterministisch: gleiche Inputs → gleiche Results.
"""

from neutrino.validation_executor.executor import ValidationRecipeExecutor
from neutrino.validation_executor.handlers import (
    EvidenceCheckHandler,
    HttpCheckHandler,
    LocalFixtureCheckHandler,
    ManualObservationHandler,
    StepHandler,
    TcpCheckHandler,
    get_handler,
)
from neutrino.validation_executor.models import (
    ExecutionStatus,
    StepExecutionStatus,
    ValidationExecutionRequest,
    ValidationExecutionResult,
    ValidationStepResult,
)

__all__ = [
    "ValidationRecipeExecutor",
    "ValidationExecutionRequest",
    "ValidationStepResult",
    "ValidationExecutionResult",
    "StepExecutionStatus",
    "ExecutionStatus",
    "StepHandler",
    "ManualObservationHandler",
    "EvidenceCheckHandler",
    "LocalFixtureCheckHandler",
    "HttpCheckHandler",
    "TcpCheckHandler",
    "get_handler",
]
