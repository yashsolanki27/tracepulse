"""SLA management: deadline computation on creation + periodic monitoring job."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import Ticket

logger = logging.getLogger("tracepulse.sla")

# Hours allowed per triaged priority; anything else (including null triage) -> default.
SLA_HOURS = {"critical": 4, "high": 8, "medium": 24, "low": 72}
DEFAULT_SLA_HOURS = 24
WARNING_FRACTION = 0.8  # flag 'warning' once 80% of the SLA window has elapsed

ACTIVE_STATUSES = ("open", "in_progress")
# Escalation order; never downgrade a ticket's sla_status.
_SEVERITY_ORDER = {None: 0, "warning": 1, "breached": 2}


def compute_deadline(created_at: datetime, priority: str | None) -> datetime:
    """SLA deadline from triaged priority: critical=4h, high=8h, medium=24h, low=72h; null -> 24h."""
    hours = SLA_HOURS.get(priority or "", DEFAULT_SLA_HOURS)
    return created_at + timedelta(hours=hours)


def check_slas() -> None:
    """Scheduled job: flag active tickets nearing (warning) or past (breached) their deadline.

    Wrapped in try/except so one bad run can never kill the scheduler or the app.
    """
    try:
        _check_slas_inner()
    except Exception:
        logger.exception("SLA check job failed; scheduler will retry on next interval")


def _check_slas_inner() -> None:
    from database import SessionLocal
    from sqlalchemy import or_

    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        tickets = (
            session.query(Ticket)
            .filter(Ticket.status.in_(ACTIVE_STATUSES))
            .filter(Ticket.target_resolution_time.isnot(None))
            .filter(or_(Ticket.sla_status.is_(None), Ticket.sla_status != "breached"))
            .all()
        )
        for ticket in tickets:
            if now >= ticket.target_resolution_time:
                new_status = "breached"
            else:
                window = (ticket.target_resolution_time - ticket.created_at).total_seconds()
                if window <= 0:
                    continue
                elapsed = (now - ticket.created_at).total_seconds()
                new_status = "warning" if elapsed >= WARNING_FRACTION * window else None
            if _SEVERITY_ORDER.get(new_status, 0) <= _SEVERITY_ORDER.get(ticket.sla_status, 0):
                continue
            logger.info(
                "SLA transition ticket_id=%d %s -> %s (target=%s, now=%s)",
                ticket.id, ticket.sla_status or "null", new_status,
                ticket.target_resolution_time.isoformat(), now.isoformat(),
            )
            ticket.sla_status = new_status
        session.commit()
    finally:
        session.close()