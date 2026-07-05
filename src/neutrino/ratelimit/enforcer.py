"""Rate-Limit Enforcer — deterministic, local enforcement of per-target rate limits.

The RateLimitEnforcer evaluates a RateLimitRequest against a ScopePolicy's
rate_limits and a local RateLimitState, producing an immutable RateLimitDecision.

Core guarantees:
    - DENY can never be overridden. If any limit is exceeded, the result is DENY.
    - Missing or incomplete limits are treated conservatively: DENY.
    - No network I/O, no DNS, no sleep, no scheduler, no persistent audit log.
    - All decisions are deterministic: same inputs + same state → same decision.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from neutrino.ratelimit.models import (
    RateLimitDecision,
    RateLimitDecisionStatus,
    RateLimitReason,
    RateLimitRequest,
    RateLimitState,
    RateLimitViolation,
)

if TYPE_CHECKING:
    from neutrino.models.policy import RateLimit, ScopePolicy

# Time windows in seconds for each limit dimension.
_WINDOW_SECOND: float = 1.0
_WINDOW_MINUTE: float = 60.0
_WINDOW_HOUR: float = 3600.0
_WINDOW_DAY: float = 86400.0


class RateLimitEnforcer:
    """Deterministic, local rate-limit enforcement against a ScopePolicy.

    Evaluates request intents against per-target rate limits using an
    in-memory state. Does NOT execute requests, DNS lookups, or sleep.

    Usage::

        enforcer = RateLimitEnforcer()
        state = RateLimitState()

        request = RateLimitRequest(
            target="api.example.com",
            timestamp=time.time(),
            request_id="req-1",
        )

        decision = enforcer.check_request(request, policy, state)
        if decision.is_allowed:
            # caller may proceed; request was added to state as active
            state.complete_request(request.request_id)  # when done
        else:
            # blocked — decision.explanation explains why
            # decision.retry_after_seconds suggests when to retry
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_request(
        self,
        request: RateLimitRequest,
        policy: ScopePolicy | None,
        state: RateLimitState,
    ) -> RateLimitDecision:
        """Evaluate a request intent against policy rate limits.

        Args:
            request: The request intent to evaluate (no I/O performed).
            policy: The ScopePolicy containing rate_limits. If None, DENY.
            state: Mutable in-memory request history. Updated on ALLOW only.

        Returns:
            A RateLimitDecision — ALLOW if within all limits, DENY otherwise.
        """
        # --- 0: Missing policy → immediate DENY ---
        if policy is None:
            return self._deny(
                target=request.target,
                reason=RateLimitReason.DENY_MISSING_POLICY,
                explanation="No ScopePolicy provided — all requests are denied.",
            )

        # --- 1: Missing rate limits → immediate DENY (conservative) ---
        limits: RateLimit | None = policy.rate_limits
        if limits is None:
            return self._deny(
                target=request.target,
                reason=RateLimitReason.DENY_MISSING_RATE_LIMIT,
                explanation="ScopePolicy has no rate_limits — all requests are denied.",
                policy_source=policy.source_url,
            )

        # --- 2: Validate target ---
        normalized = self._normalize_target(request.target)
        if not normalized:
            return self._deny(
                target=request.target,
                reason=RateLimitReason.DENY_INVALID_TARGET,
                explanation=f"Target is empty or invalid: {request.target!r}.",
                policy_source=policy.source_url,
            )

        now = request.timestamp if request.timestamp > 0 else time.time()

        # --- 3: Prune state to prevent unbounded growth ---
        state.prune_before(now - _WINDOW_DAY)

        # --- 4: Check concurrent limit ---
        if limits.concurrent_requests is not None:
            active = state.active_count(normalized)
            if active >= limits.concurrent_requests:
                return self._deny_with_violation(
                    target=normalized,
                    reason=RateLimitReason.DENY_CONCURRENT_REQUESTS_EXCEEDED,
                    limit_name="concurrent_requests",
                    limit_value=limits.concurrent_requests,
                    observed_value=active,
                    window_seconds=0,
                    now=now,
                    explanation=(
                        f"Concurrent request limit exceeded for {normalized!r}: "
                        f"{active} active (limit: {limits.concurrent_requests})."
                    ),
                    policy_source=policy.source_url,
                )

        # --- 5: Check per-second limit ---
        if limits.requests_per_second is not None:
            count = state.count_in_window(normalized, _WINDOW_SECOND, now)
            if count >= limits.requests_per_second:
                retry_after = self._calc_retry_after(state, normalized, _WINDOW_SECOND, now)
                return self._deny_with_violation(
                    target=normalized,
                    reason=RateLimitReason.DENY_REQUESTS_PER_SECOND_EXCEEDED,
                    limit_name="requests_per_second",
                    limit_value=limits.requests_per_second,
                    observed_value=count,
                    window_seconds=_WINDOW_SECOND,
                    now=now,
                    retry_after=retry_after,
                    explanation=(
                        f"Requests per second exceeded for {normalized!r}: "
                        f"{count} in window (limit: {limits.requests_per_second})."
                    ),
                    policy_source=policy.source_url,
                )

        # --- 6: Check per-minute limit ---
        if limits.requests_per_minute is not None:
            count = state.count_in_window(normalized, _WINDOW_MINUTE, now)
            if count >= limits.requests_per_minute:
                retry_after = self._calc_retry_after(state, normalized, _WINDOW_MINUTE, now)
                return self._deny_with_violation(
                    target=normalized,
                    reason=RateLimitReason.DENY_REQUESTS_PER_MINUTE_EXCEEDED,
                    limit_name="requests_per_minute",
                    limit_value=limits.requests_per_minute,
                    observed_value=count,
                    window_seconds=_WINDOW_MINUTE,
                    now=now,
                    retry_after=retry_after,
                    explanation=(
                        f"Requests per minute exceeded for {normalized!r}: "
                        f"{count} in window (limit: {limits.requests_per_minute})."
                    ),
                    policy_source=policy.source_url,
                )

        # --- 7: Check per-hour limit ---
        if limits.requests_per_hour is not None:
            count = state.count_in_window(normalized, _WINDOW_HOUR, now)
            if count >= limits.requests_per_hour:
                retry_after = self._calc_retry_after(state, normalized, _WINDOW_HOUR, now)
                return self._deny_with_violation(
                    target=normalized,
                    reason=RateLimitReason.DENY_REQUESTS_PER_HOUR_EXCEEDED,
                    limit_name="requests_per_hour",
                    limit_value=limits.requests_per_hour,
                    observed_value=count,
                    window_seconds=_WINDOW_HOUR,
                    now=now,
                    retry_after=retry_after,
                    explanation=(
                        f"Requests per hour exceeded for {normalized!r}: "
                        f"{count} in window (limit: {limits.requests_per_hour})."
                    ),
                    policy_source=policy.source_url,
                )

        # --- 8: Check per-day limit ---
        if limits.requests_per_day is not None:
            count = state.count_in_window(normalized, _WINDOW_DAY, now)
            if count >= limits.requests_per_day:
                retry_after = self._calc_retry_after(state, normalized, _WINDOW_DAY, now)
                return self._deny_with_violation(
                    target=normalized,
                    reason=RateLimitReason.DENY_REQUESTS_PER_DAY_EXCEEDED,
                    limit_name="requests_per_day",
                    limit_value=limits.requests_per_day,
                    observed_value=count,
                    window_seconds=_WINDOW_DAY,
                    now=now,
                    retry_after=retry_after,
                    explanation=(
                        f"Requests per day exceeded for {normalized!r}: "
                        f"{count} in window (limit: {limits.requests_per_day})."
                    ),
                    policy_source=policy.source_url,
                )

        # --- 9: All checks passed → ALLOW ---
        # Store the request with a normalized target so state queries
        # (which use normalized targets) correctly match.
        normalized_request = RateLimitRequest(
            target=normalized,
            timestamp=request.timestamp,
            method=request.method,
            request_id=request.request_id,
        )
        state.add_request(normalized_request)
        return RateLimitDecision(
            target=normalized,
            status=RateLimitDecisionStatus.ALLOW,
            reason=RateLimitReason.ALLOW_WITHIN_LIMIT,
            explanation=f"Request to {normalized!r} is within all rate limits.",
            policy_source=policy.source_url,
        )

    # ------------------------------------------------------------------
    # Target normalization (mirrors ScopeGuard convention)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_target(target: str) -> str:
        """Normalize a target string for consistent rate-limit tracking.

        Performs:
            - Whitespace stripping
            - Lowercase normalization
            - Scheme stripping (https://, http://)
            - Path/query/fragment stripping (keep only host portion)
            - Trailing dot stripping
            - Empty-target rejection

        Does NOT perform DNS, HTTP, or any network I/O.

        Args:
            target: Raw target string.

        Returns:
            Normalized target string (host only), or empty string if invalid.
        """
        raw = target.strip()
        if not raw:
            return ""

        raw_lower = raw.lower()

        # Strip scheme (e.g. "https://api.example.com/" → "api.example.com/")
        if "://" in raw_lower:
            _, _, raw_lower = raw_lower.partition("://")

        # Strip path, query, fragment — keep only the host portion.
        # "api.example.com/v1/status?a=1#frag" → "api.example.com"
        raw_lower = raw_lower.split("/", 1)[0]
        raw_lower = raw_lower.split("?", 1)[0]
        raw_lower = raw_lower.split("#", 1)[0]

        # Strip trailing dot (FQDN notation)
        raw_lower = raw_lower.rstrip(".")

        if not raw_lower:
            return ""

        return raw_lower

    # ------------------------------------------------------------------
    # Retry-after calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_retry_after(
        state: RateLimitState,
        target: str,
        window_seconds: float,
        now: float,
    ) -> float | None:
        """Calculate how many seconds until a retry might succeed.

        Finds the oldest request in the window and computes the time
        until it expires. If no requests exist in the window, returns None.

        Args:
            state: The current request state.
            target: The normalized target.
            window_seconds: The time window for the violated limit.
            now: Current timestamp.

        Returns:
            Seconds until retry, or None if calculation is not possible.
        """
        cutoff = now - window_seconds
        requests_in_window = [
            r for r in state.requests if r.target == target and r.timestamp > cutoff
        ]
        if not requests_in_window:
            return None
        oldest = min(r.timestamp for r in requests_in_window)
        retry = (oldest + window_seconds) - now
        return max(0.0, retry)

    # ------------------------------------------------------------------
    # Decision helpers
    # ------------------------------------------------------------------

    def _deny(
        self,
        *,
        target: str,
        reason: RateLimitReason,
        explanation: str,
        retry_after: float | None = None,
        policy_source: str | None = None,
    ) -> RateLimitDecision:
        """Create a DENY decision (no violation evidence)."""
        return RateLimitDecision(
            target=target,
            status=RateLimitDecisionStatus.DENY,
            reason=reason,
            retry_after_seconds=retry_after,
            explanation=explanation,
            policy_source=policy_source,
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def _deny_with_violation(
        self,
        *,
        target: str,
        reason: RateLimitReason,
        limit_name: str,
        limit_value: int | float,
        observed_value: int | float,
        window_seconds: int | float,
        now: float,
        explanation: str,
        retry_after: float | None = None,
        policy_source: str | None = None,
    ) -> RateLimitDecision:
        """Create a DENY decision with violation evidence (serializable audit trail)."""
        return RateLimitDecision(
            target=target,
            status=RateLimitDecisionStatus.DENY,
            reason=reason,
            retry_after_seconds=retry_after,
            explanation=explanation,
            policy_source=policy_source,
            violation=RateLimitViolation(
                target=target,
                reason=str(reason),
                limit_name=limit_name,
                limit_value=limit_value,
                observed_value=observed_value,
                window_seconds=window_seconds,
                timestamp=now,
            ),
        )
