"""Validation step handlers — Issue #19.

Each handler is a deterministic, local-only function that processes
a specific ``ValidationStepType``. Handlers do NOT perform network I/O,
shell commands, DNS resolution, or any unsafe operation.

Safety invariants:
    - No external HTTP requests (httpx, requests, urllib).
    - No socket connections (socket, ssl).
    - No DNS resolution (socket.getaddrinfo, dns.resolver).
    - No subprocess, os.system, os.popen, eval, exec, compile.
    - No file writes — only reads from allowed directories.
    - Default-deny for unknown step types.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from neutrino.validation_executor.models import StepExecutionStatus
from neutrino.validation_recipe import ValidationStep, ValidationStepType

# ------------------------------------------------------------------
# Abstract Base
# ------------------------------------------------------------------


class StepHandler(ABC):
    """Abstract base class for deterministic, local-only step handlers.

    Subclasses MUST NOT:
        - open network sockets
        - perform HTTP requests
        - resolve DNS names
        - run shell commands or subprocesses
        - access file paths outside ``allowed_fixture_dir``
        - call ``eval``, ``exec``, ``compile``, or ``os.system``
    """

    @abstractmethod
    def execute(
        self,
        step: ValidationStep,
        *,
        allowed_fixture_dir: str | None,
        evidence_context: dict[str, Any],
    ) -> tuple[StepExecutionStatus, dict[str, Any], str | None]:
        """Execute (or plan) a single validation step.

        Args:
            step: The validation step to execute.
            allowed_fixture_dir: Base directory for fixture reads (may be None).
            evidence_context: In-memory evidence for evidence_check steps.

        Returns:
            A tuple of:
                - ``StepExecutionStatus``: the outcome
                - ``dict[str, Any]``: collected evidence
                - ``str | None``: error message (None on success)
        """


# ------------------------------------------------------------------
# Concrete Handlers
# ------------------------------------------------------------------


class ManualObservationHandler(StepHandler):
    """Handler for ``manual_observation`` steps.

    Manual observations are NEVER auto-executed. This handler always
    returns ``PLANNED``, recording the expected evidence and description
    for later human review.
    """

    def execute(
        self,
        step: ValidationStep,
        *,
        allowed_fixture_dir: str | None,
        evidence_context: dict[str, Any],
    ) -> tuple[StepExecutionStatus, dict[str, Any], str | None]:
        return (
            StepExecutionStatus.PLANNED,
            {
                "mode": "manual_only",
                "description": step.description,
                "expected_evidence": step.expected_evidence,
            },
            None,
        )


class EvidenceCheckHandler(StepHandler):
    """Handler for ``evidence_check`` steps.

    Checks that all expected evidence IDs are present in the local
    in-memory ``evidence_context`` dict. This is a purely local lookup;
    no file I/O, no network access.

    Evidence matching is exact key lookup. No scoring, no fuzzy match,
    no oracle judgment — that belongs to #20.
    """

    def execute(
        self,
        step: ValidationStep,
        *,
        allowed_fixture_dir: str | None,
        evidence_context: dict[str, Any],
    ) -> tuple[StepExecutionStatus, dict[str, Any], str | None]:
        missing = [
            evidence_id
            for evidence_id in step.expected_evidence
            if evidence_id not in evidence_context
        ]

        if missing:
            return (
                StepExecutionStatus.ERROR,
                {"missing_evidence": missing},
                "Required evidence not present in local evidence_context",
            )

        return (
            StepExecutionStatus.EXECUTED,
            {
                "matched_evidence": {
                    evidence_id: evidence_context[evidence_id]
                    for evidence_id in step.expected_evidence
                }
            },
            None,
        )


class LocalFixtureCheckHandler(StepHandler):
    """Handler for ``local_fixture_check`` steps.

    Reads a deterministic local JSON fixture file by ``fixture_id``.
    The recipe provides the fixture ID via ``parameters``:

        ``parameters = {"fixture_id": "example-fixture"}``

    Resolution:
        ``allowed_fixture_dir / f"{fixture_id}.json"``

    Safety:
        - ``allowed_fixture_dir`` is mandatory.
        - The resolved path MUST stay under ``allowed_fixture_dir``.
        - Path traversal (``..``) and path separators in ``fixture_id``
          are blocked.
        - Only regular ``.json`` files are read.
        - Never writes, never creates directories.
    """

    def execute(
        self,
        step: ValidationStep,
        *,
        allowed_fixture_dir: str | None,
        evidence_context: dict[str, Any],
    ) -> tuple[StepExecutionStatus, dict[str, Any], str | None]:
        if allowed_fixture_dir is None:
            return (
                StepExecutionStatus.BLOCKED,
                {},
                "allowed_fixture_dir is required for local_fixture_check",
            )

        parameters = step.parameters or {}
        fixture_id = parameters.get("fixture_id")

        if not isinstance(fixture_id, str) or not fixture_id.strip():
            return (
                StepExecutionStatus.BLOCKED,
                {},
                "local_fixture_check requires non-empty 'fixture_id' parameter",
            )

        # Block path traversal and separators
        if "/" in fixture_id or "\\" in fixture_id or ".." in fixture_id:
            return (
                StepExecutionStatus.BLOCKED,
                {},
                "fixture_id must not contain path separators or traversal",
            )

        base = Path(allowed_fixture_dir).expanduser().resolve()
        fixture_path = (base / f"{fixture_id}.json").resolve()

        # Verify the resolved path is still under the allowed directory
        base_str = str(base)
        fixture_str = str(fixture_path)
        if not (fixture_str == base_str or fixture_str.startswith(base_str + "/")):
            return (
                StepExecutionStatus.BLOCKED,
                {},
                "fixture path escapes allowed_fixture_dir",
            )

        if not fixture_path.is_file():
            return (
                StepExecutionStatus.ERROR,
                {"fixture_id": fixture_id},
                f"fixture file not found: {fixture_id}",
            )

        # Read JSON fixture
        try:
            with fixture_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            return (
                StepExecutionStatus.ERROR,
                {"fixture_id": fixture_id},
                f"Failed to read fixture: {exc}",
            )

        return (
            StepExecutionStatus.EXECUTED,
            {
                "fixture_id": fixture_id,
                "fixture_data": data,
            },
            None,
        )


class HttpCheckHandler(StepHandler):
    """Handler for ``http_check`` steps.

    **Issue #19 behavior: PLANNING ONLY.**

    This handler NEVER makes HTTP requests. It records the planned
    action (target, parameters) for later manual or future automated
    execution. Actual HTTP execution requires a separate gated issue
    with additional safety review.

    No ``httpx``, ``requests``, ``urllib``, or ``socket`` imports.
    """

    def execute(
        self,
        step: ValidationStep,
        *,
        allowed_fixture_dir: str | None,
        evidence_context: dict[str, Any],
    ) -> tuple[StepExecutionStatus, dict[str, Any], str | None]:
        return (
            StepExecutionStatus.PLANNED,
            {
                "planned_action": "http_check",
                "target": step.target,
                "parameters": step.parameters or {},
                "note": "HTTP execution disabled in Issue #19 — planning only",
            },
            None,
        )


class TcpCheckHandler(StepHandler):
    """Handler for ``tcp_check`` steps.

    **Issue #19 behavior: PLANNING ONLY.**

    This handler NEVER opens sockets or makes TCP connections. It
    records the planned action (target, parameters) for later manual
    or future automated execution. Actual TCP execution requires a
    separate gated issue with additional safety review.

    No ``socket``, ``ssl``, or ``asyncio`` imports.
    """

    def execute(
        self,
        step: ValidationStep,
        *,
        allowed_fixture_dir: str | None,
        evidence_context: dict[str, Any],
    ) -> tuple[StepExecutionStatus, dict[str, Any], str | None]:
        return (
            StepExecutionStatus.PLANNED,
            {
                "planned_action": "tcp_check",
                "target": step.target,
                "parameters": step.parameters or {},
                "note": "TCP execution disabled in Issue #19 — planning only",
            },
            None,
        )


# ------------------------------------------------------------------
# Handler Registry (Default-Deny)
# ------------------------------------------------------------------


_HANDLER_REGISTRY: dict[ValidationStepType, type[StepHandler]] = {
    ValidationStepType.MANUAL_OBSERVATION: ManualObservationHandler,
    ValidationStepType.EVIDENCE_CHECK: EvidenceCheckHandler,
    ValidationStepType.LOCAL_FIXTURE_CHECK: LocalFixtureCheckHandler,
    ValidationStepType.HTTP_CHECK: HttpCheckHandler,
    ValidationStepType.TCP_CHECK: TcpCheckHandler,
}


def get_handler(step_type: ValidationStepType) -> StepHandler:
    """Look up the handler for a given step type.

    Default-Deny: unknown step types raise ``ValueError``.
    The caller (executor) must catch this and BLOCK the step.

    Args:
        step_type: The ``ValidationStepType`` to look up.

    Returns:
        A new handler instance for the given step type.

    Raises:
        ValueError: If ``step_type`` is not in the allowlisted registry.
    """
    handler_cls = _HANDLER_REGISTRY.get(step_type)
    if handler_cls is None:
        raise ValueError(f"Unsupported validation step type: {step_type!r}")
    return handler_cls()
