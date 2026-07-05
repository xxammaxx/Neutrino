"""ScopeGuard — deterministic, local request-gating against a ScopePolicy.

This package provides the ScopeGuard decision engine that evaluates
targets (domains, IPs, URLs) against a loaded ScopePolicy and returns
an immutable ScopeDecision. All checks are local and deterministic;
no network requests, DNS resolution, or redirect handling is used.

New in Issue #6: Redirect- und CNAME-Evasion-Prävention.
    - ``redirects.py``: Redirect chain checking (injectable, no real HTTP)
    - ``dns.py``: CNAME chain checking with injectable FakeCnameResolver
    - ``evasion.py``: Combined orchestration producing ``EvasionResult``
"""

from neutrino.scopeguard.dns import CnameResolver, FakeCnameResolver, check_cname_chain
from neutrino.scopeguard.evasion import build_evasion_result
from neutrino.scopeguard.guard import ScopeGuard
from neutrino.scopeguard.models import (
    DnsTrace,
    EvasionResult,
    RedirectTrace,
    ScopeDecision,
    ScopeDecisionStatus,
    ScopeReason,
)
from neutrino.scopeguard.redirects import RedirectHop, check_redirect_chain

__all__ = [
    "ScopeGuard",
    "ScopeDecision",
    "ScopeDecisionStatus",
    "ScopeReason",
    "CnameResolver",
    "FakeCnameResolver",
    "check_cname_chain",
    "RedirectHop",
    "check_redirect_chain",
    "build_evasion_result",
    "DnsTrace",
    "EvasionResult",
    "RedirectTrace",
]
