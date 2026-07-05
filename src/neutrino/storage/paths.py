"""Database path resolution for Neutrino Storage.

Determines the SQLite database path using configurable sources:

1. ``NEUTRINO_DB_PATH`` environment variable (highest priority)
2. Default: ``~/.neutrino/db/neutrino.db``

Tests use ``get_temp_db_path()`` to create isolated temporary databases
that never touch the production home directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import mkdtemp


def get_db_path() -> str:
    """Return the absolute path to the Neutrino SQLite database.

    Priority:
        1. ``NEUTRINO_DB_PATH`` environment variable
        2. Default: ``~/.neutrino/db/neutrino.db``

    Returns:
        Absolute path as string. Does NOT create directories or the file.
    """
    env_path = os.environ.get("NEUTRINO_DB_PATH")
    if env_path:
        return str(Path(env_path).expanduser().resolve())

    default = Path.home() / ".neutrino" / "db" / "neutrino.db"
    return str(default.resolve())


def get_temp_db_path(prefix: str = "neutrino_test_") -> str:
    """Create a temporary directory and return a database path within it.

    The temporary directory is safe for test SQLite databases and will
    never write to ``~/.neutrino/``.

    Args:
        prefix: Prefix for the temporary directory name.

    Returns:
        Absolute path to a database file inside a new temp directory.
    """
    tmpdir = mkdtemp(prefix=prefix)
    return str(Path(tmpdir) / "neutrino.db")
