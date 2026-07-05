"""TargetRepository: CRUD operations for scope targets.

Targets represent in-scope and out-of-scope assets (domains, IP ranges,
URLs) linked to a Program via ``program_id``.
"""

from __future__ import annotations

import sqlite3

from neutrino.models.entities import Target, TargetCreate, TargetUpdate
from neutrino.storage.exceptions import EntityNotFound, ForeignKeyViolation
from neutrino.storage.repositories.base import BaseRepository

_LIST_ORDER = "created_at ASC, id ASC"


class TargetRepository(BaseRepository):
    """CRUD repository for the ``targets`` table."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: TargetCreate) -> Target:
        """Insert a new target.

        Args:
            data: Target creation input.

        Returns:
            The created Target entity.

        Raises:
            ForeignKeyViolation: If ``program_id`` references a nonexistent program.
        """
        now = self._now_iso()
        sql = (
            "INSERT INTO targets (id, program_id, pattern, type, source_section, "
            "is_wildcard, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            data.id,
            data.program_id,
            data.pattern,
            data.type,
            data.source_section,
            int(data.is_wildcard),  # bool → int (0/1)
            now,
            now,
        )
        try:
            self._execute_write(sql, params)
        except sqlite3.IntegrityError as e:
            raise ForeignKeyViolation("target", "program_id", str(e)) from e
        return self.get(data.id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> Target | None:
        """Get a target by its UUID."""
        row = self._fetch_one("SELECT * FROM targets WHERE id = ?", (entity_id,))
        if row is None:
            return None
        # Convert is_wildcard from int to bool
        row["is_wildcard"] = bool(row["is_wildcard"])
        return Target(**row)

    def list_all(self) -> list[Target]:
        """List all targets ordered by ``created_at ASC, id ASC``."""
        rows = self._fetch_all(f"SELECT * FROM targets ORDER BY {_LIST_ORDER}")
        result: list[Target] = []
        for r in rows:
            r["is_wildcard"] = bool(r["is_wildcard"])
            result.append(Target(**r))
        return result

    def list_by_program(self, program_id: str) -> list[Target]:
        """List targets for a specific program.

        Args:
            program_id: Program UUID.

        Returns:
            List of Target entities (empty if none found).
        """
        rows = self._fetch_all(
            f"SELECT * FROM targets WHERE program_id = ? ORDER BY {_LIST_ORDER}",
            (program_id,),
        )
        result: list[Target] = []
        for r in rows:
            r["is_wildcard"] = bool(r["is_wildcard"])
            result.append(Target(**r))
        return result

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, entity_id: str, data: TargetUpdate) -> Target:
        """Update an existing target. Only non-None fields are updated.

        Raises:
            EntityNotFound: If the target does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("Target", entity_id)

        fields = data.model_dump(exclude_none=True)
        if not fields:
            return existing

        # Convert is_wildcard bool → int for SQLite
        if "is_wildcard" in fields:
            fields["is_wildcard"] = int(fields["is_wildcard"])

        set_clauses = [f"{k} = ?" for k in fields]
        values = list(fields.values())
        set_clauses.append("updated_at = ?")
        values.append(self._now_iso())
        values.append(entity_id)

        sql = f"UPDATE targets SET {', '.join(set_clauses)} WHERE id = ?"
        self._execute_write(sql, tuple(values))
        return self.get(entity_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, entity_id: str) -> bool:
        """Delete a target by its UUID.

        Raises:
            EntityNotFound: If the target does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("Target", entity_id)
        self._execute_write("DELETE FROM targets WHERE id = ?", (entity_id,))
        return True

    def count(self) -> int:
        """Return the total number of targets."""
        row = self._fetch_one("SELECT COUNT(*) as cnt FROM targets")
        assert row is not None
        return int(row["cnt"])
