"""Evidence State Diffing — Issue #21.

This package implements the EvidenceStateDiffer: a deterministic,
fail-closed diff engine that compares two sanitized
``EvidenceStateSnapshot`` instances and produces an immutable
``EvidenceStateDiff`` result.

Key components:
    - ``EvidenceStateDiffer`` — Core diff engine comparing snapshots.
    - ``EvidenceStateSnapshot`` — Sanitized snapshot of a validation run.
    - ``EvidenceSnapshotItem`` — Sanitized per-item representation.
    - ``EvidenceDiffEntry`` — A single detected change.
    - ``EvidenceStateDiff`` — Aggregated diff result with status and RepairContext.
    - ``RepairContext`` — Manual review context (never auto-fix).
    - ``snapshot_from_bundle()`` — Factory to create snapshots from EvidenceBundles.

Design invariants:
    - Deterministic: same inputs → same outputs (when timestamp is fixed).
    - Fail-closed: any FAIL entry → overall FAIL.
    - No raw evidence content in snapshots or diff output.
    - Sensitive fields are redacted in before/after values.
    - RepairContext never contains commands, shell, HTTP, or auto-fixes.
    - No network I/O, shell, subprocess, DNS, or scanners.
    - No real targets, no active validation.
    - No report submission, upload, or remote logging.
    - No #9 Report Quality Gate.
"""

from neutrino.evidence_diff.differ import EvidenceStateDiffer
from neutrino.evidence_diff.models import (
    REDACTED_MARKER,
    EvidenceChangeType,
    EvidenceDiffEntry,
    EvidenceDiffReasonCode,
    EvidenceDiffSeverity,
    EvidenceDiffStatus,
    EvidenceSnapshotItem,
    EvidenceStateDiff,
    EvidenceStateSnapshot,
    RepairContext,
    is_field_sensitive,
    redact_if_sensitive,
    redact_sensitive_recursive,
    snapshot_from_bundle,
)

__all__ = [
    # Differ
    "EvidenceStateDiffer",
    # Models
    "EvidenceStateSnapshot",
    "EvidenceSnapshotItem",
    "EvidenceDiffEntry",
    "EvidenceStateDiff",
    "RepairContext",
    # Enums
    "EvidenceDiffStatus",
    "EvidenceChangeType",
    "EvidenceDiffReasonCode",
    "EvidenceDiffSeverity",
    # Helpers
    "snapshot_from_bundle",
    "is_field_sensitive",
    "redact_if_sensitive",
    "redact_sensitive_recursive",
    "REDACTED_MARKER",
]
