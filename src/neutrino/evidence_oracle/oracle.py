"""EvidenceOracle — deterministic, fail-closed evidence quality evaluation.

This module implements the ``EvidenceOracle`` class that performs
mindestprüfungen (minimum quality checks) on ``EvidenceBundle``
instances. The oracle is purely deterministic: same inputs always
produce the same outputs.

Checks performed:
    1. Bundle existence and non-empty items.
    2. Scope reference per item (match against bundle scope).
    3. Reproducibility marker per item.
    4. Minimal data enforcement per item.
    5. Sensitive field detection (recursive, case-insensitive).
    6. Content presence.
    7. Payload size limits (soft + hard).

The oracle does NOT:
    - Make network requests.
    - Run shell commands or subprocesses.
    - Perform DNS resolution.
    - Execute scanners.
    - Connect to real targets.
    - Upload, log remotely, or submit reports.
    - Perform evidence state diffing (#21).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from neutrino.evidence_oracle.models import (
    HARD_ITEM_CONTENT_BYTES,
    SENSITIVE_FIELDS,
    SOFT_ITEM_CONTENT_BYTES,
    CheckStatus,
    EvidenceBundle,
    EvidenceCheckResult,
    EvidenceItem,
    EvidenceOracleResult,
    OracleStatus,
    ReasonCode,
)

# ------------------------------------------------------------------
# Sensitive Field Detection (recursive, case-insensitive)
# ------------------------------------------------------------------


def _normalize_key(key: str) -> str:
    """Normalize a key for case-insensitive sensitive-field matching.

    Converts to lowercase and replaces hyphens with underscores.
    """
    return key.lower().replace("-", "_")


# Pre-computed normalized set for fast lookups.
_NORMALIZED_SENSITIVE: frozenset[str] = frozenset(_normalize_key(k) for k in SENSITIVE_FIELDS)

#: Maximum recursion depth for sensitive-field scanning.
#: Guards against cyclic or deeply-nested payloads.
_MAX_SCAN_DEPTH: int = 64


def _contains_sensitive_field(data: Any, *, path: str = "", depth: int = 0) -> str | None:
    """Recursively scan ``data`` for known sensitive field names.

    Checks dict keys (case-insensitive, hyphen-to-underscore normalized)
    and recurses into nested dicts, lists, and tuples up to a fixed
    depth to prevent stack overflow from cyclic or deeply nested
    payloads.

    Args:
        data: The data structure to scan.
        path: Current path for error reporting (e.g. "content.headers").
        depth: Current recursion depth (capped at ``_MAX_SCAN_DEPTH``).

    Returns:
        The field path where a sensitive field was found, or ``None``
        if the depth limit was exceeded (fail-safe: treats as no match).
    """
    if depth > _MAX_SCAN_DEPTH:
        return None

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if _normalize_key(key) in _NORMALIZED_SENSITIVE:
                return current_path
            result = _contains_sensitive_field(value, path=current_path, depth=depth + 1)
            if result is not None:
                return result

    elif isinstance(data, (list, tuple)):
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"
            result = _contains_sensitive_field(item, path=current_path, depth=depth + 1)
            if result is not None:
                return result

    return None


# ------------------------------------------------------------------
# Payload Size
# ------------------------------------------------------------------


def _serialized_size(data: dict[str, Any]) -> int:
    """Return the UTF-8 byte size of the JSON-serialized data."""
    try:
        return len(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return -1


# ------------------------------------------------------------------
# Oracle
# ------------------------------------------------------------------


class EvidenceOracle:
    """Deterministic, fail-closed evidence quality evaluator.

    Performs minimum quality checks on an ``EvidenceBundle`` and
    returns an immutable ``EvidenceOracleResult``.

    Usage::

        oracle = EvidenceOracle()
        result = oracle.evaluate(bundle)

    The oracle is stateless and thread-safe. Every call to
    ``evaluate`` with the same input produces the same output,
    provided the caller supplies a fixed ``timestamp``.
    """

    #: Maximum number of items allowed in a bundle.
    MAX_ITEMS: int = 10_000

    #: Allowed evidence kind values (for classification check).
    ALLOWED_KINDS: frozenset[str] = frozenset(
        {
            "http_response",
            "http_request",
            "file_hash",
            "screenshot",
            "log_entry",
            "dns_response",
            "tcp_response",
            "manual_observation",
            "fixture_output",
            "evidence_check",
        }
    )

    def evaluate(
        self,
        bundle: EvidenceBundle | None,
        *,
        timestamp: str | None = None,
    ) -> EvidenceOracleResult:
        """Evaluate an EvidenceBundle and return the oracle result.

        Args:
            bundle: The EvidenceBundle to evaluate, or ``None``.
            timestamp: ISO 8601 timestamp for the result.
                If ``None``, the current UTC time is used (which makes
                the result non-deterministic for cross-run comparison).

        Returns:
            An ``EvidenceOracleResult`` with aggregated status, checks,
            errors, and warnings.
        """
        checks: list[EvidenceCheckResult] = []
        errors: list[str] = []
        warnings: list[str] = []

        # --- 0. Validate timestamp ---
        ts = timestamp if timestamp is not None else datetime.now(UTC).isoformat()
        if not ts or not ts.strip():
            return EvidenceOracleResult(
                status=OracleStatus.FAIL,
                bundle_id=bundle.id if bundle else "",
                checks=[
                    EvidenceCheckResult(
                        check_name="timestamp_validation",
                        status=CheckStatus.FAIL,
                        reason_code=ReasonCode.MISSING_SCOPE_REFERENCE,
                        detail="Timestamp is blank or invalid",
                        item_id=None,
                    )
                ],
                errors=["Invalid or blank timestamp"],
                warnings=[],
                timestamp=datetime.now(UTC).isoformat(),
            )

        # --- 1. Bundle existence ---
        if bundle is None:
            return EvidenceOracleResult(
                status=OracleStatus.FAIL,
                bundle_id="",
                checks=[
                    EvidenceCheckResult(
                        check_name="bundle_existence",
                        status=CheckStatus.FAIL,
                        reason_code=ReasonCode.MISSING_BUNDLE,
                        detail="Evidence bundle is None (missing)",
                        item_id=None,
                    )
                ],
                errors=["Evidence bundle is missing"],
                warnings=[],
                timestamp=ts,
            )

        # --- 2. Items existence ---
        if not bundle.items:
            return EvidenceOracleResult(
                status=OracleStatus.FAIL,
                bundle_id=bundle.id,
                checks=[
                    EvidenceCheckResult(
                        check_name="bundle_not_empty",
                        status=CheckStatus.FAIL,
                        reason_code=ReasonCode.MISSING_ITEMS,
                        detail="Evidence bundle contains no items",
                        item_id=None,
                    )
                ],
                errors=["Evidence bundle contains no items"],
                warnings=[],
                timestamp=ts,
            )

        # --- 2b. MAX_ITEMS enforcement ---
        if len(bundle.items) > self.MAX_ITEMS:
            return EvidenceOracleResult(
                status=OracleStatus.FAIL,
                bundle_id=bundle.id,
                checks=[
                    EvidenceCheckResult(
                        check_name="bundle_size_limit",
                        status=CheckStatus.FAIL,
                        reason_code=ReasonCode.EXCESSIVE_PAYLOAD,
                        detail=(
                            f"Bundle has {len(bundle.items)} items, "
                            f"exceeding maximum of {self.MAX_ITEMS}"
                        ),
                        item_id=None,
                    )
                ],
                errors=[f"Bundle exceeds item limit: {len(bundle.items)} > {self.MAX_ITEMS}"],
                warnings=[],
                timestamp=ts,
            )

        # --- 3. Bundle scope reference ---
        bundle_scope = bundle.scope_reference
        if bundle_scope.strip() == "":
            checks.append(
                EvidenceCheckResult(
                    check_name="bundle_scope",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.MISSING_SCOPE_REFERENCE,
                    detail="Bundle scope_reference is empty",
                    item_id=None,
                )
            )
            errors.append("Bundle scope_reference is empty")
        elif bundle_scope.upper() == "UNKNOWN":
            checks.append(
                EvidenceCheckResult(
                    check_name="bundle_scope",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.UNKNOWN_SCOPE,
                    detail='Bundle scope_reference is "UNKNOWN"',
                    item_id=None,
                )
            )
            errors.append('Bundle scope_reference is "UNKNOWN"')

        # --- 4. Per-item checks ---
        for item in bundle.items:
            self._check_scope(item, bundle_scope, checks, errors)
            self._check_reproducibility(item, checks, errors)
            self._check_minimal_data(item, checks, errors)
            self._check_content(item, checks, errors)

        # --- 5. Aggregate status and collect warnings from WARN checks ---
        agg_status = self._aggregate_status(checks)
        warnings = [c.detail for c in checks if c.status == CheckStatus.WARN]

        return EvidenceOracleResult(
            status=agg_status,
            bundle_id=bundle.id,
            checks=checks,
            errors=errors,
            warnings=warnings,
            timestamp=ts,
        )

    # ------------------------------------------------------------------
    # Individual Checks
    # ------------------------------------------------------------------

    def _check_scope(
        self,
        item: EvidenceItem,
        bundle_scope: str,
        checks: list[EvidenceCheckResult],
        errors: list[str],
    ) -> None:
        """Check that the item's scope_reference matches the bundle's."""
        item_scope = item.scope_reference

        if not item_scope.strip():
            checks.append(
                EvidenceCheckResult(
                    check_name="scope_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.MISSING_SCOPE_REFERENCE,
                    detail=f"Item {item.id} has empty scope_reference",
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: empty scope_reference")
            return

        if item_scope.upper() == "UNKNOWN":
            checks.append(
                EvidenceCheckResult(
                    check_name="scope_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.UNKNOWN_SCOPE,
                    detail=f'Item {item.id} scope_reference is "UNKNOWN"',
                    item_id=item.id,
                )
            )
            errors.append(f'Item {item.id}: scope_reference is "UNKNOWN"')
            return

        if item_scope != bundle_scope:
            checks.append(
                EvidenceCheckResult(
                    check_name="scope_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.SCOPE_MISMATCH,
                    detail=(
                        f"Item {item.id} scope_reference '{item_scope}' "
                        f"does not match bundle scope '{bundle_scope}'"
                    ),
                    item_id=item.id,
                )
            )
            errors.append(
                f"Item {item.id}: scope mismatch (item='{item_scope}', bundle='{bundle_scope}')"
            )
            return

        # Scope OK
        checks.append(
            EvidenceCheckResult(
                check_name="scope_check",
                status=CheckStatus.PASS,
                reason_code=ReasonCode.OK,
                detail=f"Item {item.id} scope matches bundle",
                item_id=item.id,
            )
        )

    def _check_reproducibility(
        self,
        item: EvidenceItem,
        checks: list[EvidenceCheckResult],
        errors: list[str],
    ) -> None:
        """Check that the item has a non-empty reproducibility marker."""
        marker = item.reproducibility_marker

        if not marker:
            checks.append(
                EvidenceCheckResult(
                    check_name="reproducibility_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.NO_REPRODUCIBILITY_MARKER,
                    detail=f"Item {item.id} has no reproducibility_marker",
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: missing reproducibility_marker")
            return

        if not any(marker.values()):
            checks.append(
                EvidenceCheckResult(
                    check_name="reproducibility_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.EMPTY_REPRODUCIBILITY_MARKER,
                    detail=f"Item {item.id} reproducibility_marker has no meaningful values",
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: empty reproducibility_marker")
            return

        checks.append(
            EvidenceCheckResult(
                check_name="reproducibility_check",
                status=CheckStatus.PASS,
                reason_code=ReasonCode.OK,
                detail=f"Item {item.id} reproducibility_marker present",
                item_id=item.id,
            )
        )

    def _check_minimal_data(
        self,
        item: EvidenceItem,
        checks: list[EvidenceCheckResult],
        errors: list[str],
    ) -> None:
        """Check minimal data flag, sensitive fields, and payload size."""
        # --- Minimal flag ---
        if not item.minimal:
            checks.append(
                EvidenceCheckResult(
                    check_name="minimal_data_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.MINIMAL_DATA_VIOLATION,
                    detail=f"Item {item.id} minimal=False (may contain excessive data)",
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: minimal=False")

        # --- Sensitive fields ---
        sensitive_path = _contains_sensitive_field(item.content)
        if sensitive_path is not None:
            checks.append(
                EvidenceCheckResult(
                    check_name="sensitive_data_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.SENSITIVE_DATA_DETECTED,
                    detail=(f"Item {item.id} contains sensitive field at path '{sensitive_path}'"),
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: sensitive field detected at '{sensitive_path}'")

        # Check metadata for sensitive fields too
        sensitive_meta = _contains_sensitive_field(item.metadata)
        if sensitive_meta is not None:
            checks.append(
                EvidenceCheckResult(
                    check_name="sensitive_metadata_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.SENSITIVE_DATA_DETECTED,
                    detail=(
                        f"Item {item.id} metadata contains sensitive field "
                        f"at path '{sensitive_meta}'"
                    ),
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: sensitive field in metadata at '{sensitive_meta}'")

        # --- Payload size ---
        size = _serialized_size(item.content)
        if size < 0:
            checks.append(
                EvidenceCheckResult(
                    check_name="payload_size_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.EXCESSIVE_PAYLOAD,
                    detail=f"Item {item.id} content is not serializable (size check failed)",
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: content not serializable")
        elif size > HARD_ITEM_CONTENT_BYTES:
            checks.append(
                EvidenceCheckResult(
                    check_name="payload_size_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.EXCESSIVE_PAYLOAD,
                    detail=(
                        f"Item {item.id} content size {size} bytes "
                        f"exceeds hard limit of {HARD_ITEM_CONTENT_BYTES} bytes"
                    ),
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: payload {size} bytes exceeds hard limit")
        elif size > SOFT_ITEM_CONTENT_BYTES:
            checks.append(
                EvidenceCheckResult(
                    check_name="payload_size_check",
                    status=CheckStatus.WARN,
                    reason_code=ReasonCode.PAYLOAD_WARN,
                    detail=(
                        f"Item {item.id} content size {size} bytes "
                        f"exceeds soft limit of {SOFT_ITEM_CONTENT_BYTES} bytes"
                    ),
                    item_id=item.id,
                )
            )

        # --- Unknown data classification ---
        if item.kind not in self.ALLOWED_KINDS:
            checks.append(
                EvidenceCheckResult(
                    check_name="data_classification_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.UNKNOWN_DATA_CLASSIFICATION,
                    detail=(
                        f"Item {item.id} kind '{item.kind}' is not in the allowed evidence kinds"
                    ),
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: unknown kind '{item.kind}'")

    def _check_content(
        self,
        item: EvidenceItem,
        checks: list[EvidenceCheckResult],
        errors: list[str],
    ) -> None:
        """Check that the item has non-empty content."""
        if not item.content:
            checks.append(
                EvidenceCheckResult(
                    check_name="content_check",
                    status=CheckStatus.FAIL,
                    reason_code=ReasonCode.MISSING_CONTENT,
                    detail=f"Item {item.id} has empty content",
                    item_id=item.id,
                )
            )
            errors.append(f"Item {item.id}: empty content")
        else:
            checks.append(
                EvidenceCheckResult(
                    check_name="content_check",
                    status=CheckStatus.PASS,
                    reason_code=ReasonCode.OK,
                    detail=f"Item {item.id} content present",
                    item_id=item.id,
                )
            )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_status(checks: list[EvidenceCheckResult]) -> OracleStatus:
        """Compute the aggregated oracle status from individual checks.

        Rules:
            - Any FAIL → FAIL
            - Else any WARN → WARN
            - Else PASS
        """
        has_fail = False
        has_warn = False

        for check in checks:
            if check.status == CheckStatus.FAIL:
                has_fail = True
            elif check.status == CheckStatus.WARN:
                has_warn = True

        if has_fail:
            return OracleStatus.FAIL
        if has_warn:
            return OracleStatus.WARN
        return OracleStatus.PASS
