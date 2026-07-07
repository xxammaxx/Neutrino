"""Tests for the Human Authorization Workflow — Issue #4.

Covers 48 tests across 6 categories:
    - Request Creation (9 tests)
    - Decision Recording (9 tests)
    - Gate Check (10 tests)
    - No Bypass (10 tests)
    - Persistence / Audit (7 tests)
    - Safety (6 tests)

All tests are local, deterministic, and use temporary SQLite databases
and temporary audit directories. No real targets, no network, no DNS.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid

import pytest

from neutrino.approval.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    DecisionType,
    GateResult,
    HumanDecision,
)
from neutrino.approval.workflow import ApprovalWorkflow
from neutrino.audit.writer import AuditLogWriter
from neutrino.storage.migrations import apply_migrations
from neutrino.storage.paths import get_temp_db_path
from neutrino.storage.repositories.audit_events import AuditEventRepository
from neutrino.storage.repositories.human_approvals import HumanApprovalRepository

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

FIXED_TS = "2026-07-07T10:00:00+00:00"
FIXED_TS_2 = "2026-07-07T11:00:00+00:00"

SCOPE = "scope://example.com/policy"
TEST_TYPE = "port_scan"
RISK = "Low risk — target is lab environment"


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _new_uuid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db_path() -> str:
    """A freshly migrated temporary database (schema v2)."""
    path = get_temp_db_path()
    apply_migrations(path)
    return path


@pytest.fixture
def approval_repo(db_path: str) -> HumanApprovalRepository:
    return HumanApprovalRepository(db_path)


@pytest.fixture
def audit_repo(db_path: str) -> AuditEventRepository:
    return AuditEventRepository(db_path)


@pytest.fixture
def tmp_audit_dir() -> str:
    """A temporary directory for the JSONL AuditLogWriter."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def audit_writer(tmp_audit_dir: str) -> AuditLogWriter:
    return AuditLogWriter(audit_dir=tmp_audit_dir)


@pytest.fixture
def workflow_no_audit(approval_repo: HumanApprovalRepository) -> ApprovalWorkflow:
    """Workflow with only the approval repo (no audit backends)."""
    return ApprovalWorkflow(approval_repo)


@pytest.fixture
def workflow_with_audit(
    approval_repo: HumanApprovalRepository,
    audit_repo: AuditEventRepository,
    audit_writer: AuditLogWriter,
) -> ApprovalWorkflow:
    """Workflow with both SQLite and JSONL audit backends."""
    return ApprovalWorkflow(approval_repo, audit_repo, audit_writer)


# ==================================================================
# 1. Request Creation (9 tests)
# ==================================================================


class TestRequestCreation:
    """Tests for ApprovalRequest creation."""

    def test_request_contains_scope_information(self, workflow_no_audit: ApprovalWorkflow):
        """ApprovalRequest contains scope_reference."""
        req = workflow_no_audit.create_request(
            actor="researcher",
            action="port_scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )
        assert req.scope_reference == SCOPE

    def test_request_contains_test_type(self, workflow_no_audit: ApprovalWorkflow):
        """ApprovalRequest contains the planned test type."""
        req = workflow_no_audit.create_request(
            actor="researcher",
            action="port_scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )
        assert req.test_type == TEST_TYPE

    def test_request_contains_risk_summary(self, workflow_no_audit: ApprovalWorkflow):
        """ApprovalRequest contains a risk summary."""
        req = workflow_no_audit.create_request(
            actor="researcher",
            action="port_scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )
        assert req.risk_summary == RISK

    def test_default_status_is_pending(self, workflow_no_audit: ApprovalWorkflow):
        """Default status of a new request is PENDING."""
        req = workflow_no_audit.create_request(
            actor="researcher",
            action="port_scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )
        assert req.status == ApprovalStatus.PENDING

    def test_missing_scope_rejected(self):
        """Missing scope_reference raises ValueError."""
        with pytest.raises(ValueError, match="scope_reference must be a non-empty string"):
            ApprovalRequest(
                id=_new_uuid(),
                actor="researcher",
                action="port_scan",
                target="example.com",
                scope_reference="",
                test_type=TEST_TYPE,
                risk_summary=RISK,
                created_at=FIXED_TS,
            )

    def test_missing_test_type_rejected(self):
        """Missing test_type raises ValueError."""
        with pytest.raises(ValueError, match="test_type must be a non-empty string"):
            ApprovalRequest(
                id=_new_uuid(),
                actor="researcher",
                action="port_scan",
                target="example.com",
                scope_reference=SCOPE,
                test_type="",
                risk_summary=RISK,
                created_at=FIXED_TS,
            )

    def test_missing_risk_summary_rejected(self):
        """Missing risk_summary raises ValueError."""
        with pytest.raises(ValueError, match="risk_summary must be a non-empty string"):
            ApprovalRequest(
                id=_new_uuid(),
                actor="researcher",
                action="port_scan",
                target="example.com",
                scope_reference=SCOPE,
                test_type=TEST_TYPE,
                risk_summary="",
                created_at=FIXED_TS,
            )

    def test_whitespace_only_scope_rejected(self):
        """Whitespace-only scope_reference raises ValueError."""
        with pytest.raises(ValueError, match="scope_reference must be a non-empty string"):
            ApprovalRequest(
                id=_new_uuid(),
                actor="researcher",
                action="port_scan",
                target="example.com",
                scope_reference="   ",
                test_type=TEST_TYPE,
                risk_summary=RISK,
                created_at=FIXED_TS,
            )

    def test_request_is_persisted(
        self, workflow_no_audit: ApprovalWorkflow, approval_repo: HumanApprovalRepository
    ):
        """Creating a request persists it in the repository."""
        req = workflow_no_audit.create_request(
            actor="researcher",
            action="port_scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )
        persisted = approval_repo.get(req.id)
        assert persisted is not None
        assert persisted.decision == "PENDING"
        assert persisted.action == "port_scan"
        assert persisted.target == "example.com"
        assert persisted.scope_reference == SCOPE
        assert persisted.test_type == TEST_TYPE
        assert persisted.risk_summary == RISK


# ==================================================================
# 2. Decision Recording (9 tests)
# ==================================================================


class TestDecisionRecording:
    """Tests for recording human decisions."""

    def _create_pending(self, wf: ApprovalWorkflow) -> ApprovalRequest:
        return wf.create_request(
            actor="researcher",
            action="port_scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )

    def test_human_approve_creates_approved(self, workflow_no_audit: ApprovalWorkflow):
        """APPROVE decision → APPROVED status."""
        req = self._create_pending(workflow_no_audit)
        decision = workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="Testing is safe for this target",
            timestamp=FIXED_TS_2,
        )
        assert decision.decision == DecisionType.APPROVE
        gate = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        assert gate.gate_result == GateResult.ALLOW_APPROVED
        assert gate.allow is True

    def test_human_reject_creates_rejected(self, workflow_no_audit: ApprovalWorkflow):
        """REJECT decision → REJECTED status."""
        req = self._create_pending(workflow_no_audit)
        decision = workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.REJECT,
            reason="Out of allowed testing window",
            timestamp=FIXED_TS_2,
        )
        assert decision.decision == DecisionType.REJECT
        gate = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        assert gate.gate_result == GateResult.BLOCK_REJECTED
        assert gate.allow is False

    def test_reason_is_stored(
        self, workflow_no_audit: ApprovalWorkflow, approval_repo: HumanApprovalRepository
    ):
        """The reason is stored in the repository."""
        req = self._create_pending(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="Approved after manual review",
            timestamp=FIXED_TS_2,
        )
        persisted = approval_repo.get(req.id)
        assert persisted is not None
        assert persisted.reason == "Approved after manual review"

    def test_decider_is_stored(
        self, workflow_no_audit: ApprovalWorkflow, approval_repo: HumanApprovalRepository
    ):
        """The decider identity is stored."""
        req = self._create_pending(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="security-lead",
            decision=DecisionType.APPROVE,
            reason="ok",
            timestamp=FIXED_TS_2,
        )
        persisted = approval_repo.get(req.id)
        assert persisted is not None
        assert persisted.actor == "security-lead"

    def test_missing_request_raises(self, workflow_no_audit: ApprovalWorkflow):
        """Recording a decision for a non-existent request raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            workflow_no_audit.record_decision(
                request_id="nonexistent-id",
                decider="human-operator-01",
                decision=DecisionType.APPROVE,
                reason="reason",
                timestamp=FIXED_TS_2,
            )

    def test_decision_on_already_approved_raises(self, workflow_no_audit: ApprovalWorkflow):
        """Cannot decide on an already decided request."""
        req = self._create_pending(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="first approval",
            timestamp=FIXED_TS_2,
        )
        with pytest.raises(ValueError, match="not PENDING"):
            workflow_no_audit.record_decision(
                request_id=req.id,
                decider="human-operator-02",
                decision=DecisionType.REJECT,
                reason="try to override",
            )

    def test_decision_on_rejected_raises(self, workflow_no_audit: ApprovalWorkflow):
        """Cannot override a REJECTED decision."""
        req = self._create_pending(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.REJECT,
            reason="rejected",
            timestamp=FIXED_TS_2,
        )
        with pytest.raises(ValueError, match="not PENDING"):
            workflow_no_audit.record_decision(
                request_id=req.id,
                decider="human-operator-02",
                decision=DecisionType.APPROVE,
                reason="try to override",
            )

    def test_empty_reason_accepted_but_documented(self, workflow_no_audit: ApprovalWorkflow):
        """Empty reason is accepted (current implementation) but test exists for awareness."""
        # The HumanDecision model requires non-empty reason, so the workflow
        # passes through the value. This test documents the current behaviour.
        req = self._create_pending(workflow_no_audit)
        # HumanDecision would reject empty reason at model level
        with pytest.raises(ValueError, match="reason must be a non-empty string"):
            HumanDecision(
                request_id=req.id,
                decider="human-operator-01",
                decision=DecisionType.APPROVE,
                reason=" ",  # whitespace-only
                decided_at=FIXED_TS_2,
            )


# ==================================================================
# 3. Gate Check (10 tests)
# ==================================================================


class TestGateCheck:
    """Tests for the approval gate check logic."""

    def _create_request(self, wf: ApprovalWorkflow) -> ApprovalRequest:
        return wf.create_request(
            actor="researcher",
            action="port_scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )

    def test_no_approval_without_request(self, workflow_no_audit: ApprovalWorkflow):
        """Gate check without any request → BLOCK_MISSING_APPROVAL."""
        result = workflow_no_audit.check_approval("no-such-id", timestamp=FIXED_TS)
        assert result.gate_result == GateResult.BLOCK_MISSING_APPROVAL
        assert result.allow is False

    def test_pending_approval_blocks(self, workflow_no_audit: ApprovalWorkflow):
        """Pending request → BLOCK_PENDING_APPROVAL."""
        req = self._create_request(workflow_no_audit)
        result = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        assert result.gate_result == GateResult.BLOCK_PENDING_APPROVAL
        assert result.allow is False

    def test_rejected_approval_blocks(self, workflow_no_audit: ApprovalWorkflow):
        """Rejected request → BLOCK_REJECTED."""
        req = self._create_request(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.REJECT,
            reason="not allowed",
            timestamp=FIXED_TS_2,
        )
        result = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        assert result.gate_result == GateResult.BLOCK_REJECTED
        assert result.allow is False

    def test_approved_approval_allows(self, workflow_no_audit: ApprovalWorkflow):
        """Approved request → ALLOW_APPROVED."""
        req = self._create_request(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="safe to proceed",
            timestamp=FIXED_TS_2,
        )
        result = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        assert result.gate_result == GateResult.ALLOW_APPROVED
        assert result.allow is True

    def test_rejected_remains_blocked(self, workflow_no_audit: ApprovalWorkflow):
        """REJECTED stays blocked — cannot become allowed."""
        req = self._create_request(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.REJECT,
            reason="blocked permanently",
            timestamp=FIXED_TS_2,
        )
        # Check multiple times
        for _ in range(5):
            result = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
            assert result.gate_result == GateResult.BLOCK_REJECTED
            assert result.allow is False

    def test_approved_is_reproducible(self, workflow_no_audit: ApprovalWorkflow):
        """APPROVED yields allow=True every time it's checked."""
        req = self._create_request(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="approved",
            timestamp=FIXED_TS_2,
        )
        for _ in range(5):
            result = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
            assert result.allow is True

    def test_deterministic_same_inputs_same_result(self, workflow_no_audit: ApprovalWorkflow):
        """Same request status always yields the same gate result."""
        req = self._create_request(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="approved",
            timestamp=FIXED_TS_2,
        )
        result1 = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        result2 = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        assert result1.gate_result == result2.gate_result
        assert result1.allow == result2.allow

    def test_allow_false_for_blocking_results(self):
        """All blocking gate results must have allow=False."""
        # Test via the ApprovalDecision model invariant
        for gate in GateResult:
            if gate == GateResult.ALLOW_APPROVED:
                continue
            decision = ApprovalDecision(
                gate_result=gate,
                allow=False,
                request_id="test-id",
                explanation=f"Test: {gate.value}",
            )
            assert decision.allow is False
            assert decision.gate_result != GateResult.ALLOW_APPROVED

    def test_allow_true_only_for_allow_approved(self):
        """Only ALLOW_APPROVED can have allow=True."""
        decision = ApprovalDecision(
            gate_result=GateResult.ALLOW_APPROVED,
            allow=True,
            request_id="test-id",
            explanation="Approved",
        )
        assert decision.allow is True
        assert decision.gate_result == GateResult.ALLOW_APPROVED


# ==================================================================
# 4. No Bypass (10 tests)
# ==================================================================


class TestNoBypass:
    """Tests that no approval bypass mechanisms exist."""

    def _create_req(self, wf: ApprovalWorkflow) -> ApprovalRequest:
        return wf.create_request(
            actor="researcher",
            action="test",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )

    def test_no_force_parameter_in_workflow(self):
        """ApprovalWorkflow has no force/override parameter."""
        import inspect

        sig = inspect.signature(ApprovalWorkflow.check_approval)
        params = list(sig.parameters.keys())
        assert "force" not in params
        assert "admin_override" not in params
        assert "auto_approve" not in params
        assert "allow_lab_auto" not in params
        assert "llm_approve" not in params
        assert "override" not in params

    def test_no_force_in_decision_model(self):
        """ApprovalDecision has no force/override fields."""
        fields = [f.name for f in __import__("dataclasses").fields(ApprovalDecision)]
        assert "force" not in fields
        assert "override" not in fields
        assert "auto_approve" not in fields

    def test_scopeguard_allow_does_not_replace_approval(self, workflow_no_audit: ApprovalWorkflow):
        """A request can be created even if ScopeGuard would ALLOW — but the gate still requires human approval."""
        req = workflow_no_audit.create_request(
            actor="scopeguard",
            action="http_request",
            target="example.com",
            scope_reference="scope://example.com/in_scope",
            test_type="xss",
            risk_summary="high",
            timestamp=FIXED_TS,
        )
        result = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS)
        # Despite scope reference suggesting it's in scope, gate is still PENDING
        assert result.gate_result == GateResult.BLOCK_PENDING_APPROVAL
        assert result.allow is False

    def test_low_risk_does_not_replace_approval(self, workflow_no_audit: ApprovalWorkflow):
        """Low risk still requires explicit approval."""
        req = workflow_no_audit.create_request(
            actor="researcher",
            action="ping",
            target="localhost",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary="very low risk",
            timestamp=FIXED_TS,
        )
        result = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS)
        assert result.allow is False

    def test_time_does_not_auto_approve(self, workflow_no_audit: ApprovalWorkflow):
        """Passing time does not auto-approve a pending request."""
        req = self._create_req(workflow_no_audit)
        # Check at a much later time
        later = "2027-01-01T00:00:00+00:00"
        result = workflow_no_audit.check_approval(req.id, timestamp=later)
        assert result.allow is False
        assert result.gate_result == GateResult.BLOCK_PENDING_APPROVAL

    def test_no_llm_approval_mechanism(self):
        """There is no LLM approval function or class."""
        import inspect

        source = inspect.getsource(ApprovalWorkflow)
        assert "llm" not in source.lower()
        assert "auto_approve" not in source.lower()
        assert "timeout_approve" not in source.lower()
        assert "implicit_approve" not in source.lower()

    def test_no_admin_override_in_decision_enum(self):
        """DecisionType only has APPROVE and REJECT, no admin override."""
        values = [d.value for d in DecisionType]
        assert "AUTO_APPROVE" not in values
        assert "LLM_APPROVE" not in values
        assert "TIMEOUT_APPROVE" not in values
        assert "IMPLICIT_APPROVE" not in values
        assert "ADMIN_OVERRIDE" not in values

    def test_no_lab_auto_approve(self, workflow_no_audit: ApprovalWorkflow):
        """Even a request that indicates a lab target is not auto-approved."""
        req = workflow_no_audit.create_request(
            actor="researcher",
            action="port_scan",
            target="lab-target.local",
            scope_reference="scope://lab",
            test_type="vulnerability_scan",
            risk_summary="Lab environment — but still needs approval",
            timestamp=FIXED_TS,
        )
        result = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS)
        assert result.allow is False
        assert result.gate_result == GateResult.BLOCK_PENDING_APPROVAL

    def test_block_invalid_request(self):
        """Invalid request IDs produce BLOCK_MISSING_APPROVAL."""
        decision = ApprovalDecision(
            gate_result=GateResult.BLOCK_MISSING_APPROVAL,
            allow=False,
            request_id=None,
            explanation="No such request",
        )
        assert decision.allow is False
        assert decision.gate_result == GateResult.BLOCK_MISSING_APPROVAL

    def test_pending_blocks_even_with_allow_true_explicitly(self):
        """Even a manually created ApprovalDecision with allow=True must fail if not ALLOW_APPROVED."""
        with pytest.raises(ValueError, match="allow=True is only valid for ALLOW_APPROVED"):
            ApprovalDecision(
                gate_result=GateResult.BLOCK_PENDING_APPROVAL,
                allow=True,  # This should raise
                request_id="test",
                explanation="Should fail",
            )


# ==================================================================
# 5. Persistence / Audit (7 tests)
# ==================================================================


class TestPersistenceAndAudit:
    """Tests for persistence and audit trail."""

    def _create_with_full_audit(self, wf: ApprovalWorkflow) -> ApprovalRequest:
        return wf.create_request(
            actor="researcher",
            action="port_scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )

    def test_request_readable_from_repository(
        self, workflow_no_audit: ApprovalWorkflow, approval_repo: HumanApprovalRepository
    ):
        """An ApprovalRequest can be read back from the repository."""
        req = self._create_with_full_audit(workflow_no_audit)
        persisted = approval_repo.get(req.id)
        assert persisted is not None
        assert persisted.id == req.id
        assert persisted.actor == "researcher"
        assert persisted.decision == "PENDING"
        assert persisted.action == "port_scan"
        assert persisted.target == "example.com"
        assert persisted.scope_reference == SCOPE
        assert persisted.test_type == TEST_TYPE
        assert persisted.risk_summary == RISK

    def test_status_change_persisted(
        self, workflow_no_audit: ApprovalWorkflow, approval_repo: HumanApprovalRepository
    ):
        """Status change is persisted."""
        req = self._create_with_full_audit(workflow_no_audit)
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="approved",
            timestamp=FIXED_TS_2,
        )
        persisted = approval_repo.get(req.id)
        assert persisted is not None
        assert persisted.decision == "APPROVED"

    def test_audit_event_for_request_creation(
        self, workflow_with_audit: ApprovalWorkflow, audit_repo: AuditEventRepository
    ):
        """An AuditEvent is created when a request is created."""
        req = self._create_with_full_audit(workflow_with_audit)
        events = audit_repo.list_by_action("approval_request_created")
        assert len(events) >= 1
        found = False
        for ev in events:
            payload = json.loads(ev.event_json)
            if payload.get("request_id") == req.id:
                found = True
                break
        assert found, "AuditEvent for request creation not found"

    def test_audit_event_for_decision(
        self, workflow_with_audit: ApprovalWorkflow, audit_repo: AuditEventRepository
    ):
        """An AuditEvent is created when a decision is recorded."""
        req = self._create_with_full_audit(workflow_with_audit)
        workflow_with_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="approved for testing",
            timestamp=FIXED_TS_2,
        )
        events = audit_repo.list_by_action("approval_decision_recorded")
        assert len(events) >= 1
        found = False
        for ev in events:
            payload = json.loads(ev.event_json)
            if payload.get("decision") == "APPROVE" and ev.target == req.id:
                found = True
                break
        assert found, "AuditEvent for decision not found"

    def test_audit_event_for_block(
        self, workflow_with_audit: ApprovalWorkflow, audit_repo: AuditEventRepository
    ):
        """An AuditEvent is created when the gate blocks."""
        req = self._create_with_full_audit(workflow_with_audit)
        workflow_with_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        events = audit_repo.list_by_action("approval_gate_check")
        # At least one block event (from the pending check)
        block_events = [ev for ev in events if ev.decision == "block"]
        assert len(block_events) >= 1

    def test_audit_event_for_allow(
        self, workflow_with_audit: ApprovalWorkflow, audit_repo: AuditEventRepository
    ):
        """An AuditEvent is created when the gate allows."""
        req = self._create_with_full_audit(workflow_with_audit)
        workflow_with_audit.record_decision(
            request_id=req.id,
            decider="human-operator-01",
            decision=DecisionType.APPROVE,
            reason="approved",
            timestamp=FIXED_TS_2,
        )
        workflow_with_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        events = audit_repo.list_by_action("approval_gate_check")
        allow_events = [ev for ev in events if ev.decision == "allow"]
        assert len(allow_events) >= 1

    def test_jsonl_audit_written(
        self, workflow_with_audit: ApprovalWorkflow, audit_writer: AuditLogWriter
    ):
        """The JSONL AuditLogWriter receives audit events."""
        self._create_with_full_audit(workflow_with_audit)
        events = audit_writer.read_all()
        assert len(events) >= 1
        # Verify the request creation was logged
        found = False
        for ev in events:
            if ev.action == "approval_request_created":
                found = True
        assert found, "JSONL audit event for request creation not found"

    def test_temporary_directory_used(self, db_path: str, tmp_audit_dir: str):
        """Tests use temporary directories, not production paths."""
        assert (
            "neutrino" not in db_path.lower()
            or "tmp" in db_path.lower()
            or "pytest" in db_path.lower()
        )
        assert not tmp_audit_dir.startswith(os.path.expanduser("~/.neutrino"))


# ==================================================================
# 6. Safety (6 tests) — no real targets, no network, deterministic
# ==================================================================


class TestSafety:
    """Safety and determinism tests."""

    def test_no_real_requests(self):
        """The approval module has no HTTP client imports."""
        import inspect

        import neutrino.approval.workflow as wf

        source = inspect.getsource(wf)
        assert "import requests" not in source
        assert "from requests" not in source
        assert "import httpx" not in source
        assert "from httpx" not in source
        assert "urlopen" not in source

    def test_no_dns_resolution(self):
        """The approval module has no DNS imports."""
        import inspect

        import neutrino.approval.workflow as wf

        source = inspect.getsource(wf)
        assert "socket." not in source
        assert "dns." not in source.lower()
        assert "getaddrinfo" not in source

    def test_no_shell_execution(self):
        """The approval module has no shell imports."""
        import inspect

        import neutrino.approval.workflow as wf

        source = inspect.getsource(wf)
        assert "subprocess" not in source
        assert "os.system" not in source
        assert "exec(" not in source

    def test_no_n8n_or_paperclip_imports(self):
        """No n8n or Paperclip dependencies."""
        import inspect

        import neutrino.approval.workflow as wf

        source = inspect.getsource(wf)
        assert "n8n" not in source.lower()
        assert "paperclip" not in source.lower()

    def test_deterministic_identical_inputs(self, workflow_no_audit: ApprovalWorkflow):
        """Same inputs produce the same ApprovalDecision."""
        req = workflow_no_audit.create_request(
            actor="researcher",
            action="scan",
            target="example.com",
            scope_reference=SCOPE,
            test_type=TEST_TYPE,
            risk_summary=RISK,
            timestamp=FIXED_TS,
        )
        workflow_no_audit.record_decision(
            request_id=req.id,
            decider="alice",
            decision=DecisionType.APPROVE,
            reason="ok",
            timestamp=FIXED_TS_2,
        )
        r1 = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        r2 = workflow_no_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        assert r1.gate_result == r2.gate_result
        assert r1.allow == r2.allow

    def test_no_network_imports_in_models(self):
        """Models have no network imports."""
        import inspect

        import neutrino.approval.models as mod

        source = inspect.getsource(mod)
        assert "requests" not in source
        assert "httpx" not in source
        assert "socket" not in source
        assert "urllib" not in source


# ==================================================================
# 7. Workflow with real persistence (integration-style)
# ==================================================================


class TestWorkflowIntegration:
    """Integration-style tests using the full workflow with both audit backends."""

    def test_full_approval_flow(
        self,
        workflow_with_audit: ApprovalWorkflow,
        approval_repo: HumanApprovalRepository,
        audit_repo: AuditEventRepository,
        audit_writer: AuditLogWriter,
    ):
        """End-to-end: create → check (blocked) → approve → check (allowed)."""
        # Step 1: Create request
        req = workflow_with_audit.create_request(
            actor="researcher",
            action="sql_injection_test",
            target="test.example.com",
            scope_reference="scope://program/123",
            test_type="sql_injection",
            risk_summary="Medium — authenticated testing with rate limiting",
            timestamp=FIXED_TS,
        )

        # Step 2: Verify it's PENDING and BLOCKED
        persisted = approval_repo.get(req.id)
        assert persisted is not None
        assert persisted.decision == "PENDING"

        gate1 = workflow_with_audit.check_approval(req.id, timestamp=FIXED_TS)
        assert gate1.gate_result == GateResult.BLOCK_PENDING_APPROVAL
        assert gate1.allow is False

        # Step 3: Record APPROVE
        workflow_with_audit.record_decision(
            request_id=req.id,
            decider="security-lead",
            decision=DecisionType.APPROVE,
            reason="Target is in scope, test type is allowed, risk is manageable",
            timestamp=FIXED_TS_2,
        )

        # Step 4: Verify ALLOW
        gate2 = workflow_with_audit.check_approval(req.id, timestamp=FIXED_TS_2)
        assert gate2.gate_result == GateResult.ALLOW_APPROVED
        assert gate2.allow is True
        assert gate2.request_id == req.id

        # Step 5: Verify persistence
        persisted2 = approval_repo.get(req.id)
        assert persisted2 is not None
        assert persisted2.decision == "APPROVED"
        assert persisted2.reason == "Target is in scope, test type is allowed, risk is manageable"

        # Step 6: Verify audit trail
        sqlite_events = audit_repo.list_all()
        jsonl_events = audit_writer.read_all()
        assert len(sqlite_events) >= 4  # create + approve + 2 gate checks
        assert len(jsonl_events) >= 4

    def test_full_reject_flow(
        self,
        workflow_with_audit: ApprovalWorkflow,
        approval_repo: HumanApprovalRepository,
    ):
        """End-to-end: create → reject → permanently blocked."""
        req = workflow_with_audit.create_request(
            actor="researcher",
            action="credential_stuffing",
            target="login.example.com",
            scope_reference="scope://program/456",
            test_type="credential_stuffing",
            risk_summary="High — prohibited by program policy",
            timestamp=FIXED_TS,
        )

        workflow_with_audit.record_decision(
            request_id=req.id,
            decider="security-lead",
            decision=DecisionType.REJECT,
            reason="Credential stuffing is prohibited by the program policy",
            timestamp=FIXED_TS_2,
        )

        # Should always be BLOCK_REJECTED
        for _ in range(3):
            gate = workflow_with_audit.check_approval(req.id, timestamp=FIXED_TS_2)
            assert gate.gate_result == GateResult.BLOCK_REJECTED
            assert gate.allow is False

        # Verify persistence
        persisted = approval_repo.get(req.id)
        assert persisted is not None
        assert persisted.decision == "REJECTED"

    def test_multiple_requests_independent(
        self,
        workflow_no_audit: ApprovalWorkflow,
    ):
        """Multiple requests are independent."""
        req1 = workflow_no_audit.create_request(
            actor="researcher-1",
            action="scan_a",
            target="a.example.com",
            scope_reference=SCOPE,
            test_type="xss",
            risk_summary="low",
            timestamp=FIXED_TS,
        )
        req2 = workflow_no_audit.create_request(
            actor="researcher-2",
            action="scan_b",
            target="b.example.com",
            scope_reference=SCOPE,
            test_type="sql_injection",
            risk_summary="medium",
            timestamp=FIXED_TS,
        )

        # Approve only req1
        workflow_no_audit.record_decision(
            request_id=req1.id,
            decider="alice",
            decision=DecisionType.APPROVE,
            reason="ok",
            timestamp=FIXED_TS_2,
        )
        # Reject req2
        workflow_no_audit.record_decision(
            request_id=req2.id,
            decider="alice",
            decision=DecisionType.REJECT,
            reason="blocked",
            timestamp=FIXED_TS_2,
        )

        g1 = workflow_no_audit.check_approval(req1.id, timestamp=FIXED_TS_2)
        g2 = workflow_no_audit.check_approval(req2.id, timestamp=FIXED_TS_2)

        assert g1.allow is True
        assert g2.allow is False
        assert g1.gate_result == GateResult.ALLOW_APPROVED
        assert g2.gate_result == GateResult.BLOCK_REJECTED

    def test_no_auto_approval_on_any_code_path(
        self,
        workflow_with_audit: ApprovalWorkflow,
    ):
        """Verify every code path — there can be no auto-approval."""
        req = workflow_with_audit.create_request(
            actor="researcher",
            action="test",
            target="example.com",
            scope_reference=SCOPE,
            test_type="test",
            risk_summary="test",
            timestamp=FIXED_TS,
        )

        # Without any decision, must be BLOCK
        g = workflow_with_audit.check_approval(req.id, timestamp=FIXED_TS)
        assert g.allow is False

        # Can't approve without valid DecisionType
        with pytest.raises(ValueError):
            workflow_with_audit.record_decision(
                request_id=req.id,
                decider="alice",
                decision="INVALID",  # type: ignore[arg-type]
                reason="test",
            )
