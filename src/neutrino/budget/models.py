"""Budget models for Neutrino research run cost control.

These models are intentionally small and serializable. They model a
local budget policy with limits on requests, cost, and runtime — NOT
real-money billing or cloud-provider integration.

BudgetStatus:
    OK          — within all limits.
    WARNING     — approaching a limit (reserved for future use).
    EXHAUSTED   — at least one limit reached or exceeded.
    ERROR       — invalid input or missing configuration.

BudgetDecision is a pure data record of an evaluation, fully determined
by its inputs (plus an optional injectable timestamp for reproducibility).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class BudgetStatus(StrEnum):
    """Status of a budget evaluation.

    Values reflect deterministic, safety-first reasoning:
        - OK: all defined limits are respected.
        - WARNING: reserved for threshold-based alerts (not yet used).
        - EXHAUSTED: at least one limit is met or exceeded.
        - ERROR: configuration error, invalid input, or missing policy.
    """

    OK = "ok"
    WARNING = "warning"
    EXHAUSTED = "exhausted"
    ERROR = "error"


class BudgetPolicy(BaseModel):
    """A budget policy defining optional limits for a ResearchRun.

    All limits are optional (``None`` means "no limit specified").
    When NO limits are specified, the policy is considered *unconfigured*
    and the evaluation will return ``ERROR`` with reason ``missing_budget_limits``.

    Attributes:
        max_requests: Maximum number of requests allowed.
        max_cost_cents: Maximum cost in cents (currency-agnostic).
        max_runtime_seconds: Maximum runtime in seconds.
    """

    max_requests: int | None = None
    max_cost_cents: int | None = None
    max_runtime_seconds: int | None = None

    def has_any_limit(self) -> bool:
        """Return True if at least one limit is set."""
        return (
            self.max_requests is not None
            or self.max_cost_cents is not None
            or self.max_runtime_seconds is not None
        )


class BudgetUsage(BaseModel):
    """Current usage counters for a ResearchRun.

    All values default to 0. Negative values are considered invalid
    and will produce an ERROR decision.

    Attributes:
        requests_used: Number of requests already consumed.
        cost_cents_used: Cost in cents already consumed.
        runtime_seconds_used: Runtime in seconds already consumed.
    """

    requests_used: int = 0
    cost_cents_used: int = 0
    runtime_seconds_used: int = 0

    def is_valid(self) -> bool:
        """Return True if no usage values are negative."""
        return (
            self.requests_used >= 0 and self.cost_cents_used >= 0 and self.runtime_seconds_used >= 0
        )


class BudgetDecision(BaseModel):
    """Result of a budget evaluation.

    Fully determined by ``policy``, ``usage``, and ``timestamp``.
    Two evaluations with identical inputs produce identical decisions.

    Attributes:
        status: The evaluated BudgetStatus.
        reason: Human-readable explanation.
        limit_name: Name of the limit that triggered EXHAUSTED (if any).
        limit_value: Value of the violated limit (if any).
        observed_value: Actual usage value that violated the limit (if any).
        timestamp: ISO 8601 timestamp of the evaluation.
    """

    status: BudgetStatus
    reason: str
    limit_name: str | None = None
    limit_value: int | None = None
    observed_value: int | None = None
    timestamp: str  # ISO 8601
