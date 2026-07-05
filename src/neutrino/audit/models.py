"""AuditLogEvent model for the JSONL AuditLog writer.

This module defines the ``AuditLogEvent`` Pydantic model — a single,
immutable audit entry with mandatory actor, action, target, decision,
and timestamp fields. Every entry also carries a unique id and an
optional freeform ``event`` dictionary for payload data.

The model is designed for JSON serialization and direct consumption
by the append-only ``AuditLogWriter``. Unlike the SQLite
``AuditEvent`` entity (#11), this model does NOT have ``created_at``
/ ``updated_at`` columns (the file mtime serves that purpose) and
requires ``target`` and ``decision`` to be non-empty strings.

Adapter class methods are provided for converting existing
decision models (ScopeDecision, RateLimitDecision,
ProgramPolicyDecision) into ``AuditLogEvent`` instances.

No network I/O. No file I/O. Pure data model.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from neutrino.policy_enforcement.models import ProgramPolicyDecision
    from neutrino.ratelimit.models import RateLimitDecision
    from neutrino.scopeguard.models import ScopeDecision

# ------------------------------------------------------------------
# AuditLogEvent
# ------------------------------------------------------------------


class AuditLogEvent(BaseModel):
    """A single, immutable audit entry for the JSONL AuditLog.

    All fields except ``event`` are mandatory and must be non-empty
    strings. The ``event`` field is an optional freeform dictionary
    for payload-specific data (reason details, violation evidence,
    matched policy entries, etc.).

    Attributes:
        id: Unique identifier (UUID string). Auto-generated if not
            provided.
        actor: Who or what triggered this event (e.g. "scopeguard",
            "ratelimiter", "policy_enforcer", "human_approval").
        action: What action was taken (e.g. "check_target",
            "approve_request", "deny_request").
        target: The target that was evaluated (domain, URL, or
            descriptive identifier). Must be non-empty.
        decision: The decision outcome (e.g. "allow", "deny",
            "deny_unknown_target"). Must be non-empty.
        timestamp: ISO 8601 UTC timestamp of the event. Auto-generated
            if not provided.
        event: Optional freeform dictionary with event payload data
            (reason codes, matched entries, violation evidence, etc.).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    actor: str = Field(min_length=1, description="Who triggered this event")
    action: str = Field(min_length=1, description="What action was taken")
    target: str = Field(min_length=1, description="Target that was evaluated")
    decision: str = Field(min_length=1, description="Decision outcome")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 UTC timestamp",
    )
    event: dict[str, Any] | None = Field(
        default=None,
        description="Optional freeform event payload",
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @field_validator("actor", "action", "target", "decision")
    @classmethod
    def _reject_blank_strings(cls, v: str) -> str:
        """Reject strings that are empty or whitespace-only.

        Raises:
            ValueError: If the value is blank after stripping.
        """
        if not v or not v.strip():
            raise ValueError("must be a non-empty string")
        return v

    # ------------------------------------------------------------------
    # Adapters — convert domain decision models into AuditLogEvent
    # ------------------------------------------------------------------

    @classmethod
    def from_scope_decision(cls, decision: ScopeDecision) -> AuditLogEvent:
        """Create an AuditLogEvent from a ScopeGuard ``ScopeDecision``.

        Args:
            decision: A completed ScopeGuard evaluation.

        Returns:
            AuditLogEvent with actor="scopeguard", action="check_target",
            and the decision's target/status/reason mapped to the audit
            fields.
        """
        return cls(
            actor="scopeguard",
            action="check_target",
            target=decision.target,
            decision=f"{decision.status.value}_{decision.reason.value}",
            event={
                "status": decision.status.value,
                "reason": decision.reason.value,
                "matched_entry": decision.matched_entry,
                "policy_source": decision.policy_source,
                "explanation": decision.explanation,
            },
        )

    @classmethod
    def from_rate_limit_decision(cls, decision: RateLimitDecision) -> AuditLogEvent:
        """Create an AuditLogEvent from a RateLimitEnforcer ``RateLimitDecision``.

        Args:
            decision: A completed rate-limit evaluation.

        Returns:
            AuditLogEvent with actor="ratelimiter", action="check_rate_limit",
            and the decision's target/status/reason mapped to the audit
            fields.
        """
        event_data: dict[str, Any] = {
            "status": decision.status.value,
            "reason": decision.reason.value,
            "retry_after_seconds": decision.retry_after_seconds,
            "explanation": decision.explanation,
            "policy_source": decision.policy_source,
        }
        if decision.violation:
            event_data["violation"] = decision.violation.model_dump()

        return cls(
            actor="ratelimiter",
            action="check_rate_limit",
            target=decision.target,
            decision=f"{decision.status.value}_{decision.reason.value}",
            event=event_data,
        )

    @classmethod
    def from_program_policy_decision(cls, decision: ProgramPolicyDecision) -> AuditLogEvent:
        """Create an AuditLogEvent from a ProgramPolicyEnforcer
        ``ProgramPolicyDecision``.

        Args:
            decision: A completed program-policy evaluation.

        Returns:
            AuditLogEvent with actor="policy_enforcer",
            action="check_program_policy", and the decision's
            target/status/reason mapped to the audit fields.
        """
        event_data: dict[str, Any] = {
            "status": decision.status.value,
            "reason": decision.reason.value,
            "test_type": decision.test_type,
            "explanation": decision.explanation,
            "policy_source": decision.policy_source,
        }
        if decision.violation:
            event_data["violation"] = decision.violation.model_dump()

        return cls(
            actor="policy_enforcer",
            action="check_program_policy",
            target=decision.target,
            decision=f"{decision.status.value}_{decision.reason.value}",
            event=event_data,
        )
