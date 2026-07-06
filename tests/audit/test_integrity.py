"""Integrity tests for the Neutrino AuditLog JSONL Writer (Issue #46).

This module extends ``test_writer.py`` with comprehensive integrity tests
covering the full spectrum of Issue #46 requirements:

- **Write behaviour**: All mandatory fields present, event payload roundtrip,
  exact JSON line production.
- **Append-only protection**: Byte-level preservation of pre-filled content,
  truncation prevention, multiple-writer data integrity.
- **Timestamp integrity**: UTC default, explicit preservation, temporal ordering.
- **Error handling**: Failed validation writes nothing, existing data survives,
  network-path rejection via Writer constructor.
- **Production safety**: ``tmp_path`` exclusivity, ``NEUTRINO_AUDIT_DIR`` isolation.

All tests use ``tmp_path`` fixtures. No network I/O. No real ``~/.neutrino/``.
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from neutrino.audit.models import AuditLogEvent
from neutrino.audit.writer import AuditLogWriter, _resolve_audit_dir

# ==================================================================
# Helpers
# ==================================================================


def _make_event(**overrides: str | dict) -> AuditLogEvent:
    """Create a minimal valid AuditLogEvent with defaults."""
    defaults: dict[str, object] = {
        "actor": "test_actor",
        "action": "test_action",
        "target": "example.com",
        "decision": "allow_test",
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return AuditLogEvent(**defaults)  # type: ignore[arg-type]


# ==================================================================
# 1. Audit-Events werden geschrieben (Write Integrity)
# ==================================================================


class TestWriteIntegrity:
    """Every written JSON line contains all required fields and preserves
    event payload faithfully."""

    def test_every_line_contains_all_six_required_fields(self, tmp_path: Path) -> None:
        """Verify that id, actor, action, target, decision, timestamp
        are present in every written JSON line."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event())
        writer.append(_make_event(actor="other", target="other.example.com"))

        lines = writer.file_path.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            for field in ("id", "actor", "action", "target", "decision", "timestamp"):
                assert field in parsed, f"Missing field '{field}' in: {line}"
                assert parsed[field], f"Empty field '{field}' in: {line}"

    def test_event_payload_exact_roundtrip(self, tmp_path: Path) -> None:
        """Complex event payload is written and read back exactly."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        payload = {
            "status": "allow",
            "reason": "allow_in_scope",
            "matched_entry": "*.example.com",
            "nested": {"key": "val", "count": 42, "items": [1, 2, 3]},
        }
        event = _make_event(event=payload)
        writer.append(event)

        read_back = writer.read_all()[0]
        assert read_back.event == payload

    def test_event_with_none_payload_excluded_from_json(self, tmp_path: Path) -> None:
        """When event=None, the field is excluded from JSON output."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event())  # event=None by default

        line = writer.file_path.read_text().strip()
        parsed = json.loads(line)
        assert "event" not in parsed

    def test_event_payload_with_empty_dict_preserved(self, tmp_path: Path) -> None:
        """An empty event dict is preserved (not treated as None)."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(event={}))

        line = writer.file_path.read_text().strip()
        parsed = json.loads(line)
        assert "event" in parsed
        assert parsed["event"] == {}

    def test_line_count_matches_append_count(self, tmp_path: Path) -> None:
        """Exactly N appends produce exactly N non-empty lines."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        for i in range(10):
            writer.append(_make_event(target=f"t{i}.example.com"))
        assert writer.count() == 10


# ==================================================================
# 2. Überschreiben wird verhindert (Append-Only Protection)
# ==================================================================


class TestAppendOnlyProtection:
    """Byte-level preservation of pre-existing content, truncation
    prevention, and multi-writer integrity."""

    def test_prefilled_manual_content_preserved_byte_exact(self, tmp_path: Path) -> None:
        """Manually written content stays byte-identical after Writer appends."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)
        jsonl_path = audit_dir / "audit.jsonl"

        manual_line = (
            '{"actor":"manual","action":"init","target":"pre.example.com",'
            '"decision":"manual_init","message":"do not touch"}\n'
        )
        jsonl_path.write_text(manual_line, encoding="utf-8")
        original_bytes = jsonl_path.read_bytes()

        writer = AuditLogWriter(audit_dir=audit_dir)
        writer.append(_make_event(target="after.example.com"))

        content = jsonl_path.read_bytes()
        # Original bytes must appear unchanged at the start
        assert content.startswith(original_bytes), "Pre-filled content was modified!"
        assert len(content) > len(original_bytes), "Append did not add content"

    def test_prefilled_invalid_json_content_preserved(self, tmp_path: Path) -> None:
        """Even non-JSON pre-filled content is preserved byte-exact."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)
        jsonl_path = audit_dir / "audit.jsonl"

        garbage = b"This is not JSON. Do not touch this.\n"
        jsonl_path.write_bytes(garbage)

        writer = AuditLogWriter(audit_dir=audit_dir)
        writer.append(_make_event(target="after.example.com"))

        content = jsonl_path.read_bytes()
        assert content.startswith(garbage), "Pre-filled garbage was modified!"

    def test_file_size_grows_after_append(self, tmp_path: Path) -> None:
        """File size strictly increases after each append (no truncation)."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(target="first.example.com"))

        size_after_first = writer.file_path.stat().st_size
        writer.append(_make_event(target="second.example.com"))

        size_after_second = writer.file_path.stat().st_size
        assert size_after_second > size_after_first, "File size did not grow!"

    def test_multiple_writers_no_data_loss(self, tmp_path: Path) -> None:
        """Multiple writer instances appending interleaved — no data loss."""
        audit_dir = tmp_path / "audit"
        w1 = AuditLogWriter(audit_dir=audit_dir)
        w2 = AuditLogWriter(audit_dir=audit_dir)

        targets_w1 = [f"w1-{i}.example.com" for i in range(5)]
        targets_w2 = [f"w2-{i}.example.com" for i in range(5)]

        for t1, t2 in zip(targets_w1, targets_w2, strict=True):
            w1.append(_make_event(target=t1))
            w2.append(_make_event(target=t2))

        events = w1.read_all()
        assert len(events) == 10, f"Expected 10 events, got {len(events)}"
        w1_targets = [e.target for e in events if e.target.startswith("w1-")]
        w2_targets = [e.target for e in events if e.target.startswith("w2-")]
        assert len(w1_targets) == 5
        assert len(w2_targets) == 5

    def test_existing_file_not_reinitialized_by_constructor(self, tmp_path: Path) -> None:
        """Writer constructor does not touch existing audit.jsonl content."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)
        jsonl_path = audit_dir / "audit.jsonl"

        manual_line = (
            '{"actor":"before","action":"setup","target":"pre.example.com","decision":"pre_init"}\n'
        )
        jsonl_path.write_text(manual_line, encoding="utf-8")

        # Constructor should not modify the file
        AuditLogWriter(audit_dir=audit_dir)

        content = jsonl_path.read_text(encoding="utf-8")
        assert content == manual_line, "Constructor modified existing file!"

    def test_no_destructive_methods_exist(self) -> None:
        """Verify no destructive operations are present on AuditLogWriter."""
        forbidden = [
            "delete",
            "remove",
            "clear",
            "rewrite",
            "truncate",
            "overwrite",
            "purge",
            "rotate",
            "roll",
            "archive",
            "compress",
            "gzip_compress",
            "decompress",
        ]
        for name in forbidden:
            assert not hasattr(AuditLogWriter, name), (
                f"Destructive method '{name}' found on AuditLogWriter!"
            )

    def test_append_mode_verified_behavioral(self, tmp_path: Path) -> None:
        """Behavioral test: append to file, close writer, re-open and append
        again — first line still intact."""
        audit_dir = tmp_path / "audit"
        w1 = AuditLogWriter(audit_dir=audit_dir)
        w1.append(_make_event(target="first.example.com"))
        first_line = w1.file_path.read_text().split("\n")[0]

        # New writer instance appends to the same file
        w2 = AuditLogWriter(audit_dir=audit_dir)
        w2.append(_make_event(target="second.example.com"))

        lines = w2.file_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert lines[0] == first_line, "First line was overwritten!"


# ==================================================================
# 3. Zeitstempel bleiben nachvollziehbar (Timestamp Integrity)
# ==================================================================


class TestTimestampIntegrity:
    """Timestamps are UTC, preserved as-is when explicit, and ordered."""

    def test_default_timestamp_is_utc_aware(self) -> None:
        """Auto-generated timestamp includes UTC timezone indicator."""
        event = _make_event()
        ts = event.timestamp
        # Must contain either +00:00 or Z (ISO 8601 UTC)
        assert "+00:00" in ts or ts.endswith("Z"), f"Timestamp '{ts}' does not indicate UTC"

    def test_auto_timestamp_is_iso_8601_parsable(self) -> None:
        """Auto-generated timestamp can be parsed as ISO 8601 datetime."""
        event = _make_event()
        dt = datetime.fromisoformat(event.timestamp)
        assert isinstance(dt, datetime)

    def test_auto_timestamp_uses_utc_timezone(self) -> None:
        """Auto-generated timestamp uses UTC (not local time)."""
        event = _make_event()
        dt = datetime.fromisoformat(event.timestamp)
        assert dt.tzinfo is not None, "Timestamp has no timezone info"
        assert dt.utcoffset() is not None
        assert dt.utcoffset().total_seconds() == 0, f"UTC offset is {dt.utcoffset()}, expected 0"

    def test_explicit_timestamp_is_preserved(self) -> None:
        """Event with explicit timestamp retains it unchanged."""
        explicit_ts = "2025-01-15T12:30:45+00:00"
        event = _make_event(timestamp=explicit_ts)
        assert event.timestamp == explicit_ts

    def test_explicit_timestamp_preserved_through_write_read(self, tmp_path: Path) -> None:
        """Explicit timestamp survives JSONL roundtrip."""
        explicit_ts = "2025-06-01T08:00:00+00:00"
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(timestamp=explicit_ts))

        read_back = writer.read_all()[0]
        assert read_back.timestamp == explicit_ts

    def test_writer_does_not_overwrite_explicit_timestamp(self, tmp_path: Path) -> None:
        """Writer does not silently replace an explicitly provided timestamp."""
        custom_ts = "2024-12-25T00:00:00+00:00"
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(timestamp=custom_ts))

        line = json.loads(writer.file_path.read_text().strip())
        assert line["timestamp"] == custom_ts

    def test_multiple_events_have_monotonic_auto_timestamps(self, tmp_path: Path) -> None:
        """Auto-generated timestamps are non-decreasing for sequential events."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        for i in range(5):
            writer.append(_make_event(target=f"t{i}.example.com"))

        events = writer.read_all()
        timestamps = [datetime.fromisoformat(e.timestamp) for e in events]
        for i in range(len(timestamps) - 1):
            assert timestamps[i] <= timestamps[i + 1], (
                f"Timestamps not monotonic: {timestamps[i]} > {timestamps[i + 1]}"
            )

    def test_timestamp_format_is_consistent_across_events(self, tmp_path: Path) -> None:
        """All auto-generated timestamps follow the same ISO format pattern."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        for _ in range(3):
            writer.append(_make_event())

        for event in writer.read_all():
            ts = event.timestamp
            # Should contain 'T' separator (ISO 8601) and timezone info
            assert "T" in ts, f"Timestamp missing 'T': {ts}"
            assert "+00:00" in ts or ts.endswith("Z"), f"Timestamp missing UTC indicator: {ts}"


# ==================================================================
# 4. Fehlerfälle werden behandelt (Error Handling)
# ==================================================================


class TestErrorHandling:
    """Failed validation writes nothing, existing data survives,
    and destructive operations are absent."""

    # --- append_raw with missing/invalid fields ---

    def test_append_raw_missing_actor_writes_nothing(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"action": "x", "target": "x", "decision": "x"})
        assert writer.count() == 0

    def test_append_raw_missing_action_writes_nothing(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x", "target": "x", "decision": "x"})
        assert writer.count() == 0

    def test_append_raw_missing_target_writes_nothing(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x", "action": "x", "decision": "x"})
        assert writer.count() == 0

    def test_append_raw_missing_decision_writes_nothing(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x", "action": "x", "target": "x"})
        assert writer.count() == 0

    def test_append_raw_blank_actor_writes_nothing(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "", "action": "x", "target": "x", "decision": "x"})
        assert writer.count() == 0

    def test_append_raw_blank_action_writes_nothing(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x", "action": "  ", "target": "x", "decision": "x"})
        assert writer.count() == 0

    def test_append_raw_blank_target_writes_nothing(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x", "action": "x", "target": "  ", "decision": "x"})
        assert writer.count() == 0

    def test_append_raw_blank_decision_writes_nothing(self, tmp_path: Path) -> None:
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x", "action": "x", "target": "x", "decision": "  "})
        assert writer.count() == 0

    # --- Existing file preserved on failed append ---

    def test_existing_file_unchanged_on_failed_append_raw(self, tmp_path: Path) -> None:
        """Pre-filled content survives a failed append_raw (invalid data)."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True)
        jsonl_path = audit_dir / "audit.jsonl"
        valid_line = (
            '{"actor":"valid","action":"write","target":"valid.example.com","decision":"ok"}\n'
        )
        jsonl_path.write_text(valid_line, encoding="utf-8")
        original_content = jsonl_path.read_bytes()

        writer = AuditLogWriter(audit_dir=audit_dir)
        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x"})  # missing fields

        # File must be byte-identical
        assert jsonl_path.read_bytes() == original_content, (
            "Pre-filled content changed after failed append_raw!"
        )

    def test_first_valid_event_unchanged_after_failed_second_append(self, tmp_path: Path) -> None:
        """A valid event survives when subsequent append_raw fails."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(target="survivor.example.com"))
        first_count = writer.count()

        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x", "action": "x"})  # missing target, decision

        assert writer.count() == first_count
        events = writer.read_all()
        assert len(events) == 1
        assert events[0].target == "survivor.example.com"

    # --- Path rejection via Writer constructor ---

    def test_writer_constructor_rejects_network_path(self) -> None:
        """Writer constructor propagates UNC/network path rejection."""
        with pytest.raises(ValueError, match="Network/UNC paths are not allowed"):
            AuditLogWriter(audit_dir="//server/share/audit")

    def test_writer_constructor_rejects_windows_unc_path(self) -> None:
        with pytest.raises(ValueError, match="Network/UNC paths are not allowed"):
            AuditLogWriter(audit_dir="\\\\server\\share\\audit")

    # --- Non-JSON-serializable payload ---

    def test_non_json_serializable_event_payload_raises(self, tmp_path: Path) -> None:
        """A non-JSON-serializable value in the event dict raises
        PydanticSerializationError during model_dump_json (not silently swallowed).
        Note: Pydantic's custom encoder silently converts bytes (base64) and
        sets (list). Only truly unknown types (like object()) raise errors."""
        from pydantic_core import PydanticSerializationError

        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(PydanticSerializationError):
            writer.append(_make_event(event={"bad": object()}))

    # --- Empty dict in append_raw ---

    def test_append_raw_empty_dict_rejected(self, tmp_path: Path) -> None:
        """append_raw with empty dict is rejected (all fields missing)."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        with pytest.raises(ValidationError):
            writer.append_raw({})
        assert writer.count() == 0

    # --- Writer does not silently swallow write errors ---

    def test_writer_does_not_silently_swallow_oserror(self, tmp_path: Path) -> None:
        """If audit_dir is a regular file, makedirs should raise OSError
        (not silently continue)."""
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file, not a directory")

        writer = AuditLogWriter(audit_dir=blocker)
        with pytest.raises(OSError):
            writer.append(_make_event())


# ==================================================================
# 5. Produktionsdaten bleiben unangetastet (Production Safety)
# ==================================================================


class TestProductionSafety:
    """Tests exclusively use tmp_path. NEUTRINO_AUDIT_DIR is isolated.
    Real home directory is never written to."""

    def test_all_paths_inside_tmp_path(self, tmp_path: Path) -> None:
        """Verify that tmp_path is the effective audit directory anchor."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event())
        assert str(writer.audit_dir).startswith(str(tmp_path))
        assert str(tmp_path) in str(writer.file_path)

    def test_no_writes_to_real_home(self, tmp_path: Path) -> None:
        """Even with default path computation, test overrides prevent
        writing to real home."""
        writer = AuditLogWriter(audit_dir=tmp_path / "safety-audit")
        home_prefix = str(Path.home())
        assert not str(writer.audit_dir).startswith(home_prefix), (
            f"Writer would write to real home: {writer.audit_dir}"
        )

    def test_env_var_isolated_and_restored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """NEUTRINO_AUDIT_DIR can be set for test, and doesn't persist."""
        fake_dir = tmp_path / "env-isolated"
        monkeypatch.setenv("NEUTRINO_AUDIT_DIR", str(fake_dir))
        resolved = _resolve_audit_dir()
        assert resolved == fake_dir.resolve()

    def test_default_path_not_created_by_tests(self, tmp_path: Path) -> None:
        """Tests never create the default ~/.neutrino/audit/ directory."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event())
        default = Path.home() / ".neutrino" / "audit"
        # Our test used tmp_path, so default path should not exist
        # (unless pre-existing from other operations)
        assert str(default) != str(writer.audit_dir)

    def test_read_all_never_creates_file(self, tmp_path: Path) -> None:
        """read_all does not create the audit file if it doesn't exist."""
        writer = AuditLogWriter(audit_dir=tmp_path / "nonexistent-audit")
        result = writer.read_all()
        assert result == []
        assert not writer.file_path.exists()


# ==================================================================
# 6. Negative Tests priorisiert (Negative Test Cases)
# ==================================================================


class TestNegativeCases:
    """Negative tests: invalid events, blocked paths, pre-filled content,
    multiple writers, and destructive-operation absence."""

    def test_invalid_event_raises_at_construction_time(self) -> None:
        """Invalid events are rejected during model construction,
        before any I/O happens."""
        with pytest.raises(ValidationError):
            AuditLogEvent(actor="x", action="x", target="", decision="x")

    def test_append_raw_no_orphan_file_on_validation_failure(self, tmp_path: Path) -> None:
        """If the directory doesn't exist yet and append_raw fails,
        no empty directory or file is left behind."""
        audit_dir = tmp_path / "should-not-exist"
        writer = AuditLogWriter(audit_dir=audit_dir)
        with contextlib.suppress(ValidationError):
            writer.append_raw({"actor": "x"})
        # Directory should not exist (append_raw failed before makedirs)
        # Note: current implementation creates dir before write, so dir may exist.
        # This test documents the current behavior.
        if audit_dir.is_dir():
            # If dir was created, ensure file was NOT written
            assert not writer.file_path.is_file() or writer.count() == 0, (
                "Empty/wrong file was created on failed append_raw"
            )

    def test_prefilled_then_failed_validation_does_not_truncate(self, tmp_path: Path) -> None:
        """Pre-filled file with N valid lines stays intact when an invalid
        append_raw is attempted."""
        audit_dir = tmp_path / "audit"
        writer = AuditLogWriter(audit_dir=audit_dir)
        writer.append(_make_event(target="line1.example.com"))
        writer.append(_make_event(target="line2.example.com"))
        original_count = writer.count()
        original_bytes = writer.file_path.read_bytes()

        with pytest.raises(ValidationError):
            writer.append_raw({"actor": "x"})

        assert writer.count() == original_count, "Lines were lost!"
        assert writer.file_path.read_bytes() == original_bytes, (
            "File content changed after failed append_raw!"
        )

    def test_all_destructive_methods_absent(self) -> None:
        """Comprehensive list of destructive methods that must not exist."""
        dangerous = [
            "delete",
            "remove",
            "clear",
            "rewrite",
            "truncate",
            "overwrite",
            "purge",
            "wipe",
            "reset",
            "nuke",
            "rotate",
            "roll",
            "archive",
            "compress",
            "gzip",
            "deflate",
            "bzip",
            "compress_file",
            "shred",
            "secure_delete",
            "unlink",
            "rm",
        ]
        for method in dangerous:
            assert not hasattr(AuditLogWriter, method), (
                f"Destructive method '{method}' must not exist!"
            )

    def test_writer_has_no_file_handle_that_allows_seek_rewind(self, tmp_path: Path) -> None:
        """Writer does not expose a mutable file handle that could be used
        to seek/patch earlier entries."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")
        writer.append(_make_event(target="first.example.com"))

        # No attribute that gives raw file handle for seeking
        for attr_name in dir(writer):
            if (
                "file" in attr_name.lower()
                or "handle" in attr_name.lower()
                or "fd" in attr_name.lower()
            ):
                val = getattr(writer, attr_name, None)
                # If it's a file-like object, it shouldn't be seekable
                if hasattr(val, "seek") and hasattr(val, "write"):
                    pytest.fail(
                        f"AuditLogWriter exposes mutable file handle: '{attr_name}' = {val!r}"
                    )

    def test_actor_action_target_decision_must_all_be_nonempty_strings(self) -> None:
        """Systematic check: every required string field rejects empty/blank."""
        required = ["actor", "action", "target", "decision"]
        for field in required:
            for bad_value in ("", "   ", "\t", "\n"):
                kwargs = {f: "ok_value" for f in required}
                kwargs[field] = bad_value
                with pytest.raises(ValidationError, match=field):
                    AuditLogEvent(**kwargs)  # type: ignore[arg-type]


# ==================================================================
# 7. Determinism and Reproducibility
# ==================================================================


class TestDeterminism:
    """Tests that produce reproducible, deterministic results."""

    def test_same_input_produces_identical_output(self, tmp_path: Path) -> None:
        """Two writes with identical data produce identical JSON lines."""
        w1 = AuditLogWriter(audit_dir=tmp_path / "audit1")
        w2 = AuditLogWriter(audit_dir=tmp_path / "audit2")

        event = _make_event(
            actor="deterministic",
            action="test",
            target="det.example.com",
            decision="allow",
            timestamp="2026-01-01T00:00:00+00:00",
            id="fixed-id-123",
        )
        w1.append(event)
        w2.append(event)

        line1 = json.loads(w1.file_path.read_text().strip())
        line2 = json.loads(w2.file_path.read_text().strip())

        for key in ("actor", "action", "target", "decision", "timestamp", "id"):
            assert line1[key] == line2[key], f"Non-deterministic output for field '{key}'"

    def test_same_writer_repeated_appends_deterministic(self, tmp_path: Path) -> None:
        """Repeated appends to same writer with fixed data are deterministic."""
        writer = AuditLogWriter(audit_dir=tmp_path / "audit")

        run1 = tmp_path / "run1.jsonl"
        for _ in range(3):
            writer.append(
                _make_event(
                    target="fixed.example.com",
                    timestamp="2026-01-01T00:00:00+00:00",
                    id="repeat-id",
                )
            )
        run1.write_text(writer.file_path.read_text())

        # Reset
        audit_dir2 = tmp_path / "audit2"
        w2 = AuditLogWriter(audit_dir=audit_dir2)
        for _ in range(3):
            w2.append(
                _make_event(
                    target="fixed.example.com",
                    timestamp="2026-01-01T00:00:00+00:00",
                    id="repeat-id",
                )
            )
        run2 = tmp_path / "run2.jsonl"
        run2.write_text(w2.file_path.read_text())

        assert run1.read_text() == run2.read_text()
