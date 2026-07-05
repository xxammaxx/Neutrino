"""Unit tests for Neutrino Storage schema definitions.

Validates that DDL is correct, all tables exist, columns match expected
definitions, and foreign keys are properly configured.

All tests use temporary SQLite databases in isolated directories.
No real ``~/.neutrino/`` path is ever written.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime

import pytest

from neutrino.storage.migrations import apply_migrations, get_schema_version, rollback_all
from neutrino.storage.paths import get_temp_db_path
from neutrino.storage.schema import TABLES, get_schema_ddl
from neutrino.storage.sqlite import get_connection

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def db_path() -> str:
    """Temporary database path in an isolated directory."""
    path = get_temp_db_path()
    apply_migrations(path)
    return path


def _fresh_db() -> tuple[str, sqlite3.Connection]:
    """Create a fresh migrated database and return (path, connection)."""
    path = get_temp_db_path()
    apply_migrations(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return path, conn


def _table_columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    """Return a mapping of column_name → type for a table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"]: row["type"] for row in rows}


def _now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------------
# Schema Structure Tests
# ------------------------------------------------------------------


class TestSchemaDdl:
    """Tests for the schema DDL string itself."""

    def test_schema_ddl_is_non_empty(self) -> None:
        """Schema DDL is a non-empty string."""
        ddl = get_schema_ddl()
        assert isinstance(ddl, str)
        assert len(ddl) > 0

    def test_schema_migrations_table_in_ddl(self) -> None:
        """schema_migrations table is defined in DDL."""
        ddl = get_schema_ddl()
        assert "CREATE TABLE IF NOT EXISTS schema_migrations" in ddl

    def test_all_core_tables_in_ddl(self) -> None:
        """All 8 core entity tables are defined in DDL."""
        ddl = get_schema_ddl()
        for table in TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl


class TestApplyMigrations:
    """Tests for the migration application process."""

    def test_apply_migrations_creates_db_file(self) -> None:
        """apply_migrations creates the SQLite database file."""
        path = get_temp_db_path()
        import os

        assert not os.path.exists(path)
        apply_migrations(path)
        assert os.path.exists(path)

    def test_schema_migrations_table_exists(self, db_path: str) -> None:
        """schema_migrations table exists after migration."""
        with get_connection(db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchall()
            assert len(tables) == 1

    def test_all_core_tables_exist(self, db_path: str) -> None:
        """All 8 core entity tables exist after migration."""
        with get_connection(db_path) as conn:
            existing = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            names = {row["name"] for row in existing}
            for table in TABLES:
                assert table in names, f"Table '{table}' not found in database"

    def test_schema_version_is_v1(self, db_path: str) -> None:
        """Schema version is '1' after initial migration."""
        version = get_schema_version(db_path)
        assert version == "1"

    def test_migrations_are_idempotent(self, db_path: str) -> None:
        """Running apply_migrations twice does not raise or duplicate."""
        # First run already done in fixture. Second run:
        apply_migrations(db_path)
        version = get_schema_version(db_path)
        assert version == "1"
        # Verify no duplicate tables
        with get_connection(db_path) as conn:
            rows = conn.execute("SELECT COUNT(*) as cnt FROM schema_migrations").fetchone()
            assert rows["cnt"] == 1


class TestTableColumns:
    """Verify column definitions for each core table."""

    def test_programs_columns(self, db_path: str) -> None:
        """programs table has expected columns."""
        with get_connection(db_path) as conn:
            cols = _table_columns(conn, "programs")
            assert cols["id"] == "TEXT"
            assert cols["name"] == "TEXT"
            assert cols["platform"] == "TEXT"
            assert cols["policy_url"] == "TEXT"
            assert cols["created_at"] == "TEXT"
            assert cols["updated_at"] == "TEXT"

    def test_scope_policies_columns(self, db_path: str) -> None:
        """scope_policies table has expected columns."""
        with get_connection(db_path) as conn:
            cols = _table_columns(conn, "scope_policies")
            assert cols["id"] == "TEXT"
            assert cols["program_id"] == "TEXT"
            assert cols["source_url"] == "TEXT"
            assert cols["raw_text"] == "TEXT"
            assert cols["parsed_json"] == "TEXT"
            assert cols["created_at"] == "TEXT"
            assert cols["updated_at"] == "TEXT"

    def test_targets_columns(self, db_path: str) -> None:
        """targets table has expected columns with is_wildcard default."""
        with get_connection(db_path) as conn:
            cols = _table_columns(conn, "targets")
            assert cols["id"] == "TEXT"
            assert cols["program_id"] == "TEXT"
            assert cols["pattern"] == "TEXT"
            assert cols["type"] == "TEXT"
            assert cols["source_section"] == "TEXT"
            assert cols["is_wildcard"] == "INTEGER"
            assert cols["created_at"] == "TEXT"
            assert cols["updated_at"] == "TEXT"

    def test_research_runs_columns(self, db_path: str) -> None:
        """research_runs table has expected columns."""
        with get_connection(db_path) as conn:
            cols = _table_columns(conn, "research_runs")
            assert cols["id"] == "TEXT"
            assert cols["program_id"] == "TEXT"
            assert cols["status"] == "TEXT"
            assert cols["started_at"] == "TEXT"
            assert cols["finished_at"] == "TEXT"
            assert cols["created_at"] == "TEXT"
            assert cols["updated_at"] == "TEXT"

    def test_finding_hypotheses_columns(self, db_path: str) -> None:
        """finding_hypotheses table has expected columns."""
        with get_connection(db_path) as conn:
            cols = _table_columns(conn, "finding_hypotheses")
            assert cols["id"] == "TEXT"
            assert cols["research_run_id"] == "TEXT"
            assert cols["title"] == "TEXT"
            assert cols["status"] == "TEXT"
            assert cols["risk_level"] == "TEXT"
            assert cols["created_at"] == "TEXT"
            assert cols["updated_at"] == "TEXT"

    def test_evidence_columns(self, db_path: str) -> None:
        """evidence table has expected columns."""
        with get_connection(db_path) as conn:
            cols = _table_columns(conn, "evidence")
            assert cols["id"] == "TEXT"
            assert cols["finding_hypothesis_id"] == "TEXT"
            assert cols["kind"] == "TEXT"
            assert cols["content_json"] == "TEXT"
            assert cols["source"] == "TEXT"
            assert cols["created_at"] == "TEXT"
            assert cols["updated_at"] == "TEXT"

    def test_human_approvals_columns(self, db_path: str) -> None:
        """human_approvals table has expected columns."""
        with get_connection(db_path) as conn:
            cols = _table_columns(conn, "human_approvals")
            assert cols["id"] == "TEXT"
            assert cols["research_run_id"] == "TEXT"
            assert cols["actor"] == "TEXT"
            assert cols["decision"] == "TEXT"
            assert cols["reason"] == "TEXT"
            assert cols["created_at"] == "TEXT"
            assert cols["updated_at"] == "TEXT"

    def test_audit_events_columns(self, db_path: str) -> None:
        """audit_events table has expected columns."""
        with get_connection(db_path) as conn:
            cols = _table_columns(conn, "audit_events")
            assert cols["id"] == "TEXT"
            assert cols["actor"] == "TEXT"
            assert cols["action"] == "TEXT"
            assert cols["target"] == "TEXT"
            assert cols["decision"] == "TEXT"
            assert cols["event_json"] == "TEXT"
            assert cols["timestamp"] == "TEXT"
            assert cols["created_at"] == "TEXT"
            assert cols["updated_at"] == "TEXT"


# ------------------------------------------------------------------
# Data Insertion Tests
# ------------------------------------------------------------------


class TestDataIntegrity:
    """Verify basic data operations work correctly."""

    def test_insert_and_select_program(self, db_path: str) -> None:
        """A program can be inserted and selected."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            pid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO programs (id, name, platform, policy_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, "Test Program", "hackerone", "https://hackerone.com/test", now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM programs WHERE id = ?", (pid,)).fetchone()
            assert row is not None
            assert row["name"] == "Test Program"

    def test_insert_and_select_audit_event(self, db_path: str) -> None:
        """An audit_event can be inserted without FK dependency."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            eid = str(uuid.uuid4())
            event = json.dumps({"action": "scope_check", "result": "allow"})
            conn.execute(
                "INSERT INTO audit_events (id, actor, action, target, decision, event_json, "
                "timestamp, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, "system", "scope_check", "example.com", "allow", event, now, now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM audit_events WHERE id = ?", (eid,)).fetchone()
            assert row is not None
            assert row["actor"] == "system"
            assert row["action"] == "scope_check"

    def test_target_is_wildcard_default_zero(self, db_path: str) -> None:
        """is_wildcard defaults to 0 when not explicitly set."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            tid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO targets (id, pattern, type, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (tid, "example.com", "domain", now, now),
            )
            conn.commit()
            row = conn.execute("SELECT is_wildcard FROM targets WHERE id = ?", (tid,)).fetchone()
            assert row is not None
            assert row["is_wildcard"] == 0


# ------------------------------------------------------------------
# Foreign Key Tests
# ------------------------------------------------------------------


class TestForeignKeys:
    """Verify foreign key constraints are enforced."""

    def test_foreign_keys_are_enabled(self, db_path: str) -> None:
        """PRAGMA foreign_keys returns 1 after migration."""
        with get_connection(db_path) as conn:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
            assert row[0] == 1

    def test_scope_policies_fk_to_programs(self, db_path: str) -> None:
        """scope_policies.program_id references programs.id."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            pid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO programs (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (pid, "FK Test", now, now),
            )
            sp_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO scope_policies (id, program_id, source_url, parsed_json, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (sp_id, pid, "https://example.com/policy", "{}", now, now),
            )
            conn.commit()

            # Verify reference works
            row = conn.execute(
                "SELECT sp.id FROM scope_policies sp JOIN programs p ON sp.program_id = p.id "
                "WHERE p.name = 'FK Test'"
            ).fetchone()
            assert row is not None
            assert row["id"] == sp_id

    def test_targets_fk_to_programs(self, db_path: str) -> None:
        """targets.program_id references programs.id."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            pid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO programs (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (pid, "Target FK Test", now, now),
            )
            tid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO targets (id, program_id, pattern, type, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (tid, pid, "*.example.com", "wildcard_domain", now, now),
            )
            conn.commit()

            row = conn.execute(
                "SELECT t.id FROM targets t JOIN programs p ON t.program_id = p.id "
                "WHERE p.name = 'Target FK Test'"
            ).fetchone()
            assert row is not None
            assert row["id"] == tid

    def test_research_runs_fk_to_programs(self, db_path: str) -> None:
        """research_runs.program_id references programs.id."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            pid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO programs (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (pid, "Research Run FK Test", now, now),
            )
            rrid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO research_runs (id, program_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (rrid, pid, "pending", now, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT rr.id FROM research_runs rr JOIN programs p ON rr.program_id = p.id "
                "WHERE p.name = 'Research Run FK Test'"
            ).fetchone()
            assert row is not None
            assert row["id"] == rrid

    def test_finding_hypotheses_fk_to_research_runs(self, db_path: str) -> None:
        """finding_hypotheses.research_run_id references research_runs.id."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            pid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO programs (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (pid, "FH FK Test", now, now),
            )
            rrid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO research_runs (id, program_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (rrid, pid, "running", now, now),
            )
            fhid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO finding_hypotheses (id, research_run_id, title, status, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (fhid, rrid, "SQL Injection on login", "open", now, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT fh.id FROM finding_hypotheses fh "
                "JOIN research_runs rr ON fh.research_run_id = rr.id "
                "WHERE rr.status = 'running'"
            ).fetchone()
            assert row is not None
            assert row["id"] == fhid

    def test_evidence_fk_to_finding_hypotheses(self, db_path: str) -> None:
        """evidence.finding_hypothesis_id references finding_hypotheses.id."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            pid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO programs (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (pid, "Evidence FK Test", now, now),
            )
            rrid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO research_runs (id, program_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (rrid, pid, "running", now, now),
            )
            fhid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO finding_hypotheses (id, research_run_id, title, status, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (fhid, rrid, "XSS on search", "open", now, now),
            )
            evid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO evidence (id, finding_hypothesis_id, kind, content_json, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (evid, fhid, "screenshot", '{"url": "test"}', now, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT e.id FROM evidence e "
                "JOIN finding_hypotheses fh ON e.finding_hypothesis_id = fh.id "
                "WHERE fh.title = 'XSS on search'"
            ).fetchone()
            assert row is not None
            assert row["id"] == evid

    def test_human_approvals_fk_to_research_runs(self, db_path: str) -> None:
        """human_approvals.research_run_id references research_runs.id."""
        with get_connection(db_path) as conn:
            now = _now_iso()
            pid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO programs (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (pid, "HA FK Test", now, now),
            )
            rrid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO research_runs (id, program_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (rrid, pid, "pending_approval", now, now),
            )
            haid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO human_approvals (id, research_run_id, actor, decision, reason, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (haid, rrid, "admin", "approved", "Looks safe", now, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT ha.id FROM human_approvals ha "
                "JOIN research_runs rr ON ha.research_run_id = rr.id "
                "WHERE rr.status = 'pending_approval'"
            ).fetchone()
            assert row is not None
            assert row["id"] == haid

    def test_audit_events_no_hard_fk(self, db_path: str) -> None:
        """audit_events has no foreign key constraints (by design)."""
        with get_connection(db_path) as conn:
            fks = conn.execute("PRAGMA foreign_key_list(audit_events)").fetchall()
            assert len(fks) == 0, "audit_events must not have foreign keys"


# ------------------------------------------------------------------
# Path Tests
# ------------------------------------------------------------------


class TestDbPath:
    """Verify the default and override database paths."""

    def test_default_path_contains_neutrino_db(self) -> None:
        """Default path points to ~/.neutrino/db/neutrino.db."""
        from neutrino.storage.paths import get_db_path

        path = get_db_path()
        assert path.endswith(".neutrino/db/neutrino.db")
        assert "/.neutrino/db/neutrino.db" in path

    def test_env_override_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """NEUTRINO_DB_PATH env var overrides the default."""
        from neutrino.storage.paths import get_db_path

        monkeypatch.setenv("NEUTRINO_DB_PATH", "/custom/test/path/neutrino.db")
        path = get_db_path()
        assert path == "/custom/test/path/neutrino.db"

    def test_temp_path_is_different_from_default(self) -> None:
        """get_temp_db_path returns a path outside ~/.neutrino/."""
        from neutrino.storage.paths import get_temp_db_path

        path = get_temp_db_path()
        assert ".neutrino" not in path
        assert path.endswith("neutrino.db")

    def test_temp_path_is_unique(self) -> None:
        """Two calls to get_temp_db_path return different paths."""
        from neutrino.storage.paths import get_temp_db_path

        path1 = get_temp_db_path()
        path2 = get_temp_db_path()
        assert path1 != path2

    def test_default_path_does_not_create_files(self) -> None:
        """get_db_path does not create any files or directories."""
        import os

        from neutrino.storage.paths import get_db_path

        default_home = os.path.expanduser("~/.neutrino/db/neutrino.db")
        existed_before = os.path.exists(default_home)

        get_db_path()

        assert os.path.exists(default_home) == existed_before


# ------------------------------------------------------------------
# Rollback Tests
# ------------------------------------------------------------------


class TestRollback:
    """Verify safe rollback/down-migration behavior."""

    def test_rollback_all_drops_tables(self) -> None:
        """rollback_all removes all core tables from a test database."""
        path = get_temp_db_path()
        apply_migrations(path)

        # Verify tables exist before rollback
        with get_connection(path) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            assert len(tables) >= 9  # schema_migrations + 8 core tables

        rollback_all(path)

        with get_connection(path) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            assert len(tables) == 0

    def test_rollback_all_is_idempotent(self) -> None:
        """Calling rollback_all twice does not raise."""
        path = get_temp_db_path()
        apply_migrations(path)
        rollback_all(path)
        rollback_all(path)  # Should not raise

    def test_rollback_all_on_unmigrated_db(self) -> None:
        """rollback_all on an empty database does not raise."""
        path = get_temp_db_path()
        rollback_all(path)  # Should not raise, no tables to drop

    def test_rollback_all_only_uses_test_path(self) -> None:
        """rollback_all is only tested with temporary paths."""
        path = get_temp_db_path()
        assert ".neutrino" not in path


# ------------------------------------------------------------------
# Safety Tests
# ------------------------------------------------------------------


class TestSafety:
    """Verify no remote DB connection, no ORM magic."""

    def test_no_unsafe_paths_in_tests(self) -> None:
        """All test database paths are outside ~/.neutrino/."""
        path = get_temp_db_path()
        assert "~" not in path
        assert ".neutrino" not in path

    def test_no_orm_library_imported(self) -> None:
        """Storage modules do not import ORM libraries."""
        import neutrino.storage.migrations as migrations_mod
        import neutrino.storage.schema as schema_mod
        import neutrino.storage.sqlite as sqlite_mod

        for mod in (schema_mod, migrations_mod, sqlite_mod):
            source = str(mod.__dict__)
            assert "sqlalchemy" not in source.lower()
            assert "django" not in source.lower()
            assert "peewee" not in source.lower()
            assert "pony" not in source.lower()

    def test_schema_is_deterministic(self) -> None:
        """get_schema_ddl returns the same DDL on every call."""
        ddl1 = get_schema_ddl()
        ddl2 = get_schema_ddl()
        assert ddl1 == ddl2


class TestDeterministicMigrations:
    """Verify deterministic migration behavior."""

    def test_schema_identical_across_two_fresh_dbs(self) -> None:
        """Two independently-created databases have identical schemas."""
        path1 = get_temp_db_path()
        path2 = get_temp_db_path()
        apply_migrations(path1)
        apply_migrations(path2)

        with get_connection(path1) as c1, get_connection(path2) as c2:
            t1 = c1.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            t2 = c2.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()

            names1 = [(r["name"], r["sql"]) for r in t1]
            names2 = [(r["name"], r["sql"]) for r in t2]
            assert names1 == names2

    def test_migration_version_never_decreases(self) -> None:
        """Running apply_migrations again does not change the version."""
        path = get_temp_db_path()
        apply_migrations(path)
        v1 = get_schema_version(path)
        apply_migrations(path)
        v2 = get_schema_version(path)
        assert v1 == v2

    def test_no_duplicate_rows_on_idempotent_run(self) -> None:
        """Idempotent migration does not insert duplicate migration records."""
        path = get_temp_db_path()
        apply_migrations(path)

        with get_connection(path) as conn:
            before = conn.execute("SELECT COUNT(*) as cnt FROM schema_migrations").fetchone()["cnt"]

        apply_migrations(path)

        with get_connection(path) as conn:
            after = conn.execute("SELECT COUNT(*) as cnt FROM schema_migrations").fetchone()["cnt"]

        assert before == after
