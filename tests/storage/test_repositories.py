"""Unit tests for Neutrino Storage CRUD Repositories.

Tests all 8 entity repositories with temporary SQLite databases.
Validates CRUD operations, foreign key constraints, error handling,
deterministic ordering, and append-only audit semantics.

No real ``~/.neutrino/`` path is ever written. No ORM, no network I/O.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from neutrino.models.entities import (
    AuditEventCreate,
    EvidenceCreate,
    EvidenceUpdate,
    FindingHypothesisCreate,
    FindingHypothesisUpdate,
    HumanApprovalCreate,
    HumanApprovalUpdate,
    ProgramCreate,
    ProgramUpdate,
    ResearchRunCreate,
    ResearchRunUpdate,
    ScopePolicyCreate,
    ScopePolicyUpdate,
    TargetCreate,
    TargetUpdate,
)
from neutrino.storage.exceptions import (
    AuditEventImmutable,
    EntityNotFound,
    ForeignKeyViolation,
)
from neutrino.storage.migrations import apply_migrations
from neutrino.storage.paths import get_temp_db_path
from neutrino.storage.repositories.audit_events import AuditEventRepository
from neutrino.storage.repositories.evidence import EvidenceRepository
from neutrino.storage.repositories.finding_hypotheses import FindingHypothesisRepository
from neutrino.storage.repositories.human_approvals import HumanApprovalRepository
from neutrino.storage.repositories.programs import ProgramRepository
from neutrino.storage.repositories.research_runs import ResearchRunRepository
from neutrino.storage.repositories.scope_policies import ScopePolicyRepository
from neutrino.storage.repositories.targets import TargetRepository

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@pytest.fixture
def db_path() -> str:
    """A freshly migrated temporary database path."""
    path = get_temp_db_path()
    apply_migrations(path)
    return path


@pytest.fixture
def program_repo(db_path: str) -> ProgramRepository:
    return ProgramRepository(db_path)


@pytest.fixture
def scope_policy_repo(db_path: str) -> ScopePolicyRepository:
    return ScopePolicyRepository(db_path)


@pytest.fixture
def target_repo(db_path: str) -> TargetRepository:
    return TargetRepository(db_path)


@pytest.fixture
def research_run_repo(db_path: str) -> ResearchRunRepository:
    return ResearchRunRepository(db_path)


@pytest.fixture
def finding_repo(db_path: str) -> FindingHypothesisRepository:
    return FindingHypothesisRepository(db_path)


@pytest.fixture
def evidence_repo(db_path: str) -> EvidenceRepository:
    return EvidenceRepository(db_path)


@pytest.fixture
def approval_repo(db_path: str) -> HumanApprovalRepository:
    return HumanApprovalRepository(db_path)


@pytest.fixture
def audit_repo(db_path: str) -> AuditEventRepository:
    return AuditEventRepository(db_path)


# Helper to create a program for FK-dependent tests
def _create_program(repo: ProgramRepository, name: str = "Test Program") -> str:
    pid = _new_uuid()
    repo.create(ProgramCreate(id=pid, name=name, platform="hackerone"))
    return pid


def _create_research_run(
    repo: ResearchRunRepository, program_id: str, status: str = "pending"
) -> str:
    rid = _new_uuid()
    repo.create(ResearchRunCreate(id=rid, program_id=program_id, status=status))
    return rid


def _create_finding_hypothesis(
    repo: FindingHypothesisRepository, research_run_id: str, title: str = "Test Finding"
) -> str:
    fid = _new_uuid()
    repo.create(FindingHypothesisCreate(id=fid, research_run_id=research_run_id, title=title))
    return fid


# ===================================================================
# ProgramRepository Tests
# ===================================================================


class TestProgramRepository:
    """CRUD tests for ProgramRepository."""

    def test_create_and_get(self, program_repo: ProgramRepository) -> None:
        pid = _new_uuid()
        created = program_repo.create(ProgramCreate(id=pid, name="Test", platform="hackerone"))
        assert created.id == pid
        assert created.name == "Test"
        assert created.platform == "hackerone"

        fetched = program_repo.get(pid)
        assert fetched is not None
        assert fetched.id == pid
        assert fetched.name == "Test"

    def test_list_all_returns_empty_initially(self, program_repo: ProgramRepository) -> None:
        assert program_repo.list_all() == []

    def test_list_all_deterministic_ordering(self, program_repo: ProgramRepository) -> None:
        p1 = _new_uuid()
        p2 = _new_uuid()
        import time

        program_repo.create(ProgramCreate(id=p1, name="A"))
        time.sleep(0.1)  # ensure different created_at
        program_repo.create(ProgramCreate(id=p2, name="B"))
        programs = program_repo.list_all()
        assert len(programs) == 2
        assert programs[0].id == p1  # earlier created_at
        assert programs[1].id == p2

    def test_update(self, program_repo: ProgramRepository) -> None:
        pid = _create_program(program_repo, "Old Name")
        updated = program_repo.update(pid, ProgramUpdate(name="New Name"))
        assert updated.name == "New Name"

    def test_update_noop(self, program_repo: ProgramRepository) -> None:
        pid = _create_program(program_repo, "Keep")
        result = program_repo.update(pid, ProgramUpdate())  # empty update
        assert result.name == "Keep"

    def test_delete(self, program_repo: ProgramRepository) -> None:
        pid = _create_program(program_repo, "Delete Me")
        assert program_repo.delete(pid) is True
        assert program_repo.get(pid) is None

    def test_get_missing(self, program_repo: ProgramRepository) -> None:
        assert program_repo.get("nonexistent-id") is None

    def test_update_missing_raises(self, program_repo: ProgramRepository) -> None:
        with pytest.raises(EntityNotFound, match="Program"):
            program_repo.update("nonexistent", ProgramUpdate(name="X"))

    def test_delete_missing_raises(self, program_repo: ProgramRepository) -> None:
        with pytest.raises(EntityNotFound, match="Program"):
            program_repo.delete("nonexistent")

    def test_count(self, program_repo: ProgramRepository) -> None:
        assert program_repo.count() == 0
        _create_program(program_repo, "P1")
        assert program_repo.count() == 1
        _create_program(program_repo, "P2")
        assert program_repo.count() == 2


# ===================================================================
# ScopePolicyRepository Tests
# ===================================================================


class TestScopePolicyRepository:
    """CRUD tests for ScopePolicyRepository."""

    def test_create_and_get(
        self, scope_policy_repo: ScopePolicyRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        spid = _new_uuid()
        parsed = json.dumps({"in_scope": [], "out_of_scope": []})
        created = scope_policy_repo.create(
            ScopePolicyCreate(
                id=spid, program_id=pid, source_url="https://example.com/policy", parsed_json=parsed
            )
        )
        assert created.id == spid
        assert created.program_id == pid
        assert json.loads(created.parsed_json) == {"in_scope": [], "out_of_scope": []}

        fetched = scope_policy_repo.get(spid)
        assert fetched is not None
        assert fetched.program_id == pid

    def test_list_by_program(
        self, scope_policy_repo: ScopePolicyRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        scope_policy_repo.create(
            ScopePolicyCreate(
                id=_new_uuid(), program_id=pid, source_url="https://a.com", parsed_json="{}"
            )
        )
        scope_policy_repo.create(
            ScopePolicyCreate(
                id=_new_uuid(), program_id=pid, source_url="https://b.com", parsed_json="{}"
            )
        )
        policies = scope_policy_repo.list_by_program(pid)
        assert len(policies) == 2

    def test_list_by_program_unknown_id_returns_empty(
        self, scope_policy_repo: ScopePolicyRepository
    ) -> None:
        assert scope_policy_repo.list_by_program("nonexistent") == []

    def test_fk_violation_invalid_program(self, scope_policy_repo: ScopePolicyRepository) -> None:
        with pytest.raises(ForeignKeyViolation, match="scope_policy"):
            scope_policy_repo.create(
                ScopePolicyCreate(
                    id=_new_uuid(),
                    program_id="nonexistent-program",
                    source_url="https://x.com",
                    parsed_json="{}",
                )
            )

    def test_parsed_json_roundtrip(
        self, scope_policy_repo: ScopePolicyRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        spid = _new_uuid()
        data = {"key": "value", "nested": [1, 2, 3]}
        json_str = json.dumps(data)
        scope_policy_repo.create(
            ScopePolicyCreate(
                id=spid, program_id=pid, source_url="https://x.com", parsed_json=json_str
            )
        )
        sp = scope_policy_repo.get(spid)
        assert sp is not None
        assert json.loads(sp.parsed_json) == data

    def test_update(
        self, scope_policy_repo: ScopePolicyRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        spid = _new_uuid()
        scope_policy_repo.create(
            ScopePolicyCreate(id=spid, program_id=pid, source_url="https://x.com", parsed_json="{}")
        )
        updated = scope_policy_repo.update(spid, ScopePolicyUpdate(raw_text="new text"))
        assert updated.raw_text == "new text"

    def test_delete(
        self, scope_policy_repo: ScopePolicyRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        spid = _new_uuid()
        scope_policy_repo.create(
            ScopePolicyCreate(id=spid, program_id=pid, source_url="https://x.com", parsed_json="{}")
        )
        assert scope_policy_repo.delete(spid) is True
        assert scope_policy_repo.get(spid) is None

    def test_get_missing(self, scope_policy_repo: ScopePolicyRepository) -> None:
        assert scope_policy_repo.get("nonexistent") is None

    def test_update_missing_raises(self, scope_policy_repo: ScopePolicyRepository) -> None:
        with pytest.raises(EntityNotFound, match="ScopePolicy"):
            scope_policy_repo.update("nonexistent", ScopePolicyUpdate(raw_text="x"))

    def test_delete_missing_raises(self, scope_policy_repo: ScopePolicyRepository) -> None:
        with pytest.raises(EntityNotFound, match="ScopePolicy"):
            scope_policy_repo.delete("nonexistent")

    def test_list_all_deterministic(
        self, scope_policy_repo: ScopePolicyRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        import time

        sp1 = _new_uuid()
        scope_policy_repo.create(
            ScopePolicyCreate(id=sp1, program_id=pid, source_url="https://a.com", parsed_json="{}")
        )
        time.sleep(0.1)
        sp2 = _new_uuid()
        scope_policy_repo.create(
            ScopePolicyCreate(id=sp2, program_id=pid, source_url="https://b.com", parsed_json="{}")
        )
        policies = scope_policy_repo.list_all()
        assert len(policies) == 2
        assert policies[0].id == sp1
        assert policies[1].id == sp2


# ===================================================================
# TargetRepository Tests
# ===================================================================


class TestTargetRepository:
    """CRUD tests for TargetRepository."""

    def test_create_and_get(
        self, target_repo: TargetRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        tid = _new_uuid()
        created = target_repo.create(
            TargetCreate(id=tid, program_id=pid, pattern="example.com", type="domain")
        )
        assert created.id == tid
        assert created.pattern == "example.com"
        assert not created.is_wildcard

        fetched = target_repo.get(tid)
        assert fetched is not None
        assert fetched.type == "domain"

    def test_wildcard_roundtrip(
        self, target_repo: TargetRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        tid = _new_uuid()
        target_repo.create(
            TargetCreate(
                id=tid,
                program_id=pid,
                pattern="*.example.com",
                type="wildcard_domain",
                is_wildcard=True,
            )
        )
        t = target_repo.get(tid)
        assert t is not None
        assert t.is_wildcard is True
        assert t.pattern == "*.example.com"

    def test_is_wildcard_defaults_false(
        self, target_repo: TargetRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        tid = _new_uuid()
        target_repo.create(
            TargetCreate(id=tid, program_id=pid, pattern="sub.example.com", type="domain")
        )
        t = target_repo.get(tid)
        assert t is not None
        assert t.is_wildcard is False

    def test_list_by_program(
        self, target_repo: TargetRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        target_repo.create(
            TargetCreate(id=_new_uuid(), program_id=pid, pattern="a.com", type="domain")
        )
        target_repo.create(
            TargetCreate(id=_new_uuid(), program_id=pid, pattern="b.com", type="domain")
        )
        targets = target_repo.list_by_program(pid)
        assert len(targets) == 2

    def test_fk_violation(self, target_repo: TargetRepository) -> None:
        with pytest.raises(ForeignKeyViolation, match="target"):
            target_repo.create(
                TargetCreate(
                    id=_new_uuid(), program_id="nonexistent", pattern="x.com", type="domain"
                )
            )

    def test_update(self, target_repo: TargetRepository, program_repo: ProgramRepository) -> None:
        pid = _create_program(program_repo)
        tid = _new_uuid()
        target_repo.create(TargetCreate(id=tid, program_id=pid, pattern="old.com", type="domain"))
        updated = target_repo.update(tid, TargetUpdate(pattern="new.com", is_wildcard=True))
        assert updated.pattern == "new.com"
        assert updated.is_wildcard is True

    def test_delete(self, target_repo: TargetRepository, program_repo: ProgramRepository) -> None:
        pid = _create_program(program_repo)
        tid = _new_uuid()
        target_repo.create(TargetCreate(id=tid, program_id=pid, pattern="x.com", type="domain"))
        assert target_repo.delete(tid) is True
        assert target_repo.get(tid) is None

    def test_get_missing(self, target_repo: TargetRepository) -> None:
        assert target_repo.get("nonexistent") is None

    def test_update_missing_raises(self, target_repo: TargetRepository) -> None:
        with pytest.raises(EntityNotFound, match="Target"):
            target_repo.update("nonexistent", TargetUpdate(pattern="x"))

    def test_delete_missing_raises(self, target_repo: TargetRepository) -> None:
        with pytest.raises(EntityNotFound, match="Target"):
            target_repo.delete("nonexistent")

    def test_list_all_deterministic(
        self, target_repo: TargetRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        import time

        t1 = _new_uuid()
        target_repo.create(TargetCreate(id=t1, program_id=pid, pattern="a.com", type="domain"))
        time.sleep(0.1)
        t2 = _new_uuid()
        target_repo.create(TargetCreate(id=t2, program_id=pid, pattern="b.com", type="domain"))
        targets = target_repo.list_all()
        assert len(targets) == 2
        assert targets[0].id == t1
        assert targets[1].id == t2


# ===================================================================
# ResearchRunRepository Tests
# ===================================================================


class TestResearchRunRepository:
    """CRUD tests for ResearchRunRepository."""

    def test_create_and_get(
        self, research_run_repo: ResearchRunRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        rid = _new_uuid()
        created = research_run_repo.create(
            ResearchRunCreate(id=rid, program_id=pid, status="pending")
        )
        assert created.id == rid
        assert created.status == "pending"
        fetched = research_run_repo.get(rid)
        assert fetched is not None

    def test_list_by_program(
        self, research_run_repo: ResearchRunRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        research_run_repo.create(ResearchRunCreate(id=_new_uuid(), program_id=pid))
        research_run_repo.create(ResearchRunCreate(id=_new_uuid(), program_id=pid))
        runs = research_run_repo.list_by_program(pid)
        assert len(runs) == 2

    def test_fk_violation(self, research_run_repo: ResearchRunRepository) -> None:
        with pytest.raises(ForeignKeyViolation, match="research_run"):
            research_run_repo.create(ResearchRunCreate(id=_new_uuid(), program_id="nonexistent"))

    def test_update_status_and_finished_at(
        self, research_run_repo: ResearchRunRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        rid = _new_uuid()
        research_run_repo.create(ResearchRunCreate(id=rid, program_id=pid, status="pending"))
        now = _now_iso()
        updated = research_run_repo.update(
            rid, ResearchRunUpdate(status="completed", finished_at=now)
        )
        assert updated.status == "completed"
        assert updated.finished_at == now

    def test_delete(
        self, research_run_repo: ResearchRunRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        rid = _new_uuid()
        research_run_repo.create(ResearchRunCreate(id=rid, program_id=pid))
        assert research_run_repo.delete(rid) is True
        assert research_run_repo.get(rid) is None

    def test_get_missing(self, research_run_repo: ResearchRunRepository) -> None:
        assert research_run_repo.get("nonexistent") is None

    def test_update_missing_raises(self, research_run_repo: ResearchRunRepository) -> None:
        with pytest.raises(EntityNotFound, match="ResearchRun"):
            research_run_repo.update("nonexistent", ResearchRunUpdate(status="x"))

    def test_delete_missing_raises(self, research_run_repo: ResearchRunRepository) -> None:
        with pytest.raises(EntityNotFound, match="ResearchRun"):
            research_run_repo.delete("nonexistent")

    def test_list_all_deterministic(
        self, research_run_repo: ResearchRunRepository, program_repo: ProgramRepository
    ) -> None:
        pid = _create_program(program_repo)
        import time

        r1 = _new_uuid()
        research_run_repo.create(ResearchRunCreate(id=r1, program_id=pid))
        time.sleep(0.1)
        r2 = _new_uuid()
        research_run_repo.create(ResearchRunCreate(id=r2, program_id=pid))
        runs = research_run_repo.list_all()
        assert len(runs) == 2
        assert runs[0].id == r1
        assert runs[1].id == r2


# ===================================================================
# FindingHypothesisRepository Tests
# ===================================================================


class TestFindingHypothesisRepository:
    """CRUD tests for FindingHypothesisRepository."""

    @pytest.fixture
    def run_id(
        self, program_repo: ProgramRepository, research_run_repo: ResearchRunRepository
    ) -> str:
        pid = _create_program(program_repo)
        return _create_research_run(research_run_repo, pid)

    def test_create_and_get(self, finding_repo: FindingHypothesisRepository, run_id: str) -> None:
        fid = _new_uuid()
        created = finding_repo.create(
            FindingHypothesisCreate(
                id=fid, research_run_id=run_id, title="SQLi on login", risk_level="high"
            )
        )
        assert created.title == "SQLi on login"
        assert created.risk_level == "high"
        assert created.status == "open"  # default

        fetched = finding_repo.get(fid)
        assert fetched is not None
        assert fetched.title == "SQLi on login"

    def test_list_by_research_run(
        self, finding_repo: FindingHypothesisRepository, run_id: str
    ) -> None:
        finding_repo.create(
            FindingHypothesisCreate(id=_new_uuid(), research_run_id=run_id, title="A")
        )
        finding_repo.create(
            FindingHypothesisCreate(id=_new_uuid(), research_run_id=run_id, title="B")
        )
        findings = finding_repo.list_by_research_run(run_id)
        assert len(findings) == 2

    def test_fk_violation(self, finding_repo: FindingHypothesisRepository) -> None:
        with pytest.raises(ForeignKeyViolation, match="finding_hypothesis"):
            finding_repo.create(
                FindingHypothesisCreate(id=_new_uuid(), research_run_id="nonexistent", title="X")
            )

    def test_update(self, finding_repo: FindingHypothesisRepository, run_id: str) -> None:
        fid = _new_uuid()
        finding_repo.create(FindingHypothesisCreate(id=fid, research_run_id=run_id, title="Old"))
        updated = finding_repo.update(fid, FindingHypothesisUpdate(title="New", status="confirmed"))
        assert updated.title == "New"
        assert updated.status == "confirmed"

    def test_delete(self, finding_repo: FindingHypothesisRepository, run_id: str) -> None:
        fid = _new_uuid()
        finding_repo.create(FindingHypothesisCreate(id=fid, research_run_id=run_id, title="X"))
        assert finding_repo.delete(fid) is True
        assert finding_repo.get(fid) is None

    def test_get_missing(self, finding_repo: FindingHypothesisRepository) -> None:
        assert finding_repo.get("nonexistent") is None

    def test_update_missing_raises(self, finding_repo: FindingHypothesisRepository) -> None:
        with pytest.raises(EntityNotFound, match="FindingHypothesis"):
            finding_repo.update("nonexistent", FindingHypothesisUpdate(title="x"))

    def test_delete_missing_raises(self, finding_repo: FindingHypothesisRepository) -> None:
        with pytest.raises(EntityNotFound, match="FindingHypothesis"):
            finding_repo.delete("nonexistent")


# ===================================================================
# EvidenceRepository Tests
# ===================================================================


class TestEvidenceRepository:
    """CRUD tests for EvidenceRepository."""

    @pytest.fixture
    def finding_id(
        self,
        program_repo: ProgramRepository,
        research_run_repo: ResearchRunRepository,
        finding_repo: FindingHypothesisRepository,
    ) -> str:
        pid = _create_program(program_repo)
        rid = _create_research_run(research_run_repo, pid)
        return _create_finding_hypothesis(finding_repo, rid)

    def test_create_and_get(self, evidence_repo: EvidenceRepository, finding_id: str) -> None:
        eid = _new_uuid()
        created = evidence_repo.create(
            EvidenceCreate(
                id=eid,
                finding_hypothesis_id=finding_id,
                kind="screenshot",
                content_json='{"url":"test.png"}',
            )
        )
        assert created.kind == "screenshot"
        assert json.loads(created.content_json) == {"url": "test.png"}

        fetched = evidence_repo.get(eid)
        assert fetched is not None

    def test_content_json_roundtrip(
        self, evidence_repo: EvidenceRepository, finding_id: str
    ) -> None:
        eid = _new_uuid()
        complex_data = {"key": "value", "list": [1, 2], "nested": {"a": 1}}
        evidence_repo.create(
            EvidenceCreate(
                id=eid,
                finding_hypothesis_id=finding_id,
                kind="log",
                content_json=json.dumps(complex_data),
            )
        )
        ev = evidence_repo.get(eid)
        assert ev is not None
        assert json.loads(ev.content_json) == complex_data

    def test_list_by_finding(self, evidence_repo: EvidenceRepository, finding_id: str) -> None:
        evidence_repo.create(
            EvidenceCreate(
                id=_new_uuid(),
                finding_hypothesis_id=finding_id,
                kind="screenshot",
                content_json="{}",
            )
        )
        evidence_repo.create(
            EvidenceCreate(
                id=_new_uuid(), finding_hypothesis_id=finding_id, kind="log", content_json="{}"
            )
        )
        items = evidence_repo.list_by_finding(finding_id)
        assert len(items) == 2

    def test_fk_violation(self, evidence_repo: EvidenceRepository) -> None:
        with pytest.raises(ForeignKeyViolation, match="evidence"):
            evidence_repo.create(
                EvidenceCreate(
                    id=_new_uuid(), finding_hypothesis_id="nonexistent", kind="x", content_json="{}"
                )
            )

    def test_update(self, evidence_repo: EvidenceRepository, finding_id: str) -> None:
        eid = _new_uuid()
        evidence_repo.create(
            EvidenceCreate(id=eid, finding_hypothesis_id=finding_id, kind="old", content_json="{}")
        )
        updated = evidence_repo.update(eid, EvidenceUpdate(kind="new", source="updated_source"))
        assert updated.kind == "new"
        assert updated.source == "updated_source"

    def test_delete(self, evidence_repo: EvidenceRepository, finding_id: str) -> None:
        eid = _new_uuid()
        evidence_repo.create(
            EvidenceCreate(id=eid, finding_hypothesis_id=finding_id, kind="x", content_json="{}")
        )
        assert evidence_repo.delete(eid) is True
        assert evidence_repo.get(eid) is None

    def test_get_missing(self, evidence_repo: EvidenceRepository) -> None:
        assert evidence_repo.get("nonexistent") is None

    def test_update_missing_raises(self, evidence_repo: EvidenceRepository) -> None:
        with pytest.raises(EntityNotFound, match="Evidence"):
            evidence_repo.update("nonexistent", EvidenceUpdate(kind="x"))

    def test_delete_missing_raises(self, evidence_repo: EvidenceRepository) -> None:
        with pytest.raises(EntityNotFound, match="Evidence"):
            evidence_repo.delete("nonexistent")


# ===================================================================
# HumanApprovalRepository Tests
# ===================================================================


class TestHumanApprovalRepository:
    """CRUD tests for HumanApprovalRepository."""

    @pytest.fixture
    def run_id(
        self, program_repo: ProgramRepository, research_run_repo: ResearchRunRepository
    ) -> str:
        pid = _create_program(program_repo)
        return _create_research_run(research_run_repo, pid)

    def test_create_and_get(self, approval_repo: HumanApprovalRepository, run_id: str) -> None:
        aid = _new_uuid()
        created = approval_repo.create(
            HumanApprovalCreate(
                id=aid, research_run_id=run_id, actor="admin", decision="approved", reason="Safe"
            )
        )
        assert created.actor == "admin"
        assert created.decision == "approved"
        assert created.reason == "Safe"

        fetched = approval_repo.get(aid)
        assert fetched is not None

    def test_list_by_research_run(
        self, approval_repo: HumanApprovalRepository, run_id: str
    ) -> None:
        approval_repo.create(
            HumanApprovalCreate(
                id=_new_uuid(), research_run_id=run_id, actor="u1", decision="approved"
            )
        )
        approval_repo.create(
            HumanApprovalCreate(
                id=_new_uuid(), research_run_id=run_id, actor="u2", decision="rejected"
            )
        )
        approvals = approval_repo.list_by_research_run(run_id)
        assert len(approvals) == 2

    def test_fk_violation(self, approval_repo: HumanApprovalRepository) -> None:
        with pytest.raises(ForeignKeyViolation, match="human_approval"):
            approval_repo.create(
                HumanApprovalCreate(
                    id=_new_uuid(), research_run_id="nonexistent", actor="x", decision="approved"
                )
            )

    def test_update_decision(self, approval_repo: HumanApprovalRepository, run_id: str) -> None:
        aid = _new_uuid()
        approval_repo.create(
            HumanApprovalCreate(id=aid, research_run_id=run_id, actor="admin", decision="pending")
        )
        updated = approval_repo.update(
            aid, HumanApprovalUpdate(decision="approved", reason="Reviewed")
        )
        assert updated.decision == "approved"
        assert updated.reason == "Reviewed"

    def test_delete(self, approval_repo: HumanApprovalRepository, run_id: str) -> None:
        aid = _new_uuid()
        approval_repo.create(
            HumanApprovalCreate(id=aid, research_run_id=run_id, actor="admin", decision="approved")
        )
        assert approval_repo.delete(aid) is True
        assert approval_repo.get(aid) is None

    def test_get_missing(self, approval_repo: HumanApprovalRepository) -> None:
        assert approval_repo.get("nonexistent") is None

    def test_update_missing_raises(self, approval_repo: HumanApprovalRepository) -> None:
        with pytest.raises(EntityNotFound, match="HumanApproval"):
            approval_repo.update("nonexistent", HumanApprovalUpdate(decision="x"))

    def test_delete_missing_raises(self, approval_repo: HumanApprovalRepository) -> None:
        with pytest.raises(EntityNotFound, match="HumanApproval"):
            approval_repo.delete("nonexistent")


# ===================================================================
# AuditEventRepository Tests
# ===================================================================


class TestAuditEventRepository:
    """Append-only tests for AuditEventRepository."""

    def test_create_and_get(self, audit_repo: AuditEventRepository) -> None:
        eid = _new_uuid()
        created = audit_repo.create(
            AuditEventCreate(
                id=eid,
                actor="system",
                action="scope_check",
                target="example.com",
                decision="allow",
                event_json=json.dumps({"result": "ok"}),
                timestamp=_now_iso(),
            )
        )
        assert created.actor == "system"
        assert created.action == "scope_check"

        fetched = audit_repo.get(eid)
        assert fetched is not None
        assert fetched.target == "example.com"

    def test_append_is_alias_for_create(self, audit_repo: AuditEventRepository) -> None:
        eid = _new_uuid()
        created = audit_repo.append(
            AuditEventCreate(
                id=eid,
                actor="agent",
                action="test",
                event_json="{}",
                timestamp=_now_iso(),
            )
        )
        assert created.actor == "agent"
        assert audit_repo.get(eid) is not None

    def test_event_json_roundtrip(self, audit_repo: AuditEventRepository) -> None:
        eid = _new_uuid()
        data = {"a": 1, "b": [2, 3], "c": {"d": "e"}}
        audit_repo.create(
            AuditEventCreate(
                id=eid,
                actor="test",
                action="json_test",
                event_json=json.dumps(data),
                timestamp=_now_iso(),
            )
        )
        event = audit_repo.get(eid)
        assert event is not None
        assert json.loads(event.event_json) == data

    def test_list_all_deterministic(self, audit_repo: AuditEventRepository) -> None:
        import time

        t1 = _now_iso()
        time.sleep(0.1)
        e1 = _new_uuid()
        audit_repo.create(
            AuditEventCreate(id=e1, actor="a", action="first", event_json="{}", timestamp=t1)
        )
        time.sleep(0.1)
        t2 = _now_iso()
        e2 = _new_uuid()
        audit_repo.create(
            AuditEventCreate(id=e2, actor="b", action="second", event_json="{}", timestamp=t2)
        )
        events = audit_repo.list_all()
        assert len(events) == 2
        assert events[0].id == e1  # earlier timestamp
        assert events[1].id == e2

    def test_list_by_actor(self, audit_repo: AuditEventRepository) -> None:
        audit_repo.create(
            AuditEventCreate(
                id=_new_uuid(), actor="agent_x", action="a", event_json="{}", timestamp=_now_iso()
            )
        )
        audit_repo.create(
            AuditEventCreate(
                id=_new_uuid(), actor="agent_x", action="b", event_json="{}", timestamp=_now_iso()
            )
        )
        audit_repo.create(
            AuditEventCreate(
                id=_new_uuid(), actor="agent_y", action="c", event_json="{}", timestamp=_now_iso()
            )
        )
        x_events = audit_repo.list_by_actor("agent_x")
        assert len(x_events) == 2
        y_events = audit_repo.list_by_actor("agent_y")
        assert len(y_events) == 1

    def test_list_by_action(self, audit_repo: AuditEventRepository) -> None:
        audit_repo.create(
            AuditEventCreate(
                id=_new_uuid(), actor="a", action="login", event_json="{}", timestamp=_now_iso()
            )
        )
        audit_repo.create(
            AuditEventCreate(
                id=_new_uuid(), actor="b", action="login", event_json="{}", timestamp=_now_iso()
            )
        )
        events = audit_repo.list_by_action("login")
        assert len(events) == 2

    def test_update_forbidden(self, audit_repo: AuditEventRepository) -> None:
        with pytest.raises(AuditEventImmutable, match="UPDATE"):
            audit_repo.update("some-id")

    def test_delete_forbidden(self, audit_repo: AuditEventRepository) -> None:
        with pytest.raises(AuditEventImmutable, match="DELETE"):
            audit_repo.delete("some-id")

    def test_get_missing(self, audit_repo: AuditEventRepository) -> None:
        assert audit_repo.get("nonexistent") is None

    def test_no_foreign_keys(self, audit_repo: AuditEventRepository) -> None:
        """Audit events should accept any values (no FK constraints)."""
        # Should NOT raise
        audit_repo.create(
            AuditEventCreate(
                id=_new_uuid(),
                actor="any",
                action="any",
                target="nonexistent-target",
                decision="any",
                event_json="{}",
                timestamp=_now_iso(),
            )
        )


# ===================================================================
# Determinism Tests
# ===================================================================


class TestDeterminism:
    """Verify deterministic ordering across all list operations."""

    def test_ordering_is_stable_across_same_timestamp(
        self, db_path: str, program_repo: ProgramRepository
    ) -> None:
        """With identical created_at, ordering falls back to id ASC."""
        p1 = _new_uuid()
        p2 = _new_uuid()
        # Create both quickly — they'll have very close timestamps
        program_repo.create(ProgramCreate(id=p1, name="First"))
        program_repo.create(ProgramCreate(id=p2, name="Second"))
        programs = program_repo.list_all()
        assert len(programs) == 2
        # Order is created_at ASC, id ASC — so p1 should come before p2 if timestamps equal
        if programs[0].created_at == programs[1].created_at:
            assert programs[0].id <= programs[1].id


# ===================================================================
# Safety Tests
# ===================================================================


class TestRepositoriesSafety:
    """Verify no ORM, no remote DB, no production paths in tests."""

    def test_no_orm_libraries_imported(self) -> None:
        """Repository modules do not import ORM libraries."""
        from neutrino.storage.repositories import base as base_mod
        from neutrino.storage.repositories import programs as prog_mod

        for mod in (base_mod, prog_mod):
            source = str(mod.__dict__)
            assert "sqlalchemy" not in source.lower()
            assert "django" not in source.lower()
            assert "peewee" not in source.lower()

    def test_all_test_paths_outside_home(self, db_path: str) -> None:
        """Test database path is outside ~/.neutrino/."""
        assert ".neutrino" not in db_path

    def test_no_network_in_repository_modules(self) -> None:
        """Repository modules have no network-related code."""
        from neutrino.storage.repositories import (
            audit_events,
            programs,
        )

        for mod in (audit_events, programs):
            source = str(mod.__dict__)
            assert "socket" not in source.lower()
            assert "http" not in source.lower()
            assert "requests" not in source.lower()

    def test_repos_use_explicit_sql(self) -> None:
        """Repositories use explicit SQL, not ORM query builders."""
        from neutrino.storage.repositories.programs import ProgramRepository

        source = ProgramRepository.create.__code__.co_consts
        assert any("INSERT INTO programs" in str(c) for c in source if isinstance(c, str))
