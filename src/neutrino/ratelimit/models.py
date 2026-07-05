"""Decision models for Rate-Limit Enforcement — immutable, serializable, auditable.

Every rate-limit decision is captured as a RateLimitDecision that records
the target, outcome, reason code, and optional violation evidence. These
decisions are designed to be serialized for later audit trail consumption.

No network I/O. No DNS. No sleep. No persistent audit log.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RateLimitDecisionStatus(StrEnum):
    """Binary outcome of a RateLimitEnforcer evaluation.

    Only two states exist. There is no UNKNOWN — if a determination
    cannot be made with certainty, the result is DENY.
    """

    ALLOW = "allow"
    DENY = "deny"


class RateLimitReason(StrEnum):
    """Deterministic reason code explaining WHY a rate-limit decision was made.

    Each code maps to exactly one evaluation path in the enforcer.
    There is no generic or fallback code — every path is explicit.
    """

    ALLOW_WITHIN_LIMIT = "allow_within_limit"
    DENY_MISSING_POLICY = "deny_missing_policy"
    DENY_MISSING_RATE_LIMIT = "deny_missing_rate_limit"
    DENY_REQUESTS_PER_SECOND_EXCEEDED = "deny_requests_per_second_exceeded"
    DENY_REQUESTS_PER_MINUTE_EXCEEDED = "deny_requests_per_minute_exceeded"
    DENY_REQUESTS_PER_HOUR_EXCEEDED = "deny_requests_per_hour_exceeded"
    DENY_REQUESTS_PER_DAY_EXCEEDED = "deny_requests_per_day_exceeded"
    DENY_CONCURRENT_REQUESTS_EXCEEDED = "deny_concurrent_requests_exceeded"
    DENY_INVALID_TARGET = "deny_invalid_target"


class RateLimitViolation(BaseModel):
    """Serializable evidence for an audit-relevant rate-limit violation.

    Captures exactly which limit was exceeded, by how much, and in
    which time window. Designed for consumption by an AuditLog but
    does NOT persist anything itself (no file/DB writes).
    """

    target: str = Field(description="The target that exceeded the limit")
    reason: str = Field(description="Human-readable description of the violation")
    limit_name: str = Field(description="Name of the limit that was exceeded")
    limit_value: int | float = Field(description="The configured limit value")
    observed_value: int | float = Field(
        description="The observed value that triggered the violation"
    )
    window_seconds: int | float = Field(
        default=0,
        description="The time window in seconds for this limit (0 for concurrent)",
    )
    timestamp: float = Field(description="Unix timestamp of when the violation occurred")


class RateLimitRequest(BaseModel):
    """Local, non-executing request intent descriptor.

    Describes a request that would be made to a target. Does NOT
    perform any network I/O, DNS resolution, or HTTP communication.
    """

    target: str = Field(description="Normalised target (domain, host, no scheme)")
    timestamp: float = Field(description="Unix timestamp of the request")
    method: str = Field(default="GET", description="HTTP method or action identifier")
    request_id: str = Field(description="Unique identifier for this request intent")


class RateLimitState(BaseModel):
    """Local, in-memory request history per target.

    Tracks past requests for time-window counting (all requests) and
    concurrency counting (active requests only). Completed requests
    still count towards time-window limits but NOT towards concurrency.

    Callers should call ``complete_request()`` when a concurrent slot
    frees up — the request stays in the history for time-window purposes.
    """

    requests: list[RateLimitRequest] = Field(
        default_factory=list,
        description="All requests tracked in the state (for time-window counting)",
    )
    _active_ids: set[str] = set()

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        self._active_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Mutating operations
    # ------------------------------------------------------------------

    def add_request(self, request: RateLimitRequest) -> None:
        """Add a request as active (call after ALLOW decision).

        The request is tracked for both time-window and concurrency limits.
        """
        self.requests.append(request)
        self._active_ids.add(request.request_id)

    def complete_request(self, request_id: str) -> None:
        """Mark a request as completed (frees concurrent slots).

        The request is NOT removed from history — it still counts
        towards time-window limits (per-second, per-minute, etc.).
        Only concurrent capacity is freed.
        """
        self._active_ids.discard(request_id)

    def _remove_request(self, request_id: str) -> None:
        """Fully remove a request from both history and active tracking."""
        self.requests = [r for r in self.requests if r.request_id != request_id]
        self._active_ids.discard(request_id)

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def count_in_window(self, target: str, window_seconds: float, now: float) -> int:
        """Count ALL requests (active + completed) for a target within a time window.

        Args:
            target: The normalized target string.
            window_seconds: Look-back window in seconds (e.g. 1.0, 60.0, 3600.0).
            now: Current timestamp for cutoff calculation.

        Returns:
            Number of requests within the window (always >= 0).
        """
        if window_seconds <= 0:
            return 0
        cutoff = now - window_seconds
        return sum(1 for r in self.requests if r.target == target and r.timestamp > cutoff)

    def active_count(self, target: str) -> int:
        """Count only ACTIVE (in-flight) requests for a target.

        Returns:
            Number of concurrently active requests for the target.
        """
        return sum(
            1 for r in self.requests if r.target == target and r.request_id in self._active_ids
        )

    def prune_before(self, cutoff: float) -> None:
        """Remove completed requests older than a cutoff timestamp.

        Active requests are never pruned (they represent in-flight work).
        Prevents unbounded memory growth from accumulated history.

        Args:
            cutoff: Remove completed requests with timestamp <= this value.
        """
        self.requests = [
            r for r in self.requests if r.timestamp > cutoff or r.request_id in self._active_ids
        ]


class RateLimitDecision(BaseModel):
    """Immutable record of a single RateLimitEnforcer evaluation.

    Attributes:
        target: The target that was evaluated.
        status: ALLOW or DENY.
        reason: Deterministic reason code explaining the outcome.
        retry_after_seconds: Seconds until a retry may succeed, or None.
        explanation: Human-readable description of why the decision was made.
        policy_source: Source URL of the policy used, if any.
        violation: Violation evidence for denied requests, if applicable.
    """

    target: str = Field(description="The evaluated target")
    status: RateLimitDecisionStatus = Field(description="ALLOW or DENY")
    reason: RateLimitReason = Field(description="Deterministic reason code")
    retry_after_seconds: float | None = Field(
        default=None,
        description="Seconds until retry may succeed (None if unknown or concurrent)",
    )
    explanation: str = Field(
        default="",
        description="Human-readable explanation of the decision",
    )
    policy_source: str | None = Field(
        default=None,
        description="Source URL of the policy used for this decision",
    )
    violation: RateLimitViolation | None = Field(
        default=None,
        description="Violation evidence for denied requests (serializable audit trail)",
    )

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def is_allowed(self) -> bool:
        """True if the decision is ALLOW."""
        return self.status == RateLimitDecisionStatus.ALLOW

    @property
    def is_denied(self) -> bool:
        """True if the decision is DENY."""
        return self.status == RateLimitDecisionStatus.DENY
