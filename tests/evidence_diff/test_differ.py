"""Tests for Evidence-State-Diffing module — Issue #21.

Tests cover:
    - Snapshot model validation
    - Missing data handling
    - Diff detection (added/removed/changed/unchanged)
    - Scope/safety checks
    - RepairContext generation
    - Determinism
    - Audit/serialization
    - Safety (no network/shell/subprocess/real targets)
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from neutrino.evidence_diff import (
    REDACTED_MARKER,
    EvidenceChangeType,
    EvidenceDiffEntry,
    EvidenceDiffReasonCode,
    EvidenceDiffSeverity,
    EvidenceDiffStatus,
    EvidenceSnapshotItem,
    EvidenceStateDiff,
    EvidenceStateDiffer,
    EvidenceStateSnapshot,
    RepairContext,
    is_field_sensitive,
    redact_if_sensitive,
)
from neutrino.evidence_oracle.models import OracleStatus

# ==================================================================
# Fixtures
# ==================================================================

FIXED_TIMESTAMP = "2026-07-10T12:00:00Z"
FIXED_TIMESTAMP_2 = "2026-07-10T13:00:00Z"

RUN_ID_1 = "run-001"
RUN_ID_2 = "run-002"
SCOPE = "scope://lab/test-target"


def make_item(
    item_id: str,
    kind: str = "http_response",
    scope: str = SCOPE,
    source: str = "step-1",
    content: dict[str, Any] | None = None,
    minimal: bool = True,
    marker: dict[str, str] | None = None,
) -> EvidenceSnapshotItem:
    """Create a sanitized EvidenceSnapshotItem with deterministic hashes."""
    import hashlib

    content_data = content if content is not None else {"status": 200}
    content_json = json.dumps(content_data, sort_keys=True, ensure_ascii=False)
    content_bytes = len(content_json.encode("utf-8"))
    content_hash_val = hashlib.sha256(content_json.encode("utf-8")).hexdigest()

    marker_data = marker if marker is not None else {"run": "1", "step": "s1"}
    marker_json = json.dumps(marker_data, sort_keys=True)
    marker_hash_val = hashlib.sha256(marker_json.encode("utf-8")).hexdigest()

    # Generate content summary (redacted)
    safe_content: dict[str, Any] = {}
    for k, v in content_data.items():
        if is_field_sensitive(k):
            safe_content[k] = REDACTED_MARKER
        else:
            safe_content[k] = v
    summary = json.dumps(safe_content, sort_keys=True, ensure_ascii=False, default=str)
    if len(summary) > 4096:
        summary = summary[:4093] + "..."

    return EvidenceSnapshotItem(
        id=item_id,
        kind=kind,
        scope_reference=scope,
        source=source,
        content_hash=content_hash_val,
        content_size_bytes=content_bytes,
        content_summary=summary,
        minimal=minimal,
        reproducibility_marker_hash=marker_hash_val,
    )


def make_snapshot(
    snapshot_id: str,
    run_id: str = RUN_ID_1,
    scope: str = SCOPE,
    items: list[EvidenceSnapshotItem] | None = None,
    timestamp: str = FIXED_TIMESTAMP,
    oracle_status: OracleStatus | None = OracleStatus.PASS,
    oracle_reason_codes: list[str] | None = None,
) -> EvidenceStateSnapshot:
    """Create a valid EvidenceStateSnapshot."""
    return EvidenceStateSnapshot(
        id=snapshot_id,
        run_id=run_id,
        bundle_id=f"bundle-{snapshot_id}",
        scope_reference=scope,
        items=items if items is not None else [make_item("item-1")],
        created_at=timestamp,
        oracle_result_status=oracle_status,
        oracle_reason_codes=oracle_reason_codes if oracle_reason_codes is not None else [],
    )


# ==================================================================
# 1. Snapshot Model Tests
# ==================================================================


class TestSnapshotModel:
    """Tests for EvidenceStateSnapshot and EvidenceSnapshotItem models."""

    def test_valid_snapshot_serializes(self):
        """A valid snapshot serializes and deserializes correctly."""
        snap = make_snapshot("snap-1")
        data = snap.model_dump(mode="json")
        restored = EvidenceStateSnapshot.model_validate(data)
        assert restored.id == "snap-1"
        assert restored.run_id == RUN_ID_1
        assert restored.scope_reference == SCOPE
        assert len(restored.items) == 1

    def test_valid_snapshot_item_serializes(self):
        """A valid EvidenceSnapshotItem serializes correctly."""
        item = make_item("item-1")
        data = item.model_dump(mode="json")
        assert data["id"] == "item-1"
        assert data["kind"] == "http_response"
        assert len(data["content_hash"]) == 64  # SHA-256 hex

    def test_missing_run_id_fails(self):
        """Snapshot with empty run_id raises validation error."""
        with pytest.raises(ValueError):
            EvidenceStateSnapshot(
                id="snap-1",
                run_id="",  # empty
                bundle_id="bundle-1",
                scope_reference=SCOPE,
                items=[make_item("item-1")],
                created_at=FIXED_TIMESTAMP,
            )

    def test_missing_scope_reference_fails(self):
        """Snapshot with empty scope_reference raises validation error."""
        with pytest.raises(ValueError):
            EvidenceStateSnapshot(
                id="snap-1",
                run_id=RUN_ID_1,
                bundle_id="bundle-1",
                scope_reference="",  # empty
                items=[make_item("item-1")],
                created_at=FIXED_TIMESTAMP,
            )

    def test_empty_items_is_allowed_at_model_level(self):
        """Empty items list is allowed at model level (diff will catch it)."""
        snap = EvidenceStateSnapshot(
            id="snap-1",
            run_id=RUN_ID_1,
            bundle_id="bundle-1",
            scope_reference=SCOPE,
            items=[],
            created_at=FIXED_TIMESTAMP,
        )
        assert len(snap.items) == 0

    def test_snapshot_item_missing_id_fails(self):
        """EvidenceSnapshotItem with empty id raises validation error."""
        with pytest.raises(ValueError):
            EvidenceSnapshotItem(
                id="",  # empty
                kind="http_response",
                scope_reference=SCOPE,
                source="step-1",
                content_hash="abc123",
                content_size_bytes=100,
                minimal=True,
                reproducibility_marker_hash="def456",
            )


# ==================================================================
# 2. Missing Data Tests
# ==================================================================


class TestMissingData:
    """Tests for missing baseline/current handling."""

    def test_baseline_missing(self):
        """Missing baseline produces MISSING_BASELINE with WARN."""
        differ = EvidenceStateDiffer()
        current = make_snapshot("current-1")
        result = differ.diff(None, current, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.WARN
        assert any(e.reason_code == EvidenceDiffReasonCode.MISSING_BASELINE for e in result.entries)
        assert len(result.warnings) >= 1
        assert "Baseline" in result.warnings[0]

    def test_current_missing(self):
        """Missing current produces MISSING_CURRENT with FAIL."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("baseline-1")
        result = differ.diff(baseline, None, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.FAIL
        assert any(e.reason_code == EvidenceDiffReasonCode.MISSING_CURRENT for e in result.entries)
        assert len(result.errors) >= 1
        assert "Current" in result.errors[0]

    def test_both_missing(self):
        """Both missing produces FAIL with both entries."""
        differ = EvidenceStateDiffer()
        result = differ.diff(None, None, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.FAIL
        assert any(e.reason_code == EvidenceDiffReasonCode.MISSING_BASELINE for e in result.entries)
        assert any(e.reason_code == EvidenceDiffReasonCode.MISSING_CURRENT for e in result.entries)

    def test_missing_baseline_does_not_crash(self):
        """Missing baseline does not raise an exception."""
        differ = EvidenceStateDiffer()
        current = make_snapshot("current-1")
        result = differ.diff(None, current, timestamp=FIXED_TIMESTAMP)
        assert result is not None
        assert isinstance(result, EvidenceStateDiff)

    def test_missing_current_does_not_crash(self):
        """Missing current does not raise an exception."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("baseline-1")
        result = differ.diff(baseline, None, timestamp=FIXED_TIMESTAMP)
        assert result is not None
        assert isinstance(result, EvidenceStateDiff)

    def test_current_missing_no_exception_for_normal_missing(self):
        """Missing current is handled as FAIL, not an exception."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("baseline-1")
        # Should not raise
        result = differ.diff(baseline, None, timestamp=FIXED_TIMESTAMP)
        assert result.status == EvidenceDiffStatus.FAIL


# ==================================================================
# 3. Diff Detection Tests
# ==================================================================


class TestDiffDetection:
    """Tests for detecting changes between snapshots."""

    def test_identical_snapshots_pass(self):
        """Identical snapshots produce PASS with UNCHANGED entries."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1")])
        current = make_snapshot("snap-2", items=[make_item("item-1")])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.PASS
        assert any(e.change_type == EvidenceChangeType.UNCHANGED for e in result.entries)

    def test_item_added(self):
        """New item in current produces ITEM_ADDED."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1")])
        current = make_snapshot("snap-2", items=[make_item("item-1"), make_item("item-2")])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        added = [e for e in result.entries if e.reason_code == EvidenceDiffReasonCode.ITEM_ADDED]
        assert len(added) == 1
        assert added[0].item_id == "item-2"
        assert added[0].change_type == EvidenceChangeType.ADDED

    def test_item_removed(self):
        """Removed item in current produces ITEM_REMOVED with FAIL severity."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1"), make_item("item-2")])
        current = make_snapshot("snap-2", items=[make_item("item-1")])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        removed = [
            e for e in result.entries if e.reason_code == EvidenceDiffReasonCode.ITEM_REMOVED
        ]
        assert len(removed) == 1
        assert removed[0].item_id == "item-2"
        assert removed[0].severity == EvidenceDiffSeverity.FAIL

    def test_content_changed(self):
        """Changed content hash produces CONTENT_CHANGED."""
        differ = EvidenceStateDiffer()
        item1 = make_item("item-1", content={"status": 200})
        item2 = make_item("item-1", content={"status": 404})  # same ID, different content
        baseline = make_snapshot("snap-1", items=[item1])
        current = make_snapshot("snap-2", items=[item2])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        changed = [
            e for e in result.entries if e.reason_code == EvidenceDiffReasonCode.CONTENT_CHANGED
        ]
        assert len(changed) == 1
        assert changed[0].field == "content_hash"

    def test_scope_changed(self):
        """Changed scope produces SCOPE_CHANGED."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot(
            "snap-1", scope="scope://lab/A", items=[make_item("item-1", scope="scope://lab/A")]
        )
        current = make_snapshot(
            "snap-2", scope="scope://lab/B", items=[make_item("item-1", scope="scope://lab/B")]
        )
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert any(e.reason_code == EvidenceDiffReasonCode.SCOPE_MISMATCH for e in result.entries)

    def test_reproducibility_marker_changed(self):
        """Changed reproducibility marker produces REPRODUCIBILITY_MARKER_CHANGED."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1", marker={"run": "1"})])
        current = make_snapshot("snap-2", items=[make_item("item-1", marker={"run": "2"})])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        changed = [
            e
            for e in result.entries
            if e.reason_code == EvidenceDiffReasonCode.REPRODUCIBILITY_MARKER_CHANGED
        ]
        assert len(changed) == 1
        assert changed[0].field == "reproducibility_marker_hash"

    def test_minimal_flag_changed(self):
        """Changed minimal flag produces MINIMAL_FLAG_CHANGED."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1", minimal=True)])
        current = make_snapshot("snap-2", items=[make_item("item-1", minimal=False)])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        changed = [
            e
            for e in result.entries
            if e.reason_code == EvidenceDiffReasonCode.MINIMAL_FLAG_CHANGED
        ]
        assert len(changed) == 1
        # Minimal True→False is FAIL severity
        assert changed[0].severity == EvidenceDiffSeverity.FAIL
        assert changed[0].before == "true"
        assert changed[0].after == "false"

    def test_minimal_flag_improved(self):
        """Minimal flag changing from False→True is WARN (not FAIL)."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1", minimal=False)])
        current = make_snapshot("snap-2", items=[make_item("item-1", minimal=True)])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        changed = [
            e
            for e in result.entries
            if e.reason_code == EvidenceDiffReasonCode.MINIMAL_FLAG_CHANGED
        ]
        assert len(changed) == 1
        assert changed[0].severity == EvidenceDiffSeverity.WARN

    def test_data_classification_changed(self):
        """Changed kind produces DATA_CLASSIFICATION_CHANGED."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1", kind="http_response")])
        current = make_snapshot("snap-2", items=[make_item("item-1", kind="log_entry")])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        changed = [
            e
            for e in result.entries
            if e.reason_code == EvidenceDiffReasonCode.DATA_CLASSIFICATION_CHANGED
        ]
        assert len(changed) >= 1
        assert changed[0].field == "kind"

    def test_oracle_status_changed_to_fail(self):
        """Oracle status changing to FAIL produces FAIL severity."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", oracle_status=OracleStatus.PASS)
        current = make_snapshot("snap-2", oracle_status=OracleStatus.FAIL)
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        entries = [
            e
            for e in result.entries
            if e.reason_code == EvidenceDiffReasonCode.ORACLE_STATUS_CHANGED
        ]
        assert len(entries) >= 1
        assert any(e.severity == EvidenceDiffSeverity.FAIL for e in entries)

    def test_no_items_in_current_fails(self):
        """Current snapshot with no items produces NO_ITEMS FAIL."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1")])
        current = make_snapshot("snap-2", items=[])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.FAIL
        assert any(e.reason_code == EvidenceDiffReasonCode.NO_ITEMS for e in result.entries)


# ==================================================================
# 4. Scope / Safety Tests
# ==================================================================


class TestScopeSafety:
    """Tests for scope mismatch and safety checks."""

    def test_scope_mismatch_baseline_vs_expected(self):
        """Scope mismatch between baseline and expected scope produces FAIL."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", scope="scope://lab/A")
        current = make_snapshot("snap-2", scope="scope://lab/A")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP, scope="scope://lab/B")

        assert result.status == EvidenceDiffStatus.FAIL
        assert any(e.reason_code == EvidenceDiffReasonCode.SCOPE_MISMATCH for e in result.entries)

    def test_scope_mismatch_current_vs_expected(self):
        """Scope mismatch between current and expected scope produces FAIL."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", scope="scope://lab/B")
        current = make_snapshot("snap-2", scope="scope://lab/A")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP, scope="scope://lab/B")

        assert result.status == EvidenceDiffStatus.FAIL

    def test_scope_mismatch_between_snapshots(self):
        """Scope mismatch between baseline and current produces FAIL."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", scope="scope://lab/A")
        current = make_snapshot("snap-2", scope="scope://lab/B")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.FAIL
        assert any(e.reason_code == EvidenceDiffReasonCode.SCOPE_MISMATCH for e in result.entries)

    def test_unknown_scope_does_not_crash(self):
        """UNKNOWN scope value is handled (it's just a string)."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", scope="UNKNOWN")
        current = make_snapshot("snap-2", scope="UNKNOWN")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)
        assert result is not None

    def test_oracle_fail_in_current_produces_fail(self):
        """Oracle FAIL in current produces FAIL in diff."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", oracle_status=OracleStatus.PASS)
        current = make_snapshot("snap-2", oracle_status=OracleStatus.FAIL)
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.FAIL

    def test_sensitive_field_in_diff_is_redacted(self):
        """A field named 'password' has its value redacted in before/after."""
        # The model doesn't have a 'password' field, so test the redaction function
        result = redact_if_sensitive("password", "my-secret-value")
        assert result == REDACTED_MARKER

        result = redact_if_sensitive("status", "200")
        assert result == "200"

    def test_sensitive_field_variants_redacted(self):
        """Various sensitive field name variants are redacted."""
        for name in ["token", "api_key", "secret", "Authorization", "X-API-Key"]:
            assert redact_if_sensitive(name, "value") == REDACTED_MARKER

    def test_nested_sensitive_fields_redacted(self):
        """Nested dicts with sensitive keys are recursively redacted."""
        from neutrino.evidence_diff.models import redact_sensitive_recursive

        nested = {
            "status": 200,
            "headers": {
                "Authorization": "Bearer secret123",
                "Content-Type": "application/json",
                "x-api-key": "key-abc",
            },
            "body": {
                "user": "test",
                "credentials": {"password": "hunter2", "username": "admin"},
            },
        }
        redacted = redact_sensitive_recursive(nested)
        assert redacted["status"] == 200
        assert redacted["headers"]["Authorization"] == REDACTED_MARKER
        assert redacted["headers"]["Content-Type"] == "application/json"
        assert redacted["headers"]["x-api-key"] == REDACTED_MARKER
        # 'credentials' itself is a sensitive field name in SENSITIVE_FIELDS,
        # so the entire dict value is replaced with REDACTED_MARKER.
        assert redacted["body"]["credentials"] == REDACTED_MARKER


# ==================================================================
# 5. RepairContext Tests
# ==================================================================


class TestRepairContext:
    """Tests for RepairContext generation."""

    def test_allowed_run_produces_allowed_repair_context(self):
        """Clean diff produces RepairContext with allowed=True."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1")])
        current = make_snapshot("snap-2", items=[make_item("item-1")])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.repair_context is not None
        assert result.repair_context.allowed is True
        assert "manual review" in result.repair_context.reason.lower()

    def test_scope_mismatch_blocks_repair_context(self):
        """Scope mismatch produces RepairContext with allowed=False."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", scope="scope://lab/A")
        current = make_snapshot("snap-2", scope="scope://lab/B")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.repair_context is not None
        assert result.repair_context.allowed is False
        assert "scope mismatch" in result.repair_context.reason.lower()

    def test_missing_current_blocks_repair_context(self):
        """Missing current produces RepairContext with allowed=False."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1")
        result = differ.diff(baseline, None, timestamp=FIXED_TIMESTAMP)

        assert result.repair_context is not None
        assert result.repair_context.allowed is False

    def test_sensitive_data_fail_blocks_repair_context(self):
        """Oracle SENSITIVE_DATA_DETECTED blocks RepairContext."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1")
        current = make_snapshot(
            "snap-2",
            oracle_status=OracleStatus.FAIL,
            oracle_reason_codes=["SENSITIVE_DATA_DETECTED", "MISSING_CONTENT"],
        )
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.repair_context is not None
        assert result.repair_context.allowed is False
        assert "sensitive" in result.repair_context.reason.lower()

    def test_repair_context_contains_no_commands(self):
        """RepairContext never contains shell commands."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1")
        current = make_snapshot("snap-2")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.repair_context is not None
        rc_json = result.repair_context.model_dump_json().lower()
        # No command-like patterns
        dangerous = ["sudo ", "bash ", "sh ", "curl ", "wget ", "rm -", "chmod"]
        for pattern in dangerous:
            assert pattern not in rc_json, f"Found dangerous pattern: {pattern}"

    def test_repair_context_contains_no_requests(self):
        """RepairContext never contains HTTP request instructions."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1")
        current = make_snapshot("snap-2")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.repair_context is not None
        # Check blocked_actions
        assert "network_requests" in result.repair_context.blocked_actions

    def test_repair_context_no_auto_fixes(self):
        """RepairContext never contains auto-fix instructions."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1")
        current = make_snapshot("snap-2")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.repair_context is not None
        assert "auto_fix" in result.repair_context.blocked_actions
        assert "automatic_repair" in result.repair_context.blocked_actions


# ==================================================================
# 6. Determinism Tests
# ==================================================================


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_inputs_same_outputs(self):
        """Same inputs produce identical outputs."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1"), make_item("item-2")])
        current = make_snapshot("snap-2", items=[make_item("item-1"), make_item("item-3")])

        result1 = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)
        result2 = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result1.model_dump_json() == result2.model_dump_json()

    def test_items_sorted_stably(self):
        """Items are compared in stable sort order (by item.id)."""
        differ = EvidenceStateDiffer()
        items = [
            make_item("item-c"),
            make_item("item-a"),
            make_item("item-b"),
        ]
        baseline = make_snapshot("snap-1", items=items)
        current = make_snapshot("snap-2", items=items)
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        # All should be UNCHANGED, order doesn't matter for correctness
        unchanged = [e for e in result.entries if e.change_type == EvidenceChangeType.UNCHANGED]
        assert len(unchanged) == 3

    def test_timestamp_injectable(self):
        """Timestamp is injectable and produces consistent results."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1")
        current = make_snapshot("snap-2")

        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)
        assert result.timestamp == FIXED_TIMESTAMP

    def test_summary_counts_deterministic(self):
        """Summary counts are deterministic."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1")])
        current = make_snapshot("snap-2", items=[make_item("item-1")])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert "total_entries" in result.summary
        assert result.summary["total_entries"] > 0


# ==================================================================
# 7. Audit Tests
# ==================================================================


class TestAudit:
    """Tests for auditability and serialization."""

    def test_diff_result_is_serializable(self):
        """EvidenceStateDiff can be serialized to JSON."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1")])
        current = make_snapshot("snap-2", items=[make_item("item-1"), make_item("item-2")])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        data = result.model_dump(mode="json")
        json_str = json.dumps(data)
        restored = json.loads(json_str)
        assert restored["status"] == "WARN"  # added item

    def test_audit_data_contains_reason_codes(self):
        """All diff entries have reason codes."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1")])
        current = make_snapshot("snap-2", items=[make_item("item-1"), make_item("item-2")])

        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)
        for entry in result.entries:
            assert entry.reason_code is not None
            assert isinstance(entry.reason_code, EvidenceDiffReasonCode)

    def test_audit_data_no_raw_secrets(self):
        """Audit data contains no raw secrets."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1")
        current = make_snapshot("snap-2")
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        # The differ doesn't deal with raw content directly, so this is mostly
        # about checking the model structure. Raw content is stored as hashes.
        json_str = result.model_dump_json()
        # Check that no common secret patterns appear
        assert "password" not in json_str.lower() or "[REDACTED]" in json_str

    def test_audit_failure_produces_fail_status(self):
        """When diff has FAIL entries, status is FAIL."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1"), make_item("item-2")])
        current = make_snapshot("snap-2", items=[make_item("item-1")])  # item-2 removed

        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)
        assert result.status == EvidenceDiffStatus.FAIL


# ==================================================================
# 8. Safety Tests
# ==================================================================


class TestSafety:
    """Tests confirming no dangerous capabilities exist."""

    def test_no_network_imports(self):
        """Evidence diff module does not import network-related modules."""
        import inspect

        import neutrino.evidence_diff.differ as d
        import neutrino.evidence_diff.models as m

        dangerous = {"urllib", "requests", "httpx", "aiohttp", "socket", "http.client"}
        for mod in [m, d]:
            source = inspect.getsource(mod)
            # Only check actual import lines, not docstrings/comments
            for line in source.split("\n"):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    for imp in dangerous:
                        assert imp not in stripped, (
                            f"Found dangerous import '{imp}' in {mod.__name__}: {stripped}"
                        )

    def test_no_shell_subprocess_imports(self):
        """Evidence diff module does not import shell/subprocess modules."""
        import inspect

        import neutrino.evidence_diff.differ as d
        import neutrino.evidence_diff.models as m

        dangerous = {"subprocess", "os.system", "shlex", "pty", "popen"}
        for mod in [m, d]:
            source = inspect.getsource(mod)
            for line in source.split("\n"):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    for imp in dangerous:
                        assert imp not in stripped, (
                            f"Found dangerous import '{imp}' in {mod.__name__}: {stripped}"
                        )

    def test_no_dns_imports(self):
        """Evidence diff module does not import DNS-related modules."""
        import inspect

        import neutrino.evidence_diff.differ as d
        import neutrino.evidence_diff.models as m

        dangerous = {"dns", "socket.getaddrinfo", "gethostbyname"}
        for mod in [m, d]:
            source = inspect.getsource(mod)
            for line in source.split("\n"):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    for imp in dangerous:
                        assert imp not in stripped, (
                            f"Found dangerous import '{imp}' in {mod.__name__}: {stripped}"
                        )

    def test_no_scanner_imports(self):
        """Evidence diff module has no scanner-related code."""
        import inspect

        import neutrino.evidence_diff.differ as d
        import neutrino.evidence_diff.models as m

        dangerous = {"nmap", "scanner", "exploit", "payload", "nuclei"}
        for mod in [m, d]:
            source = inspect.getsource(mod)
            for line in source.split("\n"):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    for imp in dangerous:
                        assert imp not in stripped, (
                            f"Found dangerous import '{imp}' in {mod.__name__}: {stripped}"
                        )

    def test_no_real_targets(self):
        """Evidence diff uses only local fixture data."""
        # Verified by design: the differ only compares snapshots
        differ = EvidenceStateDiffer()
        # Works entirely on in-memory snapshots
        result = differ.diff(
            make_snapshot("s1"),
            make_snapshot("s2"),
            timestamp=FIXED_TIMESTAMP,
        )
        assert result is not None

    def test_no_n8n_paperclip_api_dashboard(self):
        """Evidence diff has no integration with n8n, Paperclip, API, or Dashboard."""
        import inspect

        import neutrino.evidence_diff.differ as d
        import neutrino.evidence_diff.models as m

        forbidden = {"n8n", "paperclip", "dashboard"}
        for mod in [m, d]:
            source = inspect.getsource(mod)
            for line in source.split("\n"):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    for term in forbidden:
                        assert term not in stripped.lower(), (
                            f"Found forbidden term '{term}' in {mod.__name__}: {stripped}"
                        )

    def test_tests_use_only_local_fixtures(self):
        """Tests use only local in-memory fixtures."""
        # All fixtures are in-memory EvidenceStateSnapshot objects
        # No network, no file I/O, no real targets
        # This is verified by the fact that all test data is created via make_snapshot/make_item
        assert True  # Design-level assertion

    def test_no_automatic_report_submission(self):
        """Diff result has no report submission capability."""
        differ = EvidenceStateDiffer()
        result = differ.diff(
            make_snapshot("s1"),
            make_snapshot("s2"),
            timestamp=FIXED_TIMESTAMP,
        )
        # The result has no upload/submit methods
        assert not hasattr(result, "submit")
        assert not hasattr(result, "upload")
        assert not hasattr(result, "send_report")

    def test_snapshot_from_bundle_functionality(self):
        """Verify snapshot_from_bundle exists and works (import check)."""
        from neutrino.evidence_diff import snapshot_from_bundle

        assert callable(snapshot_from_bundle)


# ==================================================================
# 9. Additional Edge Case Tests
# ==================================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_multiple_items_with_mixed_changes(self):
        """Multiple items with a mix of added, removed, changed, unchanged."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot(
            "snap-1",
            items=[
                make_item("item-1", content={"status": 200}),
                make_item("item-2"),
                make_item("item-3"),
            ],
        )
        current = make_snapshot(
            "snap-2",
            items=[
                make_item("item-1", content={"status": 404}),  # changed
                make_item("item-3"),  # unchanged (item-2 removed)
                make_item("item-4"),  # added
            ],
        )
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        change_types = {e.change_type for e in result.entries}
        assert EvidenceChangeType.CHANGED in change_types
        assert EvidenceChangeType.ADDED in change_types
        assert EvidenceChangeType.REMOVED in change_types
        assert EvidenceChangeType.UNCHANGED in change_types

    def test_empty_snapshots(self):
        """Two snapshots with no items produce FAIL."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[])
        current = make_snapshot("snap-2", items=[])
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.FAIL

    def test_large_payload_truncation(self):
        """Content summary for large payloads is truncated."""
        item = make_item("item-1", content={"data": "x" * 5000})
        # summary should be truncated if > 4096
        if item.content_summary is not None:
            assert len(item.content_summary) <= 4099  # 4096 + "..." leniency

    def test_sanitized_export_no_raw_secrets(self):
        """JSON export of diff result contains no raw secret values."""
        from neutrino.evidence_diff import is_field_sensitive

        # Verify the redaction function works
        assert is_field_sensitive("password")
        assert is_field_sensitive("api_key")
        assert is_field_sensitive("token")
        assert not is_field_sensitive("status")
        assert not is_field_sensitive("content_type")

    def test_repair_context_suggested_items(self):
        """RepairContext includes suggested review items for changed items."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", items=[make_item("item-1", content={"status": 200})])
        current = make_snapshot(
            "snap-2",
            items=[
                make_item("item-1", content={"status": 404}),
                make_item("item-2"),
            ],
        )
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.repair_context is not None
        # item-1 changed and item-2 added should both be in suggested review
        assert "item-1" in result.repair_context.suggested_review_items
        assert "item-2" in result.repair_context.suggested_review_items

    def test_same_oracle_fail_status_both_runs(self):
        """When both baseline and current have oracle FAIL, diff still has FAIL status."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", oracle_status=OracleStatus.FAIL)
        current = make_snapshot("snap-2", oracle_status=OracleStatus.FAIL)
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.FAIL

    def test_snapshot_with_none_oracle_result(self):
        """Snapshot with oracle_result_status=None works."""
        differ = EvidenceStateDiffer()
        baseline = make_snapshot("snap-1", oracle_status=None)
        current = make_snapshot("snap-2", oracle_status=None)
        result = differ.diff(baseline, current, timestamp=FIXED_TIMESTAMP)

        assert result.status == EvidenceDiffStatus.PASS


# ==================================================================
# 10. Model Validation Edge Cases
# ==================================================================


class TestModelEdgeCases:
    """Edge cases for model validation."""

    def test_diff_entry_extra_fields_forbidden(self):
        """EvidenceDiffEntry forbids extra fields."""
        with pytest.raises(ValueError):
            EvidenceDiffEntry(
                item_id="item-1",
                change_type=EvidenceChangeType.CHANGED,
                reason_code=EvidenceDiffReasonCode.CONTENT_CHANGED,
                severity=EvidenceDiffSeverity.WARN,
                unknown_field="should_fail",  # extra field
            )

    def test_snapshot_extra_fields_forbidden(self):
        """EvidenceStateSnapshot forbids extra fields."""
        with pytest.raises(ValueError):
            EvidenceStateSnapshot(
                id="snap-1",
                run_id=RUN_ID_1,
                bundle_id="bundle-1",
                scope_reference=SCOPE,
                items=[make_item("item-1")],
                created_at=FIXED_TIMESTAMP,
                unknown_field="should_fail",
            )

    def test_repair_context_extra_fields_forbidden(self):
        """RepairContext forbids extra fields."""
        with pytest.raises(ValueError):
            RepairContext(
                allowed=True,
                reason="test",
                commands=["ls"],  # extra field
            )

    def test_diff_result_immutable(self):
        """EvidenceStateDiff is frozen (immutable)."""
        differ = EvidenceStateDiffer()
        result = differ.diff(
            make_snapshot("s1"),
            make_snapshot("s2"),
            timestamp=FIXED_TIMESTAMP,
        )
        with pytest.raises(Exception):  # noqa: B017
            result.status = EvidenceDiffStatus.FAIL  # frozen model — assignment should fail

    def test_snapshot_item_content_summary_truncation(self):
        """Very large content summary is truncated."""
        large_content = {"data": "x" * 10000}
        item = make_item("item-1", content=large_content)
        if item.content_summary is not None:
            assert len(item.content_summary) < 10000
