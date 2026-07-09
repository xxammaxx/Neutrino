"""Tests for the Active-Validation-Gate — Issue #14.

Covers 48+ tests across 8 categories.
All tests are local, deterministic, and use temporary SQLite databases
and temporary audit directories. No real targets, no network, no DNS.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict

import pytest

from neutrino.active_validation.gate import ActiveValidationGate
from neutrino.active_validation.models import (
    ActiveValidationGateDecision,
    ActiveValidationIntent,
    ReasonCode,
)
from neutrino.approval.models import DecisionType
from neutrino.approval.workflow import ApprovalWorkflow
from neutrino.audit.writer import AuditLogWriter
from neutrino.models.policy import ScopeEntry, ScopePolicy
from neutrino.scopeguard.guard import ScopeGuard
from neutrino.storage.migrations import apply_migrations
from neutrino.storage.paths import get_temp_db_path
from neutrino.storage.repositories.audit_events import AuditEventRepository
from neutrino.storage.repositories.human_approvals import HumanApprovalRepository

FIXED_TS = "2026-07-09T10:00:00+00:00"
FIXED_TS_2 = "2026-07-09T11:00:00+00:00"
FIXED_TS_3 = "2026-07-09T12:00:00+00:00"

SCOPE = "scope://example.com/policy"
TEST_TYPE = "port_scan"
RISK = "Low risk — target is lab environment"
ACTOR = "researcher"
TARGET = "example.com"
ACTION = "port_scan"


def _new_uuid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db_path() -> str:
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
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def audit_writer(tmp_audit_dir: str) -> AuditLogWriter:
    return AuditLogWriter(audit_dir=tmp_audit_dir)


@pytest.fixture
def approval_workflow(approval_repo: HumanApprovalRepository) -> ApprovalWorkflow:
    return ApprovalWorkflow(approval_repo)


@pytest.fixture
def scope_guard() -> ScopeGuard:
    return ScopeGuard()


@pytest.fixture
def scope_policy() -> ScopePolicy:
    return ScopePolicy(
        source_url="https://example.com/policy",
        raw_text="example.com in scope",
        in_scope=[ScopeEntry(pattern="example.com", type="domain")],
        out_of_scope=[],
    )


@pytest.fixture
def deny_scope_policy() -> ScopePolicy:
    return ScopePolicy(
        source_url="https://other.com/policy",
        raw_text="other.com in scope",
        in_scope=[ScopeEntry(pattern="other.com", type="domain")],
        out_of_scope=[],
    )


@pytest.fixture
def gate(
    approval_workflow: ApprovalWorkflow,
    approval_repo: HumanApprovalRepository,
    scope_guard: ScopeGuard,
    scope_policy: ScopePolicy,
    audit_writer: AuditLogWriter,
    audit_repo: AuditEventRepository,
) -> ActiveValidationGate:
    return ActiveValidationGate(
        approval_workflow=approval_workflow,
        approval_repo=approval_repo,
        scope_guard=scope_guard,
        scope_policy=scope_policy,
        audit_writer=audit_writer,
        audit_repo=audit_repo,
    )


def _make_intent(
    *,
    target: str = TARGET,
    scope_reference: str = SCOPE,
    test_type: str = TEST_TYPE,
    risk_summary: str = RISK,
    approval_request_id: str | None = None,
) -> ActiveValidationIntent:
    return ActiveValidationIntent(
        id=_new_uuid(),
        actor=ACTOR,
        action=ACTION,
        target=target,
        scope_reference=scope_reference,
        test_type=test_type,
        risk_summary=risk_summary,
        approval_request_id=approval_request_id or _new_uuid(),
        created_at=FIXED_TS_3,
    )


def _create_approved_request(
    wf: ApprovalWorkflow,
    target: str = TARGET,
    scope_reference: str = SCOPE,
    test_type: str = TEST_TYPE,
    risk_summary: str = RISK,
) -> str:
    req = wf.create_request(
        actor=ACTOR,
        action=ACTION,
        target=target,
        scope_reference=scope_reference,
        test_type=test_type,
        risk_summary=risk_summary,
        timestamp=FIXED_TS,
    )
    wf.record_decision(
        request_id=req.id,
        decider="human-operator",
        decision=DecisionType.APPROVE,
        reason="Approved for testing",
        timestamp=FIXED_TS_2,
    )
    return req.id


class TestIntentModel:
    def test_valid_intent_serializable(self) -> None:
        intent = _make_intent()
        data = asdict(intent)
        assert json.dumps(data)

    def test_missing_actor_rejected(self) -> None:
        with pytest.raises(ValueError, match="actor must be a non-empty string"):
            ActiveValidationIntent(
                id=_new_uuid(), actor="", action=ACTION, target=TARGET,
                scope_reference=SCOPE, test_type=TEST_TYPE, risk_summary=RISK,
                approval_request_id=_new_uuid(), created_at=FIXED_TS,
            )

    def test_missing_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="target must be a non-empty string"):
            ActiveValidationIntent(
                id=_new_uuid(), actor=ACTOR, action=ACTION, target="",
                scope_reference=SCOPE, test_type=TEST_TYPE, risk_summary=RISK,
                approval_request_id=_new_uuid(), created_at=FIXED_TS,
            )

    def test_missing_scope_reference_rejected(self) -> None:
        with pytest.raises(ValueError, match="scope_reference must be a non-empty string"):
            ActiveValidationIntent(
                id=_new_uuid(), actor=ACTOR, action=ACTION, target=TARGET,
                scope_reference="", test_type=TEST_TYPE, risk_summary=RISK,
                approval_request_id=_new_uuid(), created_at=FIXED_TS,
            )

    def test_missing_test_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="test_type must be a non-empty string"):
            ActiveValidationIntent(
                id=_new_uuid(), actor=ACTOR, action=ACTION, target=TARGET,
                scope_reference=SCOPE, test_type="", risk_summary=RISK,
                approval_request_id=_new_uuid(), created_at=FIXED_TS,
            )

    def test_missing_risk_summary_rejected(self) -> None:
        with pytest.raises(ValueError, match="risk_summary must be a non-empty string"):
            ActiveValidationIntent(
                id=_new_uuid(), actor=ACTOR, action=ACTION, target=TARGET,
                scope_reference=SCOPE, test_type=TEST_TYPE, risk_summary="",
                approval_request_id=_new_uuid(), created_at=FIXED_TS,
            )

    def test_missing_approval_request_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="approval_request_id must be a non-empty string"):
            ActiveValidationIntent(
                id=_new_uuid(), actor=ACTOR, action=ACTION, target=TARGET,
                scope_reference=SCOPE, test_type=TEST_TYPE, risk_summary=RISK,
                approval_request_id="", created_at=FIXED_TS,
            )


class TestGateDecisionModel:
    def test_allow_true_only_for_allow_approved_in_scope(self) -> None:
        decision = ActiveValidationGateDecision(
            reason=ReasonCode.ALLOW_APPROVED_IN_SCOPE,
            intent_id=_new_uuid(), target=TARGET,
            approval_request_id=_new_uuid(), scope_reference=SCOPE,
            timestamp=FIXED_TS,
        )
        assert decision.allow is True

    def test_allow_true_for_any_other_reason_raises(self) -> None:
        with pytest.raises(ValueError, match="allow=True is only valid"):
            ActiveValidationGateDecision(
                reason=ReasonCode.BLOCK_MISSING_APPROVAL,
                intent_id=_new_uuid(), target=TARGET,
                approval_request_id=_new_uuid(), scope_reference=SCOPE,
                allow=True, timestamp=FIXED_TS,
            )

    def test_allow_defaults_to_false_for_block_reasons(self) -> None:
        for reason in ReasonCode:
            if reason == ReasonCode.ALLOW_APPROVED_IN_SCOPE:
                continue
            decision = ActiveValidationGateDecision(
                reason=reason, intent_id=_new_uuid(), target=TARGET,
                approval_request_id=_new_uuid(), scope_reference=SCOPE,
                timestamp=FIXED_TS,
            )
            assert decision.allow is False, f"Expected allow=False for {reason.value}"


class TestApprovalCheck:
    def test_without_approval_block_missing(self, gate: ActiveValidationGate) -> None:
        intent = _make_intent(approval_request_id="nonexistent")
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_MISSING_APPROVAL

    def test_pending_approval_block(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req = approval_workflow.create_request(
            actor=ACTOR, action=ACTION, target=TARGET, scope_reference=SCOPE,
            test_type=TEST_TYPE, risk_summary=RISK, timestamp=FIXED_TS,
        )
        intent = _make_intent(approval_request_id=req.id)
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_PENDING_APPROVAL

    def test_rejected_approval_block(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req = approval_workflow.create_request(
            actor=ACTOR, action=ACTION, target=TARGET, scope_reference=SCOPE,
            test_type=TEST_TYPE, risk_summary=RISK, timestamp=FIXED_TS,
        )
        approval_workflow.record_decision(
            request_id=req.id, decider="human-operator",
            decision=DecisionType.REJECT, reason="Not allowed", timestamp=FIXED_TS_2,
        )
        intent = _make_intent(approval_request_id=req.id)
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_REJECTED_APPROVAL

    def test_invalid_approval_block(
        self, gate: ActiveValidationGate, approval_repo: HumanApprovalRepository,
    ) -> None:
        from neutrino.models.entities import HumanApprovalCreate
        rid = _new_uuid()
        approval_repo.create(HumanApprovalCreate(
            id=rid, actor=ACTOR, decision="EXPIRED", reason="test",
            action=ACTION, target=TARGET, scope_reference=SCOPE,
            test_type=TEST_TYPE, risk_summary=RISK,
        ))
        intent = _make_intent(approval_request_id=rid)
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_INVALID_APPROVAL

    def test_approved_alone_not_enough_without_scopeguard_allow(
        self, approval_workflow: ApprovalWorkflow, approval_repo: HumanApprovalRepository,
        scope_guard: ScopeGuard, deny_scope_policy: ScopePolicy,
        audit_writer: AuditLogWriter, audit_repo: AuditEventRepository,
    ) -> None:
        gate_deny = ActiveValidationGate(
            approval_workflow=approval_workflow, approval_repo=approval_repo,
            scope_guard=scope_guard, scope_policy=deny_scope_policy,
            audit_writer=audit_writer, audit_repo=audit_repo,
        )
        req_id = _create_approved_request(approval_workflow, target="example.com")
        intent = _make_intent(approval_request_id=req_id, target="example.com")
        decision = gate_deny.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_SCOPE_DENIED
        assert decision.allow is False

    def test_full_match_yields_allow(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.ALLOW_APPROVED_IN_SCOPE
        assert decision.allow is True

    def test_approval_for_different_target_block(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req_id = _create_approved_request(approval_workflow, target="example.com")
        intent = _make_intent(approval_request_id=req_id, target="other.com")
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_SCOPE_MISMATCH

    def test_approval_for_different_test_type_block(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req_id = _create_approved_request(approval_workflow, test_type="xss")
        intent = _make_intent(approval_request_id=req_id, test_type="sql_injection")
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_SCOPE_MISMATCH


class TestScopeGuardCheck:
    def test_scope_guard_deny_block(
        self, approval_workflow: ApprovalWorkflow, approval_repo: HumanApprovalRepository,
        scope_guard: ScopeGuard, deny_scope_policy: ScopePolicy,
        audit_writer: AuditLogWriter, audit_repo: AuditEventRepository,
    ) -> None:
        gate_deny = ActiveValidationGate(
            approval_workflow=approval_workflow, approval_repo=approval_repo,
            scope_guard=scope_guard, scope_policy=deny_scope_policy,
            audit_writer=audit_writer, audit_repo=audit_repo,
        )
        req_id = _create_approved_request(approval_workflow, target="example.com")
        intent = _make_intent(approval_request_id=req_id, target="example.com")
        decision = gate_deny.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_SCOPE_DENIED

    def test_scope_guard_missing_policy_block(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        gate_no_policy = ActiveValidationGate(
            approval_workflow=gate._approval_workflow,
            approval_repo=gate._approval_repo,
            scope_guard=gate._scope_guard, scope_policy=None,
            audit_writer=gate._audit_writer, audit_repo=gate._audit_repo,
        )
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        decision = gate_no_policy.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_SCOPE_DENIED

    def test_scope_guard_allow_without_approval_block(
        self, gate: ActiveValidationGate,
    ) -> None:
        intent = _make_intent(approval_request_id="nonexistent")
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_MISSING_APPROVAL

    def test_approval_for_different_scope_block(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req_id = _create_approved_request(approval_workflow, scope_reference="scope://other.com")
        intent = _make_intent(approval_request_id=req_id, scope_reference=SCOPE)
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_SCOPE_MISMATCH

    def test_normalization_lowercases(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req_id = _create_approved_request(approval_workflow, target="Example.COM")
        intent = _make_intent(approval_request_id=req_id, target="example.com")
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.ALLOW_APPROVED_IN_SCOPE


class TestAudit:
    def test_block_missing_approval_audited(
        self, gate: ActiveValidationGate, audit_writer: AuditLogWriter,
    ) -> None:
        intent = _make_intent(approval_request_id="nonexistent")
        gate.evaluate(intent, timestamp=FIXED_TS)
        events = audit_writer.read_all()
        block_events = [e for e in events if e.decision == "block"]
        assert len(block_events) >= 1

    def test_block_rejected_audited(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
        audit_writer: AuditLogWriter,
    ) -> None:
        req = approval_workflow.create_request(
            actor=ACTOR, action=ACTION, target=TARGET, scope_reference=SCOPE,
            test_type=TEST_TYPE, risk_summary=RISK, timestamp=FIXED_TS,
        )
        approval_workflow.record_decision(
            request_id=req.id, decider="human-operator",
            decision=DecisionType.REJECT, reason="Blocked", timestamp=FIXED_TS_2,
        )
        intent = _make_intent(approval_request_id=req.id)
        gate.evaluate(intent, timestamp=FIXED_TS)
        events = audit_writer.read_all()
        block_events = [e for e in events if e.decision == "block"]
        assert len(block_events) >= 1

    def test_block_scope_denied_audited(
        self, approval_workflow: ApprovalWorkflow, approval_repo: HumanApprovalRepository,
        scope_guard: ScopeGuard, deny_scope_policy: ScopePolicy,
        audit_writer: AuditLogWriter, audit_repo: AuditEventRepository,
    ) -> None:
        gate_deny = ActiveValidationGate(
            approval_workflow=approval_workflow, approval_repo=approval_repo,
            scope_guard=scope_guard, scope_policy=deny_scope_policy,
            audit_writer=audit_writer, audit_repo=audit_repo,
        )
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        before = audit_writer.count()
        gate_deny.evaluate(intent, timestamp=FIXED_TS)
        assert audit_writer.count() > before

    def test_allow_audited(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
        audit_writer: AuditLogWriter,
    ) -> None:
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.ALLOW_APPROVED_IN_SCOPE
        events = audit_writer.read_all()
        allow_events = [e for e in events if e.decision == "allow"]
        assert len(allow_events) >= 1

    def test_audit_failure_produces_block(
        self, approval_workflow: ApprovalWorkflow, approval_repo: HumanApprovalRepository,
        scope_guard: ScopeGuard, scope_policy: ScopePolicy,
    ) -> None:
        broken_writer = AuditLogWriter(audit_dir="/dev/null/audit")
        gate_no_audit = ActiveValidationGate(
            approval_workflow=approval_workflow, approval_repo=approval_repo,
            scope_guard=scope_guard, scope_policy=scope_policy,
            audit_writer=broken_writer, audit_repo=None,
        )
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        decision = gate_no_audit.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_AUDIT_FAILED

    def test_no_audit_sink_produces_block(
        self, approval_workflow: ApprovalWorkflow, approval_repo: HumanApprovalRepository,
        scope_guard: ScopeGuard, scope_policy: ScopePolicy,
    ) -> None:
        gate_no_audit = ActiveValidationGate(
            approval_workflow=approval_workflow, approval_repo=approval_repo,
            scope_guard=scope_guard, scope_policy=scope_policy,
            audit_writer=None, audit_repo=None,
        )
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        decision = gate_no_audit.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_AUDIT_FAILED

    def test_audit_event_contains_required_fields(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
        audit_writer: AuditLogWriter,
    ) -> None:
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        gate.evaluate(intent, timestamp=FIXED_TS)
        events = audit_writer.read_all()
        av_events = [e for e in events if e.actor == "active_validation_gate"]
        assert len(av_events) >= 1
        event = av_events[-1]
        assert event.actor == "active_validation_gate"
        assert event.action == "evaluate_active_validation"
        assert event.target == TARGET
        assert event.decision in ("allow", "block")
        assert event.timestamp
        assert event.event is not None


class TestFailClosed:
    def test_no_force_parameter(self) -> None:
        import inspect
        sig = inspect.signature(ActiveValidationGate.evaluate)
        params = list(sig.parameters.keys())
        for forbidden in ("force", "override", "admin_override", "skip_approval",
                          "allow_without_scope", "auto_approve", "llm_approve"):
            assert forbidden not in params, f"Found forbidden param: {forbidden}"

    def test_no_admin_override_in_decision(self) -> None:
        from dataclasses import fields
        field_names = [f.name for f in fields(ActiveValidationGateDecision)]
        for forbidden in ("force", "override", "admin_override", "skip_audit"):
            assert forbidden not in field_names, f"Found forbidden field: {forbidden}"

    def test_no_llm_approve(self) -> None:
        import inspect
        source = inspect.getsource(ActiveValidationGate)
        assert "llm" not in source.lower()
        assert "auto_approve" not in source.lower()

    def test_lab_target_no_auto_allow(self, gate: ActiveValidationGate) -> None:
        intent = _make_intent(target="lab-target.local", approval_request_id="nonexistent")
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_MISSING_APPROVAL
        assert decision.allow is False

    def test_no_auto_approval_decisions(self) -> None:
        values = [r.value for r in ReasonCode]
        for forbidden in ("AUTO_APPROVE", "LLM_APPROVE", "TIMEOUT_APPROVE", "LAB_AUTO_APPROVE"):
            assert forbidden not in values, f"Found forbidden code: {forbidden}"

    def test_fail_closed_on_all_checks(self) -> None:
        for reason in ReasonCode:
            if reason == ReasonCode.ALLOW_APPROVED_IN_SCOPE:
                continue
            assert reason.value.startswith("BLOCK_"), f"{reason.value} should start with BLOCK_"

    def test_deterministic_same_inputs(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        r1 = gate.evaluate(intent, timestamp=FIXED_TS)
        r2 = gate.evaluate(intent, timestamp=FIXED_TS)
        assert r1.reason == r2.reason
        assert r1.allow == r2.allow

    def test_no_time_based_auto_approve(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req = approval_workflow.create_request(
            actor=ACTOR, action=ACTION, target=TARGET, scope_reference=SCOPE,
            test_type=TEST_TYPE, risk_summary=RISK, timestamp=FIXED_TS,
        )
        intent = _make_intent(approval_request_id=req.id)
        decision = gate.evaluate(intent, timestamp="2027-01-01T00:00:00+00:00")
        assert decision.reason == ReasonCode.BLOCK_PENDING_APPROVAL


class TestSafety:
    def test_no_real_requests(self) -> None:
        import inspect
        source = inspect.getsource(ActiveValidationGate)
        for forbidden in ("import requests", "from requests", "import httpx", "from httpx", "urlopen"):
            assert forbidden not in source, f"Found: {forbidden}"

    def test_no_dns_resolution(self) -> None:
        import inspect
        source = inspect.getsource(ActiveValidationGate)
        assert "socket." not in source
        assert "getaddrinfo" not in source

    def test_no_shell_execution(self) -> None:
        import inspect
        source = inspect.getsource(ActiveValidationGate)
        assert "subprocess" not in source
        assert "os.system" not in source
        assert "exec(" not in source

    def test_no_n8n_or_paperclip_imports(self) -> None:
        import inspect
        source = inspect.getsource(ActiveValidationGate)
        assert "n8n" not in source.lower()
        assert "paperclip" not in source.lower()

    def test_no_github_actions(self) -> None:
        assert not os.path.isdir(".github/workflows")

    def test_tests_use_temporary_directories(
        self, tmp_audit_dir: str, db_path: str,
    ) -> None:
        assert "tmp" in str(tmp_audit_dir).lower() or "pytest" in str(tmp_audit_dir).lower()
        assert not tmp_audit_dir.startswith(os.path.expanduser("~/.neutrino"))
        assert "tmp" in db_path.lower() or "pytest" in db_path.lower()

    def test_deterministic_same_gate(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        gate2 = ActiveValidationGate(
            approval_workflow=gate._approval_workflow,
            approval_repo=gate._approval_repo,
            scope_guard=gate._scope_guard, scope_policy=gate._scope_policy,
            audit_writer=gate._audit_writer, audit_repo=gate._audit_repo,
        )
        r1 = gate.evaluate(intent, timestamp=FIXED_TS)
        r2 = gate2.evaluate(intent, timestamp=FIXED_TS)
        assert r1.reason == r2.reason
        assert r1.allow == r2.allow

    def test_no_scanner_imports(self) -> None:
        import inspect
        source = inspect.getsource(ActiveValidationGate)
        assert "nmap" not in source.lower()
        assert "scanner" not in source.lower()
        assert "exploit" not in source.lower()


class TestIntegration:
    def test_full_allow_flow(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
        audit_writer: AuditLogWriter, audit_repo: AuditEventRepository,
    ) -> None:
        req_id = _create_approved_request(approval_workflow)
        intent = _make_intent(approval_request_id=req_id)
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.ALLOW_APPROVED_IN_SCOPE
        assert decision.allow is True
        assert decision.intent_id == intent.id
        assert decision.approval_request_id == req_id
        jsonl_events = audit_writer.read_all()
        av_events = [e for e in jsonl_events if e.actor == "active_validation_gate"]
        assert len(av_events) >= 1
        sqlite_events = audit_repo.list_all()
        av_sql = [e for e in sqlite_events if e.actor == "active_validation_gate"]
        assert len(av_sql) >= 1

    def test_full_reject_flow(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req = approval_workflow.create_request(
            actor=ACTOR, action=ACTION, target=TARGET, scope_reference=SCOPE,
            test_type=TEST_TYPE, risk_summary=RISK, timestamp=FIXED_TS,
        )
        approval_workflow.record_decision(
            request_id=req.id, decider="human-operator",
            decision=DecisionType.REJECT, reason="Not allowed", timestamp=FIXED_TS_2,
        )
        intent = _make_intent(approval_request_id=req.id)
        decision = gate.evaluate(intent, timestamp=FIXED_TS)
        assert decision.reason == ReasonCode.BLOCK_REJECTED_APPROVAL
        assert decision.allow is False

    def test_decision_reason_code_deterministic(
        self, gate: ActiveValidationGate, approval_workflow: ApprovalWorkflow,
    ) -> None:
        req = approval_workflow.create_request(
            actor=ACTOR, action=ACTION, target=TARGET, scope_reference=SCOPE,
            test_type=TEST_TYPE, risk_summary=RISK, timestamp=FIXED_TS,
        )
        intent = _make_intent(approval_request_id=req.id)
        for _ in range(3):
            decision = gate.evaluate(intent, timestamp=FIXED_TS)
            assert decision.reason == ReasonCode.BLOCK_PENDING_APPROVAL
