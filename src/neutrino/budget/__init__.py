"""Neutrino Budget — local, deterministic budget policy logic for ResearchRuns.

This module provides budget status evaluation, exhaustion detection, and
status change persistence. No external billing, no cloud cost tracking,
no automatic recovery — purely local safety logic.

Components:
    - ``models``: BudgetStatus, BudgetPolicy, BudgetUsage, BudgetDecision.
    - ``policy``: ``evaluate_budget()`` — pure function for budget evaluation.
    - ``status``: ``apply_budget_decision()`` — persist status changes to
      ResearchRunRepository and AuditEventRepository.
"""

from neutrino.budget.models import (
    BudgetDecision,
    BudgetPolicy,
    BudgetStatus,
    BudgetUsage,
)
from neutrino.budget.policy import evaluate_budget
from neutrino.budget.status import apply_budget_decision

__all__ = [
    "BudgetDecision",
    "BudgetPolicy",
    "BudgetStatus",
    "BudgetUsage",
    "apply_budget_decision",
    "evaluate_budget",
]
