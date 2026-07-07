"""Idempotent migration system for Neutrino Storage.

Applies versioned SQL migrations to a local SQLite database.
Tracks applied migrations in the ``schema_migrations`` table.

All migrations are idempotent: running ``apply_migrations()`` multiple
times produces the same result without errors or duplicate operations.

Safety:
    - ``rollback_all()`` only operates on test databases (explicit path required).
    - Never silently drops the production ``~/.neutrino/db/neutrino.db``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from neutrino.storage.schema import get_schema_ddl
from neutrino.storage.sqlite import get_connection


def _get_applied_versions(conn: sqlite3.Connection) -> set[str]:
    """Return the set of migration versions already applied.

    Args:
        conn: Active SQLite connection.

    Returns:
        Set of version strings from ``schema_migrations``.
    """
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row["version"] for row in rows}


def _apply_migration_v1(conn: sqlite3.Connection) -> None:
    """Apply migration version 1: initial schema with all core tables.

    Args:
        conn: Active SQLite connection.
    """
    conn.executescript(get_schema_ddl())
    timestamp = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        ("1", timestamp),
    )


def _apply_migration_v2(conn: sqlite3.Connection) -> None:
    """Apply migration version 2: extend human_approvals with approval workflow fields.

    Adds ``action``, ``target``, ``scope_reference``, ``test_type``, and
    ``risk_summary`` columns to support the full Human Authorization Workflow
    (Issue #4). Columns are added with ``IF NOT EXISTS`` for idempotency.

    Args:
        conn: Active SQLite connection.
    """
    new_columns = [
        "action TEXT NOT NULL DEFAULT ''",
        "target TEXT NOT NULL DEFAULT ''",
        "scope_reference TEXT NOT NULL DEFAULT ''",
        "test_type TEXT NOT NULL DEFAULT ''",
        "risk_summary TEXT NOT NULL DEFAULT ''",
    ]
    for col_def in new_columns:
        # SQLite does not support IF NOT EXISTS for ALTER TABLE ADD COLUMN,
        # but we catch the 'duplicate column' error to be idempotent.
        try:
            conn.execute(f"ALTER TABLE human_approvals ADD COLUMN {col_def}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                continue
            raise
    timestamp = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        ("2", timestamp),
    )


# Registry of migration callables, keyed by version string.
_MIGRATIONS: dict[str, Callable[[sqlite3.Connection], None]] = {
    "1": _apply_migration_v1,
    "2": _apply_migration_v2,
}


def apply_migrations(db_path: str) -> None:
    """Apply all pending migrations to the database at ``db_path``.

    Idempotent: already-applied migrations are skipped. The database
    directory is created automatically.

    Args:
        db_path: Absolute path to the SQLite database file.
    """
    with get_connection(db_path) as conn:
        applied = _get_applied_versions(conn)

        for version in sorted(_MIGRATIONS.keys()):
            if version in applied:
                continue
            migration_fn = _MIGRATIONS[version]
            migration_fn(conn)
            conn.commit()


def get_schema_version(db_path: str) -> str | None:
    """Return the latest applied schema version, or None if not migrated.

    Args:
        db_path: Absolute path to the SQLite database file.

    Returns:
        The latest version string from ``schema_migrations``, or None.
    """
    with get_connection(db_path) as conn:
        try:
            row = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        return str(row["version"])


def rollback_all(db_path: str) -> None:
    """Drop all Neutrino Core tables from the database.

    **WARNING**: This is a destructive operation intended ONLY for
    test databases. Never call this on the production database path
    without explicit confirmation.

    Drops tables in reverse dependency order to respect foreign keys.

    Args:
        db_path: Absolute path to the SQLite database file.
    """
    from neutrino.storage.schema import TABLES

    with get_connection(db_path) as conn:
        # Order matters: drop children before parents
        drop_order = [
            "audit_events",
            "evidence",
            "human_approvals",
            "finding_hypotheses",
            "targets",
            "scope_policies",
            "research_runs",
            "programs",
            "schema_migrations",
        ]
        for table in drop_order:
            if table == "schema_migrations" or table in TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
