"""SQLite DDL schema for all Neutrino Core entities.

Defines the complete database schema as explicit SQL statements.
All tables use TEXT primary keys (UUIDs), ISO 8601 timestamps, and
foreign keys with CASCADE or SET NULL as appropriate.

No ORM, no code generation — explicit SQL only.
"""

from __future__ import annotations

SCHEMA_VERSION = "1"

TABLES = [
    "programs",
    "scope_policies",
    "targets",
    "research_runs",
    "finding_hypotheses",
    "evidence",
    "human_approvals",
    "audit_events",
]

_SCHEMA_DDL = f"""
-- Neutrino Core Schema v{SCHEMA_VERSION}
-- Generated: 2026-07-05
-- All IDs are UUIDs stored as TEXT. Timestamps are ISO 8601 TEXT.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS programs (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    platform TEXT,
    policy_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scope_policies (
    id TEXT PRIMARY KEY NOT NULL,
    program_id TEXT,
    source_url TEXT NOT NULL,
    raw_text TEXT,
    parsed_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS targets (
    id TEXT PRIMARY KEY NOT NULL,
    program_id TEXT,
    pattern TEXT NOT NULL,
    type TEXT NOT NULL,
    source_section TEXT,
    is_wildcard INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY NOT NULL,
    program_id TEXT,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS finding_hypotheses (
    id TEXT PRIMARY KEY NOT NULL,
    research_run_id TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (research_run_id) REFERENCES research_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY NOT NULL,
    finding_hypothesis_id TEXT,
    kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (finding_hypothesis_id) REFERENCES finding_hypotheses(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS human_approvals (
    id TEXT PRIMARY KEY NOT NULL,
    research_run_id TEXT,
    actor TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (research_run_id) REFERENCES research_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    decision TEXT,
    event_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def get_schema_ddl() -> str:
    """Return the complete DDL for the Neutrino Core schema.

    Includes ``schema_migrations`` table and all 8 core entity tables
    with foreign key constraints.

    Returns:
        Complete SQL DDL as a single string.
    """
    return _SCHEMA_DDL
