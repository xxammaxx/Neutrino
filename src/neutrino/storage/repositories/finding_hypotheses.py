"""FindingHypothesisRepository: CRUD operations for security finding hypotheses.

FindingHypotheses represent potential security issues discovered during
research, linked to a ResearchRun via ``research_run_id``.
"""

from __future__ import annotations

import sqlite3

from neutrino.models.entities import (
    FindingHypothesis,
    FindingHypothesisCreate,
    FindingHypothesisUpdate,
)
from neutrino.storage.exceptions import EntityNotFound, ForeignKeyViolation
from neutrino.storage.repositories.base import BaseRepository

_LIST_ORDER = "created_at ASC, id ASC"


class FindingHypothesisRepository(BaseRepository):
    """CRUD repository for the ``finding_hypotheses`` table."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: FindingHypothesisCreate) -> FindingHypothesis:
        """Insert a new finding hypothesis.

        Raises:
            ForeignKeyViolation: If ``research_run_id`` references a nonexistent research run.
        """
        now = self._now_iso()
        sql = (
            "INSERT INTO finding_hypotheses (id, research_run_id, title, status, "
            "risk_level, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        params = (data.id, data.research_run_id, data.title, data.status, data.risk_level, now, now)
        try:
            self._execute_write(sql, params)
        except sqlite3.IntegrityError as e:
            raise ForeignKeyViolation("finding_hypothesis", "research_run_id", str(e)) from e
        return self.get(data.id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> FindingHypothesis | None:
        """Get a finding hypothesis by its UUID."""
        row = self._fetch_one("SELECT * FROM finding_hypotheses WHERE id = ?", (entity_id,))
        if row is None:
            return None
        return FindingHypothesis(**row)

    def list_all(self) -> list[FindingHypothesis]:
        """List all finding hypotheses ordered by ``created_at ASC, id ASC``."""
        rows = self._fetch_all(f"SELECT * FROM finding_hypotheses ORDER BY {_LIST_ORDER}")
        return [FindingHypothesis(**r) for r in rows]

    def list_by_research_run(self, research_run_id: str) -> list[FindingHypothesis]:
        """List finding hypotheses for a specific research run."""
        rows = self._fetch_all(
            f"SELECT * FROM finding_hypotheses WHERE research_run_id = ? ORDER BY {_LIST_ORDER}",
            (research_run_id,),
        )
        return [FindingHypothesis(**r) for r in rows]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, entity_id: str, data: FindingHypothesisUpdate) -> FindingHypothesis:
        """Update an existing finding hypothesis.

        Raises:
            EntityNotFound: If the finding hypothesis does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("FindingHypothesis", entity_id)

        fields = data.model_dump(exclude_none=True)
        if not fields:
            return existing

        set_clauses = [f"{k} = ?" for k in fields]
        values = list(fields.values())
        set_clauses.append("updated_at = ?")
        values.append(self._now_iso())
        values.append(entity_id)

        sql = f"UPDATE finding_hypotheses SET {', '.join(set_clauses)} WHERE id = ?"
        self._execute_write(sql, tuple(values))
        return self.get(entity_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, entity_id: str) -> bool:
        """Delete a finding hypothesis by its UUID.

        Raises:
            EntityNotFound: If the finding hypothesis does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("FindingHypothesis", entity_id)
        self._execute_write("DELETE FROM finding_hypotheses WHERE id = ?", (entity_id,))
        return True

    def count(self) -> int:
        """Return the total number of finding hypotheses."""
        row = self._fetch_one("SELECT COUNT(*) as cnt FROM finding_hypotheses")
        assert row is not None
        return int(row["cnt"])
