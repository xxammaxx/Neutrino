"""Neutrino Storage — local SQLite persistence layer.

This package provides the database foundation for all Neutrino Core entities:
schema definitions, idempotent migrations, connection management, and path
resolution.

All storage is local-only. No remote databases, no ORM magic, no network I/O.

Design:
    - Database path: ``~/.neutrino/db/neutrino.db`` (overridable via env var)
    - Migrations: versioned, idempotent, applied from ``schema_migrations`` table
    - Foreign Keys: enabled on every connection
    - Tests: temporary SQLite databases in isolated directories

This package does NOT implement CRUD repositories (Issue #11) or the
AuditLog JSONL-Writer (Issue #12). It provides only schema, migrations,
and minimal connection helpers.
"""

from neutrino.storage.migrations import apply_migrations, get_schema_version, rollback_all
from neutrino.storage.paths import get_db_path, get_temp_db_path
from neutrino.storage.schema import SCHEMA_VERSION, TABLES, get_schema_ddl
from neutrino.storage.sqlite import ensure_db_directory, get_connection

__all__ = [
    "apply_migrations",
    "ensure_db_directory",
    "get_connection",
    "get_db_path",
    "get_schema_ddl",
    "get_schema_version",
    "get_temp_db_path",
    "rollback_all",
    "SCHEMA_VERSION",
    "TABLES",
]
