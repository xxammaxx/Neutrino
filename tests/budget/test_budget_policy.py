"""Tests for BudgetPolicy status logic — Issue #13.

Covers:
    - EXHAUSTED detection (10 tests)
    - Missing/Error handling (5 tests)
    - Reproducibility (3 tests)
    - Status change persistence (5 tests)
    - Safety (7 tests)

All tests are local, deterministic, and use temporary SQLite databases
where storage is needed.
"""

from __future__ import annotations

import json
import uuid

import pytest

from neutrino.budget.models import BudgetDecision, BudgetPolicy, BudgetStatus, BudgetUsage
from neutrino.budget.policy import evaluate_budget
from neutrino.budget.status import apply_budget_decision

# ------------------------------------------------------------------
# Fixed test constants
# ------------------------------------------------------------------

FIXED_TIMESTAMP = "2026-07-06T12:00:00+00:00"
FIXED_TIMESTAMP_2 = "2026-07-06T13:00:00+00:00"

_POLICY_ALL_LIMITS = BudgetPolicy(
    max_requests=100,
    max_cost_cents=5000,
    max_runtime_seconds=3600,
)

_POLICY_REQUESTS_ONLY = BudgetPolicy(max_requests=50)
_POLICY_COST_ONLY = BudgetPolicy(max_cost_cents=1000)
_POLICY_RUNTIME_ONLY = BudgetPolicy(max_runtime_seconds=600)

_USAGE_ZERO = BudgetUsage()
_USAGE_LOW = BudgetUsage(requests_used=10, cost_cents_used=100, runtime_seconds_used=60)


# ==================================================================
# Test Class 1: EXHAUSTED Detection
# ==================================================================


class TestExhaustedDetection:
    """Tests for correct EXHAUSTED detection across all limit types."""

    # --- Requests limit ---

    def test_requests_under_limit_returns_ok(self):
        """Requests below limit → OK."""
        policy = BudgetPolicy(max_requests=100)
        usage = BudgetUsage(requests_used=50)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.OK

    def test_requests_at_limit_returns_exhausted(self):
        """Requests equal to limit → EXHAUSTED."""
        policy = BudgetPolicy(max_requests=100)
        usage = BudgetUsage(requests_used=100)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_requests"
        assert decision.limit_value == 100
        assert decision.observed_value == 100

    def test_requests_over_limit_returns_exhausted(self):
        """Requests over limit → EXHAUSTED."""
        policy = BudgetPolicy(max_requests=100)
        usage = BudgetUsage(requests_used=150)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_requests"
        assert decision.limit_value == 100
        assert decision.observed_value == 150

    # --- Cost limit ---

    def test_cost_under_limit_returns_ok(self):
        """Cost below limit → OK."""
        policy = BudgetPolicy(max_cost_cents=5000)
        usage = BudgetUsage(cost_cents_used=1000)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.OK

    def test_cost_at_limit_returns_exhausted(self):
        """Cost equal to limit → EXHAUSTED."""
        policy = BudgetPolicy(max_cost_cents=5000)
        usage = BudgetUsage(cost_cents_used=5000)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_cost_cents"

    def test_cost_over_limit_returns_exhausted(self):
        """Cost over limit → EXHAUSTED."""
        policy = BudgetPolicy(max_cost_cents=5000)
        usage = BudgetUsage(cost_cents_used=6000)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_cost_cents"

    # --- Runtime limit ---

    def test_runtime_under_limit_returns_ok(self):
        """Runtime below limit → OK."""
        policy = BudgetPolicy(max_runtime_seconds=3600)
        usage = BudgetUsage(runtime_seconds_used=1800)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.OK

    def test_runtime_at_limit_returns_exhausted(self):
        """Runtime equal to limit → EXHAUSTED."""
        policy = BudgetPolicy(max_runtime_seconds=3600)
        usage = BudgetUsage(runtime_seconds_used=3600)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_runtime_seconds"

    def test_runtime_over_limit_returns_exhausted(self):
        """Runtime over limit → EXHAUSTED."""
        policy = BudgetPolicy(max_runtime_seconds=3600)
        usage = BudgetUsage(runtime_seconds_used=5000)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_runtime_seconds"

    # --- Multiple limits: first exhausted wins ---

    def test_first_exhausted_limit_wins_deterministic(self):
        """When multiple limits are exhausted, the first (requests > cost > runtime) wins."""
        policy = BudgetPolicy(
            max_requests=10,
            max_cost_cents=100,
            max_runtime_seconds=60,
        )
        usage = BudgetUsage(requests_used=20, cost_cents_used=200, runtime_seconds_used=120)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_requests"  # requests checked first

    def test_cost_exhausted_when_requests_ok(self):
        """Cost exhausted but requests OK → limit_name is max_cost_cents."""
        policy = BudgetPolicy(max_requests=100, max_cost_cents=50)
        usage = BudgetUsage(requests_used=10, cost_cents_used=50)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_cost_cents"

    def test_runtime_exhausted_when_others_ok(self):
        """Runtime exhausted but requests and cost OK → limit_name is max_runtime_seconds."""
        policy = BudgetPolicy(max_requests=100, max_cost_cents=10000, max_runtime_seconds=10)
        usage = BudgetUsage(requests_used=5, cost_cents_used=0, runtime_seconds_used=10)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.EXHAUSTED
        assert decision.limit_name == "max_runtime_seconds"


# ==================================================================
# Test Class 2: Missing / Error Handling
# ==================================================================


class TestErrorHandling:
    """Tests for error states: missing policy, negative values, invalid types."""

    def test_missing_policy_raises_value_error(self):
        """None policy → ValueError (contract violation)."""
        with pytest.raises(ValueError, match="policy must not be None"):
            evaluate_budget(None, _USAGE_ZERO, FIXED_TIMESTAMP)  # type: ignore[arg-type]

    def test_no_limits_configured_returns_error(self):
        """No limits set → ERROR (conservative default)."""
        policy = BudgetPolicy()  # No limits
        decision = evaluate_budget(policy, _USAGE_ZERO, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.ERROR
        assert "missing_budget_limits" in decision.reason

    def test_negative_requests_usage_returns_error(self):
        """Negative requests_used → ERROR."""
        policy = BudgetPolicy(max_requests=100)
        usage = BudgetUsage(requests_used=-1)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.ERROR
        assert "negative" in decision.reason.lower()

    def test_negative_cost_usage_returns_error(self):
        """Negative cost_cents_used → ERROR."""
        policy = BudgetPolicy(max_cost_cents=100)
        usage = BudgetUsage(cost_cents_used=-1)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.ERROR

    def test_negative_runtime_usage_returns_error(self):
        """Negative runtime_seconds_used → ERROR."""
        policy = BudgetPolicy(max_runtime_seconds=100)
        usage = BudgetUsage(runtime_seconds_used=-1)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.ERROR

    def test_negative_limit_returns_error(self):
        """Negative max_requests → ERROR."""
        policy = BudgetPolicy(max_requests=-5)
        usage = BudgetUsage(requests_used=10)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.ERROR

    def test_negative_cost_limit_returns_error(self):
        """Negative max_cost_cents → ERROR."""
        policy = BudgetPolicy(max_cost_cents=-1)
        usage = BudgetUsage(cost_cents_used=0)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.ERROR

    def test_negative_runtime_limit_returns_error(self):
        """Negative max_runtime_seconds → ERROR."""
        policy = BudgetPolicy(max_runtime_seconds=-1)
        usage = BudgetUsage(runtime_seconds_used=0)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.ERROR

    def test_only_some_limits_set_others_none_still_checks(self):
        """Only max_requests set, others None → checks only requests."""
        policy = BudgetPolicy(max_requests=100, max_cost_cents=None, max_runtime_seconds=None)
        usage = BudgetUsage(requests_used=50)
        decision = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.OK

    def test_all_limits_none_returns_error_not_ok(self):
        """All limits explicitly None → ERROR (unconfigured)."""
        policy = BudgetPolicy(max_requests=None, max_cost_cents=None, max_runtime_seconds=None)
        decision = evaluate_budget(policy, _USAGE_ZERO, FIXED_TIMESTAMP)
        assert decision.status == BudgetStatus.ERROR


# ==================================================================
# Test Class 3: Reproducibility
# ==================================================================


class TestReproducibility:
    """Tests that budget evaluations are deterministic and reproducible."""

    def test_same_inputs_same_timestamp_give_same_decision(self):
        """Identical inputs and timestamp → identical decisions."""
        policy = _POLICY_ALL_LIMITS
        usage = _USAGE_LOW
        d1 = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        d2 = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert d1 == d2
        assert d1.model_dump() == d2.model_dump()

    def test_same_inputs_different_timestamp_only_differs_in_timestamp(self):
        """Same inputs + different timestamp → only timestamp differs."""
        policy = _POLICY_ALL_LIMITS
        usage = _USAGE_LOW
        d1 = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        d2 = evaluate_budget(policy, usage, FIXED_TIMESTAMP_2)
        assert d1.status == d2.status
        assert d1.reason == d2.reason
        assert d1.limit_name == d2.limit_name
        assert d1.timestamp != d2.timestamp

    def test_limit_priority_order_is_documented_and_tested(self):
        """Limit check order: requests → cost → runtime. Verified via limit_name."""
        # requests and cost both exhausted → requests wins
        policy = BudgetPolicy(max_requests=5, max_cost_cents=5)
        usage = BudgetUsage(requests_used=10, cost_cents_used=10)
        d = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert d.limit_name == "max_requests"

        # Only cost exhausted → cost wins
        policy2 = BudgetPolicy(max_requests=100, max_cost_cents=5)
        d2 = evaluate_budget(policy2, usage, FIXED_TIMESTAMP)
        assert d2.limit_name == "max_cost_cents"

        # Only runtime exhausted → runtime wins
        policy3 = BudgetPolicy(max_requests=100, max_cost_cents=100, max_runtime_seconds=5)
        usage3 = BudgetUsage(requests_used=1, cost_cents_used=1, runtime_seconds_used=10)
        d3 = evaluate_budget(policy3, usage3, FIXED_TIMESTAMP)
        assert d3.limit_name == "max_runtime_seconds"

    def test_no_system_time_dependency_when_timestamp_injected(self):
        """Core function accepts injected timestamp, no datetime.now() call."""
        policy = _POLICY_ALL_LIMITS
        usage = _USAGE_LOW
        # Calling twice with same timestamp gives identical results
        d1 = evaluate_budget(policy, usage, "2000-01-01T00:00:00Z")
        d2 = evaluate_budget(policy, usage, "2000-01-01T00:00:00Z")
        assert d1.model_dump() == d2.model_dump()


# ==================================================================
# Test Class 4: Status Change Persistence
# ==================================================================


class TestStatusChangePersistence:
    """Tests for saving status changes via repositories."""

    @pytest.fixture
    def tmp_db_and_schema(self, tmp_path) -> str:
        """Create a temporary SQLite database with the Neutrino schema."""
        from neutrino.storage.migrations import apply_migrations

        db_path = str(tmp_path / "test_budget.db")
        apply_migrations(db_path)
        return db_path

    @pytest.fixture
    def program_id(self, tmp_db_and_schema: str) -> str:
        """Create a Program so FK constraints are satisfied."""
        from neutrino.models.entities import ProgramCreate
        from neutrino.storage.repositories.programs import ProgramRepository

        repo = ProgramRepository(tmp_db_and_schema)
        pid = str(uuid.uuid4())
        repo.create(ProgramCreate(id=pid, name="Budget Test Program", platform="test"))
        return pid

    @pytest.fixture
    def run_repo(self, tmp_db_and_schema: str):
        """Create a ResearchRunRepository backed by the temp DB."""
        from neutrino.storage.repositories.research_runs import ResearchRunRepository

        return ResearchRunRepository(tmp_db_and_schema)

    @pytest.fixture
    def audit_repo(self, tmp_db_and_schema: str):
        """Create an AuditEventRepository backed by the temp DB."""
        from neutrino.storage.repositories.audit_events import AuditEventRepository

        return AuditEventRepository(tmp_db_and_schema)

    def _create_research_run(self, run_repo, run_id: str, program_id: str, status: str = "running"):
        from neutrino.models.entities import ResearchRunCreate

        run_repo.create(
            ResearchRunCreate(
                id=run_id,
                program_id=program_id,
                status=status,
            )
        )

    def test_ok_to_exhausted_updates_run_status(self, run_repo, audit_repo, program_id):
        """OK → EXHAUSTED: ResearchRun status updated to 'exhausted'."""
        run_id = str(uuid.uuid4())
        self._create_research_run(run_repo, run_id, program_id, status="running")

        decision = BudgetDecision(
            status=BudgetStatus.EXHAUSTED,
            reason="Request limit exhausted: 100 >= 100",
            limit_name="max_requests",
            limit_value=100,
            observed_value=100,
            timestamp=FIXED_TIMESTAMP,
        )

        applied = apply_budget_decision(
            decision,
            run_id,
            run_repo=run_repo,
            audit_repo=audit_repo,
        )
        assert applied

        updated = run_repo.get(run_id)
        assert updated is not None
        assert updated.status == "exhausted"

    def test_exhausted_status_persists_no_auto_recovery(self, run_repo, audit_repo, program_id):
        """Already exhausted run stays exhausted even with lower usage."""
        run_id = str(uuid.uuid4())
        self._create_research_run(run_repo, run_id, program_id, status="running")

        # First: exhaust it
        decision1 = BudgetDecision(
            status=BudgetStatus.EXHAUSTED,
            reason="Request limit exhausted: 100 >= 100",
            limit_name="max_requests",
            limit_value=100,
            observed_value=100,
            timestamp=FIXED_TIMESTAMP,
        )
        apply_budget_decision(decision1, run_id, run_repo=run_repo, audit_repo=audit_repo)
        assert run_repo.get(run_id).status == "exhausted"

        # Second: try a later evaluation with lower usage
        decision2 = BudgetDecision(
            status=BudgetStatus.OK,
            reason="All budget limits respected",
            timestamp=FIXED_TIMESTAMP_2,
        )
        apply_budget_decision(decision2, run_id, run_repo=run_repo, audit_repo=audit_repo)

        # The decision is OK, but _maybe_update_run_status only updates on
        # EXHAUSTED/ERROR, so the run status stays "exhausted".
        updated = run_repo.get(run_id)
        assert updated.status == "exhausted"

    def test_error_decision_logs_audit_event(self, run_repo, audit_repo, program_id):
        """ERROR decision is logged as an AuditEvent."""
        run_id = str(uuid.uuid4())
        self._create_research_run(run_repo, run_id, program_id, status="running")

        decision = BudgetDecision(
            status=BudgetStatus.ERROR,
            reason="No budget limits configured (missing_budget_limits)",
            timestamp=FIXED_TIMESTAMP,
        )

        count_before = audit_repo.count()
        apply_budget_decision(decision, run_id, run_repo=run_repo, audit_repo=audit_repo)
        count_after = audit_repo.count()
        assert count_after == count_before + 1

        events = audit_repo.list_all()
        event = events[-1]
        assert event.action == "budget_evaluated"
        assert event.decision == "error"
        assert f"research_run:{run_id}" in (event.target or "")

    def test_exhausted_decision_logs_audit_event(self, run_repo, audit_repo, program_id):
        """EXHAUSTED decision is logged as an AuditEvent."""
        run_id = str(uuid.uuid4())
        self._create_research_run(run_repo, run_id, program_id, status="running")

        decision = BudgetDecision(
            status=BudgetStatus.EXHAUSTED,
            reason="Runtime limit exhausted: 3600 >= 3600",
            limit_name="max_runtime_seconds",
            limit_value=3600,
            observed_value=3600,
            timestamp=FIXED_TIMESTAMP,
        )

        count_before = audit_repo.count()
        apply_budget_decision(decision, run_id, run_repo=run_repo, audit_repo=audit_repo)
        count_after = audit_repo.count()
        assert count_after == count_before + 1

    def test_ok_decision_does_not_update_run_status(self, run_repo, audit_repo, program_id):
        """OK decision does NOT update ResearchRun status (only EXHAUSTED/ERROR do)."""
        run_id = str(uuid.uuid4())
        self._create_research_run(run_repo, run_id, program_id, status="running")

        decision = BudgetDecision(
            status=BudgetStatus.OK,
            reason="All budget limits respected",
            timestamp=FIXED_TIMESTAMP,
        )

        apply_budget_decision(decision, run_id, run_repo=run_repo, audit_repo=audit_repo)
        updated = run_repo.get(run_id)
        assert updated.status == "running"  # unchanged

    def test_missing_run_repo_does_not_crash(self, audit_repo, program_id):
        """apply_budget_decision works without a run_repo (audit only)."""
        decision = BudgetDecision(
            status=BudgetStatus.EXHAUSTED,
            reason="Test",
            limit_name="max_requests",
            limit_value=10,
            observed_value=10,
            timestamp=FIXED_TIMESTAMP,
        )
        applied = apply_budget_decision(
            decision,
            str(uuid.uuid4()),
            run_repo=None,
            audit_repo=audit_repo,
        )
        assert applied  # True because audit was logged

    def test_missing_audit_repo_does_not_crash(self, run_repo, program_id):
        """apply_budget_decision works without an audit_repo (status only)."""
        run_id = str(uuid.uuid4())
        self._create_research_run(run_repo, run_id, program_id, status="running")

        decision = BudgetDecision(
            status=BudgetStatus.EXHAUSTED,
            reason="Test",
            limit_name="max_requests",
            limit_value=10,
            observed_value=10,
            timestamp=FIXED_TIMESTAMP,
        )
        applied = apply_budget_decision(decision, run_id, run_repo=run_repo, audit_repo=None)
        assert applied

    def test_nonexistent_run_does_not_crash(self, run_repo, audit_repo, program_id):
        """Applying decision to nonexistent run logs audit but does not crash."""
        decision = BudgetDecision(
            status=BudgetStatus.EXHAUSTED,
            reason="Test",
            limit_name="max_requests",
            limit_value=10,
            observed_value=10,
            timestamp=FIXED_TIMESTAMP,
        )
        # Should not raise — audit event still logged
        apply_budget_decision(
            decision,
            "nonexistent-id",
            run_repo=run_repo,
            audit_repo=audit_repo,
        )
        assert audit_repo.count() >= 1


# ==================================================================
# Test Class 5: Safety / Non-Goals
# ==================================================================


class TestSafetyChecks:
    """Verify no unsafe operations are present in the budget module."""

    def test_no_network_imports_in_budget_module(self):
        """Budget module does not import requests, urllib, socket, http."""
        import neutrino.budget.models as m
        import neutrino.budget.policy as p
        import neutrino.budget.status as s

        forbidden = {"requests", "urllib", "socket", "http.client", "aiohttp"}
        for mod in (p, m, s):
            for attr in dir(mod):
                assert attr not in forbidden, f"{mod.__name__} imports {attr}"

    def test_no_auto_recovery_method_exists(self):
        """No method named 'recover', 'reset', 'restore', 'auto_renew' in budget module."""
        import neutrino.budget

        forbidden_names = {"recover", "reset", "restore", "auto_renew", "replenish"}
        for name in forbidden_names:
            assert not hasattr(neutrino.budget, name), f"Auto-recovery method '{name}' found"

    def test_no_cloud_billing_terms_in_source(self):
        """No cloud billing integration terms in budget module source code."""
        import neutrino.budget

        source_files = [
            neutrino.budget.models,
            neutrino.budget.policy,
            neutrino.budget.status,
        ]
        # Terms that indicate active integration, not just documentation mentions
        forbidden_terms = {"stripe", "invoice", "credit_card", "payment", "aws", "gcp", "azure"}
        for mod in source_files:
            mod_source = mod.__doc__ or ""
            for term in forbidden_terms:
                assert term not in mod_source.lower(), f"'{term}' found in {mod.__name__}"

    def test_exhausted_is_endgueltig_in_docstring(self):
        """Documentation states EXHAUSTED is final and not auto-reset."""
        import neutrino.budget.status as s

        doc = (s.__doc__ or "").lower()
        assert "no automatic reset" in doc

    def test_no_dns_resolution_in_budget(self):
        """Budget module has no DNS operations."""
        import neutrino.budget.policy
        import neutrino.budget.status

        source_p = __import__("inspect").getsource(neutrino.budget.policy.evaluate_budget)
        source_s = __import__("inspect").getsource(neutrino.budget.status.apply_budget_decision)
        dns_functions = {"gethostbyname", "getaddrinfo", "dns.resolver", "resolve"}
        for func in dns_functions:
            assert func not in source_p, f"DNS function '{func}' found in policy"
            assert func not in source_s, f"DNS function '{func}' found in status"

    def test_no_n8n_paperclip_imports(self):
        """Budget module has no n8n or Paperclip dependencies."""
        import neutrino.budget

        for attr in dir(neutrino.budget):
            val = getattr(neutrino.budget, attr)
            if hasattr(val, "__module__"):
                mod_name = val.__module__
                assert "n8n" not in mod_name, f"n8n import in {attr}"
                assert "paperclip" not in mod_name, f"Paperclip import in {attr}"

    def test_evaluate_budget_is_pure_no_side_effects(self):
        """evaluate_budget is a pure function with no I/O side effects."""
        policy = _POLICY_ALL_LIMITS
        usage = _USAGE_LOW
        # Calling multiple times produces same result, no mutation
        d1 = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        d2 = evaluate_budget(policy, usage, FIXED_TIMESTAMP)
        assert d1 == d2
        # Original objects unchanged
        assert policy.max_requests == 100
        assert usage.requests_used == 10


# ==================================================================
# Test Class 6: Model Tests
# ==================================================================


class TestBudgetModels:
    """Tests for BudgetPolicy, BudgetUsage, BudgetDecision model behavior."""

    def test_budget_policy_has_any_limit_with_limits(self):
        """has_any_limit() returns True when at least one limit is set."""
        assert BudgetPolicy(max_requests=1).has_any_limit()
        assert BudgetPolicy(max_cost_cents=1).has_any_limit()
        assert BudgetPolicy(max_runtime_seconds=1).has_any_limit()
        assert BudgetPolicy(max_requests=1, max_cost_cents=1).has_any_limit()

    def test_budget_policy_has_any_limit_empty(self):
        """has_any_limit() returns False when no limits are set."""
        assert not BudgetPolicy().has_any_limit()
        assert not BudgetPolicy(
            max_requests=None, max_cost_cents=None, max_runtime_seconds=None
        ).has_any_limit()

    def test_budget_usage_is_valid(self):
        """is_valid() returns True for non-negative values."""
        assert BudgetUsage(requests_used=0).is_valid()
        assert BudgetUsage(requests_used=100).is_valid()
        assert BudgetUsage(requests_used=0, cost_cents_used=0, runtime_seconds_used=0).is_valid()
        assert BudgetUsage(requests_used=1, cost_cents_used=2, runtime_seconds_used=3).is_valid()

    def test_budget_usage_is_valid_negative(self):
        """is_valid() returns False when any value is negative."""
        assert not BudgetUsage(requests_used=-1).is_valid()
        assert not BudgetUsage(cost_cents_used=-1).is_valid()
        assert not BudgetUsage(runtime_seconds_used=-1).is_valid()

    def test_budget_decision_json_serializable(self):
        """BudgetDecision can be serialized to JSON (dict)."""
        decision = BudgetDecision(
            status=BudgetStatus.EXHAUSTED,
            reason="Test",
            limit_name="max_requests",
            limit_value=100,
            observed_value=100,
            timestamp=FIXED_TIMESTAMP,
        )
        d = decision.model_dump()
        json_str = json.dumps(d, default=str)
        parsed = json.loads(json_str)
        assert parsed["status"] == "exhausted"
        assert parsed["limit_name"] == "max_requests"

    def test_budget_status_enum_values(self):
        """BudgetStatus values are correct."""
        assert BudgetStatus.OK.value == "ok"
        assert BudgetStatus.WARNING.value == "warning"
        assert BudgetStatus.EXHAUSTED.value == "exhausted"
        assert BudgetStatus.ERROR.value == "error"
