"""Repository-layer exceptions for Neutrino Storage.

These exceptions provide clear, typed error handling for CRUD operations.
All exceptions inherit from ``RepositoryError`` for easy catching.

Design:
    - ``get(id)`` on missing entity returns ``None`` (not an exception).
    - ``update(id, ...)`` and ``delete(id)`` on missing entity raise ``EntityNotFound``.
    - FK violations raise ``ForeignKeyViolation`` (subclass of ``RepositoryError``).
    - ``AuditEventRepository`` forbids ``update``/``delete`` via ``AuditEventImmutable``.
"""

from __future__ import annotations


class RepositoryError(Exception):
    """Base exception for all repository-layer errors."""


class EntityNotFound(RepositoryError):  # noqa: N818
    """Raised when an entity is not found by its primary key.

    Example:
        >>> repo.update("nonexistent-id", name="New")  # raises EntityNotFound
    """

    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with id '{entity_id}' not found")


class ForeignKeyViolation(RepositoryError):  # noqa: N818
    """Raised when a foreign key constraint is violated.

    Wraps ``sqlite3.IntegrityError`` and provides the entity type and
    referenced field for clearer error messages.

    Example:
        >>> repo.create(program_id="nonexistent")  # raises ForeignKeyViolation
    """

    def __init__(self, entity_type: str, fk_field: str, detail: str = "") -> None:
        self.entity_type = entity_type
        self.fk_field = fk_field
        msg = f"FK violation on {entity_type}.{fk_field}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class AuditEventImmutable(RepositoryError):  # noqa: N818
    """Raised when attempting to update or delete an AuditEvent.

    AuditEvents are append-only by design. Updates and deletes are
    always forbidden.
    """

    def __init__(self, action: str, entity_id: str = "") -> None:
        self.action = action
        self.entity_id = entity_id
        msg = f"{action} is not allowed on AuditEvent"
        if entity_id:
            msg += f" (id={entity_id})"
        super().__init__(msg)
