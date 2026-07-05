"""Neutrino Audit Log — append-only JSONL audit trail.

This package provides a local, append-only JSONL AuditLog writer
for Neutrino Core. Every security decision, agent action, and
workflow step is recorded as an immutable JSON line in
``~/.neutrino/audit/``.

Key components:
    - ``AuditLogEvent`` — Pydantic model for a single audit entry
      with mandatory actor, action, target, decision, and timestamp.
    - ``AuditLogWriter`` — Append-only JSONL writer that never
      overwrites, truncates, rotates, or deletes audit data.

Design invariants:
    - Append-only: no update, no delete, no overwrite, no truncate.
    - Local-only: no network I/O, no remote shipping, no cloud logs.
    - Test-safe: ``audit_dir`` is overridable; tests use temp dirs.
    - No rotation, no compression, no automatic deletion.

This is NOT the SQLite ``AuditEventRepository`` (#11). That layer
operates on the schema-driven ``audit_events`` table. This writer
produces a plain JSONL file suitable for external tool consumption
and manual inspection.
"""

from __future__ import annotations

from neutrino.audit.models import AuditLogEvent
from neutrino.audit.writer import AuditLogWriter

__all__ = [
    "AuditLogEvent",
    "AuditLogWriter",
]
