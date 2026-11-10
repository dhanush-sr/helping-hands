"""Reminders the day before a shift (HH-28: HH-F-018).

A background job calls ``send_due`` every few minutes. It finds the confirmed sign-ups
whose shift starts within the next day and queues one in-app reminder for each.

Each sign-up is reminded once: sending stamps ``reminded_at``, and the search skips
anything already stamped. So a restart, an overlapping run or a job that fires more often
than planned still cannot produce a second reminder.

Nothing is sent for a sign-up that was withdrawn or declined, for a cancelled shift, or
for a shift that has already started.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import security
from app.models import Shift, ShiftStatus, SignUp, SignUpStatus
from app.services import notifications
from app.services.shifts import local

REMIND_WITHIN = timedelta(hours=24)


def due(db: Session) -> list[SignUp]:
    """Confirmed sign-ups starting within the next 24 hours that have not been reminded."""
    now = security.utcnow()
    return list(
        db.scalars(
            select(SignUp)
            .join(Shift, Shift.id == SignUp.shift_id)
            .options(selectinload(SignUp.shift).selectinload(Shift.store))
            .where(
                SignUp.status == SignUpStatus.CONFIRMED,
                SignUp.reminded_at.is_(None),
                Shift.status != ShiftStatus.CANCELLED,
                Shift.starts_at > now,
                Shift.starts_at <= now + REMIND_WITHIN,
            )
            .order_by(Shift.starts_at, SignUp.id)
        )
    )


def message_for(signup: SignUp) -> str:
    starts = local(signup.shift.starts_at)
    return (
        f"Reminder: {signup.shift.task} at {signup.shift.store.name} "
        f"tomorrow, {starts:%d %b} at {starts:%H:%M}."
    )


def send_due(db: Session) -> int:
    """Send every reminder that is due and return how many went out."""
    now = security.utcnow()
    sent = 0
    for signup in due(db):
        notifications.notify(db, signup.volunteer_id, message_for(signup), signup.shift)
        signup.reminded_at = now
        sent += 1
    if sent:
        db.commit()
    return sent
