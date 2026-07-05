"""Minimal SQLite connection management for Neutrino Storage.

Provides a context-manager-based connection helper that:
- Creates the database directory if it does not exist.
- Enables foreign key enforcement on every connection.
- Returns a ``sqlite3.Connection`` with ``row_factory = sqlite3.Row``.

No connection pooling, no ORM, no magic.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator


def ensure_db_directory(db_path: str) -> None:
    """Create the parent directory for the database file if it does not exist.

    Args:
        db_path: Absolute path to the SQLite database file.
    """
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Open a SQLite connection with foreign keys enabled.

    Creates the parent directory automatically. The connection is
    closed when the context manager exits.

    Args:
        db_path: Absolute path to the SQLite database file.

    Yields:
        A ``sqlite3.Connection`` with ``row_factory`` set to ``sqlite3.Row``
        and foreign key enforcement enabled.
    """
    ensure_db_directory(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
