"""Base repository providing shared SQLite helpers for all entity repositories.

All repositories use this base to access their SQLite database
with foreign key enforcement, deterministic row-to-dict conversion,
and standard timestamp generation.

Design:
    - Every operation opens a new connection via ``get_connection``.
    - Reads return ``dict`` or ``None``. Writes raise on failure.
    - No ORM, no lazy loading, no connection pooling.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from neutrino.storage.sqlite import get_connection

if TYPE_CHECKING:
    import sqlite3


class BaseRepository:
    """Shared base for all Neutrino entity repositories.

    Provides:
        - ``db_path`` storage, injected at construction time.
        - ``_now_iso()`` for UTC ISO 8601 timestamps.
        - ``_row_to_dict()`` for deterministic sqlite3.Row → dict conversion.
        - ``_fetch_one()`` and ``_fetch_all()`` helpers.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the repository with a database path.

        Args:
            db_path: Absolute path to the SQLite database file.
        """
        self.db_path = db_path

    @staticmethod
    def _now_iso() -> str:
        """Return the current UTC timestamp as an ISO 8601 string."""
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a ``sqlite3.Row`` to a plain ``dict``.

        Args:
            row: A row returned from a SQLite query.

        Returns:
            Dictionary with column names as keys.
        """
        return dict(row)

    def _fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Execute a SELECT query and return the first row as a dict, or None.

        Args:
            sql: SQL SELECT statement.
            params: Query parameters.

        Returns:
            Row as a dict, or None if no result.
        """
        with get_connection(self.db_path) as conn:
            row = conn.execute(sql, params).fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)

    def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a SELECT query and return all rows as a list of dicts.

        Args:
            sql: SQL SELECT statement.
            params: Query parameters.

        Returns:
            List of row dicts (empty list if no results).
        """
        with get_connection(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def _execute_write(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Execute an INSERT, UPDATE, or DELETE statement.

        Args:
            sql: SQL write statement.
            params: Query parameters.

        Raises:
            sqlite3.IntegrityError: On foreign key violations.
        """
        with get_connection(self.db_path) as conn:
            conn.execute(sql, params)
