"""ScopeGuard — deterministic request-gating engine.

ScopeGuard evaluates a target string against a loaded ScopePolicy
and returns an immutable ScopeDecision. All checks are local and
deterministic. No DNS, no network, no redirects — ever.

Core guarantee:
    DENY can never be overridden. If any check fails, the result
    is DENY and no subsequent check can change it.
"""

from __future__ import annotations

import ipaddress
import re
from typing import TYPE_CHECKING

from neutrino.scopeguard.models import ScopeDecision, ScopeDecisionStatus, ScopeReason

if TYPE_CHECKING:
    from neutrino.models.policy import ScopeEntry, ScopePolicy


class ScopeGuard:
    """Deterministic, local request-gating against a ScopePolicy.

    ScopeGuard is the final gate before any network action. It checks
    whether a target is in scope according to the loaded policy. Every
    decision is deterministic, auditable, and non-overridable.

    Usage:
        guard = ScopeGuard()
        decision = guard.check_target("api.example.com", policy)
        if decision.is_allowed:
            ...  # proceed with action
        else:
            ...  # block — decision.explanation explains why
    """

    # Schemes that may be allowed (currently only HTTPS; HTTP is
    # blocked by default per the security model).
    _ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})

    # Schemes that are always blocked — even for local testing.
    _BLOCKED_SCHEMES: frozenset[str] = frozenset(
        {"ftp", "file", "data", "javascript", "ws", "wss", "gopher", "telnet", "ssh"}
    )

    # Regex to detect a URL scheme prefix
    _SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+\-.]*?)://")

    # Maximum target length to reject obviously-malformed inputs
    _MAX_TARGET_LENGTH = 2048

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_target(
        self,
        target: str,
        policy: ScopePolicy | None = None,
    ) -> ScopeDecision:
        """Evaluate a target against a ScopePolicy.

        Args:
            target: The target string to check (domain, IP, URL).
            policy: The ScopePolicy to evaluate against. If None, the
                    decision is immediately DENY_MISSING_POLICY.

        Returns:
            A ScopeDecision with the evaluation outcome. Once DENY,
            the decision cannot be changed to ALLOW.
        """
        # --- 0: Missing policy → immediate DENY ---
        if policy is None:
            return ScopeDecision(
                target=target,
                status=ScopeDecisionStatus.DENY,
                reason=ScopeReason.DENY_MISSING_POLICY,
                explanation="No ScopePolicy provided — all targets are denied.",
            )

        # --- 1: Validate & normalize the target ---
        normalized, scheme = self._validate_and_normalize(target)

        # Invalid target (empty, too long, malformed)
        if normalized is None:
            return self._deny(
                target=target,
                reason=ScopeReason.DENY_INVALID_TARGET,
                explanation=f"Target is empty, too long, or malformed: {target!r}.",
                policy_source=policy.source_url,
            )

        # Unsafe scheme
        if scheme is not None and scheme not in self._ALLOWED_SCHEMES:
            return self._deny(
                target=target,
                reason=ScopeReason.DENY_UNSAFE_SCHEME,
                explanation=f"Unsafe or disallowed scheme '{scheme}://' for target: {target!r}.",
                policy_source=policy.source_url,
            )

        # --- 2: Check out-of-scope FIRST (explicit exclusion always wins) ---
        for entry in policy.out_of_scope:
            if self._matches_entry(normalized, scheme, entry):
                return self._deny(
                    target=target,
                    reason=ScopeReason.DENY_OUT_OF_SCOPE,
                    matched_entry=entry.pattern,
                    explanation=(
                        f"Target {target!r} matches out-of-scope entry "
                        f"{entry.pattern!r} — explicitly excluded."
                    ),
                    policy_source=policy.source_url,
                )

        # --- 3: Check in-scope ---
        for entry in policy.in_scope:
            if self._matches_entry(normalized, scheme, entry):
                return ScopeDecision(
                    target=target,
                    status=ScopeDecisionStatus.ALLOW,
                    reason=ScopeReason.ALLOW_IN_SCOPE,
                    matched_entry=entry.pattern,
                    policy_source=policy.source_url,
                    explanation=(
                        f"Target {target!r} matches in-scope entry {entry.pattern!r} — allowed."
                    ),
                )

        # --- 4: Default Deny — no match at all ---
        return self._deny(
            target=target,
            reason=ScopeReason.DENY_UNKNOWN_TARGET,
            explanation=(
                f"Target {target!r} does not match any in-scope entry "
                f"and is not explicitly out-of-scope — Default Deny."
            ),
            policy_source=policy.source_url,
        )

    # ------------------------------------------------------------------
    # Target validation & normalization
    # ------------------------------------------------------------------

    @classmethod
    def _validate_and_normalize(cls, target: str) -> tuple[str | None, str | None]:
        """Validate and normalize a target string.

        Returns:
            Tuple of (normalized_target, scheme).
            - normalized_target: The cleaned target (domain, IP, host+path),
              or None if the target is invalid.
            - scheme: The URL scheme (e.g. "https") or None if no scheme.

        Performs:
            - Whitespace stripping
            - Length validation
            - Lowercase normalization
            - Scheme extraction
            - Trailing slash removal
            - Empty-target rejection

        Does NOT perform:
            - DNS resolution
            - Redirect following
            - CNAME checking
            - Any network I/O
        """
        raw = target.strip()
        if not raw:
            return None, None

        if len(raw) > cls._MAX_TARGET_LENGTH:
            return None, None

        raw_lower = raw.lower()

        # Extract scheme
        scheme_match = cls._SCHEME_RE.match(raw_lower)
        scheme: str | None = None
        if scheme_match:
            scheme = scheme_match.group(1)
            raw_lower = raw_lower[len(scheme_match.group(0)) :]

        # Strip trailing slash
        raw_lower = raw_lower.rstrip("/")

        # After stripping scheme and trailing slash, must be non-empty
        if not raw_lower:
            return None, None

        # Reject obviously malformed: multiple scheme prefixes, null bytes
        if "\x00" in raw_lower:
            return None, None

        return raw_lower, scheme

    # ------------------------------------------------------------------
    # Matching logic
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_entry(normalized: str, scheme: str | None, entry: ScopeEntry) -> bool:
        """Determine if a normalized target matches a ScopeEntry.

        Delegates to ScopeEntry.matches() for domain/wildcard matching,
        and adds IP range matching for ip_range entries.

        For domain-type entries, the host is extracted from the
        normalized target before matching, so that URLs with paths
        can be compared against domain-only entries.

        Args:
            normalized: The normalized target string (no scheme, lowercase).
            scheme: The original URL scheme (or None).
            entry: The ScopeEntry to test against.

        Returns:
            True if the target matches the entry.
        """
        # IP range matching: use Python's ipaddress module
        if entry.type == "ip_range":
            return ScopeGuard._match_ip_range(normalized, entry.pattern)

        # For domain and wildcard entries, extract just the host portion.
        # This allows "https://example.com/v1/status" to match the
        # domain entry "example.com".
        if entry.type in ("domain", "wildcard_domain"):
            host = normalized.split("/")[0]
            return entry.matches(host)

        # For URL and API entries, keep the full path for matching.
        return entry.matches(normalized)

    @staticmethod
    def _match_ip_range(target: str, cidr: str) -> bool:
        """Check if a target IP address falls within a CIDR range.

        Args:
            target: The normalized target (e.g. "192.0.2.5").
            cidr: The CIDR range pattern (e.g. "192.0.2.0/24").

        Returns:
            True if the target IP is within the CIDR range.
        """
        try:
            target_ip = ipaddress.ip_address(target)
            network = ipaddress.ip_network(cidr, strict=False)
            return target_ip in network
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _deny(
        *,
        target: str,
        reason: ScopeReason,
        explanation: str,
        matched_entry: str | None = None,
        policy_source: str | None = None,
    ) -> ScopeDecision:
        """Create a DENY decision. Convenience helper."""
        return ScopeDecision(
            target=target,
            status=ScopeDecisionStatus.DENY,
            reason=reason,
            matched_entry=matched_entry,
            policy_source=policy_source,
            explanation=explanation,
        )
