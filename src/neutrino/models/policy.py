"""Data models for bug bounty scope policies.

These models represent the structured output of the Policy Parser and are
the foundation for all subsequent scope validation and safety decisions.

All models use Pydantic for validation and serialization.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ScopeEntry(BaseModel):
    """A single scope entry — represents one in-scope or out-of-scope asset.

    Attributes:
        pattern: The domain, IP range, URL, or identifier (e.g., "*.example.com").
        type: Asset type — "domain", "wildcard_domain", "ip_range", "url", "api", "unknown".
        is_wildcard: Whether this entry contains a wildcard (e.g., "*.example.com").
        description: Optional human-readable description from the policy.
        source_section: Which policy section this entry was extracted from ("in_scope", "out_of_scope").
        bounty_eligible: Whether this asset is eligible for bounty rewards.
    """

    pattern: str
    type: str = Field(default="domain", description="Asset type")
    is_wildcard: bool = Field(
        default=False, description="Pattern contains a wildcard (e.g. *.example.com)"
    )
    description: str | None = Field(default=None, description="Human-readable description")
    source_section: str | None = Field(
        default=None, description="Policy section of origin (in_scope, out_of_scope)"
    )
    bounty_eligible: bool = Field(default=False, description="Bounty-eligible asset")

    def matches(self, target: str) -> bool:
        """Check if a target matches this scope entry pattern.

        Supports:
        - Exact domain match: "example.com" matches "example.com"
        - Single-level wildcard: "*.example.com" matches "sub.example.com" but NOT "deep.sub.example.com"
        - Subdomain match: "example.com" also matches "sub.example.com" (without explicit wildcard)

        Args:
            target: The target domain or identifier to check.

        Returns:
            True if the target matches this scope entry's pattern.
        """
        # Normalize: strip protocols and trailing slashes
        normalized = target.lower().rstrip("/")
        if normalized.startswith(("https://", "http://")):
            normalized = normalized.split("://", 1)[1]

        pattern_lower = self.pattern.lower()

        # Exact match
        if normalized == pattern_lower:
            return True

        # Single-level wildcard: "*.example.com" matches "sub.example.com" but not "deep.sub.example.com"
        if pattern_lower.startswith("*."):
            base_domain = pattern_lower[2:]  # remove "*."
            parts = normalized.split(".")
            base_parts = base_domain.split(".")
            # The target must end with the base domain and have exactly ONE extra label
            return len(parts) == len(base_parts) + 1 and parts[-len(base_parts) :] == base_parts

        # Subdomain match: "example.com" matches "sub.example.com"
        return normalized.endswith("." + pattern_lower)


class RateLimit(BaseModel):
    """Rate-limit configuration extracted from the policy.

    Attributes:
        requests_per_second: Max requests per second (float for fractional limits).
        requests_per_minute: Max requests per minute.
        requests_per_hour: Max requests per hour.
        requests_per_day: Max requests per day.
        concurrent_requests: Max concurrent connections.
        auto_throttle: Whether to automatically throttle to these limits.
    """

    requests_per_second: float | None = Field(default=None, ge=0)
    requests_per_minute: int | None = Field(default=None, ge=0)
    requests_per_hour: int | None = Field(default=None, ge=0)
    requests_per_day: int | None = Field(default=None, ge=0)
    concurrent_requests: int | None = Field(default=None, ge=0)
    auto_throttle: bool = Field(default=True)


class PolicyRule(BaseModel):
    """A single rule extracted from the policy.

    Attributes:
        description: Human-readable rule description.
        category: Rule category (e.g., "testing", "reporting", "disclosure").
        is_blocking: If True, violation must be blocked (not just warned).
    """

    description: str
    category: str = Field(default="general", description="Rule category")
    is_blocking: bool = Field(default=False, description="Block violation automatically")


class AutomationPolicy(BaseModel):
    """Describes the automation policy extracted from a bug bounty program.

    Attributes:
        status: One of "allowed", "prohibited", "requires_approval", or "unknown".
            Conservative by default: if nothing is found, it is "unknown".
        evidence: The text snippet that led to this classification.
    """

    status: str = Field(
        default="unknown", description="allowed | prohibited | requires_approval | unknown"
    )
    evidence: str | None = Field(
        default=None, description="Snippet that led to this classification"
    )

    @property
    def is_allowed(self) -> bool:
        """Automation is explicitly allowed."""
        return self.status == "allowed"

    @property
    def is_prohibited(self) -> bool:
        """Automation is explicitly prohibited."""
        return self.status == "prohibited"

    @property
    def requires_approval(self) -> bool:
        """Automation requires prior human or program approval."""
        return self.status == "requires_approval"

    @property
    def is_unknown(self) -> bool:
        """Automation policy is unknown (nothing found in the policy text)."""
        return self.status == "unknown"


class ScopePolicy(BaseModel):
    """Complete parsed bug bounty program policy.

    This is the primary output of the Policy Parser. It contains all
    structured information extracted from a bug bounty program policy page.

    Attributes:
        source_url: The URL from which this policy was fetched.
        source_fetched_at: Timestamp of when the policy was fetched.
        program_name: Optional name of the bug bounty program.
        platform: Optional platform identifier (e.g., "hackerone", "bugcrowd").
        in_scope: Assets that are in scope for testing.
        out_of_scope: Assets that are explicitly excluded.
        rate_limits: Rate-limit configuration (None if not specified).
        rules: Policy rules extracted from the text.
        automation_policy: Automation-policy classification (default: unknown).
        allowed_test_types: Test types explicitly allowed by the policy.
        prohibited_test_types: Test types explicitly prohibited by the policy.
        raw_text: The original, unmodified policy text (for audit trail).
    """

    source_url: str
    source_fetched_at: datetime = Field(default_factory=datetime.utcnow)
    program_name: str | None = Field(default=None)
    platform: str | None = Field(default=None)
    in_scope: list[ScopeEntry] = Field(default_factory=list)
    out_of_scope: list[ScopeEntry] = Field(default_factory=list)
    rate_limits: RateLimit | None = Field(default=None)
    rules: list[PolicyRule] = Field(default_factory=list)
    automation_policy: AutomationPolicy = Field(default_factory=AutomationPolicy)
    allowed_test_types: list[str] = Field(default_factory=list)
    prohibited_test_types: list[str] = Field(default_factory=list)
    raw_text: str = Field(default="", description="Original policy text for audit trail")

    def is_in_scope(self, target: str) -> bool:
        """Check if a target is in scope.

        Respects Default-Deny: returns False if target matches nothing
        or if it matches an out_of_scope entry.

        Args:
            target: The target domain or identifier to check.

        Returns:
            True only if the target matches an in_scope entry and does NOT
            match any out_of_scope entry.
        """
        # Check out_of_scope first (explicit exclusions always win)
        for entry in self.out_of_scope:
            if entry.matches(target):
                return False

        # Then check in_scope — Default Deny if no match
        return any(entry.matches(target) for entry in self.in_scope)

    def has_blocking_rules(self) -> bool:
        """Check if the policy contains any blocking rules.

        Returns:
            True if at least one rule has is_blocking=True.
        """
        return any(rule.is_blocking for rule in self.rules)

    def get_blocking_rules(self) -> list[PolicyRule]:
        """Get all blocking rules.

        Returns:
            List of PolicyRule entries where is_blocking=True.
        """
        return [rule for rule in self.rules if rule.is_blocking]
