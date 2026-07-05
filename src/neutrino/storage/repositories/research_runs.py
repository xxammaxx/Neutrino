"""ResearchRunRepository: CRUD operations for research runs.

ResearchRuns represent an automated or manual research session,
linked to a Program via ``program_id``.
"""

from __future__ import annotations

import sqlite3

from neutrino.models.entities import ResearchRun, ResearchRunCreate, ResearchRunUpdate
from neutrino.storage.exceptions import EntityNotFound, ForeignKeyViolation
from neutrino.storage.repositories.base import BaseRepository

_LIST_ORDER = "created_at ASC, id ASC"


class ResearchRunRepository(BaseRepository):
    """CRUD repository for the ``research_runs`` table."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: ResearchRunCreate) -> ResearchRun:
        """Insert a new research run.

        Raises:
            ForeignKeyViolation: If ``program_id`` references a nonexistent program.
        """
        now = self._now_iso()
        sql = (
            "INSERT INTO research_runs (id, program_id, status, started_at, "
            "finished_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            data.id,
            data.program_id,
            data.status,
            data.started_at,
            data.finished_at,
            now,
            now,
        )
        try:
            self._execute_write(sql, params)
        except sqlite3.IntegrityError as e:
            raise ForeignKeyViolation("research_run", "program_id", str(e)) from e
        return self.get(data.id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> ResearchRun | None:
        """Get a research run by its UUID."""
        row = self._fetch_one("SELECT * FROM research_runs WHERE id = ?", (entity_id,))
        if row is None:
            return None
        return ResearchRun(**row)

    def list_all(self) -> list[ResearchRun]:
        """List all research runs ordered by ``created_at ASC, id ASC``."""
        rows = self._fetch_all(f"SELECT * FROM research_runs ORDER BY {_LIST_ORDER}")
        return [ResearchRun(**r) for r in rows]

    def list_by_program(self, program_id: str) -> list[ResearchRun]:
        """List research runs for a specific program."""
        rows = self._fetch_all(
            f"SELECT * FROM research_runs WHERE program_id = ? ORDER BY {_LIST_ORDER}",
            (program_id,),
        )
        return [ResearchRun(**r) for r in rows]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, entity_id: str, data: ResearchRunUpdate) -> ResearchRun:
        """Update an existing research run. Only non-None fields are updated.

        Raises:
            EntityNotFound: If the research run does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("ResearchRun", entity_id)

        fields = data.model_dump(exclude_none=True)
        if not fields:
            return existing

        set_clauses = [f"{k} = ?" for k in fields]
        values = list(fields.values())
        set_clauses.append("updated_at = ?")
        values.append(self._now_iso())
        values.append(entity_id)

        sql = f"UPDATE research_runs SET {', '.join(set_clauses)} WHERE id = ?"
        self._execute_write(sql, tuple(values))
        return self.get(entity_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, entity_id: str) -> bool:
        """Delete a research run by its UUID.

        Raises:
            EntityNotFound: If the research run does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("ResearchRun", entity_id)
        self._execute_write("DELETE FROM research_runs WHERE id = ?", (entity_id,))
        return True

    def count(self) -> int:
        """Return the total number of research runs."""
        row = self._fetch_one("SELECT COUNT(*) as cnt FROM research_runs")
        assert row is not None
        return int(row["cnt"])
