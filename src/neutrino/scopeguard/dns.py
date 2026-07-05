"""DNS / CNAME evasion-prevention — local, mockable, deterministic.

This module provides CNAME chain checking against a ScopePolicy.
All resolution is performed via an injectable ``CnameResolver`` interface
so that tests can supply static answers without real DNS requests.

Design guarantees:
    - No real DNS requests — all resolution is injected.
    - Every CNAME hop is re-evaluated against the ScopePolicy.
    - Loop detection prevents infinite CNAME chains.
    - Hop limits prevent unbounded recursion.
    - Wildcards are NOT inherited by CNAME targets.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from neutrino.scopeguard.models import DnsTrace, ScopeReason

if TYPE_CHECKING:
    from neutrino.models.policy import ScopePolicy
    from neutrino.scopeguard.guard import ScopeGuard

# ------------------------------------------------------------------
# Limits
# ------------------------------------------------------------------

DEFAULT_MAX_CNAME_HOPS: int = 10

# ------------------------------------------------------------------
# Resolver interface
# ------------------------------------------------------------------


class CnameResolver(ABC):
    """Abstract interface for DNS CNAME resolution.

    Implementations must NOT perform real network I/O unless inside
    a controlled, human-approved environment. The canonical test
    implementation is ``FakeCnameResolver`` which answers from a
    static mapping.
    """

    @abstractmethod
    def resolve_cname(self, name: str) -> list[str] | None:
        """Resolve CNAME records for *name*.

        Returns:
            A list of canonical names in resolution order, or
            ``None`` if resolution failed / produced no answer.
        """
        ...


class FakeCnameResolver(CnameResolver):
    """Deterministic CNAME resolver backed by a static mapping.

    Answers are served from an in-memory dictionary. If a name is
    not found, ``resolve_cname`` returns ``None`` (UNKNOWN).

    Usage::

        resolver = FakeCnameResolver(
            {
                "sub.example.com": ["target.example.net"],
                "target.example.net": ["final.cdn.example.org"],
            }
        )
    """

    def __init__(self, cname_map: dict[str, list[str]] | None = None) -> None:
        self._cname_map: dict[str, list[str]] = dict(cname_map or {})

    def resolve_cname(self, name: str) -> list[str] | None:
        """Look up CNAME answers for *name* in the static map."""
        return self._cname_map.get(name)


# ------------------------------------------------------------------
# CNAME chain checker
# ------------------------------------------------------------------


def check_cname_chain(
    initial_target: str,
    policy: ScopePolicy | None,
    *,
    resolver: CnameResolver,
    guard: ScopeGuard | None = None,
    max_hops: int = DEFAULT_MAX_CNAME_HOPS,
) -> tuple[list[DnsTrace], ScopeReason | None]:
    """Evaluate a CNAME chain against a ScopePolicy.

    The initial target is first checked by ScopeGuard. Then each
    CNAME hop is resolved (via the injected *resolver*) and checked
    independently. A CNAME target that is out-of-scope, unknown, or
    exceeds the hop limit results in an immediate block.

    Args:
        initial_target: The starting domain/hostname.
        policy: The ScopePolicy to evaluate against.
        resolver: An injected ``CnameResolver`` (e.g. ``FakeCnameResolver``).
        guard: Optional pre-constructed ``ScopeGuard``. A fresh instance
               is created if ``None``.
        max_hops: Maximum CNAME hops before ``DENY_CNAME_LIMIT_EXCEEDED``.

    Returns:
        A tuple of ``(traces, blocking_reason)``.
        *traces* always contains at least one entry (the initial target).
        If *blocking_reason* is ``None`` the chain is safe;
        otherwise it contains the first DENY reason encountered.
    """
    from neutrino.scopeguard.guard import ScopeGuard

    if guard is None:
        guard = ScopeGuard()

    traces: list[DnsTrace] = []

    # --- Step 0: check the initial target ---
    initial_decision = guard.check_target(initial_target, policy)
    traces.append(
        DnsTrace(
            queried_name=initial_target,
            record_type="A",
            answers=[initial_target],
            source="scope_guard",
            decision=initial_decision.reason.value,
        )
    )
    if initial_decision.is_denied:
        return traces, initial_decision.reason

    # --- Step 1-N: follow the CNAME chain ---
    current = initial_target
    seen: set[str] = {initial_target}

    for _hop in range(max_hops):
        answers = resolver.resolve_cname(current)

        # No CNAME — chain ends naturally
        if answers is None:
            traces.append(
                DnsTrace(
                    queried_name=current,
                    record_type="CNAME",
                    answers=[],
                    source="fake_resolver",
                    decision="no_cname_record",
                )
            )
            return traces, None

        if not answers:
            traces.append(
                DnsTrace(
                    queried_name=current,
                    record_type="CNAME",
                    answers=[],
                    source="fake_resolver",
                    decision="empty_cname_response",
                )
            )
            return traces, ScopeReason.DENY_DNS_UNKNOWN

        for cname_target in answers:
            # Loop detection
            if cname_target in seen:
                traces.append(
                    DnsTrace(
                        queried_name=cname_target,
                        record_type="CNAME",
                        answers=[cname_target],
                        source="fake_resolver",
                        decision=ScopeReason.DENY_CNAME_LOOP.value,
                    )
                )
                return traces, ScopeReason.DENY_CNAME_LOOP

            seen.add(cname_target)

            # Check the CNAME target against scope policy
            decision = guard.check_target(cname_target, policy)
            decision_val = decision.reason.value

            traces.append(
                DnsTrace(
                    queried_name=cname_target,
                    record_type="CNAME",
                    answers=[cname_target],
                    source="fake_resolver",
                    decision=decision_val,
                )
            )

            if decision.is_denied:
                # Map the generic reason to a CNAME-specific reason
                cname_reason = _map_generic_to_cname_reason(decision.reason)
                return traces, cname_reason

            # Follow the chain
            current = cname_target

    # Hop limit exceeded
    return traces, ScopeReason.DENY_CNAME_LIMIT_EXCEEDED


def _map_generic_to_cname_reason(reason: ScopeReason) -> ScopeReason:
    """Map a generic ScopeReason to its CNAME-specific equivalent."""
    mapping: dict[ScopeReason, ScopeReason] = {
        ScopeReason.DENY_OUT_OF_SCOPE: ScopeReason.DENY_CNAME_OUT_OF_SCOPE,
        ScopeReason.DENY_UNKNOWN_TARGET: ScopeReason.DENY_CNAME_UNKNOWN,
        ScopeReason.DENY_INVALID_TARGET: ScopeReason.DENY_CNAME_UNKNOWN,
        ScopeReason.DENY_UNSAFE_SCHEME: ScopeReason.DENY_CNAME_UNKNOWN,
        ScopeReason.DENY_MISSING_POLICY: ScopeReason.DENY_DNS_UNKNOWN,
    }
    return mapping.get(reason, ScopeReason.DENY_DNS_UNKNOWN)
