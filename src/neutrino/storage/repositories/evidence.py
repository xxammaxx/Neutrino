"""EvidenceRepository: CRUD operations for security evidence.

Evidence represents proof (screenshots, logs, requests) collected for a
FindingHypothesis, linked via ``finding_hypothesis_id``.
"""

from __future__ import annotations

import sqlite3

from neutrino.models.entities import Evidence, EvidenceCreate, EvidenceUpdate
from neutrino.storage.exceptions import EntityNotFound, ForeignKeyViolation
from neutrino.storage.repositories.base import BaseRepository

_LIST_ORDER = "created_at ASC, id ASC"


class EvidenceRepository(BaseRepository):
    """CRUD repository for the ``evidence`` table."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: EvidenceCreate) -> Evidence:
        """Insert new evidence.

        Raises:
            ForeignKeyViolation: If ``finding_hypothesis_id`` references a nonexistent hypothesis.
        """
        now = self._now_iso()
        sql = (
            "INSERT INTO evidence (id, finding_hypothesis_id, kind, content_json, "
            "source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            data.id,
            data.finding_hypothesis_id,
            data.kind,
            data.content_json,
            data.source,
            now,
            now,
        )
        try:
            self._execute_write(sql, params)
        except sqlite3.IntegrityError as e:
            raise ForeignKeyViolation("evidence", "finding_hypothesis_id", str(e)) from e
        return self.get(data.id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> Evidence | None:
        """Get evidence by its UUID."""
        row = self._fetch_one("SELECT * FROM evidence WHERE id = ?", (entity_id,))
        if row is None:
            return None
        return Evidence(**row)

    def list_all(self) -> list[Evidence]:
        """List all evidence ordered by ``created_at ASC, id ASC``."""
        rows = self._fetch_all(f"SELECT * FROM evidence ORDER BY {_LIST_ORDER}")
        return [Evidence(**r) for r in rows]

    def list_by_finding(self, finding_hypothesis_id: str) -> list[Evidence]:
        """List evidence for a specific finding hypothesis."""
        rows = self._fetch_all(
            f"SELECT * FROM evidence WHERE finding_hypothesis_id = ? ORDER BY {_LIST_ORDER}",
            (finding_hypothesis_id,),
        )
        return [Evidence(**r) for r in rows]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, entity_id: str, data: EvidenceUpdate) -> Evidence:
        """Update existing evidence.

        Raises:
            EntityNotFound: If the evidence does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("Evidence", entity_id)

        fields = data.model_dump(exclude_none=True)
        if not fields:
            return existing

        set_clauses = [f"{k} = ?" for k in fields]
        values = list(fields.values())
        set_clauses.append("updated_at = ?")
        values.append(self._now_iso())
        values.append(entity_id)

        sql = f"UPDATE evidence SET {', '.join(set_clauses)} WHERE id = ?"
        self._execute_write(sql, tuple(values))
        return self.get(entity_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, entity_id: str) -> bool:
        """Delete evidence by its UUID.

        Raises:
            EntityNotFound: If the evidence does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("Evidence", entity_id)
        self._execute_write("DELETE FROM evidence WHERE id = ?", (entity_id,))
        return True

    def count(self) -> int:
        """Return the total number of evidence records."""
        row = self._fetch_one("SELECT COUNT(*) as cnt FROM evidence")
        assert row is not None
        return int(row["cnt"])
