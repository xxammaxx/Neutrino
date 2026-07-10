"""Evidence-State-Diffing domain models — Issue #21.

This module defines all data models for the EvidenceStateDiffer:
snapshots, diff entries, the diff result, and RepairContext.

Key invariants:
    - ALL models use ``extra="forbid"`` (no bypass fields).
    - ALL models are ``frozen=True`` (immutable).
    - Snapshots store only sanitized data (hashes, summaries) — never raw evidence.
    - RepairContext never contains commands, shell, HTTP, or auto-fixes.
    - Sensitive fields are redacted in before/after.
    - Deterministic: same inputs → same outputs.
    - No network I/O. No persistence. Pure domain models.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from neutrino.evidence_oracle.models import SENSITIVE_FIELDS, OracleStatus

# ------------------------------------------------------------------
# Reason Codes
# ------------------------------------------------------------------


class EvidenceDiffReasonCode(StrEnum):
    """Deterministic reason codes for evidence state diffs."""

    ITEM_ADDED = "ITEM_ADDED"
    ITEM_REMOVED = "ITEM_REMOVED"
    CONTENT_CHANGED = "CONTENT_CHANGED"
    SCOPE_CHANGED = "SCOPE_CHANGED"
    REPRODUCIBILITY_MARKER_CHANGED = "REPRODUCIBILITY_MARKER_CHANGED"
    MINIMAL_FLAG_CHANGED = "MINIMAL_FLAG_CHANGED"
    DATA_CLASSIFICATION_CHANGED = "DATA_CLASSIFICATION_CHANGED"
    ORACLE_STATUS_CHANGED = "ORACLE_STATUS_CHANGED"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    MISSING_BASELINE = "MISSING_BASELINE"
    MISSING_CURRENT = "MISSING_CURRENT"
    NO_ITEMS = "NO_ITEMS"
    UNCHANGED = "UNCHANGED"


# ------------------------------------------------------------------
# Diff Status
# ------------------------------------------------------------------


class EvidenceDiffStatus(StrEnum):
    """Aggregated status of the evidence state diff."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


# ------------------------------------------------------------------
# Change Types
# ------------------------------------------------------------------


class EvidenceChangeType(StrEnum):
    """Type of change detected between baseline and current snapshot."""

    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    MISSING_BASELINE = "missing_baseline"
    MISSING_CURRENT = "missing_current"


# ------------------------------------------------------------------
# Severity
# ------------------------------------------------------------------


class EvidenceDiffSeverity(StrEnum):
    """Severity of a single diff entry."""

    INFO = "INFO"
    WARN = "WARN"
    FAIL = "FAIL"


# ------------------------------------------------------------------
# Sensitive Field Redaction
# ------------------------------------------------------------------

#: Normalized set of sensitive field names (case-insensitive, hyphen-to-underscore).
_NORMALIZED_SENSITIVE: frozenset[str] = frozenset(
    k.lower().replace("-", "_") for k in SENSITIVE_FIELDS
)

#: Marker string used for redacted values in before/after fields.
REDACTED_MARKER: str = "[REDACTED]"

#: Maximum size in bytes for content to be included as summary.
#: Content larger than this is represented by hash only.
MAX_CONTENT_SUMMARY_BYTES: int = 64 * 1024  # 64 KiB


def _normalize_key(key: str) -> str:
    """Normalize a key for case-insensitive sensitive-field matching."""
    return key.lower().replace("-", "_")


def is_field_sensitive(field_name: str) -> bool:
    """Return True if ``field_name`` matches a known sensitive field name.

    Matching is case-insensitive and converts hyphens to underscores.
    """
    return _normalize_key(field_name) in _NORMALIZED_SENSITIVE


def redact_sensitive_recursive(data: Any, *, depth: int = 0, max_depth: int = 64) -> Any:
    """Recursively redact sensitive field values in ``data``.

    Replaces values of known sensitive field names (case-insensitive,
    hyphen-to-underscore normalized) with ``REDACTED_MARKER``.

    Handles dicts (by key), lists, and tuples recursively.
    Non-dict/list/tuple values are returned unchanged.

    Args:
        data: The data structure to scan and redact.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth (guard against cyclic structures).

    Returns:
        A redacted copy of ``data`` with sensitive values replaced.
    """
    if depth > max_depth:
        return data

    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for k, v in data.items():
            if is_field_sensitive(k):
                result[k] = REDACTED_MARKER
            else:
                result[k] = redact_sensitive_recursive(v, depth=depth + 1, max_depth=max_depth)
        return result

    if isinstance(data, list):
        return [redact_sensitive_recursive(v, depth=depth + 1, max_depth=max_depth) for v in data]

    if isinstance(data, tuple):
        return tuple(
            redact_sensitive_recursive(v, depth=depth + 1, max_depth=max_depth) for v in data
        )

    return data


def redact_if_sensitive(field_name: str, value: str | None) -> str | None:
    """Return ``REDACTED_MARKER`` if field is sensitive, else ``value`` unchanged."""
    if value is None:
        return None
    if is_field_sensitive(field_name):
        return REDACTED_MARKER
    return value


# ------------------------------------------------------------------
# EvidenceSnapshotItem
# ------------------------------------------------------------------


class EvidenceSnapshotItem(BaseModel):
    """Sanitized representation of a single evidence item.

    Stores only hashes and summaries — never raw content, secrets,
    or sensitive field values.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, description="Unique evidence item identifier")
    kind: str = Field(
        min_length=1,
        description="Evidence kind (http_response, file_hash, screenshot, …)",
    )
    scope_reference: str = Field(min_length=1, description="Scope reference for this evidence")
    source: str = Field(
        min_length=1,
        description="Origin of this evidence (recipe_id, step_id, run_id)",
    )

    content_hash: str = Field(
        min_length=1,
        description="SHA-256 hash of the canonical JSON evidence content",
    )
    content_size_bytes: int = Field(
        ge=0,
        description="Byte size of the serialized evidence content",
    )
    content_summary: str | None = Field(
        default=None,
        description=(
            "Short, sanitized content summary (only for small payloads). "
            "Never contains raw secrets."
        ),
    )

    minimal: bool = Field(
        default=False,
        description="True if only strictly necessary data is included",
    )
    reproducibility_marker_hash: str = Field(
        min_length=1,
        description="SHA-256 hash of the reproducibility marker dict",
    )
    metadata_hash: str | None = Field(
        default=None,
        description="SHA-256 hash of the metadata dict, if present",
    )


# ------------------------------------------------------------------
# EvidenceStateSnapshot
# ------------------------------------------------------------------


class EvidenceStateSnapshot(BaseModel):
    """A snapshot of evidence state for a single validation run.

    Stores sanitized per-item hashes and summaries. Never contains
    raw evidence content, secrets, or sensitive field values.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, description="Unique snapshot identifier")
    run_id: str = Field(min_length=1, description="Validation run identifier")
    bundle_id: str = Field(min_length=1, description="Evidence bundle identifier")
    scope_reference: str = Field(
        min_length=1, description="Expected scope for all items in this snapshot"
    )
    items: list[EvidenceSnapshotItem] = Field(
        default_factory=list,
        description="Sanitized evidence items (sorted by id for determinism)",
    )
    created_at: str = Field(min_length=1, description="ISO 8601 snapshot creation timestamp")
    oracle_result_status: OracleStatus | None = Field(
        default=None,
        description="Oracle evaluation result (PASS, FAIL, WARN), if evaluated",
    )
    oracle_reason_codes: list[str] = Field(
        default_factory=list,
        description="Oracle reason codes from the evaluation (for safety gating)",
    )


# ------------------------------------------------------------------
# EvidenceDiffEntry
# ------------------------------------------------------------------


class EvidenceDiffEntry(BaseModel):
    """A single detected change between baseline and current snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str | None = Field(
        default=None,
        description="Evidence item ID this entry applies to (None for global entries like MISSING_BASELINE)",
    )
    change_type: EvidenceChangeType = Field(description="Type of change detected")
    field: str | None = Field(
        default=None,
        description=("Name of the field that changed. None for added/removed/missing entries."),
    )
    before: str | None = Field(
        default=None,
        description=(
            "Value before the change. Sensitive values are replaced "
            "with [REDACTED]. None for added items."
        ),
    )
    after: str | None = Field(
        default=None,
        description=(
            "Value after the change. Sensitive values are replaced "
            "with [REDACTED]. None for removed items."
        ),
    )
    reason_code: EvidenceDiffReasonCode = Field(description="Machine-readable reason code")
    severity: EvidenceDiffSeverity = Field(description="INFO, WARN, or FAIL")


# ------------------------------------------------------------------
# RepairContext
# ------------------------------------------------------------------


class RepairContext(BaseModel):
    """Context for manual review after a diff operation.

    This is NOT an auto-fix instruction. It contains suggested review
    items and blocked actions only. No commands, shell, HTTP, or
    auto-remediation instructions are ever included.

    ``allowed`` is True only when all safety gates pass:
        - No scope mismatch.
        - Current snapshot exists.
        - Oracle did not fail due to sensitive data.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool = Field(description="True if manual review of this diff is allowed")
    reason: str = Field(min_length=1, description="Human-readable reason for allow/block decision")
    suggested_review_items: list[str] = Field(
        default_factory=list, description="Item IDs suggested for manual review"
    )
    blocked_actions: list[str] = Field(
        default_factory=list, description="Actions that are explicitly blocked"
    )


# ------------------------------------------------------------------
# EvidenceStateDiff
# ------------------------------------------------------------------


class EvidenceStateDiff(BaseModel):
    """Overall result of an evidence state diff operation.

    Aggregates all entries, summary counts, repair context, and
    status determination.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EvidenceDiffStatus = Field(description="Aggregated status: PASS, WARN, or FAIL")
    baseline_id: str | None = Field(
        default=None, description="ID of the baseline snapshot, if provided"
    )
    current_id: str | None = Field(
        default=None, description="ID of the current snapshot, if provided"
    )
    entries: list[EvidenceDiffEntry] = Field(
        default_factory=list, description="All diff entries in deterministic order"
    )
    summary: dict[str, int] = Field(
        default_factory=dict,
        description="Summary counts keyed by category (by_change_type, by_severity)",
    )
    repair_context: RepairContext | None = Field(
        default=None, description="Manual review context (only for allowed runs)"
    )
    errors: list[str] = Field(
        default_factory=list, description="Error descriptions (non-sensitive)"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Warning descriptions (non-sensitive)"
    )
    timestamp: str = Field(min_length=1, description="ISO 8601 diff timestamp")


# ------------------------------------------------------------------
# Factory: Create snapshot from EvidenceBundle and OracleResult
# ------------------------------------------------------------------


def _canonical_json(data: dict[str, Any]) -> str:
    """Serialize ``data`` to canonical JSON with sorted keys.

    Returns a deterministic string representation for hashing.
    """
    import json

    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)


def _sha256(content: str) -> str:
    """Return the SHA-256 hex digest of ``content``."""
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def snapshot_from_bundle(
    bundle: Any,  # EvidenceBundle (avoid circular import)
    *,
    run_id: str,
    snapshot_id: str | None = None,
    oracle_result: Any | None = None,  # EvidenceOracleResult
    timestamp: str | None = None,
) -> EvidenceStateSnapshot:
    """Create an EvidenceStateSnapshot from an EvidenceBundle.

    Extracts sanitized item representations (hashes, summaries) from
    the bundle's evidence items. Never stores raw content.

    Args:
        bundle: An ``EvidenceBundle`` instance.
        run_id: The validation run ID.
        snapshot_id: Optional custom snapshot ID (defaults to bundle.id).
        oracle_result: Optional ``EvidenceOracleResult`` to attach.
        timestamp: ISO 8601 timestamp for the snapshot (uses bundle.created_at if None).

    Returns:
        An immutable ``EvidenceStateSnapshot``.
    """
    items: list[EvidenceSnapshotItem] = []

    for item in bundle.items:
        content_json = _canonical_json(item.content)
        content_bytes = len(content_json.encode("utf-8"))

        # Only generate summary for small payloads
        content_summary: str | None = None
        if content_bytes <= MAX_CONTENT_SUMMARY_BYTES:
            # Recursively redact all sensitive fields in the content
            safe_content = redact_sensitive_recursive(item.content)
            content_summary = _canonical_json(safe_content)
            # Truncate summary to a reasonable length
            if len(content_summary) > 4096:
                content_summary = content_summary[:4093] + "..."

        snapshot_item = EvidenceSnapshotItem(
            id=item.id,
            kind=item.kind,
            scope_reference=item.scope_reference,
            source=item.source,
            content_hash=_sha256(content_json),
            content_size_bytes=content_bytes,
            content_summary=content_summary,
            minimal=item.minimal,
            reproducibility_marker_hash=_sha256(_canonical_json(item.reproducibility_marker)),
            metadata_hash=_sha256(_canonical_json(item.metadata)) if item.metadata else None,
        )
        items.append(snapshot_item)

    # Sort items by id for deterministic ordering
    items.sort(key=lambda i: i.id)

    ts = timestamp
    if ts is None:
        ts = bundle.created_at

    snap_id = snapshot_id if snapshot_id is not None else bundle.id

    oracle_status: OracleStatus | None = None
    oracle_codes: list[str] = []
    if oracle_result is not None:
        oracle_status = oracle_result.status
        oracle_codes = [c.reason_code.value for c in oracle_result.checks]

    return EvidenceStateSnapshot(
        id=snap_id,
        run_id=run_id,
        bundle_id=bundle.id,
        scope_reference=bundle.scope_reference,
        items=items,
        created_at=ts,
        oracle_result_status=oracle_status,
        oracle_reason_codes=oracle_codes,
    )
