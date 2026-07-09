"""Tests for the Validation-Recipe-Executor — Issue #19.

Covers:
    1. Invalid recipe → overall BLOCKED, no steps
    2. Missing approval_request_id → step BLOCKED
    3. Gate DENY → step BLOCKED
    4. Gate ALLOW + dry_run → step SKIPPED_DRY_RUN
    5. Gate ALLOW + not dry_run → handler executes
    6. Manual observation → PLANNED
    7. Evidence check → EXECUTED (found) / ERROR (missing)
    8. Local fixture check → EXECUTED (valid) / BLOCKED (path escape) / ERROR (missing)
    9. HTTP check → PLANNED (never connects)
    10. TCP check → PLANNED (never connects)
    11. Audit per step (including blocked, skipped)
    12. Unknown step type → BLOCKED
    13. Forbidden fields → rejected by model (extra="forbid")
    14. No bypass fields (force, skip_gate, etc.)
    15. No subprocess, shell, scanner, external HTTP/DNS imports
    16. Deterministic: same inputs → same results
    17. Overall status aggregation (ERROR, BLOCKED, COMPLETED)
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from neutrino.active_validation.models import (
    ActiveValidationGateDecision,
    ReasonCode,
)
from neutrino.audit import AuditLogWriter
from neutrino.models.policy import ScopePolicy
from neutrino.validation_executor import (
    ExecutionStatus,
    StepExecutionStatus,
    ValidationExecutionRequest,
    ValidationExecutionResult,
    ValidationRecipeExecutor,
    ValidationStepResult,
    get_handler,
)
from neutrino.validation_recipe import (
    ValidationRecipe,
    ValidationStep,
    ValidationStepType,
)

# ==================================================================
# Helpers
# ==================================================================

FIXED_TS = "2026-07-09T10:00:00+00:00"


def _make_gate_decision(allow: bool) -> ActiveValidationGateDecision:
    """Create a gate decision for testing."""
    return ActiveValidationGateDecision(
        reason=ReasonCode.ALLOW_APPROVED_IN_SCOPE if allow else ReasonCode.BLOCK_REJECTED_APPROVAL,
        intent_id="intent-001",
        target="http://localhost:8080",
        approval_request_id="approval-001",
        scope_reference="scope:local-lab/demo-app",
        audit_event_id="audit-gate-001",
        explanation="Approved for testing" if allow else "Rejected: no human approval",
        timestamp=FIXED_TS,
    )


def _make_recipe(valid: bool = True) -> ValidationRecipe:
    """Create a minimal valid (or invalid) recipe."""
    if valid:
        return ValidationRecipe(
            id="recipe-001",
            name="Test Recipe",
            version="1.0",
            description="A test recipe.",
            scope_references=["scope:local-lab/demo-app"],
            steps=[
                ValidationStep(
                    id="step-001",
                    name="Manual Check",
                    step_type=ValidationStepType.MANUAL_OBSERVATION,
                    target="lab:demo-app",
                    scope_reference="scope:local-lab/demo-app",
                    requires_approval=True,
                    expected_evidence=["ev-001"],
                ),
                ValidationStep(
                    id="step-002",
                    name="Evidence Check",
                    step_type=ValidationStepType.EVIDENCE_CHECK,
                    target="lab:demo-app",
                    scope_reference="scope:local-lab/demo-app",
                    requires_approval=True,
                    expected_evidence=["ev-001"],
                ),
            ],
            created_at=FIXED_TS,
        )
    # Invalid recipe: step's scope_reference not in recipe's scope_references
    # This passes Pydantic validation but fails validate_recipe()
    return ValidationRecipe(
        id="recipe-invalid",
        name="Bad Recipe",
        version="1.0",
        description="Invalid recipe: scope mismatch.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="Bad step",
                step_type=ValidationStepType.MANUAL_OBSERVATION,
                target="lab:demo-app",
                scope_reference="scope:other-program/target",  # Not in scope_references
                requires_approval=True,
                expected_evidence=["ev-001"],
            )
        ],
        created_at=FIXED_TS,
    )


# ==================================================================
# Fixtures
# ==================================================================


@pytest.fixture
def tmp_audit_dir() -> str:
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def audit_writer(tmp_audit_dir: str) -> AuditLogWriter:
    return AuditLogWriter(audit_dir=tmp_audit_dir)


@pytest.fixture
def scope_policy() -> ScopePolicy:
    return ScopePolicy(
        source_url="https://example.com/policy",
        program_name="Test Program",
    )


@pytest.fixture
def executor(audit_writer: AuditLogWriter, scope_policy: ScopePolicy) -> ValidationRecipeExecutor:
    """Executor with mocked gate, scope_guard, approval."""
    gate = MagicMock()
    gate.evaluate.return_value = _make_gate_decision(allow=True)

    scope_guard = MagicMock()
    approval = MagicMock()

    return ValidationRecipeExecutor(
        active_validation_gate=gate,
        scope_guard=scope_guard,
        scope_policy=scope_policy,
        approval_workflow=approval,
        audit_writer=audit_writer,
    )


@pytest.fixture
def blocking_executor(
    audit_writer: AuditLogWriter, scope_policy: ScopePolicy
) -> ValidationRecipeExecutor:
    """Executor whose gate always DENYs."""
    gate = MagicMock()
    gate.evaluate.return_value = _make_gate_decision(allow=False)

    scope_guard = MagicMock()
    approval = MagicMock()

    return ValidationRecipeExecutor(
        active_validation_gate=gate,
        scope_guard=scope_guard,
        scope_policy=scope_policy,
        approval_workflow=approval,
        audit_writer=audit_writer,
    )


@pytest.fixture
def valid_recipe() -> ValidationRecipe:
    return _make_recipe(valid=True)


# ==================================================================
# 1. Invalid Recipe → BLOCKED
# ==================================================================


def test_invalid_recipe_blocks_execution(executor: ValidationRecipeExecutor):
    """Invalid recipe → overall BLOCKED, no steps processed."""
    recipe = _make_recipe(valid=False)

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=True,
        approval_request_ids_by_step={"step-001": "approval-001"},
    )

    result = executor.execute(request)

    assert result.overall_status == ExecutionStatus.BLOCKED
    assert len(result.step_results) == 0
    assert len(result.audit_trail) == 1  # Recipe validation audit


# ==================================================================
# 2. Missing Approval Request ID → BLOCKED
# ==================================================================


def test_missing_approval_request_id(
    executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe
):
    """Step without approval_request_id → BLOCKED."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=valid_recipe,
        dry_run=True,
        approval_request_ids_by_step={},  # Empty
    )

    result = executor.execute(request)

    blocked_steps = [r for r in result.step_results if r.status == StepExecutionStatus.BLOCKED]
    assert len(blocked_steps) == 2
    for step_result in blocked_steps:
        assert step_result.error_message == "Missing approval_request_id for step"


# ==================================================================
# 3. Gate DENY → Step BLOCKED
# ==================================================================


def test_gate_deny_blocks_step(
    blocking_executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe
):
    """Gate returns allow=False → step BLOCKED."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=valid_recipe,
        dry_run=True,
        approval_request_ids_by_step={
            "step-001": "approval-001",
            "step-002": "approval-002",
        },
    )

    result = blocking_executor.execute(request)

    for step_result in result.step_results:
        assert step_result.status == StepExecutionStatus.BLOCKED
        assert step_result.gate_decision is not None
        assert step_result.gate_decision.allow is False


# ==================================================================
# 4. Gate ALLOW + dry_run → SKIPPED_DRY_RUN
# ==================================================================


def test_gate_allow_dry_run_skips(
    executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe
):
    """Gate allows but dry_run=True → SKIPPED_DRY_RUN."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=valid_recipe,
        dry_run=True,
        approval_request_ids_by_step={
            "step-001": "approval-001",
            "step-002": "approval-002",
        },
    )

    result = executor.execute(request)

    for step_result in result.step_results:
        assert step_result.status == StepExecutionStatus.SKIPPED_DRY_RUN
        assert step_result.evidence == {"planned": True, "dry_run": True}


# ==================================================================
# 5. Gate ALLOW + not dry_run → handler executes
# ==================================================================


def test_gate_allow_executes_manual_observation(
    executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe
):
    """Manual observation executes → PLANNED."""
    # Recipe with only manual_observation step
    recipe = ValidationRecipe(
        id="recipe-manual",
        name="Manual",
        version="1.0",
        description="Manual only.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="Manual Check",
                step_type=ValidationStepType.MANUAL_OBSERVATION,
                target="lab:demo-app",
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-001"],
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,  # Real execution
        approval_request_ids_by_step={"step-001": "approval-001"},
    )

    result = executor.execute(request)

    assert result.step_results[0].status == StepExecutionStatus.PLANNED
    assert result.step_results[0].evidence["mode"] == "manual_only"


def test_gate_allow_executes_evidence_check_found(executor: ValidationRecipeExecutor):
    """Evidence check with evidence present → EXECUTED."""
    recipe = ValidationRecipe(
        id="recipe-ev",
        name="Evidence",
        version="1.0",
        description="Evidence check.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="Evidence Check",
                step_type=ValidationStepType.EVIDENCE_CHECK,
                target="lab:demo-app",
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-001"],
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,
        approval_request_ids_by_step={"step-001": "approval-001"},
        evidence_context={"ev-001": {"status": "verified"}},
    )

    result = executor.execute(request)

    assert result.step_results[0].status == StepExecutionStatus.EXECUTED
    assert "matched_evidence" in result.step_results[0].evidence


def test_gate_allow_executes_evidence_check_missing(executor: ValidationRecipeExecutor):
    """Evidence check with missing evidence → ERROR."""
    recipe = ValidationRecipe(
        id="recipe-ev",
        name="Evidence",
        version="1.0",
        description="Evidence check.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="Evidence Check",
                step_type=ValidationStepType.EVIDENCE_CHECK,
                target="lab:demo-app",
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-missing"],
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,
        approval_request_ids_by_step={"step-001": "approval-001"},
        evidence_context={},  # Empty — evidence missing
    )

    result = executor.execute(request)

    assert result.step_results[0].status == StepExecutionStatus.ERROR
    assert "missing_evidence" in result.step_results[0].evidence


def test_gate_allow_executes_local_fixture(executor: ValidationRecipeExecutor):
    """Local fixture check with valid fixture → EXECUTED."""
    with tempfile.TemporaryDirectory() as fixture_dir:
        fixture_path = os.path.join(fixture_dir, "test-fixture.json")
        with open(fixture_path, "w") as f:
            json.dump({"key": "value"}, f)

        recipe = ValidationRecipe(
            id="recipe-fix",
            name="Fixture",
            version="1.0",
            description="Fixture check.",
            scope_references=["scope:local-lab/demo-app"],
            steps=[
                ValidationStep(
                    id="step-001",
                    name="Fixture Check",
                    step_type=ValidationStepType.LOCAL_FIXTURE_CHECK,
                    target="fixture:test-fixture",
                    scope_reference="scope:local-lab/demo-app",
                    requires_approval=True,
                    expected_evidence=["ev-001"],
                    parameters={"fixture_id": "test-fixture"},
                ),
            ],
            created_at=FIXED_TS,
        )

        request = ValidationExecutionRequest(
            request_id="req-001",
            recipe=recipe,
            dry_run=False,
            allowed_fixture_dir=fixture_dir,
            approval_request_ids_by_step={"step-001": "approval-001"},
        )

        result = executor.execute(request)

        assert result.step_results[0].status == StepExecutionStatus.EXECUTED
        assert result.step_results[0].evidence["fixture_data"] == {"key": "value"}


def test_local_fixture_missing_allowed_dir(executor: ValidationRecipeExecutor):
    """Local fixture without allowed_fixture_dir → BLOCKED."""
    recipe = ValidationRecipe(
        id="recipe-fix",
        name="Fixture",
        version="1.0",
        description="Fixture check.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="Fixture Check",
                step_type=ValidationStepType.LOCAL_FIXTURE_CHECK,
                target="fixture:test-fixture",
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-dummy-001"],
                parameters={"fixture_id": "test-fixture"},
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,
        allowed_fixture_dir=None,  # Missing
        approval_request_ids_by_step={"step-001": "approval-001"},
    )

    result = executor.execute(request)

    assert result.step_results[0].status == StepExecutionStatus.BLOCKED
    assert "allowed_fixture_dir is required" in result.step_results[0].error_message


def test_local_fixture_path_traversal_blocked(executor: ValidationRecipeExecutor):
    """Local fixture with path traversal → BLOCKED."""
    recipe = ValidationRecipe(
        id="recipe-fix",
        name="Fixture",
        version="1.0",
        description="Fixture check.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="Fixture Check",
                step_type=ValidationStepType.LOCAL_FIXTURE_CHECK,
                target="fixture:bad",
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-dummy-001"],
                parameters={"fixture_id": "../etc/passwd"},
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,
        allowed_fixture_dir="/tmp/fixtures",
        approval_request_ids_by_step={"step-001": "approval-001"},
    )

    result = executor.execute(request)

    assert result.step_results[0].status == StepExecutionStatus.BLOCKED
    assert "path separators or traversal" in result.step_results[0].error_message


def test_local_fixture_missing_file(executor: ValidationRecipeExecutor):
    """Local fixture with missing file → ERROR."""
    with tempfile.TemporaryDirectory() as fixture_dir:
        recipe = ValidationRecipe(
            id="recipe-fix",
            name="Fixture",
            version="1.0",
            description="Fixture check.",
            scope_references=["scope:local-lab/demo-app"],
            steps=[
                ValidationStep(
                    id="step-001",
                    name="Fixture Check",
                    step_type=ValidationStepType.LOCAL_FIXTURE_CHECK,
                    target="fixture:nonexistent",
                    scope_reference="scope:local-lab/demo-app",
                    requires_approval=True,
                    expected_evidence=["ev-dummy-001"],
                    parameters={"fixture_id": "nonexistent"},
                ),
            ],
            created_at=FIXED_TS,
        )

        request = ValidationExecutionRequest(
            request_id="req-001",
            recipe=recipe,
            dry_run=False,
            allowed_fixture_dir=fixture_dir,
            approval_request_ids_by_step={"step-001": "approval-001"},
        )

        result = executor.execute(request)

        assert result.step_results[0].status == StepExecutionStatus.ERROR
        assert "not found" in result.step_results[0].error_message


# ==================================================================
# 6. HTTP Check → PLANNED (never connects)
# ==================================================================


def test_http_check_planned_only(executor: ValidationRecipeExecutor):
    """HTTP check always returns PLANNED, never makes requests."""
    recipe = ValidationRecipe(
        id="recipe-http",
        name="HTTP",
        version="1.0",
        description="HTTP check.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="HTTP Check",
                step_type=ValidationStepType.HTTP_CHECK,
                target="http://localhost:8080",
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-001"],
                parameters={"method": "GET"},
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,  # Even in non-dry-run, HTTP is only planned
        approval_request_ids_by_step={"step-001": "approval-001"},
    )

    result = executor.execute(request)

    assert result.step_results[0].status == StepExecutionStatus.PLANNED
    assert result.step_results[0].evidence["planned_action"] == "http_check"
    assert "HTTP execution disabled" in result.step_results[0].evidence["note"]


# ==================================================================
# 7. TCP Check → PLANNED (never connects)
# ==================================================================


def test_tcp_check_planned_only(executor: ValidationRecipeExecutor):
    """TCP check always returns PLANNED, never opens sockets."""
    recipe = ValidationRecipe(
        id="recipe-tcp",
        name="TCP",
        version="1.0",
        description="TCP check.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="TCP Check",
                step_type=ValidationStepType.TCP_CHECK,
                target="lab:tcp-target",  # lab: prefix — safe local target
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-dummy-001"],
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,
        approval_request_ids_by_step={"step-001": "approval-001"},
    )

    result = executor.execute(request)

    assert result.step_results[0].status == StepExecutionStatus.PLANNED
    assert result.step_results[0].evidence["planned_action"] == "tcp_check"
    assert "TCP execution disabled" in result.step_results[0].evidence["note"]


# ==================================================================
# 8. Audit per Step
# ==================================================================


def test_every_step_is_audited(executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe):
    """Every step produces an audit event ID."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=valid_recipe,
        dry_run=True,
        approval_request_ids_by_step={
            "step-001": "approval-001",
            "step-002": "approval-002",
        },
    )

    result = executor.execute(request)

    assert len(result.step_results) == 2
    for step_result in result.step_results:
        assert step_result.audit_event_id is not None

    # audit_trail contains all audit event IDs
    assert len(result.audit_trail) == 2


def test_blocked_steps_are_audited(
    blocking_executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe
):
    """Even blocked steps produce audit events."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=valid_recipe,
        dry_run=True,
        approval_request_ids_by_step={
            "step-001": "approval-001",
            "step-002": "approval-002",
        },
    )

    result = blocking_executor.execute(request)

    for step_result in result.step_results:
        assert step_result.audit_event_id is not None
        assert step_result.status == StepExecutionStatus.BLOCKED


# ==================================================================
# 9. Overall Status Aggregation
# ==================================================================


def test_overall_completed(executor: ValidationRecipeExecutor):
    """All steps PLANNED/SKIPPED_DRY_RUN/EXECUTED → COMPLETED."""
    recipe = ValidationRecipe(
        id="recipe-ok",
        name="OK",
        version="1.0",
        description="All good.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="Manual",
                step_type=ValidationStepType.MANUAL_OBSERVATION,
                target="lab:demo-app",
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-dummy-001"],
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,
        approval_request_ids_by_step={"step-001": "approval-001"},
    )

    result = executor.execute(request)
    assert result.overall_status == ExecutionStatus.COMPLETED


def test_overall_blocked(
    blocking_executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe
):
    """At least one BLOCKED → overall BLOCKED."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=valid_recipe,
        dry_run=True,
        approval_request_ids_by_step={
            "step-001": "approval-001",
            "step-002": "approval-002",
        },
    )

    result = blocking_executor.execute(request)
    assert result.overall_status == ExecutionStatus.BLOCKED


def test_overall_error(executor: ValidationRecipeExecutor):
    """At least one ERROR → overall ERROR (supersedes BLOCKED)."""
    recipe = ValidationRecipe(
        id="recipe-err",
        name="Error",
        version="1.0",
        description="Evidence error.",
        scope_references=["scope:local-lab/demo-app"],
        steps=[
            ValidationStep(
                id="step-001",
                name="Evidence Check",
                step_type=ValidationStepType.EVIDENCE_CHECK,
                target="lab:demo-app",
                scope_reference="scope:local-lab/demo-app",
                requires_approval=True,
                expected_evidence=["ev-missing"],
            ),
        ],
        created_at=FIXED_TS,
    )

    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=recipe,
        dry_run=False,
        approval_request_ids_by_step={"step-001": "approval-001"},
        evidence_context={},
    )

    result = executor.execute(request)
    assert result.overall_status == ExecutionStatus.ERROR


# ==================================================================
# 10. Forbidden Fields (extra="forbid")
# ==================================================================


def test_no_force_field_allowed():
    """ValidationExecutionRequest rejects 'force' field."""
    with pytest.raises(ValidationError):
        ValidationExecutionRequest(
            request_id="req-001",
            recipe=_make_recipe(valid=True),
            force=True,  # type: ignore[call-arg]
        )


def test_no_skip_gate_field_allowed():
    """ValidationExecutionRequest rejects 'skip_gate' field."""
    with pytest.raises(ValidationError):
        ValidationExecutionRequest(
            request_id="req-001",
            recipe=_make_recipe(valid=True),
            skip_gate=True,  # type: ignore[call-arg]
        )


def test_no_unsafe_field_allowed():
    """ValidationExecutionRequest rejects 'unsafe' field."""
    with pytest.raises(ValidationError):
        ValidationExecutionRequest(
            request_id="req-001",
            recipe=_make_recipe(valid=True),
            unsafe=True,  # type: ignore[call-arg]
        )


def test_result_models_reject_extra_fields():
    """All result models have extra='forbid'."""
    with pytest.raises(ValidationError):
        ValidationStepResult(
            step_id="s1",
            step_type=ValidationStepType.MANUAL_OBSERVATION,
            status=StepExecutionStatus.PLANNED,
            bypass=True,  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        ValidationExecutionResult(
            request_id="req-001",
            recipe_id="recipe-001",
            overall_status=ExecutionStatus.COMPLETED,
            step_results=[],
            force=True,  # type: ignore[call-arg]
        )


# ==================================================================
# 11. No Unsafe Imports
# ==================================================================


def test_no_subprocess_shell_imports():
    """Executor/handler modules must not import subprocess, os.system, etc."""
    forbidden_imports = [
        "subprocess",
        "os.system",
        "os.popen",
        "eval",
        "exec",
        "compile",
        "pickle",
        "shelve",
    ]
    # Check executor module
    executor_path = "src/neutrino/validation_executor/executor.py"
    if os.path.exists(executor_path):
        with open(executor_path) as f:
            content = f.read()
        for forbidden in forbidden_imports:
            assert f"import {forbidden}" not in content, f"executor.py imports {forbidden}"
            assert f"from {forbidden}" not in content, f"executor.py imports from {forbidden}"

    # Check handlers module
    handlers_path = "src/neutrino/validation_executor/handlers.py"
    if os.path.exists(handlers_path):
        with open(handlers_path) as f:
            content = f.read()
        for forbidden in forbidden_imports:
            assert f"import {forbidden}" not in content, f"handlers.py imports {forbidden}"
            assert f"from {forbidden}" not in content, f"handlers.py imports from {forbidden}"


def test_no_http_socket_imports_in_handlers():
    """Handlers must not import httpx, requests, urllib, socket."""
    forbidden_network = [
        "httpx",
        "requests",
        "urllib.request",
        "urllib3",
        "socket",
        "asyncio",
        "aiohttp",
        "dns.resolver",
        "dns.asyncresolver",
    ]
    handlers_path = "src/neutrino/validation_executor/handlers.py"
    if os.path.exists(handlers_path):
        with open(handlers_path) as f:
            content = f.read()
        for forbidden in forbidden_network:
            assert f"import {forbidden}" not in content, f"handlers.py imports {forbidden}"
            assert f"from {forbidden}" not in content, f"handlers.py imports from {forbidden}"


def test_no_dns_in_executor():
    """Executor must not perform DNS resolution."""
    executor_path = "src/neutrino/validation_executor/executor.py"
    if os.path.exists(executor_path):
        with open(executor_path) as f:
            content = f.read()
        assert "getaddrinfo" not in content
        assert "gethostbyname" not in content
        assert "dns.resolver" not in content


# ==================================================================
# 12. Deterministic Behavior
# ==================================================================


def test_deterministic_same_input_same_output(
    executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe
):
    """Same inputs → same results (excluding timestamps)."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=valid_recipe,
        dry_run=True,
        approval_request_ids_by_step={
            "step-001": "approval-001",
            "step-002": "approval-002",
        },
    )

    result1 = executor.execute(request)
    result2 = executor.execute(request)

    assert result1.overall_status == result2.overall_status
    assert result1.recipe_id == result2.recipe_id
    assert len(result1.step_results) == len(result2.step_results)

    for r1, r2 in zip(result1.step_results, result2.step_results, strict=True):
        assert r1.step_id == r2.step_id
        assert r1.status == r2.status
        assert r1.evidence == r2.evidence
        assert r1.error_message == r2.error_message


# ==================================================================
# 13. Default Dry-Run
# ==================================================================


def test_dry_run_defaults_to_true():
    """dry_run defaults to True."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=_make_recipe(valid=True),
    )
    assert request.dry_run is True


# ==================================================================
# 14. Handler Lookup
# ==================================================================


def test_get_handler_all_valid_types():
    """All 5 allowed step types return a handler."""
    for step_type in ValidationStepType:
        handler = get_handler(step_type)
        assert handler is not None


def test_get_handler_raises_for_unknown():
    """get_handler with unknown type raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported"):
        get_handler("nonexistent_type")  # type: ignore[arg-type]


# ==================================================================
# 15. Gate Called Per Step
# ==================================================================


def test_gate_called_per_step(executor: ValidationRecipeExecutor, valid_recipe: ValidationRecipe):
    """ActiveValidationGate.evaluate() is called for each step."""
    request = ValidationExecutionRequest(
        request_id="req-001",
        recipe=valid_recipe,
        dry_run=True,
        approval_request_ids_by_step={
            "step-001": "approval-001",
            "step-002": "approval-002",
        },
    )

    result = executor.execute(request)

    # Verify gate was called twice (once per step)
    assert executor._gate.evaluate.call_count == 2  # type: ignore[union-attr]

    # Each result has a gate_decision
    for step_result in result.step_results:
        assert step_result.gate_decision is not None
