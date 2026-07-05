"""Core entity models for Neutrino Storage.

Pydantic models representing the 8 core entities in the Neutrino schema.
These models are used by the repository layer for validation, serialization,
and typed interfaces.

All IDs are UUIDs stored as strings. Timestamps are ISO 8601 strings.
"""

from __future__ import annotations

from pydantic import BaseModel

# ------------------------------------------------------------------
# Program
# ------------------------------------------------------------------


class Program(BaseModel):
    """A bug bounty program with platform and policy URL."""

    id: str  # UUID
    name: str
    platform: str | None = None
    policy_url: str | None = None
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601


class ProgramCreate(BaseModel):
    """Input for creating a Program (id, name are required)."""

    id: str
    name: str
    platform: str | None = None
    policy_url: str | None = None


class ProgramUpdate(BaseModel):
    """Input for updating a Program (all fields optional)."""

    name: str | None = None
    platform: str | None = None
    policy_url: str | None = None


# ------------------------------------------------------------------
# ScopePolicy
# ------------------------------------------------------------------


class ScopePolicy(BaseModel):
    """A parsed scope policy document linked to a Program."""

    id: str
    program_id: str | None = None
    source_url: str
    raw_text: str | None = None
    parsed_json: str  # JSON-serialized parsed policy
    created_at: str
    updated_at: str


class ScopePolicyCreate(BaseModel):
    """Input for creating a ScopePolicy."""

    id: str
    program_id: str | None = None
    source_url: str
    raw_text: str | None = None
    parsed_json: str


class ScopePolicyUpdate(BaseModel):
    """Input for updating a ScopePolicy."""

    program_id: str | None = None
    source_url: str | None = None
    raw_text: str | None = None
    parsed_json: str | None = None


# ------------------------------------------------------------------
# Target
# ------------------------------------------------------------------


class Target(BaseModel):
    """A scope target (domain, IP range, URL, etc.) linked to a Program."""

    id: str
    program_id: str | None = None
    pattern: str
    type: str  # "domain", "wildcard_domain", etc.
    source_section: str | None = None
    is_wildcard: bool = False
    created_at: str
    updated_at: str


class TargetCreate(BaseModel):
    """Input for creating a Target."""

    id: str
    program_id: str | None = None
    pattern: str
    type: str
    source_section: str | None = None
    is_wildcard: bool = False


class TargetUpdate(BaseModel):
    """Input for updating a Target."""

    program_id: str | None = None
    pattern: str | None = None
    type: str | None = None
    source_section: str | None = None
    is_wildcard: bool | None = None


# ------------------------------------------------------------------
# ResearchRun
# ------------------------------------------------------------------


class ResearchRun(BaseModel):
    """A research run linked to a Program."""

    id: str
    program_id: str | None = None
    status: str  # "pending", "running", "completed", etc.
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str
    updated_at: str


class ResearchRunCreate(BaseModel):
    """Input for creating a ResearchRun."""

    id: str
    program_id: str | None = None
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None


class ResearchRunUpdate(BaseModel):
    """Input for updating a ResearchRun."""

    program_id: str | None = None
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


# ------------------------------------------------------------------
# FindingHypothesis
# ------------------------------------------------------------------


class FindingHypothesis(BaseModel):
    """A security finding hypothesis linked to a ResearchRun."""

    id: str
    research_run_id: str | None = None
    title: str
    status: str  # "open", "confirmed", "rejected", etc.
    risk_level: str | None = None
    created_at: str
    updated_at: str


class FindingHypothesisCreate(BaseModel):
    """Input for creating a FindingHypothesis."""

    id: str
    research_run_id: str | None = None
    title: str
    status: str = "open"
    risk_level: str | None = None


class FindingHypothesisUpdate(BaseModel):
    """Input for updating a FindingHypothesis."""

    research_run_id: str | None = None
    title: str | None = None
    status: str | None = None
    risk_level: str | None = None


# ------------------------------------------------------------------
# Evidence
# ------------------------------------------------------------------


class Evidence(BaseModel):
    """Evidence (screenshot, log, etc.) linked to a FindingHypothesis."""

    id: str
    finding_hypothesis_id: str | None = None
    kind: str  # "screenshot", "log", "request", "response", etc.
    content_json: str  # JSON-serialized evidence content
    source: str | None = None
    created_at: str
    updated_at: str


class EvidenceCreate(BaseModel):
    """Input for creating Evidence."""

    id: str
    finding_hypothesis_id: str | None = None
    kind: str
    content_json: str
    source: str | None = None


class EvidenceUpdate(BaseModel):
    """Input for updating Evidence."""

    finding_hypothesis_id: str | None = None
    kind: str | None = None
    content_json: str | None = None
    source: str | None = None


# ------------------------------------------------------------------
# HumanApproval
# ------------------------------------------------------------------


class HumanApproval(BaseModel):
    """A human approval decision linked to a ResearchRun."""

    id: str
    research_run_id: str | None = None
    actor: str
    decision: str  # "approved", "rejected", "pending"
    reason: str | None = None
    created_at: str
    updated_at: str


class HumanApprovalCreate(BaseModel):
    """Input for creating a HumanApproval."""

    id: str
    research_run_id: str | None = None
    actor: str
    decision: str
    reason: str | None = None


class HumanApprovalUpdate(BaseModel):
    """Input for updating a HumanApproval."""

    research_run_id: str | None = None
    actor: str | None = None
    decision: str | None = None
    reason: str | None = None


# ------------------------------------------------------------------
# AuditEvent
# ------------------------------------------------------------------


class AuditEvent(BaseModel):
    """An immutable audit event logged in the system.

    AuditEvents are append-only: update and delete are forbidden.
    They have no foreign keys (by design) to ensure they never
    block referential integrity.
    """

    id: str
    actor: str
    action: str
    target: str | None = None
    decision: str | None = None
    event_json: str  # JSON-serialized event payload
    timestamp: str  # ISO 8601 event time
    created_at: str
    updated_at: str


class AuditEventCreate(BaseModel):
    """Input for creating an AuditEvent (append-only)."""

    id: str
    actor: str
    action: str
    target: str | None = None
    decision: str | None = None
    event_json: str
    timestamp: str
