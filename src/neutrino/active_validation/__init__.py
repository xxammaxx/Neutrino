"""Neutrino Active Validation Gate — Issue #14.

This package implements the Active-Validation-Gate as a deterministic,
fail-closed orchestrator. The gate evaluates ``ActiveValidationIntent``
against Human Approval (from #4), Scope metadata match, and ScopeGuard,
returning a binary ``ActiveValidationGateDecision``.

Key components:
    - ``ActiveValidationIntent`` — Serializable intent describing a
      planned active validation action. Describes only, never executes.
    - ``ActiveValidationGateDecision`` — Binary gate result with
      ``allow=True`` only when ALL checks pass.
    - ``ActiveValidationGate`` — Core evaluator orchestrating Approval,
      ScopeGuard, and Audit.
    - ``ReasonCode`` — Deterministic reason codes for gate decisions.

Design invariants:
    - Default-Deny: ``allow=False`` unless all checks pass.
    - Fail-closed: Unknown states, invalid intents, audit failures → BLOCK.
    - No execution: The gate decides ONLY. No HTTP, DNS, shell, exploits.
    - No bypass: No force, override, auto-approve, LLM-approve paths.
    - Deterministic: Same inputs always yield the same decision.
    - All decisions are audited; audit failure → BLOCK_AUDIT_FAILED.
"""

from __future__ import annotations

from neutrino.active_validation.gate import ActiveValidationGate
from neutrino.active_validation.models import (
    ActiveValidationGateDecision,
    ActiveValidationIntent,
    ReasonCode,
)

__all__ = [
    "ActiveValidationGate",
    "ActiveValidationGateDecision",
    "ActiveValidationIntent",
    "ReasonCode",
]
