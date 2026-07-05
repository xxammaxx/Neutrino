"""Append-only JSONL AuditLog writer for Neutrino Core.

This module implements ``AuditLogWriter`` — a local, append-only
JSONL writer that records security decisions, agent actions, and
workflow steps as immutable JSON lines in ``~/.neutrino/audit/``.

Design invariants:
    - Append-only: ``open(path, "a")`` only. No write, no truncate.
    - Single JSON object per line. No trailing commas or separators.
    - Directory auto-created on first write.
    - No rotation, no compression, no deletion, no rewriting.
    - No network I/O, no remote shipping, no cloud logs.
    - Tests override ``audit_dir``; never write to real home.

Path resolution (priority order):
    1. Explicit ``audit_dir`` constructor argument.
    2. ``NEUTRINO_AUDIT_DIR`` environment variable.
    3. Default: ``~/.neutrino/audit/``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from neutrino.audit.models import AuditLogEvent

_DEFAULT_FILE_NAME = "audit.jsonl"


def _resolve_audit_dir(audit_dir: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the audit directory path.

    Priority:
        1. Explicit ``audit_dir`` argument.
        2. ``NEUTRINO_AUDIT_DIR`` environment variable.
        3. Default: ``~/.neutrino/audit/``.

    Args:
        audit_dir: Explicit path override (highest priority).

    Returns:
        Resolved absolute ``Path`` to the audit directory.

    Raises:
        ValueError: If the resolved path looks like a remote/network
            path (starts with ``//`` or ``\\\\``).
    """
    # Safety: reject network/UNC paths BEFORE resolution
    raw: str
    if audit_dir is not None:
        raw = str(audit_dir)
        path = Path(audit_dir).expanduser().resolve()
    else:
        env_dir = os.environ.get("NEUTRINO_AUDIT_DIR")
        if env_dir:
            raw = env_dir
            path = Path(env_dir).expanduser().resolve()
        else:
            return Path.home() / ".neutrino" / "audit"

    # Check raw input for UNC-style paths (cross-platform):
    #   - Windows: \\server\share
    #   - Linux/Unix: // followed by non-/ character (POSIX network convention)
    resolved_str = str(path)
    if (
        raw.startswith("\\\\")
        or (raw.startswith("//") and len(raw) > 2 and raw[2] != "/")
        or resolved_str.startswith("\\\\")
        or (resolved_str.startswith("//") and len(resolved_str) > 2 and resolved_str[2] != "/")
    ):
        raise ValueError(f"Network/UNC paths are not allowed: {raw!r}")

    return path


class AuditLogWriter:
    """Append-only JSONL AuditLog writer.

    Writes ``AuditLogEvent`` instances as single JSON lines to
    ``{audit_dir}/audit.jsonl``. Never overwrites, truncates,
    rotates, or deletes existing entries.

    Usage::

        writer = AuditLogWriter(audit_dir=tmp_path)
        writer.append(event)

    Args:
        audit_dir: Explicit audit directory (overrides env var and
            default). Use in tests with a ``tmp_path``.
        file_name: JSONL file name (default: ``audit.jsonl``).
    """

    def __init__(
        self,
        audit_dir: str | os.PathLike[str] | None = None,
        file_name: str = _DEFAULT_FILE_NAME,
    ) -> None:
        self._audit_dir: Path = _resolve_audit_dir(audit_dir)
        self._file_name: str = file_name

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def audit_dir(self) -> Path:
        """The resolved audit directory (absolute path)."""
        return self._audit_dir

    @property
    def file_path(self) -> Path:
        """Full path to the JSONL audit file."""
        return self._audit_dir / self._file_name

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, event: AuditLogEvent) -> AuditLogEvent:
        """Append a single audit event as a JSON line.

        Creates the audit directory (and parent directories) if they
        do not exist. Opens the JSONL file in append mode and writes
        exactly one ``\\n``-terminated JSON line.

        Args:
            event: The ``AuditLogEvent`` to append.

        Returns:
            The same ``AuditLogEvent`` that was written.

        Raises:
            ValidationError: If the event has missing or empty
                required fields (caught by Pydantic on construction).
            OSError: If the directory cannot be created or the file
                cannot be opened/ written.
        """
        os.makedirs(str(self._audit_dir), exist_ok=True)

        line = event.model_dump_json(exclude_none=True) + "\n"
        with open(str(self.file_path), "a", encoding="utf-8") as f:
            f.write(line)

        return event

    def append_raw(self, event_dict: dict[str, Any]) -> AuditLogEvent:
        """Append an audit event from a raw dictionary.

        Convenience wrapper that constructs an ``AuditLogEvent`` from
        a dictionary before passing it to ``append()``.

        Args:
            event_dict: Dictionary with audit event fields.

        Returns:
            The constructed and appended ``AuditLogEvent``.

        Raises:
            ValidationError: If required fields are missing or empty.
        """
        event = AuditLogEvent(**event_dict)
        return self.append(event)

    # ------------------------------------------------------------------
    # Read (convenience, not primary use case)
    # ------------------------------------------------------------------

    def read_all(self) -> list[AuditLogEvent]:
        """Read all audit events from the JSONL file.

        Returns:
            List of ``AuditLogEvent`` instances, or empty list if the
            file does not exist.

        Note:
            This is a convenience read method for testing and
            inspection. The primary interface is write-only.
        """
        if not self.file_path.is_file():
            return []

        events: list[AuditLogEvent] = []
        with open(str(self.file_path), encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    events.append(AuditLogEvent(**json.loads(stripped)))
        return events

    def count(self) -> int:
        """Count the number of events in the JSONL file.

        Returns:
            Number of non-empty lines, or 0 if the file does not exist.
        """
        if not self.file_path.is_file():
            return 0

        count = 0
        with open(str(self.file_path), encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
