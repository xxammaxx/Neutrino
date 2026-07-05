"""Decision model for ScopeGuard — immutable, serializable, auditable.

Every ScopeGuard decision is captured as a ScopeDecision that records
the target, outcome, reason code, matched scope entry, and human-readable
explanation. These decisions are designed to be serialized for later
audit trail consumption.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ScopeDecisionStatus(StrEnum):
    """Binary outcome of a ScopeGuard evaluation.

    Only two states exist. There is no UNKNOWN — if a determination
    cannot be made with certainty, the result is DENY.
    """

    ALLOW = "allow"
    DENY = "deny"


class ScopeReason(StrEnum):
    """Deterministic reason code explaining WHY a decision was made.

    Each code maps to exactly one evaluation path in ScopeGuard.
    There is no generic or fallback code — every path is explicit.
    """

    ALLOW_IN_SCOPE = "allow_in_scope"
    DENY_OUT_OF_SCOPE = "deny_out_of_scope"
    DENY_UNKNOWN_TARGET = "deny_unknown_target"
    DENY_INVALID_TARGET = "deny_invalid_target"
    DENY_UNSAFE_SCHEME = "deny_unsafe_scheme"
    DENY_MISSING_POLICY = "deny_missing_policy"

    # Redirect evasion — ScopeGuard evaluates each redirect hop
    DENY_REDIRECT_OUT_OF_SCOPE = "deny_redirect_out_of_scope"
    DENY_REDIRECT_UNKNOWN = "deny_redirect_unknown"
    DENY_REDIRECT_LIMIT_EXCEEDED = "deny_redirect_limit_exceeded"
    DENY_INVALID_REDIRECT = "deny_invalid_redirect"

    # CNAME / DNS evasion — ScopeGuard evaluates each CNAME hop
    DENY_CNAME_OUT_OF_SCOPE = "deny_cname_out_of_scope"
    DENY_CNAME_UNKNOWN = "deny_cname_unknown"
    DENY_CNAME_LIMIT_EXCEEDED = "deny_cname_limit_exceeded"
    DENY_CNAME_LOOP = "deny_cname_loop"

    # DNS — resolver could not produce a determinate answer
    DENY_DNS_UNKNOWN = "deny_dns_unknown"


class ScopeDecision(BaseModel):
    """Immutable record of a single ScopeGuard evaluation.

    Attributes:
        target: The original (unmodified) target string that was evaluated.
        status: ALLOW or DENY.
        reason: Determistic reason code explaining the outcome.
        matched_entry: The ScopeEntry pattern that caused the match, if any.
        policy_source: The source URL of the policy used for this decision.
        explanation: Human-readable description of why the decision was made.
    """

    target: str = Field(description="Original target string evaluated")
    status: ScopeDecisionStatus = Field(description="ALLOW or DENY")
    reason: ScopeReason = Field(description="Deterministic reason code")
    matched_entry: str | None = Field(
        default=None,
        description="ScopeEntry pattern that matched (or None)",
    )
    policy_source: str | None = Field(
        default=None,
        description="Source URL of the policy used for this decision",
    )
    explanation: str = Field(
        default="",
        description="Human-readable explanation of the decision",
    )

    @property
    def is_allowed(self) -> bool:
        """Convenience accessor: True if the decision is ALLOW."""
        return self.status == ScopeDecisionStatus.ALLOW

    @property
    def is_denied(self) -> bool:
        """Convenience accessor: True if the decision is DENY."""
        return self.status == ScopeDecisionStatus.DENY


class DnsTrace(BaseModel):
    """Serializable record of a single simulated DNS resolution step.

    Captures the query and its answer for later audit-log consumption.
    No real network I/O — purely a data structure for mock resolvers.
    """

    queried_name: str = Field(description="The name that was queried (domain, hostname)")
    record_type: str = Field(description="DNS record type (CNAME, A, AAAA, etc.)")
    answers: list[str] = Field(default_factory=list, description="Resolved answer values")
    source: str = Field(
        default="fake_resolver",
        description="How the answer was obtained: fake_resolver, provided_trace, etc.",
    )
    decision: str = Field(
        default="",
        description="ScopeGuard decision for this resolution step (allow/deny reason)",
    )


class RedirectTrace(BaseModel):
    """Serializable record of a single HTTP redirect hop.

    Records the from/to locations, status code, and scope decision.
    """

    from_url: str = Field(description="The URL that issued the redirect")
    to_url: str = Field(description="The redirect target (Location header value)")
    status_code: int = Field(description="HTTP status code (301, 302, 307, 308)")
    decision: str = Field(description="ScopeGuard decision for the redirect target")


class EvasionResult(BaseModel):
    """Aggregate result from redirect and CNAME evasion checks.

    Combines the initial ScopeGuard decision with redirect-chain and
    CNAME-chain analysis into a single, auditable outcome.
    """

    initial_target: str = Field(description="The original target that was checked")
    initial_decision: ScopeDecision = Field(description="ScopeGuard decision on initial target")
    redirect_traces: list[RedirectTrace] = Field(
        default_factory=list, description="Per-hop redirect decisions"
    )
    dns_traces: list[DnsTrace] = Field(
        default_factory=list, description="Per-hop DNS/CNAME decisions"
    )
    final_decision: ScopeDecisionStatus = Field(
        description="Final verdict: ALLOW only if initial + all hops are allowed"
    )
    final_reason: ScopeReason = Field(description="Reason code for the final verdict")
    explanation: str = Field(
        default="", description="Human-readable explanation of the combined result"
    )
