"""EvidenceStateDiffer — deterministic evidence state diffing.

This module implements the ``EvidenceStateDiffer`` class that compares
two ``EvidenceStateSnapshot`` instances and produces a deterministic
``EvidenceStateDiff`` result.

The differ is purely deterministic: same inputs always produce the
same outputs, provided the caller supplies a fixed ``timestamp``.

The differ does NOT:
    - Make network requests.
    - Run shell commands or subprocesses.
    - Perform DNS resolution.
    - Execute scanners.
    - Connect to real targets.
    - Upload, log remotely, or submit reports.
    - Produce auto-fix instructions.
    - Perform evidence collection or oracle evaluation.
"""

from __future__ import annotations

from datetime import UTC, datetime

from neutrino.evidence_diff.models import (
    EvidenceChangeType,
    EvidenceDiffEntry,
    EvidenceDiffReasonCode,
    EvidenceDiffSeverity,
    EvidenceDiffStatus,
    EvidenceStateDiff,
    EvidenceStateSnapshot,
    RepairContext,
    redact_if_sensitive,
)

# ------------------------------------------------------------------
# Field Comparison Table
# ------------------------------------------------------------------

#: Field comparison rules used when two items (same ID) are compared.
#:
#: Each entry maps:
#:   field_name → (reason_code, severity_for_change)
_FIELD_RULES: dict[str, tuple[EvidenceDiffReasonCode, EvidenceDiffSeverity]] = {
    "kind": (EvidenceDiffReasonCode.DATA_CLASSIFICATION_CHANGED, EvidenceDiffSeverity.FAIL),
    "scope_reference": (EvidenceDiffReasonCode.SCOPE_CHANGED, EvidenceDiffSeverity.FAIL),
    "content_hash": (EvidenceDiffReasonCode.CONTENT_CHANGED, EvidenceDiffSeverity.WARN),
    "reproducibility_marker_hash": (
        EvidenceDiffReasonCode.REPRODUCIBILITY_MARKER_CHANGED,
        EvidenceDiffSeverity.WARN,
    ),
    "minimal": (EvidenceDiffReasonCode.MINIMAL_FLAG_CHANGED, EvidenceDiffSeverity.WARN),
}

# When minimal changes from True → False, severity upgrades to FAIL
_MINIMAL_DEGRADATION_SEVERITY: EvidenceDiffSeverity = EvidenceDiffSeverity.FAIL


# ------------------------------------------------------------------
# EvidenceStateDiffer
# ------------------------------------------------------------------


class EvidenceStateDiffer:
    """Deterministic evidence state diff engine.

    Compares two ``EvidenceStateSnapshot`` instances (baseline and
    current) and produces an immutable ``EvidenceStateDiff`` result.

    Usage::

        differ = EvidenceStateDiffer()
        diff_result = differ.diff(
            baseline=baseline_snapshot,
            current=current_snapshot,
            timestamp="2026-07-10T12:00:00Z",
        )
    """

    def diff(
        self,
        baseline: EvidenceStateSnapshot | None,
        current: EvidenceStateSnapshot | None,
        *,
        timestamp: str | None = None,
        scope: str | None = None,
    ) -> EvidenceStateDiff:
        """Compare baseline and current snapshots and return a diff result.

        Args:
            baseline: The baseline snapshot to compare against, or None.
            current: The current snapshot to evaluate, or None.
            timestamp: ISO 8601 timestamp for the result.
                If None, current UTC time is used (making the result
                non-deterministic for cross-run comparison).
            scope: Expected scope reference. If provided, mismatches
                against either snapshot's scope produce FAIL entries.

        Returns:
            An immutable ``EvidenceStateDiff`` with aggregated status,
            entries, summary, repair context, errors, and warnings.
        """
        ts = timestamp
        if ts is None:
            ts = datetime.now(UTC).isoformat()

        entries: list[EvidenceDiffEntry] = []
        errors: list[str] = []
        warnings_list: list[str] = []

        baseline_id: str | None = baseline.id if baseline is not None else None
        current_id: str | None = current.id if current is not None else None

        # ------------------------------------------------------------------
        # Both missing
        # ------------------------------------------------------------------
        if baseline is None and current is None:
            entries.append(
                EvidenceDiffEntry(
                    change_type=EvidenceChangeType.MISSING_BASELINE,
                    reason_code=EvidenceDiffReasonCode.MISSING_BASELINE,
                    severity=EvidenceDiffSeverity.FAIL,
                )
            )
            entries.append(
                EvidenceDiffEntry(
                    change_type=EvidenceChangeType.MISSING_CURRENT,
                    reason_code=EvidenceDiffReasonCode.MISSING_CURRENT,
                    severity=EvidenceDiffSeverity.FAIL,
                )
            )
            errors.append("Both baseline and current snapshots are missing.")
            return self._build_result(
                entries=entries,
                errors=errors,
                warnings=warnings_list,
                baseline_id=baseline_id,
                current_id=current_id,
                timestamp=ts,
            )

        # ------------------------------------------------------------------
        # Track missing state
        # ------------------------------------------------------------------
        baseline_missing = baseline is None
        current_missing = current is None

        # ------------------------------------------------------------------
        # Baseline missing only
        # ------------------------------------------------------------------
        if baseline_missing and not current_missing:
            entries.append(
                EvidenceDiffEntry(
                    change_type=EvidenceChangeType.MISSING_BASELINE,
                    reason_code=EvidenceDiffReasonCode.MISSING_BASELINE,
                    severity=EvidenceDiffSeverity.WARN,
                )
            )
            warnings_list.append(
                "Baseline snapshot is missing. Only current snapshot is available."
            )

        # ------------------------------------------------------------------
        # Current missing only
        # ------------------------------------------------------------------
        if current_missing:
            entries.append(
                EvidenceDiffEntry(
                    change_type=EvidenceChangeType.MISSING_CURRENT,
                    reason_code=EvidenceDiffReasonCode.MISSING_CURRENT,
                    severity=EvidenceDiffSeverity.FAIL,
                )
            )
            errors.append("Current snapshot is missing.")
            return self._build_result(
                entries=entries,
                errors=errors,
                warnings=warnings_list,
                baseline_id=baseline_id,
                current_id=current_id,
                timestamp=ts,
            )

        # From here, current is non-None.
        assert current is not None

        # ------------------------------------------------------------------
        # Scope check
        # ------------------------------------------------------------------
        if scope is not None:
            if not baseline_missing:
                assert baseline is not None  # type narrowing
                if baseline.scope_reference != scope:
                    entries.append(
                        EvidenceDiffEntry(
                            change_type=EvidenceChangeType.CHANGED,
                            field="scope_reference",
                            before=redact_if_sensitive("scope_reference", baseline.scope_reference),
                            after=redact_if_sensitive("scope_reference", scope),
                            reason_code=EvidenceDiffReasonCode.SCOPE_MISMATCH,
                            severity=EvidenceDiffSeverity.FAIL,
                        )
                    )
                    errors.append(
                        f"Baseline scope '{baseline.scope_reference}' "
                        f"does not match expected scope '{scope}'."
                    )
            if current.scope_reference != scope:
                entries.append(
                    EvidenceDiffEntry(
                        change_type=EvidenceChangeType.CHANGED,
                        field="scope_reference",
                        before=redact_if_sensitive("scope_reference", current.scope_reference),
                        after=redact_if_sensitive("scope_reference", scope),
                        reason_code=EvidenceDiffReasonCode.SCOPE_MISMATCH,
                        severity=EvidenceDiffSeverity.FAIL,
                    )
                )
                errors.append(
                    f"Current scope '{current.scope_reference}' "
                    f"does not match expected scope '{scope}'."
                )

        # Cross-scope mismatch between baseline and current
        if not baseline_missing:
            assert baseline is not None  # type narrowing
            if baseline.scope_reference != current.scope_reference:
                entries.append(
                    EvidenceDiffEntry(
                        change_type=EvidenceChangeType.CHANGED,
                        field="scope_reference",
                        before=redact_if_sensitive("scope_reference", baseline.scope_reference),
                        after=redact_if_sensitive("scope_reference", current.scope_reference),
                        reason_code=EvidenceDiffReasonCode.SCOPE_MISMATCH,
                        severity=EvidenceDiffSeverity.FAIL,
                    )
                )
                errors.append(
                    f"Baseline scope '{baseline.scope_reference}' "
                    f"does not match current scope '{current.scope_reference}'."
                )

        # ------------------------------------------------------------------
        # Oracle status check on current
        # ------------------------------------------------------------------
        if current.oracle_result_status is not None:
            oracle_changed = (
                baseline_missing
                or baseline.oracle_result_status is None  # type: ignore[union-attr]
                or baseline.oracle_result_status != current.oracle_result_status  # type: ignore[union-attr]
            )
            if oracle_changed:
                entry = EvidenceDiffEntry(
                    change_type=EvidenceChangeType.CHANGED,
                    field="oracle_result_status",
                    before=(
                        baseline.oracle_result_status.value  # type: ignore[union-attr]
                        if not baseline_missing and baseline.oracle_result_status  # type: ignore[union-attr]
                        else None
                    ),
                    after=current.oracle_result_status.value,
                    reason_code=EvidenceDiffReasonCode.ORACLE_STATUS_CHANGED,
                    severity=(
                        EvidenceDiffSeverity.FAIL
                        if current.oracle_result_status.value == "FAIL"
                        else EvidenceDiffSeverity.WARN
                    ),
                )
                entries.append(entry)
                if current.oracle_result_status.value == "FAIL":
                    errors.append("Current snapshot has oracle FAIL status.")
            elif current.oracle_result_status.value == "FAIL":
                # Same FAIL status as baseline, still document it
                entries.append(
                    EvidenceDiffEntry(
                        change_type=EvidenceChangeType.UNCHANGED,
                        field="oracle_result_status",
                        before=current.oracle_result_status.value,
                        after=current.oracle_result_status.value,
                        reason_code=EvidenceDiffReasonCode.ORACLE_STATUS_CHANGED,
                        severity=EvidenceDiffSeverity.FAIL,
                    )
                )
                errors.append("Current snapshot has oracle FAIL status (unchanged from baseline).")

        # ------------------------------------------------------------------
        # No items in current
        # ------------------------------------------------------------------
        if len(current.items) == 0:
            entries.append(
                EvidenceDiffEntry(
                    change_type=EvidenceChangeType.MISSING_CURRENT,
                    reason_code=EvidenceDiffReasonCode.NO_ITEMS,
                    severity=EvidenceDiffSeverity.FAIL,
                )
            )
            errors.append("Current snapshot has no evidence items.")

        # ------------------------------------------------------------------
        # Per-item comparison (only when both have items to compare)
        # ------------------------------------------------------------------
        if not baseline_missing:
            assert baseline is not None  # type narrowing
            self._compare_items(baseline, current, entries)
        else:
            # Baseline missing: document all current items as added-like
            sorted_items = sorted(current.items, key=lambda i: i.id)
            for item in sorted_items:
                entries.append(
                    EvidenceDiffEntry(
                        item_id=item.id,
                        change_type=EvidenceChangeType.MISSING_BASELINE,
                        reason_code=EvidenceDiffReasonCode.MISSING_BASELINE,
                        severity=EvidenceDiffSeverity.WARN,
                    )
                )

        # ------------------------------------------------------------------
        # Build and return
        # ------------------------------------------------------------------
        return self._build_result(
            entries=entries,
            errors=errors,
            warnings=warnings_list,
            baseline_id=baseline_id,
            current_id=current_id,
            timestamp=ts,
            current_for_repair=current,
        )

    # ------------------------------------------------------------------
    # Item comparison
    # ------------------------------------------------------------------

    def _compare_items(
        self,
        baseline: EvidenceStateSnapshot,
        current: EvidenceStateSnapshot,
        entries: list[EvidenceDiffEntry],
    ) -> None:
        """Compare items between baseline and current snapshots.

        Items are matched by ID and compared field by field using
        the field rules table.
        """
        baseline_by_id = {item.id: item for item in baseline.items}
        current_by_id = {item.id: item for item in current.items}

        all_ids = sorted(set(baseline_by_id.keys()) | set(current_by_id.keys()))

        for item_id in all_ids:
            b_item = baseline_by_id.get(item_id)
            c_item = current_by_id.get(item_id)

            # Added
            if b_item is None:
                entries.append(
                    EvidenceDiffEntry(
                        item_id=item_id,
                        change_type=EvidenceChangeType.ADDED,
                        reason_code=EvidenceDiffReasonCode.ITEM_ADDED,
                        severity=EvidenceDiffSeverity.WARN,
                    )
                )
                continue

            # Removed
            if c_item is None:
                entries.append(
                    EvidenceDiffEntry(
                        item_id=item_id,
                        change_type=EvidenceChangeType.REMOVED,
                        reason_code=EvidenceDiffReasonCode.ITEM_REMOVED,
                        severity=EvidenceDiffSeverity.FAIL,
                    )
                )
                continue

            # Both present — field-by-field comparison
            has_changes = False
            for field_name, (reason_code, default_severity) in _FIELD_RULES.items():
                b_val = getattr(b_item, field_name, None)
                c_val = getattr(c_item, field_name, None)

                if b_val == c_val:
                    continue

                has_changes = True
                severity = default_severity

                # Upgrade severity for minimal degradation
                if field_name == "minimal" and b_val is True and c_val is False:
                    severity = _MINIMAL_DEGRADATION_SEVERITY

                before_str = _safe_str(b_val)
                after_str = _safe_str(c_val)

                # Redact sensitive field values
                before_str = redact_if_sensitive(field_name, before_str)
                after_str = redact_if_sensitive(field_name, after_str)

                entries.append(
                    EvidenceDiffEntry(
                        item_id=item_id,
                        change_type=EvidenceChangeType.CHANGED,
                        field=field_name,
                        before=before_str,
                        after=after_str,
                        reason_code=reason_code,
                        severity=severity,
                    )
                )

            # Unchanged item
            if not has_changes:
                entries.append(
                    EvidenceDiffEntry(
                        item_id=item_id,
                        change_type=EvidenceChangeType.UNCHANGED,
                        reason_code=EvidenceDiffReasonCode.UNCHANGED,
                        severity=EvidenceDiffSeverity.INFO,
                    )
                )

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def _build_result(
        self,
        *,
        entries: list[EvidenceDiffEntry],
        errors: list[str],
        warnings: list[str],
        baseline_id: str | None,
        current_id: str | None,
        timestamp: str,
        current_for_repair: EvidenceStateSnapshot | None = None,
    ) -> EvidenceStateDiff:
        """Assemble the final EvidenceStateDiff from collected entries.

        Computes aggregated status, summary counts, and RepairContext.
        """
        # Determine status: any FAIL → FAIL, else any WARN → WARN, else PASS
        status = EvidenceDiffStatus.PASS
        for entry in entries:
            if entry.severity == EvidenceDiffSeverity.FAIL:
                status = EvidenceDiffStatus.FAIL
                break
            elif entry.severity == EvidenceDiffSeverity.WARN:
                status = EvidenceDiffStatus.WARN

        # Build summary
        summary: dict[str, int] = {}
        # By change type
        for entry in entries:
            key = f"by_change_type.{entry.change_type.value}"
            summary[key] = summary.get(key, 0) + 1
        # By severity
        for entry in entries:
            key = f"by_severity.{entry.severity.value}"
            summary[key] = summary.get(key, 0) + 1
        # Total
        summary["total_entries"] = len(entries)

        # Build RepairContext
        repair_context = self._build_repair_context(entries=entries, current=current_for_repair)

        return EvidenceStateDiff(
            status=status,
            baseline_id=baseline_id,
            current_id=current_id,
            entries=entries,
            summary=summary,
            repair_context=repair_context,
            errors=errors,
            warnings=warnings,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # RepairContext
    # ------------------------------------------------------------------

    def _build_repair_context(
        self,
        *,
        entries: list[EvidenceDiffEntry],
        current: EvidenceStateSnapshot | None,
    ) -> RepairContext | None:
        """Build a RepairContext based on safety evaluation.

        RepairContext is only created when:
            - No SCOPE_MISMATCH entries.
            - Current snapshot exists.
            - Current oracle did NOT fail due to SENSITIVE_DATA_DETECTED.

        Even when allowed=True, RepairContext NEVER contains:
            - Commands or shell snippets.
            - HTTP requests or URLs.
            - Auto-fix instructions.
            - Scanner configurations.
        """
        # Determine if repair review is allowed
        has_scope_mismatch = any(
            e.reason_code == EvidenceDiffReasonCode.SCOPE_MISMATCH for e in entries
        )
        has_missing_current = any(
            e.reason_code == EvidenceDiffReasonCode.MISSING_CURRENT for e in entries
        )
        has_sensitive_fail = False
        if current is not None and current.oracle_reason_codes:
            has_sensitive_fail = "SENSITIVE_DATA_DETECTED" in current.oracle_reason_codes

        allowed = not (has_scope_mismatch or has_missing_current or has_sensitive_fail)

        # Collect suggested review item IDs (changed, added, removed items)
        suggested: list[str] = []
        for entry in entries:
            if (
                entry.item_id
                and entry.change_type
                in (
                    EvidenceChangeType.CHANGED,
                    EvidenceChangeType.ADDED,
                    EvidenceChangeType.REMOVED,
                )
                and entry.item_id not in suggested
            ):
                suggested.append(entry.item_id)

        blocked = [
            "automatic_repair",
            "active_validation",
            "network_requests",
            "shell_commands",
            "scanner_execution",
            "auto_fix",
            "report_submission",
        ]

        if allowed:
            reason = "Manual review context only; no automatic actions permitted."
        elif has_scope_mismatch:
            reason = "Diff review blocked: scope mismatch detected."
        elif has_missing_current:
            reason = "Diff review blocked: current snapshot is missing."
        elif has_sensitive_fail:
            reason = "Diff review blocked: oracle detected sensitive data in current snapshot."
        else:
            reason = "Diff review blocked by safety condition."

        return RepairContext(
            allowed=allowed,
            reason=reason,
            suggested_review_items=suggested,
            blocked_actions=blocked,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _safe_str(value: object) -> str | None:
    """Convert a value to a safe string representation.

    Returns None for None input, otherwise str(value).
    Booleans are converted to lowercase strings for consistency.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
