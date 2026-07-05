"""Evasion-prevention orchestration — combined redirect + CNAME checking.

This module combines the ScopeGuard decision with redirect-chain and
CNAME-chain analysis into a single, auditable ``EvasionResult``.

Design guarantees:
    - ScopeGuard is the first and final word — no override.
    - Redirect and CNAME checks are independent sub-checks.
    - A single DENY anywhere blocks the entire result.
    - All traces are serializable for future AuditLog consumption (#12).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from neutrino.scopeguard.models import (
    EvasionResult,
    ScopeDecisionStatus,
    ScopeReason,
)

if TYPE_CHECKING:
    from neutrino.models.policy import ScopePolicy
    from neutrino.scopeguard.dns import CnameResolver
    from neutrino.scopeguard.models import DnsTrace, RedirectTrace
    from neutrino.scopeguard.redirects import RedirectHop


def build_evasion_result(
    initial_target: str,
    policy: ScopePolicy | None,
    *,
    redirect_chain: list[RedirectHop] | None = None,
    cname_resolver: CnameResolver | None = None,
) -> EvasionResult:
    """Run the full evasion-prevention pipeline: initial guard + redirect + CNAME.

    This is the convenience entry point that combines:
        - ScopeGuard.check_target() on the initial target
        - check_redirect_chain() on the provided redirect hops
        - check_cname_chain() using the provided resolver

    Any DENY anywhere in the pipeline propagates into the final result.

    Args:
        initial_target: The starting URL/domain.
        policy: The ScopePolicy to evaluate against.
        redirect_chain: Optional list of redirect hops (from a fake client).
        cname_resolver: Optional CNAME resolver (from a fake resolver).
                        If None, the CNAME check is skipped entirely
                        (no DNS trace is produced).

    Returns:
        An ``EvasionResult`` with the combined outcome.
    """
    from neutrino.scopeguard.dns import check_cname_chain
    from neutrino.scopeguard.guard import ScopeGuard
    from neutrino.scopeguard.redirects import check_redirect_chain

    guard = ScopeGuard()

    # --- 1. Initial ScopeGuard check ---
    initial_decision = guard.check_target(initial_target, policy)

    redirect_traces: list[RedirectTrace] = []
    dns_traces: list[DnsTrace] = []
    current_status = initial_decision.status
    current_reason: ScopeReason = initial_decision.reason

    # --- 2. Redirect chain check ---
    if redirect_chain and current_status == ScopeDecisionStatus.ALLOW:
        r_traces, r_reason = check_redirect_chain(
            initial_target=initial_target,
            redirect_chain=redirect_chain,
            policy=policy,
            guard=guard,
        )
        redirect_traces = r_traces
        if r_reason is not None:
            current_status = ScopeDecisionStatus.DENY
            current_reason = r_reason

    # --- 3. CNAME chain check ---
    if cname_resolver is not None and current_status == ScopeDecisionStatus.ALLOW:
        c_traces, c_reason = check_cname_chain(
            initial_target=initial_target,
            policy=policy,
            resolver=cname_resolver,
            guard=guard,
        )
        dns_traces = c_traces
        if c_reason is not None:
            current_status = ScopeDecisionStatus.DENY
            current_reason = c_reason

    # --- 4. Build final explanation ---
    explanation_parts = [initial_decision.explanation]
    if current_reason != initial_decision.reason:
        if redirect_traces:
            explanation_parts.append(f"Blocked by redirect chain: {current_reason.value}")
        if dns_traces:
            explanation_parts.append(f"Blocked by CNAME chain: {current_reason.value}")
    explanation = " | ".join(explanation_parts)

    return EvasionResult(
        initial_target=initial_target,
        initial_decision=initial_decision,
        redirect_traces=redirect_traces,
        dns_traces=dns_traces,
        final_decision=current_status,
        final_reason=current_reason,
        explanation=explanation,
    )
