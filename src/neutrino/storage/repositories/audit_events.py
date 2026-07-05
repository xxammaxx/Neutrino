"""AuditEventRepository: append-only repository for immutable audit events.

AuditEvents record system actions, decisions, and state changes.
They are **immutable**: once written, they can NEVER be updated or deleted.

Key design decisions:
    - ``append()`` creates a new audit event (alias for create).
    - ``get()`` reads a single event.
    - ``list_all()`` returns all events in deterministic order.
    - ``update()`` and ``delete()`` ALWAYS raise ``AuditEventImmutable``.
    - No foreign key constraints (by design in schema).
    - This is NOT the JSONL AuditLog writer (#12). That comes later.
"""

from __future__ import annotations

from neutrino.models.entities import AuditEvent, AuditEventCreate
from neutrino.storage.exceptions import AuditEventImmutable
from neutrino.storage.repositories.base import BaseRepository

_LIST_ORDER = "timestamp ASC, id ASC"


class AuditEventRepository(BaseRepository):
    """Append-only repository for the ``audit_events`` table.

    Immutability Invariant:
        ``update()`` and ``delete()`` are permanently disabled and
        raise ``AuditEventImmutable`` on every call.
    """

    # ------------------------------------------------------------------
    # Create / Append
    # ------------------------------------------------------------------

    def create(self, data: AuditEventCreate) -> AuditEvent:
        """Insert a new audit event (append-only).

        Synonym: ``append()`` delegates to ``create()``.
        """
        now = self._now_iso()
        sql = (
            "INSERT INTO audit_events (id, actor, action, target, decision, "
            "event_json, timestamp, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            data.id,
            data.actor,
            data.action,
            data.target,
            data.decision,
            data.event_json,
            data.timestamp,
            now,
            now,
        )
        self._execute_write(sql, params)
        return self.get(data.id)  # type: ignore[return-value]

    def append(self, data: AuditEventCreate) -> AuditEvent:
        """Append a new audit event. Same as ``create()``.

        This is the preferred name for audit logging operations.
        """
        return self.create(data)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> AuditEvent | None:
        """Get an audit event by its UUID.

        Args:
            entity_id: AuditEvent UUID.

        Returns:
            AuditEvent if found, None otherwise.
        """
        row = self._fetch_one("SELECT * FROM audit_events WHERE id = ?", (entity_id,))
        if row is None:
            return None
        return AuditEvent(**row)

    def list_all(self) -> list[AuditEvent]:
        """List all audit events ordered by ``timestamp ASC, id ASC``.

        Returns:
            List of AuditEvent entities (empty if none).
        """
        rows = self._fetch_all(f"SELECT * FROM audit_events ORDER BY {_LIST_ORDER}")
        return [AuditEvent(**r) for r in rows]

    def list_by_actor(self, actor: str) -> list[AuditEvent]:
        """List audit events for a specific actor."""
        rows = self._fetch_all(
            f"SELECT * FROM audit_events WHERE actor = ? ORDER BY {_LIST_ORDER}",
            (actor,),
        )
        return [AuditEvent(**r) for r in rows]

    def list_by_action(self, action: str) -> list[AuditEvent]:
        """List audit events for a specific action type."""
        rows = self._fetch_all(
            f"SELECT * FROM audit_events WHERE action = ? ORDER BY {_LIST_ORDER}",
            (action,),
        )
        return [AuditEvent(**r) for r in rows]

    # ------------------------------------------------------------------
    # Update / Delete — FORBIDDEN
    # ------------------------------------------------------------------

    def update(self, entity_id: str, data: object = None) -> AuditEvent:  # noqa: ARG002
        """Update is FORBIDDEN for audit events.

        Raises:
            AuditEventImmutable: Always.
        """
        raise AuditEventImmutable("UPDATE", entity_id)

    def delete(self, entity_id: str) -> bool:
        """Delete is FORBIDDEN for audit events.

        Raises:
            AuditEventImmutable: Always.
        """
        raise AuditEventImmutable("DELETE", entity_id)

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the total number of audit events."""
        row = self._fetch_one("SELECT COUNT(*) as cnt FROM audit_events")
        assert row is not None
        return int(row["cnt"])
