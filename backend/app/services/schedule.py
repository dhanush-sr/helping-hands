"""A volunteer's own schedule (HH-26: HH-F-019).

What one volunteer sees about themselves: the shifts they are waiting on or confirmed for,
the ones already done with the hours recorded, and how much of this week's hour limit they
have used. Only ever their own rows; the endpoint reads the signed-in user, never an id
from the request.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import security
from app.models import (
    WEEKLY_HOUR_LIMIT,
    WITHDRAWAL_CUTOFF_HOURS,
    Attendance,
    Shift,
    SignUp,
    SignUpStatus,
    User,
)
from app.services import eligibility, rules, shifts


@dataclass
class Entry:
    """One sign-up on the volunteer's schedule."""

    signup_id: int
    shift_id: int
    store: str
    task: str
    starts_at: datetime
    ends_at: datetime
    status: SignUpStatus
    hours: float
    attendance: str | None
    hours_worked: float | None
    can_withdraw: bool


def _hours(shift: Shift) -> float:
    return eligibility.length(shift).total_seconds() / 3600


def entries(db: Session, volunteer: User) -> tuple[list[Entry], list[Entry]]:
    """This volunteer's upcoming and past sign-ups, each in time order.

    Upcoming holds the ones still ahead that they are waiting on or confirmed for, soonest
    first. Past holds everything that has already started, newest first, with whatever
    attendance the manager recorded (HH-30).
    """
    now = security.utcnow()
    cutoff = rules.value(db, WITHDRAWAL_CUTOFF_HOURS)
    rows = db.execute(
        select(SignUp, Shift, Attendance)
        .join(Shift, SignUp.shift_id == Shift.id)
        .outerjoin(Attendance, Attendance.signup_id == SignUp.id)
        .options(selectinload(Shift.store))
        .where(SignUp.volunteer_id == volunteer.id)
        .order_by(Shift.starts_at, Shift.id)
    ).all()

    upcoming: list[Entry] = []
    past: list[Entry] = []
    for signup, shift, attendance in rows:
        starts = security.as_utc(shift.starts_at)
        entry = Entry(
            signup_id=signup.id,
            shift_id=shift.id,
            store=shift.store.name,
            task=shift.task,
            starts_at=starts,
            ends_at=security.as_utc(shift.ends_at),
            status=signup.status,
            hours=_hours(shift),
            attendance=attendance.status if attendance else None,
            hours_worked=attendance.hours_worked if attendance else None,
            # Withdrawing closes a set number of hours before the shift starts (HH-F-016).
            can_withdraw=(
                signup.status in eligibility.HELD
                and starts > now
                and starts - now >= timedelta(hours=cutoff)
            ),
        )
        if starts > now and signup.status in eligibility.HELD:
            upcoming.append(entry)
        elif starts <= now:
            past.append(entry)
    past.reverse()
    return upcoming, past


def hours_this_week(db: Session, volunteer: User) -> tuple[float, int]:
    """Hours the volunteer holds in the current Monday-to-Sunday week, and the limit.

    Counted the same way the sign-up check counts them (HH-18), so the number on the page
    matches the one that refuses a sign-up.
    """
    week_starts, week_ends = eligibility.week_of(security.utcnow())
    held = eligibility.held_shifts(db, volunteer)
    booked = sum(
        (
            eligibility.length(shift)
            for shift in held
            if week_starts <= security.as_utc(shift.starts_at) < week_ends
        ),
        timedelta(),
    )
    return booked.total_seconds() / 3600, rules.value(db, WEEKLY_HOUR_LIMIT)


def local_times(entry: Entry) -> tuple[str, str, str]:
    """The entry's date and times in store time, ready to show."""
    starts, ends = shifts.local(entry.starts_at), shifts.local(entry.ends_at)
    return starts.date().isoformat(), starts.strftime("%H:%M"), ends.strftime("%H:%M")
