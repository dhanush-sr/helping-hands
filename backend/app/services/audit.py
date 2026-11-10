"""The audit history (HH-33: HH-F-023, HH-SR-007).

Every change to a shift, a sign-up decision, attendance or a user's role is recorded here,
so an admin can trace who did what. Services call ``record`` instead of building the row
themselves, which keeps the entity type in step with the action.

Append-only: nothing in the app updates or deletes an event. There is no endpoint that
writes to the history either, so an event can only arrive as a side effect of the change
it describes.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, User
from app.services.shifts import STORE_TIMEZONE

SHIFT = "SHIFT"
SIGNUP = "SIGNUP"
USER = "USER"
OTHER = "OTHER"

# Which kind of thing each action's target_id points at.
ENTITY_BY_PREFIX = {
    "SHIFT_": SHIFT,
    "SIGNUP_": SIGNUP,
    "ATTENDANCE_": SIGNUP,  # attendance hangs off a sign-up
    "USER_": USER,
}


def entity_for(action: str) -> str:
    for prefix, entity in ENTITY_BY_PREFIX.items():
        if action.startswith(prefix):
            return entity
    return OTHER


def record(
    db: Session, actor: User | int, action: str, target_id: int, detail: str
) -> AuditEvent:
    """Add one event to the caller's transaction. The caller commits."""
    event = AuditEvent(
        actor_id=actor if isinstance(actor, int) else actor.id,
        action=action,
        entity_type=entity_for(action),
        target_id=target_id,
        detail=detail,
    )
    db.add(event)
    return event


def history(
    db: Session,
    *,
    actor_id: int | None = None,
    action: str | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 200,
) -> list[tuple[AuditEvent, str]]:
    """Newest first, with each actor's name. Filters combine (HH-33's admin page).

    ``since`` and ``until`` are store-local dates and both ends are included, so picking
    the same day twice gives that whole day.
    """
    query = (
        select(AuditEvent, User.full_name)
        .join(User, AuditEvent.actor_id == User.id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    if actor_id is not None:
        query = query.where(AuditEvent.actor_id == actor_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if since is not None:
        query = query.where(
            AuditEvent.created_at >= datetime.combine(since, time(0), STORE_TIMEZONE)
        )
    if until is not None:
        end = datetime.combine(until, time(0), STORE_TIMEZONE) + timedelta(days=1)
        query = query.where(AuditEvent.created_at < end)
    return [(event, name) for event, name in db.execute(query)]


def actions(db: Session) -> list[str]:
    """The actions actually recorded so far, for the filter list on the page."""
    return list(db.scalars(select(AuditEvent.action).distinct().order_by(AuditEvent.action)))
