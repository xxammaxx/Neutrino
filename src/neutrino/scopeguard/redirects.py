"""Redirect-chain evasion-prevention — local, mockable, deterministic.

This module checks HTTP redirect chains against a ScopePolicy.
No real HTTP requests are made — redirect chains are provided as
local data structures or fake client responses.

Design guarantees:
    - No real HTTP requests — chains are injected as data.
    - Each redirect hop is re-evaluated against ScopePolicy independently.
    - Unsafe schemes (http, file, ftp, etc.) are blocked at every hop.
    - Hop limits prevent unbounded redirect following.
    - No override path for DENY — even a single bad hop blocks everything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from neutrino.scopeguard.models import RedirectTrace, ScopeReason

if TYPE_CHECKING:
    from neutrino.models.policy import ScopePolicy
    from neutrino.scopeguard.guard import ScopeGuard

# ------------------------------------------------------------------
# Limits
# ------------------------------------------------------------------

DEFAULT_MAX_REDIRECT_HOPS: int = 5

# Safe redirect status codes (no path/body change semantics ambiguity)
_REDIRECT_STATUS_CODES: frozenset[int] = frozenset({301, 302, 307, 308, 303})


# ------------------------------------------------------------------
# RedirectHop — data structure for a single redirect step
# ------------------------------------------------------------------


class RedirectHop:
    """A single redirect hop, provided as data (not from a real request).

    Attributes:
        from_url: The URL that returned the redirect response.
        to_url: The value of the ``Location`` header.
        status_code: The HTTP status code of the redirect.
    """

    def __init__(self, from_url: str, to_url: str, status_code: int = 302) -> None:
        self.from_url = from_url
        self.to_url = to_url
        self.status_code = status_code


# ------------------------------------------------------------------
# Redirect chain checker
# ------------------------------------------------------------------


def check_redirect_chain(
    initial_target: str,
    redirect_chain: list[RedirectHop],
    policy: ScopePolicy | None,
    *,
    guard: ScopeGuard | None = None,
    max_hops: int = DEFAULT_MAX_REDIRECT_HOPS,
) -> tuple[list[RedirectTrace], ScopeReason | None]:
    """Evaluate a redirect chain against a ScopePolicy.

    Each redirect hop is checked independently. If ANY hop is
    out-of-scope, unknown, uses an unsafe scheme, or exceeds the
    hop limit, the entire chain is blocked.

    Args:
        initial_target: The starting URL evaluated by ScopeGuard.
        redirect_chain: An ordered list of ``RedirectHop`` steps.
        policy: The ScopePolicy to evaluate against.
        guard: Optional pre-constructed ``ScopeGuard``.
        max_hops: Maximum redirect hops before ``DENY_REDIRECT_LIMIT_EXCEEDED``.

    Returns:
        A tuple of ``(traces, blocking_reason)``.
        *traces* lists the per-hop decisions.
        If *blocking_reason* is ``None`` the chain is safe;
        otherwise it contains the first DENY reason encountered.
    """
    from neutrino.scopeguard.guard import ScopeGuard

    if guard is None:
        guard = ScopeGuard()

    # --- Step 0: validate chain length ---
    if len(redirect_chain) > max_hops:
        return [], ScopeReason.DENY_REDIRECT_LIMIT_EXCEEDED

    traces: list[RedirectTrace] = []

    # --- Step 1: check initial target ---
    initial_decision = guard.check_target(initial_target, policy)
    if initial_decision.is_denied:
        return traces, initial_decision.reason

    # --- Step 2-N: check each redirect hop ---
    for hop in redirect_chain:
        # Validate the redirect itself
        if not hop.to_url.strip():
            trace = RedirectTrace(
                from_url=hop.from_url,
                to_url="(empty)",
                status_code=hop.status_code,
                decision=ScopeReason.DENY_INVALID_REDIRECT.value,
            )
            traces.append(trace)
            return traces, ScopeReason.DENY_INVALID_REDIRECT

        # Check the redirect target with ScopeGuard
        decision = guard.check_target(hop.to_url, policy)
        trace = RedirectTrace(
            from_url=hop.from_url,
            to_url=hop.to_url,
            status_code=hop.status_code,
            decision=decision.reason.value,
        )
        traces.append(trace)

        if decision.is_denied:
            redirect_reason = _map_generic_to_redirect_reason(decision.reason)
            return traces, redirect_reason

    return traces, None


def _map_generic_to_redirect_reason(reason: ScopeReason) -> ScopeReason:
    """Map a generic ScopeReason to its redirect-specific equivalent."""
    mapping: dict[ScopeReason, ScopeReason] = {
        ScopeReason.DENY_OUT_OF_SCOPE: ScopeReason.DENY_REDIRECT_OUT_OF_SCOPE,
        ScopeReason.DENY_UNKNOWN_TARGET: ScopeReason.DENY_REDIRECT_UNKNOWN,
        ScopeReason.DENY_INVALID_TARGET: ScopeReason.DENY_INVALID_REDIRECT,
        ScopeReason.DENY_UNSAFE_SCHEME: ScopeReason.DENY_INVALID_REDIRECT,
        ScopeReason.DENY_MISSING_POLICY: ScopeReason.DENY_REDIRECT_UNKNOWN,
    }
    return mapping.get(reason, ScopeReason.DENY_REDIRECT_UNKNOWN)
