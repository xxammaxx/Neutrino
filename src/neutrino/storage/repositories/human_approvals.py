"""HumanApprovalRepository: CRUD operations for human approval decisions.

HumanApprovals record explicit human decisions for research actions,
linked to a ResearchRun via ``research_run_id``.

Note: This is only the data access layer. The actual Human-Approval
Workflow is not yet implemented.
"""

from __future__ import annotations

import sqlite3

from neutrino.models.entities import HumanApproval, HumanApprovalCreate, HumanApprovalUpdate
from neutrino.storage.exceptions import EntityNotFound, ForeignKeyViolation
from neutrino.storage.repositories.base import BaseRepository

_LIST_ORDER = "created_at ASC, id ASC"


class HumanApprovalRepository(BaseRepository):
    """CRUD repository for the ``human_approvals`` table."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: HumanApprovalCreate) -> HumanApproval:
        """Insert a new human approval record.

        Raises:
            ForeignKeyViolation: If ``research_run_id`` references a nonexistent research run.
        """
        now = self._now_iso()
        sql = (
            "INSERT INTO human_approvals (id, research_run_id, actor, decision, "
            "reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        params = (data.id, data.research_run_id, data.actor, data.decision, data.reason, now, now)
        try:
            self._execute_write(sql, params)
        except sqlite3.IntegrityError as e:
            raise ForeignKeyViolation("human_approval", "research_run_id", str(e)) from e
        return self.get(data.id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> HumanApproval | None:
        """Get a human approval by its UUID."""
        row = self._fetch_one("SELECT * FROM human_approvals WHERE id = ?", (entity_id,))
        if row is None:
            return None
        return HumanApproval(**row)

    def list_all(self) -> list[HumanApproval]:
        """List all human approvals ordered by ``created_at ASC, id ASC``."""
        rows = self._fetch_all(f"SELECT * FROM human_approvals ORDER BY {_LIST_ORDER}")
        return [HumanApproval(**r) for r in rows]

    def list_by_research_run(self, research_run_id: str) -> list[HumanApproval]:
        """List human approvals for a specific research run."""
        rows = self._fetch_all(
            f"SELECT * FROM human_approvals WHERE research_run_id = ? ORDER BY {_LIST_ORDER}",
            (research_run_id,),
        )
        return [HumanApproval(**r) for r in rows]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, entity_id: str, data: HumanApprovalUpdate) -> HumanApproval:
        """Update an existing human approval.

        Raises:
            EntityNotFound: If the human approval does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("HumanApproval", entity_id)

        fields = data.model_dump(exclude_none=True)
        if not fields:
            return existing

        set_clauses = [f"{k} = ?" for k in fields]
        values = list(fields.values())
        set_clauses.append("updated_at = ?")
        values.append(self._now_iso())
        values.append(entity_id)

        sql = f"UPDATE human_approvals SET {', '.join(set_clauses)} WHERE id = ?"
        self._execute_write(sql, tuple(values))
        return self.get(entity_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, entity_id: str) -> bool:
        """Delete a human approval by its UUID.

        Raises:
            EntityNotFound: If the human approval does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("HumanApproval", entity_id)
        self._execute_write("DELETE FROM human_approvals WHERE id = ?", (entity_id,))
        return True

    def count(self) -> int:
        """Return the total number of human approvals."""
        row = self._fetch_one("SELECT COUNT(*) as cnt FROM human_approvals")
        assert row is not None
        return int(row["cnt"])
