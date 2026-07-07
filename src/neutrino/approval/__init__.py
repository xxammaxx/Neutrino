"""Neutrino Approval — Human Authorization Workflow.

This package implements the #4 Human Authorization Workflow as a
deterministic, local core component.

Key components:
    - ``ApprovalRequest`` — Serializable request with scope, test_type,
      and risk_summary.
    - ``HumanDecision`` — Explicit human APPROVE or REJECT decision.
    - ``ApprovalDecision`` — Gate result with binary allow/block flag.
    - ``ApprovalWorkflow`` — Core service orchestrating request creation,
      decision recording, and gate checks.

Design invariants:
    - Default-Deny: No action is allowed without explicit APPROVE.
    - No auto-approval, no LLM approval, no time-based approval.
    - All state changes are audited.
    - Deterministic: same inputs always yield the same gate result.
"""

from __future__ import annotations

from neutrino.approval.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    DecisionType,
    GateResult,
    HumanDecision,
)
from neutrino.approval.workflow import ApprovalWorkflow

__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalStatus",
    "ApprovalWorkflow",
    "DecisionType",
    "GateResult",
    "HumanDecision",
]
