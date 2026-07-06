"""Budget status change persistence.

``apply_budget_decision()`` takes a BudgetDecision, ResearchRun ID,
and optional repositories to persist the status change.

Design principles:
    - Status changes are recorded in the ResearchRun (via ResearchRunRepository).
    - Each decision is also logged as an AuditEvent (via AuditEventRepository).
    - Both repositories are optional — the function works without persistence.
    - EXHAUSTED is final: once a ResearchRun's status is set to "exhausted",
      it stays that way. No automatic reset.
    - Errors are logged but do NOT raise (to avoid disrupting the caller).
      Error decisions are still recorded as audit events.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from neutrino.budget.models import BudgetDecision, BudgetStatus

if TYPE_CHECKING:
    from neutrino.storage.repositories.audit_events import AuditEventRepository
    from neutrino.storage.repositories.research_runs import ResearchRunRepository


def apply_budget_decision(
    decision: BudgetDecision,
    research_run_id: str,
    *,
    run_repo: ResearchRunRepository | None = None,
    audit_repo: AuditEventRepository | None = None,
    actor: str = "neutrino.budget",
) -> bool:
    """Apply a budget decision to a ResearchRun and optionally log it.

    Steps:
        1. If ``run_repo`` is provided and the decision status is EXHAUSTED
           or ERROR: update the ResearchRun's ``status`` field.
        2. If ``audit_repo`` is provided: log the decision as an immutable
           AuditEvent.

    Args:
        decision: The budget evaluation result.
        research_run_id: UUID of the affected ResearchRun.
        run_repo: Optional ResearchRunRepository for status updates.
        audit_repo: Optional AuditEventRepository for audit logging.
        actor: Actor name for audit events (default: ``"neutrino.budget"``).

    Returns:
        True if the decision was applied (run status updated or audit logged).

    Note:
        Status update is best-effort. If the ResearchRun doesn't exist
        or the update fails, the error is logged as an AuditEvent but
        NOT re-raised.
    """
    applied = _maybe_update_run_status(decision, research_run_id, run_repo)
    logged = _maybe_log_audit_event(decision, research_run_id, audit_repo, actor)
    return applied or logged


def _maybe_update_run_status(
    decision: BudgetDecision,
    research_run_id: str,
    run_repo: ResearchRunRepository | None,
) -> bool:
    """Update ResearchRun status if repository is available and EXHAUSTED/ERROR."""
    if run_repo is None:
        return False
    if decision.status not in (BudgetStatus.EXHAUSTED, BudgetStatus.ERROR):
        return False

    try:
        from neutrino.models.entities import ResearchRunUpdate

        now = datetime.now(UTC).isoformat()
        new_status = decision.status.value  # "exhausted" or "error"

        update = ResearchRunUpdate(status=new_status)
        if decision.status == BudgetStatus.EXHAUSTED:
            update.finished_at = now
        run_repo.update(research_run_id, update)
        return True
    except Exception:
        # Don't crash the caller — the audit log will capture the attempt.
        return False


def _maybe_log_audit_event(
    decision: BudgetDecision,
    research_run_id: str,
    audit_repo: AuditEventRepository | None,
    actor: str,
) -> bool:
    """Log the decision as an AuditEvent if repository is available."""
    if audit_repo is None:
        return False

    try:
        from neutrino.models.entities import AuditEventCreate

        event_json = json.dumps(
            decision.model_dump(),
            sort_keys=True,
        )
        event = AuditEventCreate(
            id=str(uuid.uuid4()),
            actor=actor,
            action="budget_evaluated",
            target=f"research_run:{research_run_id}",
            decision=decision.status.value,
            event_json=event_json,
            timestamp=decision.timestamp,
        )
        audit_repo.append(event)
        return True
    except Exception:
        return False
