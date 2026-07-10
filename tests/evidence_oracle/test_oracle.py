"""Tests for the EvidenceOracle — Issue #20.

Covers all minimum checks:
    - Missing Evidence → FAIL
    - Reproducibility
    - Scope reference
    - Minimal data / sensitive fields
    - Content presence
    - Payload limits
    - Result model serialization
    - Determinism
    - Safety (no network/shell/real-target imports)

All tests use only local fixtures. No real targets, no network.
"""

from __future__ import annotations

import pytest

from neutrino.evidence_oracle import (
    HARD_ITEM_CONTENT_BYTES,
    SENSITIVE_FIELDS,
    SOFT_ITEM_CONTENT_BYTES,
    CheckStatus,
    EvidenceBundle,
    EvidenceItem,
    EvidenceOracle,
    OracleStatus,
    ReasonCode,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def oracle() -> EvidenceOracle:
    """Return a fresh EvidenceOracle instance."""
    return EvidenceOracle()


@pytest.fixture
def fixed_timestamp() -> str:
    """A fixed timestamp for deterministic tests."""
    return "2026-07-09T00:00:00.000000+00:00"


@pytest.fixture
def valid_item() -> EvidenceItem:
    """A fully valid evidence item."""
    return EvidenceItem(
        id="item-001",
        kind="http_response",
        scope_reference="scope://example.com/v1",
        source="recipe_id=rec-1;step_id=step-1",
        content={"status": 200, "body": "OK"},
        collected_at="2026-07-09T00:00:00Z",
        minimal=True,
        reproducibility_marker={"run_id": "run-1", "step_id": "step-1", "recipe_id": "rec-1"},
    )


@pytest.fixture
def valid_bundle(valid_item: EvidenceItem, fixed_timestamp: str) -> EvidenceBundle:
    """A fully valid evidence bundle with one item."""
    return EvidenceBundle(
        id="bundle-001",
        finding_id="finding-001",
        scope_reference="scope://example.com/v1",
        items=[valid_item],
        created_at=fixed_timestamp,
    )


@pytest.fixture
def second_valid_item() -> EvidenceItem:
    """A second valid evidence item, same scope."""
    return EvidenceItem(
        id="item-002",
        kind="file_hash",
        scope_reference="scope://example.com/v1",
        source="recipe_id=rec-1;step_id=step-2",
        content={"sha256": "abc123"},
        collected_at="2026-07-09T00:00:01Z",
        minimal=True,
        reproducibility_marker={"run_id": "run-1", "step_id": "step-2"},
    )


# ------------------------------------------------------------------
# 1. Missing Evidence → FAIL
# ------------------------------------------------------------------


class TestMissingEvidence:
    """Bundle is None, empty, or items have no content."""

    def test_none_bundle_returns_fail(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        result = oracle.evaluate(None, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert result.bundle_id == ""
        assert len(result.checks) == 1
        assert result.checks[0].reason_code == ReasonCode.MISSING_BUNDLE
        assert result.checks[0].check_name == "bundle_existence"
        assert "missing" in result.errors[0].lower()

    def test_empty_bundle_items_returns_fail(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        bundle = EvidenceBundle(
            id="empty-1",
            scope_reference="scope://example.com",
            items=[],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert result.bundle_id == "empty-1"
        assert result.checks[0].reason_code == ReasonCode.MISSING_ITEMS
        assert result.checks[0].check_name == "bundle_not_empty"

    def test_item_without_content_returns_fail(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="nc-1",
            kind="log_entry",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-nc",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.MISSING_CONTENT for c in result.checks)

    def test_item_without_scope_returns_fail(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="ns-1",
            kind="log_entry",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-ns",
            scope_reference=" ",  # whitespace-only bundle scope (passes Pydantic min_length=1)
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL

    def test_item_without_reproducibility_marker_returns_fail(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="nr-1",
            kind="log_entry",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={},  # empty
        )
        bundle = EvidenceBundle(
            id="bundle-nr",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.NO_REPRODUCIBILITY_MARKER for c in result.checks)


# ------------------------------------------------------------------
# 2. Reproducibility Checks
# ------------------------------------------------------------------


class TestReproducibilityChecks:
    """Reproducibility marker must be present and non-empty."""

    def test_valid_marker_passes(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS

    def test_empty_marker_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="re-1",
            kind="log_entry",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={},
        )
        bundle = EvidenceBundle(
            id="bundle-re",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.NO_REPRODUCIBILITY_MARKER for c in result.checks)

    def test_empty_values_marker_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="re-2",
            kind="log_entry",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"run_id": "", "step_id": ""},
        )
        bundle = EvidenceBundle(
            id="bundle-re2",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.EMPTY_REPRODUCIBILITY_MARKER for c in result.checks)

    def test_multiple_items_all_markers_pass(
        self,
        oracle: EvidenceOracle,
        valid_item: EvidenceItem,
        second_valid_item: EvidenceItem,
        fixed_timestamp: str,
    ) -> None:
        bundle = EvidenceBundle(
            id="bundle-multi",
            scope_reference="scope://example.com/v1",
            items=[valid_item, second_valid_item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS
        repro_checks = [c for c in result.checks if c.check_name == "reproducibility_check"]
        assert all(c.status == CheckStatus.PASS for c in repro_checks)
        assert len(repro_checks) == 2

    def test_one_item_without_marker_fails_multiple(
        self,
        oracle: EvidenceOracle,
        valid_item: EvidenceItem,
        fixed_timestamp: str,
    ) -> None:
        bad_item = EvidenceItem(
            id="bad-repro",
            kind="log_entry",
            scope_reference="scope://example.com/v1",
            source="step-x",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={},
        )
        bundle = EvidenceBundle(
            id="bundle-mixed",
            scope_reference="scope://example.com/v1",
            items=[valid_item, bad_item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL


# ------------------------------------------------------------------
# 3. Scope Checks
# ------------------------------------------------------------------


class TestScopeChecks:
    """Scope reference must be present, non-UNKNOWN, and match bundle."""

    def test_missing_bundle_scope_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="sc-1",
            kind="log_entry",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sc",
            scope_reference="   ",  # whitespace-only
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        # whitespace is stripped and treated as empty → MISSING_SCOPE_REFERENCE
        assert result.status == OracleStatus.FAIL

    def test_missing_item_scope_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="sc-2",
            kind="log_entry",
            scope_reference="  ",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sc2",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.MISSING_SCOPE_REFERENCE for c in result.checks)

    def test_scope_mismatch_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="sc-3",
            kind="log_entry",
            scope_reference="scope://other.com",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sc3",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.SCOPE_MISMATCH for c in result.checks)

    def test_matching_scopes_pass(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        scope_checks = [c for c in result.checks if c.check_name == "scope_check"]
        assert all(c.status == CheckStatus.PASS for c in scope_checks)

    def test_unknown_scope_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="sc-4",
            kind="log_entry",
            scope_reference="UNKNOWN",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sc4",
            scope_reference="UNKNOWN",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.UNKNOWN_SCOPE for c in result.checks)


# ------------------------------------------------------------------
# 4. Minimal Data / Sensitive Fields
# ------------------------------------------------------------------


class TestMinimalDataChecks:
    """minimal=False or sensitive fields → FAIL."""

    def test_minimal_true_passes(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS

    def test_minimal_false_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="md-1",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"status": 200},
            collected_at=fixed_timestamp,
            minimal=False,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-md",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.MINIMAL_DATA_VIOLATION for c in result.checks)

    def test_sensitive_field_password_fails(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="sens-1",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"body": {"password": "secret123"}},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sens",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(
            c.reason_code == ReasonCode.SENSITIVE_DATA_DETECTED
            and c.check_name == "sensitive_data_check"
            for c in result.checks
        )

    def test_sensitive_field_token_fails(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="sens-2",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"headers": {"token": "abc.def.ghi"}},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sens2",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL

    def test_sensitive_field_secret_fails(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="sens-3",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"secret": "top-secret"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sens3",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL

    def test_nested_sensitive_field_fails(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="sens-4",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={
                "request": {
                    "headers": {
                        "Authorization": "Bearer token123",
                    }
                }
            },
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sens4",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        sensitive_checks = [
            c for c in result.checks if c.reason_code == ReasonCode.SENSITIVE_DATA_DETECTED
        ]
        assert len(sensitive_checks) >= 1
        # Should find "Authorization" field (case-insensitive match against lowercased detail)
        assert any("authorization" in c.detail.lower() for c in sensitive_checks)

    def test_sensitive_in_list_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="sens-5",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"cookies": [{"session": "abc"}, {"name": "ok"}]},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sens5",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL

    def test_sensitive_in_metadata_fails(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="sens-6",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
            metadata={"api_key": "should-not-be-here"},
        )
        bundle = EvidenceBundle(
            id="bundle-sens6",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL

    def test_case_insensitive_sensitive_detection(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="sens-7",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"PASSWORD": "CaseInsensitive"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sens7",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL

    def test_hyphen_normalized_sensitive_detection(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        item = EvidenceItem(
            id="sens-8",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"Set-Cookie": "session=abc"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-sens8",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL


# ------------------------------------------------------------------
# 5. Payload Size Checks
# ------------------------------------------------------------------


class TestPayloadSizeChecks:
    """Large payloads trigger WARN or FAIL."""

    def test_payload_within_limit_passes(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS

    def test_payload_exceeds_soft_limit_warns(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        # Create a payload just over SOFT_ITEM_CONTENT_BYTES
        big_value = "x" * (SOFT_ITEM_CONTENT_BYTES // 2)
        item = EvidenceItem(
            id="big-1",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"data": big_value, "data2": big_value},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-big",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        # Should be WARN (payload between soft and hard limit)
        assert result.status == OracleStatus.WARN
        assert any(c.reason_code == ReasonCode.PAYLOAD_WARN for c in result.checks)

    def test_payload_exceeds_hard_limit_fails(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        # Create a payload over HARD_ITEM_CONTENT_BYTES
        big_value = "x" * (HARD_ITEM_CONTENT_BYTES // 2 + 100)
        item = EvidenceItem(
            id="big-2",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"data": big_value, "data2": big_value},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-big2",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.EXCESSIVE_PAYLOAD for c in result.checks)


# ------------------------------------------------------------------
# 6. Unknown Data Classification
# ------------------------------------------------------------------


class TestDataClassificationChecks:
    """Unknown or unlisted evidence kinds → FAIL."""

    def test_known_kind_passes(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS

    def test_unknown_kind_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="unk-1",
            kind="unlisted_custom_kind",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-unk",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.UNKNOWN_DATA_CLASSIFICATION for c in result.checks)


# ------------------------------------------------------------------
# 7. Result Model Serialization
# ------------------------------------------------------------------


class TestResultModel:
    """EvidenceOracleResult serializes correctly."""

    def test_pass_result_serializes(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS
        d = result.model_dump()
        assert d["status"] == "PASS"
        assert d["bundle_id"] == "bundle-001"
        assert len(d["checks"]) > 0
        assert len(d["errors"]) == 0
        assert len(d["warnings"]) == 0

    def test_fail_result_serializes(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        result = oracle.evaluate(None, timestamp=fixed_timestamp)
        d = result.model_dump()
        assert d["status"] == "FAIL"
        assert "MISSING_BUNDLE" in d["checks"][0]["reason_code"]

    def test_warn_result_serializes(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        big_value = "x" * (SOFT_ITEM_CONTENT_BYTES // 2)
        item = EvidenceItem(
            id="warn-1",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"data": big_value, "data2": big_value},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-warn",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        d = result.model_dump()
        assert d["status"] == "WARN"

    def test_checks_contain_reason_codes(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        for check in result.checks:
            assert isinstance(check.reason_code, ReasonCode)
            assert check.reason_code.value

    def test_mixed_aggregation(
        self, oracle: EvidenceOracle, valid_item: EvidenceItem, fixed_timestamp: str
    ) -> None:
        """If item has non-minimal but everything else is fine → FAIL due to MINIMAL_DATA_VIOLATION."""
        non_minimal = EvidenceItem(
            id="nm-1",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"status": 200},
            collected_at=fixed_timestamp,
            minimal=False,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-mixed-agg",
            scope_reference="scope://example.com/v1",
            items=[valid_item, non_minimal],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        # valid_item passes, non_minimal fails → overall FAIL
        assert result.status == OracleStatus.FAIL


# ------------------------------------------------------------------
# 8. Determinism
# ------------------------------------------------------------------


class TestDeterminism:
    """Same inputs produce same outputs when using fixed timestamp."""

    def test_same_input_produces_same_result(
        self,
        oracle: EvidenceOracle,
        valid_bundle: EvidenceBundle,
        fixed_timestamp: str,
    ) -> None:
        r1 = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        r2 = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        assert r1.model_dump() == r2.model_dump()

    def test_same_input_different_timestamp_differs_only_in_timestamp(
        self,
        oracle: EvidenceOracle,
        valid_bundle: EvidenceBundle,
        fixed_timestamp: str,
    ) -> None:
        r1 = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        r2 = oracle.evaluate(valid_bundle, timestamp="2026-07-10T00:00:00Z")
        d1 = r1.model_dump()
        d2 = r2.model_dump()
        d1["timestamp"] = "IGNORED"
        d2["timestamp"] = "IGNORED"
        assert d1 == d2


# ------------------------------------------------------------------
# 9. Bundle Scope Edge Cases
# ------------------------------------------------------------------


class TestBundleScopeEdgeCases:
    """Bundle scope edge cases: whitespace, UNKNOWN."""

    def test_bundle_unknown_scope_fails(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        item = EvidenceItem(
            id="bsc-1",
            kind="log_entry",
            scope_reference="UNKNOWN",
            source="step-1",
            content={"key": "value"},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-bsc",
            scope_reference="UNKNOWN",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL


# ------------------------------------------------------------------
# 10. Safety Checks
# ------------------------------------------------------------------


class TestSafety:
    """No network, shell, subprocess, or real-target imports."""

    def test_no_network_imports_in_oracle(self) -> None:
        """Verify evidence_oracle module has no network/shell imports."""
        import ast
        import inspect

        from neutrino import evidence_oracle as eo_module

        # Get all source files in the package
        source_files = [
            inspect.getsource(eo_module.models),
            inspect.getsource(eo_module.oracle),
        ]

        forbidden = {
            "socket",
            "http.client",
            "urllib.request",
            "urllib3",
            "requests",
            "httpx",
            "aiohttp",
            "subprocess",
            "os.system",
            "os.popen",
            "pty",
            "telnetlib",
        }

        for source in source_files:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name
                        for forbidden_name in forbidden:
                            if module_name == forbidden_name or module_name.startswith(
                                forbidden_name + "."
                            ):
                                pytest.fail(f"Forbidden import found: {module_name}")
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    module_name = node.module
                    for forbidden_name in forbidden:
                        if module_name == forbidden_name or module_name.startswith(
                            forbidden_name + "."
                        ):
                            pytest.fail(f"Forbidden import found: {module_name}")

    def test_no_shell_subprocess_in_oracle_module(self) -> None:
        """Verify the oracle module does not import subprocess."""
        import ast
        import inspect

        from neutrino.evidence_oracle import oracle as oracle_mod

        source = inspect.getsource(oracle_mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "subprocess" not in alias.name, "subprocess import found"
                    assert "os" not in alias.name or "os.system" in alias.name, "os import found"
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                assert "subprocess" not in node.module, "subprocess import found"
                assert "os" not in node.module, "os import found"

    def test_evidence_item_freezes_content(self) -> None:
        """EvidenceItem is frozen — cannot be modified after creation."""
        item = EvidenceItem(
            id="frozen-1",
            kind="log_entry",
            scope_reference="scope://example.com",
            source="step-1",
            content={"key": "value"},
            collected_at="2026-01-01T00:00:00Z",
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        with pytest.raises(Exception):  # noqa: B017
            item.id = "changed"  # type: ignore[misc]

    def test_sensitive_fields_set_is_frozen(self) -> None:
        """SENSITIVE_FIELDS is immutable."""
        assert isinstance(SENSITIVE_FIELDS, frozenset)

    def test_oracle_does_not_implement_diffing(self) -> None:
        """Verify oracle.py has no diff-related functions (no #21)."""
        import inspect

        from neutrino.evidence_oracle import oracle as oracle_mod

        source = inspect.getsource(oracle_mod)
        # No state comparison between runs
        assert "state_diff" not in source.lower()
        assert "diff_result" not in source.lower()
        assert "previous_bundle" not in source.lower()


# ------------------------------------------------------------------
# 11. Auditability (EvidenceCheckResult contains reason codes)
# ------------------------------------------------------------------


class TestAuditability:
    """Oracle results are auditable — every check has a reason code."""

    def test_all_checks_have_reason_code(
        self, oracle: EvidenceOracle, valid_item: EvidenceItem, fixed_timestamp: str
    ) -> None:
        bad_item = EvidenceItem(
            id="aud-1",
            kind="unlisted_kind",
            scope_reference="scope://other.com",
            source="step-1",
            content={},
            collected_at=fixed_timestamp,
            minimal=False,
            reproducibility_marker={},
        )
        bundle = EvidenceBundle(
            id="bundle-aud",
            scope_reference="scope://example.com/v1",
            items=[valid_item, bad_item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        # Every check must have a non-empty reason_code
        for check in result.checks:
            assert check.reason_code, f"Check {check.check_name} has no reason_code"
            assert check.reason_code.value

    def test_fail_status_never_empty_errors(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(None, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert len(result.errors) > 0

    def test_pass_result_has_no_errors(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS
        assert len(result.errors) == 0


# ------------------------------------------------------------------
# 12. Edge Cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge case coverage."""

    def test_item_with_only_one_marker_value_passes(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        """A single non-empty value in the marker is sufficient."""
        item = EvidenceItem(
            id="edge-1",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"status": 200},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-edge1",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS

    def test_sensitive_field_none_value_still_flagged(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        """Even if the sensitive field value is None, the key alone triggers detection."""
        item = EvidenceItem(
            id="edge-2",
            kind="http_request",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"api_key": None},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-edge2",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.reason_code == ReasonCode.SENSITIVE_DATA_DETECTED for c in result.checks)

    def test_empty_string_item_id_in_bundle(self) -> None:
        """Ensure bundle with min_length=1 item ids work correctly."""
        item = EvidenceItem(
            id="e",
            kind="http_response",
            scope_reference="scope://e.com",
            source="s",
            content={"x": 1},
            collected_at="2026-01-01T00:00:00Z",
            minimal=True,
            reproducibility_marker={"r": "run-1"},
        )
        bundle = EvidenceBundle(
            id="b",
            scope_reference="scope://e.com",
            items=[item],
            created_at="2026-01-01T00:00:00Z",
        )
        oracle = EvidenceOracle()
        result = oracle.evaluate(bundle, timestamp="2026-01-01T00:00:00Z")
        assert result.status == OracleStatus.PASS


# ------------------------------------------------------------------
# 13. Review-Agent Hardening Tests
# ------------------------------------------------------------------


class TestRecursionLimit:
    """Cyclic and deeply nested payloads must not crash the oracle."""

    def test_cyclic_payload_does_not_crash(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        """A self-referential dict must not cause RecursionError."""
        cyclic: dict = {}
        cyclic["self"] = cyclic  # self-referential
        item = EvidenceItem(
            id="cyc-1",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content=cyclic,
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-cyc",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        # Must not raise RecursionError — fail-closed is OK (returns FAIL due to unknown kind)
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL  # unknown kind is FAIL
        # But it must not have crashed
        assert len(result.checks) > 0

    def test_deeply_nested_payload_does_not_crash(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        """A deeply nested (200 levels) payload must not cause RecursionError."""
        deep: dict = {}
        current = deep
        for _i in range(200):
            current["next"] = {}
            current = current["next"]
        current["leaf"] = "value"

        item = EvidenceItem(
            id="deep-1",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content=deep,
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-deep",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        # Should not crash — fail-closed
        assert result.status in (OracleStatus.FAIL, OracleStatus.PASS, OracleStatus.WARN)


class TestMaxItemsEnforcement:
    """MAX_ITEMS must be enforced."""

    def test_bundle_exceeding_max_items_fails(
        self, oracle: EvidenceOracle, fixed_timestamp: str
    ) -> None:
        """A bundle with more than MAX_ITEMS must return FAIL."""
        oracle.MAX_ITEMS = 5  # Lower limit for test
        items = [
            EvidenceItem(
                id=f"mi-{i}",
                kind="http_response",
                scope_reference="scope://example.com/v1",
                source=f"step-{i}",
                content={"status": 200},
                collected_at=fixed_timestamp,
                minimal=True,
                reproducibility_marker={"step_id": f"step-{i}"},
            )
            for i in range(10)
        ]
        bundle = EvidenceBundle(
            id="bundle-max",
            scope_reference="scope://example.com/v1",
            items=items,
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.FAIL
        assert any(c.check_name == "bundle_size_limit" for c in result.checks)


class TestTimestampValidation:
    """Blank or invalid timestamps must fail-closed."""

    def test_blank_timestamp_fails(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle
    ) -> None:
        """An empty timestamp must return FAIL."""
        result = oracle.evaluate(valid_bundle, timestamp="")
        assert result.status == OracleStatus.FAIL
        assert any("timestamp" in c.check_name.lower() for c in result.checks)

    def test_whitespace_timestamp_fails(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle
    ) -> None:
        """A whitespace-only timestamp must return FAIL."""
        result = oracle.evaluate(valid_bundle, timestamp="   ")
        assert result.status == OracleStatus.FAIL


class TestWarningsPopulation:
    """WARN outcomes must populate the warnings field."""

    def test_warn_result_has_warnings(self, oracle: EvidenceOracle, fixed_timestamp: str) -> None:
        """When status is WARN, the warnings list must be non-empty."""
        # Create content that exceeds soft limit
        big_value = "x" * (SOFT_ITEM_CONTENT_BYTES // 2)
        item = EvidenceItem(
            id="wpop-1",
            kind="http_response",
            scope_reference="scope://example.com/v1",
            source="step-1",
            content={"data": big_value, "data2": big_value},
            collected_at=fixed_timestamp,
            minimal=True,
            reproducibility_marker={"step_id": "step-1"},
        )
        bundle = EvidenceBundle(
            id="bundle-wpop",
            scope_reference="scope://example.com/v1",
            items=[item],
            created_at=fixed_timestamp,
        )
        result = oracle.evaluate(bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.WARN
        assert len(result.warnings) > 0, "WARN result must have populated warnings"

    def test_pass_result_has_empty_warnings(
        self, oracle: EvidenceOracle, valid_bundle: EvidenceBundle, fixed_timestamp: str
    ) -> None:
        """When status is PASS, warnings list is empty."""
        result = oracle.evaluate(valid_bundle, timestamp=fixed_timestamp)
        assert result.status == OracleStatus.PASS
        assert result.warnings == []
