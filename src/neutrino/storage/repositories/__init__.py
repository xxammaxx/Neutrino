"""Neutrino Storage Repositories — CRUD access layer for all Core Entities.

This package provides deterministic, explicit-SQL repositories for:

- ``Program``
- ``ScopePolicy``
- ``Target``
- ``ResearchRun``
- ``FindingHypothesis``
- ``Evidence``
- ``HumanApproval``
- ``AuditEvent`` (append-only)

All repositories operate on a local SQLite database path, use parameterized
queries, enforce foreign keys, and return typed entity models.

No ORM, no magic, no network I/O.
"""

from neutrino.storage.repositories.audit_events import AuditEventRepository
from neutrino.storage.repositories.evidence import EvidenceRepository
from neutrino.storage.repositories.finding_hypotheses import FindingHypothesisRepository
from neutrino.storage.repositories.human_approvals import HumanApprovalRepository
from neutrino.storage.repositories.programs import ProgramRepository
from neutrino.storage.repositories.research_runs import ResearchRunRepository
from neutrino.storage.repositories.scope_policies import ScopePolicyRepository
from neutrino.storage.repositories.targets import TargetRepository

__all__ = [
    "AuditEventRepository",
    "EvidenceRepository",
    "FindingHypothesisRepository",
    "HumanApprovalRepository",
    "ProgramRepository",
    "ResearchRunRepository",
    "ScopePolicyRepository",
    "TargetRepository",
]
