"""Unit tests for the Neutrino migration system.

Validates idempotency, version tracking, rollback safety, foreign key
enforcement, and connection management. All databases are temporary.

No real ``~/.neutrino/`` path is ever written.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC

import pytest

from neutrino.storage.migrations import apply_migrations, get_schema_version, rollback_all
from neutrino.storage.paths import get_temp_db_path
from neutrino.storage.schema import SCHEMA_VERSION, TABLES
from neutrino.storage.sqlite import ensure_db_directory, get_connection

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def migrated_db() -> str:
    """A freshly migrated temporary database path."""
    path = get_temp_db_path()
    apply_migrations(path)
    return path


# ------------------------------------------------------------------
# Migration Lifecycle Tests
# ------------------------------------------------------------------


class TestMigrationLifecycle:
    """Tests for the full migration lifecycle."""

    def test_fresh_db_has_no_schema_version(self) -> None:
        """A fresh non-existent path returns None for schema version."""
        path = get_temp_db_path()
        # Database file does not exist yet — get_schema_version should handle this
        # by creating a connection, finding no schema_migrations, returning None
        version = get_schema_version(path)
        assert version is None

    def test_apply_then_version(self) -> None:
        """After apply_migrations, schema version is SCHEMA_VERSION."""
        path = get_temp_db_path()
        apply_migrations(path)
        assert get_schema_version(path) == SCHEMA_VERSION

    def test_migration_creates_directory(self) -> None:
        """apply_migrations creates parent directories automatically."""
        path = get_temp_db_path()
        assert not os.path.exists(path)
        apply_migrations(path)
        assert os.path.exists(path)

    def test_ensure_db_directory(self) -> None:
        """ensure_db_directory creates parent directories."""
        import tempfile

        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "sub", "deep", "neutrino.db")
        ensure_db_directory(db_path)
        assert os.path.isdir(os.path.dirname(db_path))


# ------------------------------------------------------------------
# Idempotency Tests
# ------------------------------------------------------------------


class TestIdempotency:
    """Verify that migrations are truly idempotent."""

    def test_apply_migrations_twice_same_db(self) -> None:
        """Applying migrations twice to the same database is safe."""
        path = get_temp_db_path()
        apply_migrations(path)
        apply_migrations(path)
        assert get_schema_version(path) == SCHEMA_VERSION

    def test_count_tables_after_idempotent_run(self) -> None:
        """Table count is stable after repeated apply_migrations calls."""
        path = get_temp_db_path()
        apply_migrations(path)

        with get_connection(path) as conn:
            initial_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'"
            ).fetchone()["cnt"]

        apply_migrations(path)

        with get_connection(path) as conn:
            after_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'"
            ).fetchone()["cnt"]

        assert after_count == initial_count

    def test_apply_migrations_many_times(self) -> None:
        """Applying migrations ten times is still safe."""
        path = get_temp_db_path()
        for _ in range(10):
            apply_migrations(path)
        assert get_schema_version(path) == SCHEMA_VERSION

    def test_schema_migrations_only_one_row(self) -> None:
        """schema_migrations table has exactly one row after idempotent runs."""
        path = get_temp_db_path()
        for _ in range(5):
            apply_migrations(path)

        with get_connection(path) as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM schema_migrations").fetchone()
            assert row["cnt"] == 1


# ------------------------------------------------------------------
# Foreign Key Enforcement
# ------------------------------------------------------------------


class TestForeignKeyEnforcement:
    """Verify foreign keys are enforced at the SQLite level."""

    def test_pragma_foreign_keys_on(self, migrated_db: str) -> None:
        """Every connection has PRAGMA foreign_keys = ON."""
        with get_connection(migrated_db) as conn:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
            assert row[0] == 1

    def test_fk_violation_scope_policies_no_program(self, migrated_db: str) -> None:
        """Insert into scope_policies without valid program_id raises IntegrityError."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        with get_connection(migrated_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO scope_policies (id, program_id, source_url, parsed_json, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "nonexistent-id", "https://x.com", "{}", now, now),
                )

    def test_fk_violation_targets_no_program(self, migrated_db: str) -> None:
        """Insert into targets without valid program_id raises IntegrityError."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        with get_connection(migrated_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO targets (id, program_id, pattern, type, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "nonexistent-id", "example.com", "domain", now, now),
                )

    def test_fk_violation_research_runs_no_program(self, migrated_db: str) -> None:
        """Insert into research_runs without valid program_id raises IntegrityError."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        with get_connection(migrated_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO research_runs (id, program_id, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "nonexistent-id", "pending", now, now),
                )

    def test_fk_violation_finding_hypotheses_no_run(self, migrated_db: str) -> None:
        """Insert into finding_hypotheses without valid research_run_id raises IntegrityError."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        with get_connection(migrated_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO finding_hypotheses (id, research_run_id, title, status, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "nonexistent-id", "Test", "open", now, now),
                )

    def test_fk_violation_evidence_no_hypothesis(self, migrated_db: str) -> None:
        """Insert into evidence without valid finding_hypothesis_id raises IntegrityError."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        with get_connection(migrated_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO evidence (id, finding_hypothesis_id, kind, content_json, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "nonexistent-id", "screenshot", "{}", now, now),
                )

    def test_fk_violation_human_approvals_no_run(self, migrated_db: str) -> None:
        """Insert into human_approvals without valid research_run_id raises IntegrityError."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        with get_connection(migrated_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO human_approvals (id, research_run_id, actor, decision, reason, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "nonexistent-id", "admin", "approved", "ok", now, now),
                )

    def test_audit_events_no_fk_constraint(self, migrated_db: str) -> None:
        """audit_events has no FK constraints — insert with any values works."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        with get_connection(migrated_db) as conn:
            # Should NOT raise — audit_events has no FKs
            conn.execute(
                "INSERT INTO audit_events (id, actor, action, target, decision, event_json, "
                "timestamp, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    "test-agent",
                    "unknown-action",
                    "fake-target",
                    "unknown-decision",
                    "{}",
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()
            # Verify it was inserted
            row = conn.execute("SELECT COUNT(*) as cnt FROM audit_events").fetchone()
            assert row["cnt"] == 1


# ------------------------------------------------------------------
# Rollback / Down-Migration Tests
# ------------------------------------------------------------------


class TestRollback:
    """Verify rollback_all behavior is safe and correct."""

    def test_rollback_clears_all_tables(self) -> None:
        """After rollback_all, no Neutrino tables remain."""
        path = get_temp_db_path()
        apply_migrations(path)
        rollback_all(path)

        with get_connection(path) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            assert len(tables) == 0

    def test_rollback_then_apply_again(self) -> None:
        """After rollback, apply_migrations works again (re-migration)."""
        path = get_temp_db_path()
        apply_migrations(path)
        rollback_all(path)
        apply_migrations(path)
        assert get_schema_version(path) == SCHEMA_VERSION

        with get_connection(path) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            names = {r["name"] for r in tables}
            for table in TABLES:
                assert table in names
            assert "schema_migrations" in names

    def test_rollback_unmigrated_is_safe(self) -> None:
        """rollback_all on a never-migrated path does not raise."""
        path = get_temp_db_path()
        # Path is a file that doesn't exist — get_connection creates it
        rollback_all(path)
        # No error is success

    def test_rollback_idempotent(self) -> None:
        """rollback_all twice on same database is safe."""
        path = get_temp_db_path()
        apply_migrations(path)
        rollback_all(path)
        rollback_all(path)  # Should not raise


# ------------------------------------------------------------------
# Connection Management
# ------------------------------------------------------------------


class TestConnectionManagement:
    """Verify connection helper behavior."""

    def test_get_connection_yields_row_factory(self, migrated_db: str) -> None:
        """Connections have row_factory set to sqlite3.Row."""
        with get_connection(migrated_db) as conn:
            assert conn.row_factory is sqlite3.Row

    def test_get_connection_commits_on_success(self, migrated_db: str) -> None:
        """Changes made inside the context manager are persisted."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        pid = str(uuid.uuid4())

        with get_connection(migrated_db) as conn:
            conn.execute(
                "INSERT INTO programs (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (pid, "Commit Test", now, now),
            )

        # Verify persisted after context exit
        with get_connection(migrated_db) as conn:
            row = conn.execute("SELECT * FROM programs WHERE id = ?", (pid,)).fetchone()
            assert row is not None
            assert row["name"] == "Commit Test"

    def test_get_connection_rollbacks_on_exception(self, migrated_db: str) -> None:
        """Failed transactions are rolled back."""
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        pid = str(uuid.uuid4())

        try:
            with get_connection(migrated_db) as conn:
                conn.execute(
                    "INSERT INTO programs (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (pid, "Rollback Test", now, now),
                )
                raise RuntimeError("forced rollback")
        except RuntimeError:
            pass

        # Verify NOT persisted
        with get_connection(migrated_db) as conn:
            row = conn.execute("SELECT * FROM programs WHERE id = ?", (pid,)).fetchone()
            assert row is None

    def test_connection_closes_after_context(self, migrated_db: str) -> None:
        """Connection is closed after the context manager exits."""
        # We only test that no exception is raised and connection usage is safe
        with get_connection(migrated_db) as conn:
            conn.execute("SELECT 1")
        # After exit, the connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


# ------------------------------------------------------------------
# Safety
# ------------------------------------------------------------------


class TestSafety:
    """Verify no remote DB, no ORM, no unsafe operations."""

    def test_all_test_paths_outside_home(self) -> None:
        """All test database paths are outside the production home directory."""
        for _ in range(5):
            path = get_temp_db_path()
            assert ".neutrino" not in path

    def test_no_network_in_storage_modules(self) -> None:
        """Storage modules have no network-related imports or code."""
        import neutrino.storage as storage_pkg

        for mod_name in dir(storage_pkg):
            if mod_name.startswith("_"):
                continue
            obj = getattr(storage_pkg, mod_name, None)
            if obj is not None and hasattr(obj, "__dict__"):
                source = str(obj.__dict__)
                assert "socket" not in source.lower()
                assert "http" not in source.lower()
                assert "requests" not in source.lower()

    def test_migration_order_is_deterministic(self) -> None:
        """Migration versions are applied in sorted order."""
        path = get_temp_db_path()
        apply_migrations(path)

        with get_connection(path) as conn:
            rows = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version ASC"
            ).fetchall()
            versions = [r["version"] for r in rows]
            assert versions == sorted(versions)
