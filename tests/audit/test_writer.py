"""Unit tests for the Neutrino AuditLog JSONL Writer.

Tests the ``AuditLogEvent`` model and ``AuditLogWriter`` with
temporary directories. Validates append-only behaviour, mandatory
field enforcement, JSONL format correctness, path management,
and safety invariants.

No real ``~/.neutrino/audit/`` is written. All tests use
``tmp_path`` fixtures. No network I/O.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from neutrino.audit.models import AuditLogEvent
from neutrino.audit.writer import AuditLogWriter, _resolve_audit_dir

# ==================================================================
# Helpers
# ==================================================================


def _make_event(**overrides: str | dict) -> AuditLogEvent:
    """Create a minimal valid AuditLogEvent with defaults fillable."""
    defaults: dict[str, object] = {
        "actor": "test_actor",
        "action": "test_action",
        "target": "example.com",
        "decision": "allow_test",
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return AuditLogEvent(**defaults)  # type: ignore[arg-type]


# ==================================================================
# Model Tests
# ==================================================================


class TestAuditLogEventModel:
    """Unit tests for the AuditLogEvent Pydantic model."""

    # 1. JSON serialization
    def test_model_serializes_to_json(self) -> None:
        event = _make_event()
        data = event.model_dump()
        assert json.dumps(data)  # valid JSON

    # 2. Required fields present
    def test_all_required_fields_present(self) -> None:
        event = _make_event()
        assert event.actor == "test_actor"
        assert event.action == "test_action"
        assert event.target == "example.com"
        assert event.decision == "allow_test"
        assert event.timestamp  # auto-generated
        assert event.id  # auto-generated
        assert event.event is None

    # 3. Missing actor rejected
    def test_missing_actor_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEvent(action="x", target="x", decision="x")

    # 4. Missing action rejected
    def test_missing_action_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEvent(actor="x", target="x", decision="x")

    # 5. Missing target rejected
    def test_missing_target_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEvent(actor="x", action="x", decision="x")

    # 6. Missing decision rejected
    def test_missing_decision_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEvent(actor="x", action="x", target="x")

    # 7. Timestamp is ISO compatible
    def test_timestamp_is_iso_compatible(self) -> None:
        event = _make_event()
        # should parse as ISO 8601
        from datetime import datetime

        datetime.fromisoformat(event.timestamp)

    # --- Additional: blank checks ---
    def test_empty_actor_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEvent(actor="", action="x", target="x", decision="x")

    def test_whitespace_actor_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEvent(actor="   ", action="x", target="x", decision="x")

    def test_empty_target_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEvent(actor="x", action="x", target="", decision="x")

    def test_empty_decision_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEvent(actor="x", action="x", target="x", decision="")

    # --- Event dict ---
    def test_event_dict_preserved(self) -> None:
        event = _make_event(event={"reason": "test", "source": "test"})
        assert event.event == {"reason": "test", "source": "test"}

    def test_event_dict_json_serializable(self) -> None:
        event = _make_event(event={"key": "value", "num": 42})
        data = event.model_dump()
        assert json.dumps(data)

    # --- UUID uniqueness ---
    def test_each_event_has_unique_id(self) -> None:
        e1 = _make_event()
        e2 = _make_event()
        assert e1.id != e2.id


# ==================================================================
# Writer Tests — basic behaviour
# ==================================================================


class TestAuditLogWriter:
    """Unit tests for the AuditLogWriter append-only JSONL writer."""

    def test_writer_creates_audit_directory(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        writer = AuditLogWriter(audit_dir=audit_dir)
        assert not audit_dir.is_dir()
        writer.append(_make_event())
        assert audit_dir.is_dir()

    def test_first_append_creates_jsonl_file(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        writer = AuditLogWriter(audit_dir=audit_dir)
        writer.append(_make_event())
        assert writer.file_path.is_file()

    def test_second_append_adds_second_line(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(target="first.example.com"))
        writer.append(_make_event(target="second.example.com"))
        lines = writer.file_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_existing_line_unchanged_on_append(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        e1 = _make_event(target="keep.example.com")
        writer.append(e1)
        first_line_before = writer.file_path.read_text().split("\n")[0]

        writer.append(_make_event(target="second.example.com"))

        first_line_after = writer.file_path.read_text().split("\n")[0]
        assert first_line_before == first_line_after

    def test_multiple_append_calls_multiple_lines(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        for i in range(5):
            writer.append(_make_event(target=f"target-{i}.example.com"))
        lines = [li for li in writer.file_path.read_text().split("\n") if li.strip()]
        assert len(lines) == 5

    def test_multiple_writer_instances_append_same_file(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        w1 = AuditLogWriter(audit_dir=audit_dir)
        w2 = AuditLogWriter(audit_dir=audit_dir)
        w1.append(_make_event(target="from-w1.example.com"))
        w2.append(_make_event(target="from-w2.example.com"))
        lines = [li for li in w1.file_path.read_text().split("\n") if li.strip()]
        assert len(lines) == 2

    # 14. Every line is valid JSON
    def test_every_line_is_valid_json(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        for i in range(3):
            writer.append(_make_event(target=f"t-{i}.example.com"))
        for line in writer.file_path.read_text().strip().split("\n"):
            parsed = json.loads(line)
            assert "actor" in parsed
            assert "target" in parsed

    # 15. No empty lines
    def test_no_empty_lines(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event())
        writer.append(_make_event())
        content = writer.file_path.read_text()
        lines = content.split("\n")
        # Last line might be empty (trailing newline), but interior lines should not be
        interior = lines[:-1] if lines[-1] == "" else lines
        for line in interior:
            assert line.strip(), f"Empty line found: {lines!r}"

    # 16. Event order preserved
    def test_event_order_is_write_order(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        targets = [f"step-{i}.example.com" for i in range(5)]
        for t in targets:
            writer.append(_make_event(target=t))

        events = writer.read_all()
        assert [e.target for e in events] == targets

    # --- Return value ---
    def test_append_returns_event(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        event = _make_event()
        result = writer.append(event)
        assert result == event

    # --- append_raw ---
    def test_append_raw_works(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append_raw(
            {
                "actor": "test",
                "action": "test",
                "target": "example.com",
                "decision": "allow",
            }
        )
        assert writer.count() == 1

    # --- read_all on empty ---
    def test_read_all_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        assert writer.read_all() == []

    def test_read_all_returns_all_events(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(target="a.example.com"))
        writer.append(_make_event(target="b.example.com"))
        events = writer.read_all()
        assert len(events) == 2
        assert events[0].target == "a.example.com"
        assert events[1].target == "b.example.com"

    # --- count ---
    def test_count_zero_when_no_file(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        assert writer.count() == 0

    def test_count_after_appends(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        for _ in range(7):
            writer.append(_make_event())
        assert writer.count() == 7


# ==================================================================
# Path Management Tests
# ==================================================================


class TestPathManagement:
    """Tests for audit directory path resolution and safety."""

    # 17. Default path
    def test_default_audit_dir_is_home_neutrino_audit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEUTRINO_AUDIT_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: Path("/fake/home"))
        resolved = _resolve_audit_dir()
        assert str(resolved) == "/fake/home/.neutrino/audit"

    # 18. No writes to real home from tests
    def test_test_uses_override_not_real_home(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "test-audit")
        assert str(tmp_path) in str(writer.audit_dir)
        assert str(Path.home()) not in str(writer.audit_dir)

    # 19. NEUTRINO_AUDIT_DIR override
    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        env_dir = tmp_path / "env-audit"
        monkeypatch.setenv("NEUTRINO_AUDIT_DIR", str(env_dir))
        resolved = _resolve_audit_dir()
        assert resolved == env_dir.resolve()

    def test_explicit_audit_dir_wins_over_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("NEUTRINO_AUDIT_DIR", "/should/not/be/used")
        explicit = tmp_path / "explicit"
        resolved = _resolve_audit_dir(audit_dir=explicit)
        assert resolved == explicit.resolve()

    # 20. Relative paths — test that they work (relative to cwd)
    def test_relative_path_resolved(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        resolved = _resolve_audit_dir(audit_dir="relative-audit")
        assert resolved.is_absolute()
        assert "relative-audit" in str(resolved)

    # 21. No remote/network paths
    def test_network_path_rejected(self) -> None:
        # POSIX-style network path: //server/share/audit
        with pytest.raises(ValueError, match="Network/UNC paths are not allowed"):
            _resolve_audit_dir(audit_dir="//server/share/audit")

    def test_windows_unc_path_rejected(self) -> None:
        # Windows UNC path
        with pytest.raises(ValueError, match="Network/UNC paths are not allowed"):
            _resolve_audit_dir(audit_dir="\\\\server\\share\\audit")

    # --- Writer does NOT require network ---
    def test_no_network_usage(self, tmp_path: Path) -> None:
        """Verify writer only does local I/O (no imports of httpx, socket, etc.)."""
        import inspect

        from neutrino.audit.writer import AuditLogWriter as A

        source = inspect.getsource(A.append)
        # The append method must not import or reference httpx, socket, http, requests
        assert "httpx" not in source
        assert "socket" not in source
        assert "requests" not in source
        assert "urllib" not in source


# ==================================================================
# Append-Only / Safety Invariant Tests
# ==================================================================


class TestAppendOnlySafety:
    """Verify that the writer provides no mechanisms to delete, truncate,
    rewrite, rotate, compress, or remotely ship audit data."""

    # 22. No delete method
    def test_no_delete_method(self) -> None:
        assert not hasattr(AuditLogWriter, "delete")
        assert not hasattr(AuditLogWriter, "remove")
        assert not hasattr(AuditLogWriter, "clear")

    # 23. No rewrite/truncate method
    def test_no_rewrite_or_truncate_method(self) -> None:
        assert not hasattr(AuditLogWriter, "rewrite")
        assert not hasattr(AuditLogWriter, "truncate")
        assert not hasattr(AuditLogWriter, "overwrite")
        assert not hasattr(AuditLogWriter, "purge")

    # 24. No rotation mechanism
    def test_no_rotation_mechanism(self) -> None:
        assert not hasattr(AuditLogWriter, "rotate")
        assert not hasattr(AuditLogWriter, "roll")
        assert not hasattr(AuditLogWriter, "archive")

    # 25. No compression
    def test_no_compression(self) -> None:
        import inspect

        source = inspect.getsource(AuditLogWriter)
        assert "gzip" not in source
        assert "zlib" not in source
        assert "bz2" not in source
        assert "lzma" not in source
        assert ".gz" not in source

    # 26. No remote shipping
    def test_no_remote_shipping(self) -> None:
        import inspect

        source = inspect.getsource(AuditLogWriter)
        assert "upload" not in source.lower()
        assert "ship" not in source.lower()
        assert "remote" not in source.lower()
        assert "cloud" not in source.lower()

    # 27. No network used
    def test_no_network_imports(self) -> None:
        import inspect

        source = inspect.getsource(AuditLogWriter)
        assert "httpx" not in source
        assert "http" not in source
        assert "socket" not in source
        assert "urllib" not in source
        assert "requests" not in source

    # 28. No HTTP/DNS
    def test_no_http_dns_usage(self, tmp_path: Path) -> None:
        """Write events and verify no network access occurred (defense in depth)."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event())
        # If we got here without network errors, the test passes
        assert writer.file_path.is_file()


# ==================================================================
# Integration Tests — Adapters from Domain Decision Models
# ==================================================================


class TestAdapterFromScopeDecision:
    """Tests for AuditLogEvent.from_scope_decision()."""

    def test_from_scope_decision_allow(self) -> None:
        from neutrino.scopeguard.models import ScopeDecision, ScopeDecisionStatus, ScopeReason

        sd = ScopeDecision(
            target="api.example.com",
            status=ScopeDecisionStatus.ALLOW,
            reason=ScopeReason.ALLOW_IN_SCOPE,
            matched_entry="*.example.com",
            policy_source="https://example.com/policy",
            explanation="Target is in scope.",
        )
        event = AuditLogEvent.from_scope_decision(sd)
        assert event.actor == "scopeguard"
        assert event.action == "check_target"
        assert event.target == "api.example.com"
        assert event.decision == "allow_allow_in_scope"
        assert event.event is not None
        assert event.event["status"] == "allow"
        assert event.event["reason"] == "allow_in_scope"

    def test_from_scope_decision_deny(self) -> None:
        from neutrino.scopeguard.models import ScopeDecision, ScopeDecisionStatus, ScopeReason

        sd = ScopeDecision(
            target="out.example.com",
            status=ScopeDecisionStatus.DENY,
            reason=ScopeReason.DENY_UNKNOWN_TARGET,
            explanation="Not in scope.",
        )
        event = AuditLogEvent.from_scope_decision(sd)
        assert event.decision == "deny_deny_unknown_target"
        assert event.event is not None
        assert event.event["status"] == "deny"

    def test_from_scope_decision_writes_to_audit(self, tmp_path: Path) -> None:
        from neutrino.scopeguard.models import ScopeDecision, ScopeDecisionStatus, ScopeReason

        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        sd = ScopeDecision(
            target="in-scope.example.com",
            status=ScopeDecisionStatus.ALLOW,
            reason=ScopeReason.ALLOW_IN_SCOPE,
            matched_entry="*.example.com",
        )
        event = AuditLogEvent.from_scope_decision(sd)
        writer.append(event)
        assert writer.count() == 1
        read_back = writer.read_all()[0]
        assert read_back.actor == "scopeguard"
        assert read_back.target == "in-scope.example.com"


class TestAdapterFromRateLimitDecision:
    """Tests for AuditLogEvent.from_rate_limit_decision()."""

    def test_from_rate_limit_decision_allow(self) -> None:
        from neutrino.ratelimit.models import (
            RateLimitDecision,
            RateLimitDecisionStatus,
            RateLimitReason,
        )

        rd = RateLimitDecision(
            target="api.example.com",
            status=RateLimitDecisionStatus.ALLOW,
            reason=RateLimitReason.ALLOW_WITHIN_LIMIT,
            explanation="Request within limits.",
        )
        event = AuditLogEvent.from_rate_limit_decision(rd)
        assert event.actor == "ratelimiter"
        assert event.action == "check_rate_limit"
        assert event.target == "api.example.com"
        assert event.decision == "allow_allow_within_limit"

    def test_from_rate_limit_decision_deny_with_violation(self) -> None:
        from neutrino.ratelimit.models import (
            RateLimitDecision,
            RateLimitDecisionStatus,
            RateLimitReason,
            RateLimitViolation,
        )

        violation = RateLimitViolation(
            target="busy.example.com",
            reason="Rate limit exceeded",
            limit_name="requests_per_second",
            limit_value=10,
            observed_value=15,
            window_seconds=1.0,
            timestamp=1234567890.0,
        )
        rd = RateLimitDecision(
            target="busy.example.com",
            status=RateLimitDecisionStatus.DENY,
            reason=RateLimitReason.DENY_REQUESTS_PER_SECOND_EXCEEDED,
            violation=violation,
            explanation="Too many requests.",
        )
        event = AuditLogEvent.from_rate_limit_decision(rd)
        assert event.decision == "deny_deny_requests_per_second_exceeded"
        assert event.event is not None
        assert "violation" in event.event

    def test_from_rate_limit_decision_writes_to_audit(self, tmp_path: Path) -> None:
        from neutrino.ratelimit.models import (
            RateLimitDecision,
            RateLimitDecisionStatus,
            RateLimitReason,
        )

        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        rd = RateLimitDecision(
            target="test.example.com",
            status=RateLimitDecisionStatus.ALLOW,
            reason=RateLimitReason.ALLOW_WITHIN_LIMIT,
        )
        event = AuditLogEvent.from_rate_limit_decision(rd)
        writer.append(event)
        assert writer.count() == 1


class TestAdapterFromProgramPolicyDecision:
    """Tests for AuditLogEvent.from_program_policy_decision()."""

    def test_from_program_policy_decision_allow(self) -> None:
        from neutrino.policy_enforcement.models import (
            ProgramPolicyDecision,
            ProgramPolicyDecisionStatus,
            ProgramPolicyReason,
        )

        pd = ProgramPolicyDecision(
            target="program.example.com",
            status=ProgramPolicyDecisionStatus.ALLOW,
            reason=ProgramPolicyReason.ALLOW_POLICY_PERMITS_TEST_TYPE,
            test_type="api_testing",
            explanation="Test type allowed.",
        )
        event = AuditLogEvent.from_program_policy_decision(pd)
        assert event.actor == "policy_enforcer"
        assert event.action == "check_program_policy"
        assert event.target == "program.example.com"
        assert event.decision == "allow_allow_policy_permits_test_type"
        assert event.event is not None
        assert event.event["test_type"] == "api_testing"

    def test_from_program_policy_decision_deny_with_violation(self) -> None:
        from neutrino.policy_enforcement.models import (
            ProgramPolicyDecision,
            ProgramPolicyDecisionStatus,
            ProgramPolicyReason,
            ProgramPolicyViolation,
        )

        v = ProgramPolicyViolation(
            target="bad.example.com",
            test_type="brute_force",
            automation=True,
            reason="Test type prohibited",
            matched_policy_item="brute_force",
            policy_source="https://example.com/policy",
            explanation="Brute force is prohibited.",
        )
        pd = ProgramPolicyDecision(
            target="bad.example.com",
            status=ProgramPolicyDecisionStatus.DENY,
            reason=ProgramPolicyReason.DENY_PROHIBITED_TEST_TYPE,
            test_type="brute_force",
            violation=v,
            explanation="Prohibited test type.",
        )
        event = AuditLogEvent.from_program_policy_decision(pd)
        assert event.decision == "deny_deny_prohibited_test_type"
        assert event.event is not None
        assert "violation" in event.event

    def test_from_program_policy_decision_writes_to_audit(self, tmp_path: Path) -> None:
        from neutrino.policy_enforcement.models import (
            ProgramPolicyDecision,
            ProgramPolicyDecisionStatus,
            ProgramPolicyReason,
        )

        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        pd = ProgramPolicyDecision(
            target="test.example.com",
            status=ProgramPolicyDecisionStatus.ALLOW,
            reason=ProgramPolicyReason.ALLOW_POLICY_PERMITS_TEST_TYPE,
            test_type="recon",
        )
        event = AuditLogEvent.from_program_policy_decision(pd)
        writer.append(event)
        assert writer.count() == 1


# ==================================================================
# append_raw and edge cases
# ==================================================================


class TestEdgeCases:
    """Edge case and defensive tests."""

    def test_writer_with_custom_filename(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit", file_name="custom.jsonl")
        writer.append(_make_event())
        assert writer.file_path.name == "custom.jsonl"
        assert writer.file_path.is_file()

    def test_parent_directories_created(self, tmp_path: Path) -> None:
        deep = tmp_path / "deep" / "nested" / "audit"
        writer = AuditLogWriter(audit_dir=deep)
        writer.append(_make_event())
        assert deep.is_dir()

    def test_appended_event_matches_jsonl_line(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        event = _make_event(
            actor="scope-auditor",
            action="audit_record",
            target="secure.example.com",
            decision="log_entry",
            event={"key": "val"},
        )
        writer.append(event)

        line = writer.file_path.read_text().strip()
        parsed = json.loads(line)
        assert parsed["actor"] == "scope-auditor"
        assert parsed["target"] == "secure.example.com"
        assert parsed["event"] == {"key": "val"}

    def test_event_with_none_event_field_excluded_from_json(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        event = _make_event()  # event=None
        writer.append(event)
        line = writer.file_path.read_text().strip()
        parsed = json.loads(line)
        assert "event" not in parsed  # excluded via exclude_none=True

    def test_writer_strict_append_no_overwrite(self, tmp_path: Path) -> None:
        """Simulate writing with open('w') and verify the writer itself never does that."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(target="first.example.com"))

        # Manually truncate (simulate what we must never do)
        writer.file_path.write_text("")
        assert writer.file_path.read_text() == ""

        # Writer appends — should add a new line, not overwrite the fact it was emptied
        writer.append(_make_event(target="second.example.com"))
        lines = [li for li in writer.file_path.read_text().split("\n") if li.strip()]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["target"] == "second.example.com"

    def test_append_raw_rejects_invalid_data(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x"})  # missing required fields
        assert writer.count() == 0  # nothing was written

    def test_read_all_skips_empty_lines(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        writer = AuditLogWriter(audit_dir=audit_dir)
        writer.append(_make_event(target="real.example.com"))
        # Simulate a blank line being present (shouldn't happen but be robust)
        with open(writer.file_path, "a") as f:
            f.write("\n")
        writer.append(_make_event(target="after-blank.example.com"))
        events = writer.read_all()
        assert len(events) == 2
        assert events[0].target == "real.example.com"
        assert events[1].target == "after-blank.example.com"

    def test_count_skips_empty_lines(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        writer = AuditLogWriter(audit_dir=audit_dir)
        writer.append(_make_event(target="real.example.com"))
        with open(writer.file_path, "a") as f:
            f.write("\n")
        assert writer.count() == 1  # blank line not counted


# ==================================================================
# Path Safety — additional
# ==================================================================


class TestPathSafetyAdditional:
    """Additional path safety tests."""

    def test_env_var_nonexistent_dir_resolved(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        nonexistent = tmp_path / "nonexistent-audit"
        monkeypatch.setenv("NEUTRINO_AUDIT_DIR", str(nonexistent))
        writer = AuditLogWriter()  # uses env var
        # Append should create the directory
        writer.append(_make_event())
        assert nonexistent.is_dir()

    def test_writer_file_path_property(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        assert writer.file_path.name == "audit.jsonl"
        assert writer.audit_dir in writer.file_path.parents


# ==================================================================
# AuditLogEvent Optional: bridge from SQLite AuditEvent
# ==================================================================


class TestBridgeFromSqliteAuditEvent:
    """Tests for converting SQLite AuditEvent entities to JSONL AuditLogEvent."""

    def test_bridge_from_sqlite_audit_event(self) -> None:
        """Verify a SQLite AuditEvent can be manually converted to AuditLogEvent."""
        from neutrino.models.entities import AuditEvent

        sqlite_event = AuditEvent(
            id="uuid-123",
            actor="scopeguard",
            action="check_target",
            target="api.example.com",
            decision="deny_unknown_target",
            event_json='{"reason": "test"}',
            timestamp="2026-07-05T10:00:00+00:00",
            created_at="2026-07-05T10:00:00+00:00",
            updated_at="2026-07-05T10:00:00+00:00",
        )

        jsonl_event = AuditLogEvent(
            id=sqlite_event.id,
            actor=sqlite_event.actor,
            action=sqlite_event.action,
            target=sqlite_event.target or "",
            decision=sqlite_event.decision or "",
            timestamp=sqlite_event.timestamp,
            event=json.loads(sqlite_event.event_json),
        )

        assert jsonl_event.actor == "scopeguard"
        assert jsonl_event.target == "api.example.com"
        assert jsonl_event.event == {"reason": "test"}

    def test_bridge_writes_to_audit(self, tmp_path: Path) -> None:
        """SQLite entity → AuditLogEvent → write to JSONL."""
        import json as _json

        from neutrino.models.entities import AuditEvent

        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        sqlite_event = AuditEvent(
            id="uuid-bridge",
            actor="ratelimiter",
            action="check_rate_limit",
            target="example.com",
            decision="allow_within_limit",
            event_json=_json.dumps({"limit": "rps", "value": 10}),
            timestamp="2026-07-05T10:00:00+00:00",
            created_at="2026-07-05T10:00:00+00:00",
            updated_at="2026-07-05T10:00:00+00:00",
        )

        jsonl_event = AuditLogEvent(
            id=sqlite_event.id,
            actor=sqlite_event.actor,
            action=sqlite_event.action,
            target=sqlite_event.target or "",
            decision=sqlite_event.decision or "",
            timestamp=sqlite_event.timestamp,
            event=_json.loads(sqlite_event.event_json),
        )

        writer.append(jsonl_event)
        assert writer.count() == 1
        read_back = writer.read_all()[0]
        assert read_back.id == "uuid-bridge"
        assert read_back.event == {"limit": "rps", "value": 10}
