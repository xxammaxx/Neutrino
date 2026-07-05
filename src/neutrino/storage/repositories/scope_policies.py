"""ScopePolicyRepository: CRUD operations for parsed scope policies.

ScopePolicies represent the structured output of the policy parser,
linked to a Program via ``program_id``.
"""

from __future__ import annotations

import sqlite3

from neutrino.models.entities import ScopePolicy, ScopePolicyCreate, ScopePolicyUpdate
from neutrino.storage.exceptions import EntityNotFound, ForeignKeyViolation
from neutrino.storage.repositories.base import BaseRepository

_LIST_ORDER = "created_at ASC, id ASC"


class ScopePolicyRepository(BaseRepository):
    """CRUD repository for the ``scope_policies`` table."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: ScopePolicyCreate) -> ScopePolicy:
        """Insert a new scope policy.

        Args:
            data: ScopePolicy creation input.

        Returns:
            The created ScopePolicy entity.

        Raises:
            ForeignKeyViolation: If ``program_id`` references a nonexistent program.
        """
        now = self._now_iso()
        sql = (
            "INSERT INTO scope_policies (id, program_id, source_url, raw_text, "
            "parsed_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            data.id,
            data.program_id,
            data.source_url,
            data.raw_text,
            data.parsed_json,
            now,
            now,
        )
        try:
            self._execute_write(sql, params)
        except sqlite3.IntegrityError as e:
            raise ForeignKeyViolation("scope_policy", "program_id", str(e)) from e
        return self.get(data.id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> ScopePolicy | None:
        """Get a scope policy by its UUID."""
        row = self._fetch_one("SELECT * FROM scope_policies WHERE id = ?", (entity_id,))
        if row is None:
            return None
        return ScopePolicy(**row)

    def list_all(self) -> list[ScopePolicy]:
        """List all scope policies ordered by ``created_at ASC, id ASC``."""
        rows = self._fetch_all(f"SELECT * FROM scope_policies ORDER BY {_LIST_ORDER}")
        return [ScopePolicy(**r) for r in rows]

    def list_by_program(self, program_id: str) -> list[ScopePolicy]:
        """List scope policies for a specific program.

        Args:
            program_id: Program UUID.

        Returns:
            List of ScopePolicy entities (empty if none found).
        """
        rows = self._fetch_all(
            f"SELECT * FROM scope_policies WHERE program_id = ? ORDER BY {_LIST_ORDER}",
            (program_id,),
        )
        return [ScopePolicy(**r) for r in rows]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, entity_id: str, data: ScopePolicyUpdate) -> ScopePolicy:
        """Update an existing scope policy. Only non-None fields are updated.

        Raises:
            EntityNotFound: If the scope policy does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("ScopePolicy", entity_id)

        fields = data.model_dump(exclude_none=True)
        if not fields:
            return existing

        set_clauses = [f"{k} = ?" for k in fields]
        values = list(fields.values())
        set_clauses.append("updated_at = ?")
        values.append(self._now_iso())
        values.append(entity_id)

        sql = f"UPDATE scope_policies SET {', '.join(set_clauses)} WHERE id = ?"
        self._execute_write(sql, tuple(values))
        return self.get(entity_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, entity_id: str) -> bool:
        """Delete a scope policy by its UUID.

        Raises:
            EntityNotFound: If the scope policy does not exist.
        """
        existing = self.get(entity_id)
        if existing is None:
            raise EntityNotFound("ScopePolicy", entity_id)
        self._execute_write("DELETE FROM scope_policies WHERE id = ?", (entity_id,))
        return True

    def count(self) -> int:
        """Return the total number of scope policies."""
        row = self._fetch_one("SELECT COUNT(*) as cnt FROM scope_policies")
        assert row is not None
        return int(row["cnt"])
