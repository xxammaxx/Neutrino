"""ProgramRepository: CRUD operations for bug bounty programs.

Programs are the top-level entity in the Neutrino data model.
They link to ScopePolicies, Targets, and ResearchRuns.
"""

from __future__ import annotations

import sqlite3

from neutrino.models.entities import Program, ProgramCreate, ProgramUpdate
from neutrino.storage.exceptions import EntityNotFound, ForeignKeyViolation
from neutrino.storage.repositories.base import BaseRepository

# Deterministic list ordering.
_LIST_ORDER = "created_at ASC, id ASC"


class ProgramRepository(BaseRepository):
    """CRUD repository for the ``programs`` table."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: ProgramCreate) -> Program:
        """Insert a new program.

        Args:
            data: Program creation input with required id and name.

        Returns:
            The created Program entity.

        Raises:
            ForeignKeyViolation: (programs have no FKs, so only raised on internal errors.)
        """
        now = self._now_iso()
        sql = (
            "INSERT INTO programs (id, name, platform, policy_url, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        params = (data.id, data.name, data.platform, data.policy_url, now, now)
        try:
            self._execute_write(sql, params)
        except sqlite3.IntegrityError as e:
            raise ForeignKeyViolation("program", "id", str(e)) from e
        return self.get(data.id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> Program | None:
        """Get a program by its UUID.

        Args:
            entity_id: Program UUID.

        Returns:
            Program if found, None otherwise.
        """
        row = self._fetch_one("SELECT * FROM programs WHERE id = ?", (entity_id,))
        if row is None:
            return None
        return Program(**row)

    def list_all(self) -> list[Program]:
        """List all programs ordered by ``created_at ASC, id ASC``.

        Returns:
            List of Program entities (empty list if no programs exist).
        """
        rows = self._fetch_all(f"SELECT * FROM programs ORDER BY {_LIST_ORDER}")
        return [Program(**r) for r in rows]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, entity_id: str, data: ProgramUpdate) -> Program:
        """Update an existing program. Only non-None fields are updated.

        Args:
            entity_id: Program UUID.
            data: ProgramUpdate with optional fields.

        Returns:
            Updated Program entity.

        Raises:
            EntityNotFound: If no program with the given ID exists.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("Program", entity_id)

        fields = data.model_dump(exclude_none=True)
        if not fields:
            return existing

        set_clauses = [f"{k} = ?" for k in fields]
        values = list(fields.values())
        set_clauses.append("updated_at = ?")
        values.append(self._now_iso())
        values.append(entity_id)

        sql = f"UPDATE programs SET {', '.join(set_clauses)} WHERE id = ?"
        self._execute_write(sql, tuple(values))
        return self.get(entity_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, entity_id: str) -> bool:
        """Delete a program by its UUID.

        Child records (ScopePolicies, Targets, ResearchRuns) are set to NULL
        via ``ON DELETE SET NULL`` in the schema — they are NOT cascade-deleted.

        Args:
            entity_id: Program UUID.

        Returns:
            True if deleted.

        Raises:
            EntityNotFound: If no program with the given ID exists.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("Program", entity_id)
        self._execute_write("DELETE FROM programs WHERE id = ?", (entity_id,))
        return True

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the total number of programs.

        Returns:
            Number of programs in the database.
        """
        row = self._fetch_one("SELECT COUNT(*) as cnt FROM programs")
        assert row is not None
        return int(row["cnt"])
