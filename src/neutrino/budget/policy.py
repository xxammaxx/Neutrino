"""Budget policy evaluation — pure, deterministic budget checking.

The central function ``evaluate_budget()`` takes a BudgetPolicy,
BudgetUsage, and an (injectable) timestamp and returns a BudgetDecision.

The evaluation follows a strict priority order:

1. **Input validation:** negative usage or limits → ERROR.
2. **Missing policy:** no limits defined → ERROR (conservative default).
3. **Limit checks** (checked in fixed order):
   a. ``requests_used >= max_requests`` → EXHAUSTED
   b. ``cost_cents_used >= max_cost_cents`` → EXHAUSTED
   c. ``runtime_seconds_used >= max_runtime_seconds`` → EXHAUSTED
4. **All OK** → OK.

Design principles:
    - Pure function: no side effects, no I/O, no randomness.
    - Timestamp injectable for test reproducibility.
    - Deterministic: same inputs → same output (except timestamp).
    - ``None`` limits are skipped (not checked).
    - First exhausted limit wins (deterministic priority order).

No network access, no cloud billing, no real-money integration.
"""

from __future__ import annotations

from neutrino.budget.models import BudgetDecision, BudgetPolicy, BudgetStatus, BudgetUsage


def evaluate_budget(
    policy: BudgetPolicy,
    usage: BudgetUsage,
    timestamp: str,
) -> BudgetDecision:
    """Evaluate whether a ResearchRun has exceeded its budget.

    Args:
        policy: The budget policy with optional limits.
        usage: Current usage counters.
        timestamp: ISO 8601 timestamp for the decision record.
                   Inject a fixed value for deterministic tests.

    Returns:
        BudgetDecision with status, reason, and limit details.

    Raises:
        ValueError: If policy is None.
    """
    if policy is None:
        raise ValueError("policy must not be None")

    # --- 1. Input validation: usage ---
    if not usage.is_valid():
        return _error(
            "Negative usage values are not allowed",
            timestamp=timestamp,
        )

    # --- 2. Input validation: policy limits ---
    if _has_negative_limit(policy):
        return _error(
            "Negative budget limits are not allowed",
            timestamp=timestamp,
        )

    # --- 3. Missing limits (conservative: ERROR) ---
    if not policy.has_any_limit():
        return _error(
            "No budget limits configured (missing_budget_limits)",
            timestamp=timestamp,
        )

    # --- 4. Limit checks (fixed priority order) ---
    return _check_limits(policy, usage, timestamp)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _error(reason: str, timestamp: str) -> BudgetDecision:
    """Build an ERROR decision."""
    return BudgetDecision(
        status=BudgetStatus.ERROR,
        reason=reason,
        timestamp=timestamp,
    )


def _exhausted(
    reason: str,
    limit_name: str,
    limit_value: int,
    observed_value: int,
    timestamp: str,
) -> BudgetDecision:
    """Build an EXHAUSTED decision with limit details."""
    return BudgetDecision(
        status=BudgetStatus.EXHAUSTED,
        reason=reason,
        limit_name=limit_name,
        limit_value=limit_value,
        observed_value=observed_value,
        timestamp=timestamp,
    )


def _ok(timestamp: str) -> BudgetDecision:
    """Build an OK decision."""
    return BudgetDecision(
        status=BudgetStatus.OK,
        reason="All budget limits respected",
        timestamp=timestamp,
    )


def _has_negative_limit(policy: BudgetPolicy) -> bool:
    """Check whether any defined limit is negative."""
    limits = (
        policy.max_requests,
        policy.max_cost_cents,
        policy.max_runtime_seconds,
    )
    return any(v is not None and v < 0 for v in limits)


def _check_limits(
    policy: BudgetPolicy,
    usage: BudgetUsage,
    timestamp: str,
) -> BudgetDecision:
    """Check limits in deterministic priority order.

    Priority:
        1. requests
        2. cost_cents
        3. runtime_seconds

    First exhausted limit wins.
    """
    # Check requests limit
    if policy.max_requests is not None and usage.requests_used >= policy.max_requests:
        return _exhausted(
            reason=f"Request limit exhausted: {usage.requests_used} >= {policy.max_requests}",
            limit_name="max_requests",
            limit_value=policy.max_requests,
            observed_value=usage.requests_used,
            timestamp=timestamp,
        )

    # Check cost limit
    if policy.max_cost_cents is not None and usage.cost_cents_used >= policy.max_cost_cents:
        return _exhausted(
            reason=f"Cost limit exhausted: {usage.cost_cents_used} >= {policy.max_cost_cents}",
            limit_name="max_cost_cents",
            limit_value=policy.max_cost_cents,
            observed_value=usage.cost_cents_used,
            timestamp=timestamp,
        )

    # Check runtime limit
    if (
        policy.max_runtime_seconds is not None
        and usage.runtime_seconds_used >= policy.max_runtime_seconds
    ):
        return _exhausted(
            reason=f"Runtime limit exhausted: {usage.runtime_seconds_used} >= {policy.max_runtime_seconds}",
            limit_name="max_runtime_seconds",
            limit_value=policy.max_runtime_seconds,
            observed_value=usage.runtime_seconds_used,
            timestamp=timestamp,
        )

    # All OK
    return _ok(timestamp)
