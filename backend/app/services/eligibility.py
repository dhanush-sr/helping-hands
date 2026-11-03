"""Whether a volunteer may sign up for a shift (HH-F-012, HH-F-013).

Sign-up (HH-17) calls ``check`` before it saves anything. A refusal is a 409 ``ApiError``
whose code says why, as in the SAD:

- ``SHIFT_CANCELLED``: the shift was cancelled
- ``SHIFT_STARTED``: the shift has already started (or is over)
- ``STORE_INACTIVE``: the store has been deactivated
- ``SHIFT_FULL``: every slot is confirmed
- ``NOTICE``: it starts inside the minimum notice (HH-18)
- ``CLASH``: it overlaps a shift the volunteer already holds (HH-18)
- ``WEEKLY_LIMIT``: it would take them over the weekly hour limit (HH-18)

The notice, clash and weekly rules are about the volunteer, so they are checked after the
ones about the shift itself: a volunteer is told the shift is full or cancelled before
being told anything about their own schedule.

A volunteer "holds" a shift while their sign-up is REQUESTED or CONFIRMED. Declined and
withdrawn sign-ups, and cancelled shifts, don't count towards a clash or the weekly hours.
The minimum notice, weekly hour limit and withdrawal cutoff are admin-editable settings
(``app/services/rules.py``), not fixed numbers.
"""

from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.errors import ApiError
from app.models import (
    MIN_NOTICE_HOURS,
    WEEKLY_HOUR_LIMIT,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    User,
)
from app.services import rules, shifts

HELD = (SignUpStatus.REQUESTED, SignUpStatus.CONFIRMED)


def refused(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def held_shifts(db: Session, volunteer: User, *, besides: int | None = None) -> list[Shift]:
    """The shifts this volunteer has asked for or been confirmed on, newest decision aside.

    ``besides`` leaves out one shift id, so signing up again after withdrawing doesn't
    clash with itself.
    """
    query = (
        select(Shift)
        .join(SignUp, SignUp.shift_id == Shift.id)
        .where(
            SignUp.volunteer_id == volunteer.id,
            SignUp.status.in_(HELD),
            Shift.status != ShiftStatus.CANCELLED,
        )
    )
    if besides is not None:
        query = query.where(Shift.id != besides)
    return list(db.scalars(query))


def length(shift: Shift) -> timedelta:
    return security.as_utc(shift.ends_at) - security.as_utc(shift.starts_at)


def overlaps(one: Shift, other: Shift) -> bool:
    """True when the two shifts share any time.

    Back-to-back shifts (one ends exactly when the other starts) do not overlap, so a
    volunteer may take both.
    """
    return security.as_utc(one.starts_at) < security.as_utc(other.ends_at) and security.as_utc(
        other.starts_at
    ) < security.as_utc(one.ends_at)


def week_of(moment: datetime) -> tuple[datetime, datetime]:
    """The Monday-to-Sunday week (store time) holding ``moment``, as a UTC half-open range."""
    day = shifts.local(moment).date()
    monday = day - timedelta(days=day.weekday())
    starts = shifts.store_time(monday, time(0))
    return starts, starts + timedelta(days=7)


def check(db: Session, volunteer: User, shift: Shift) -> None:
    """Raise a 409 ``ApiError`` if ``volunteer`` can't sign up for ``shift``."""
    now = security.utcnow()
    starts = security.as_utc(shift.starts_at)

    if shift.status == ShiftStatus.CANCELLED:
        raise refused("SHIFT_CANCELLED", "This shift has been cancelled.")
    if starts <= now:
        raise refused("SHIFT_STARTED", "This shift has already started.")
    if not shift.store.is_active:
        raise refused("STORE_INACTIVE", "This store is not taking volunteers.")
    if shift.status == ShiftStatus.FILLED or shifts.free_slots(shift) == 0:
        raise refused("SHIFT_FULL", "This shift is already full.")

    notice = rules.value(db, MIN_NOTICE_HOURS)
    if starts - now < timedelta(hours=notice):
        raise refused(
            "NOTICE", f"Sign-ups close {notice} hours before a shift starts. This one is sooner."
        )

    held = held_shifts(db, volunteer, besides=shift.id)

    for other in held:
        if overlaps(shift, other):
            raise refused(
                "CLASH",
                f"This overlaps your {other.task} shift at {other.store.name} "
                f"({shifts.local(other.starts_at):%d %b, %H:%M} to "
                f"{shifts.local(other.ends_at):%H:%M}).",
            )

    limit = rules.value(db, WEEKLY_HOUR_LIMIT)
    week_starts, week_ends = week_of(starts)

    def that_week(other: Shift) -> bool:
        return week_starts <= security.as_utc(other.starts_at) < week_ends

    booked = sum((length(other) for other in held if that_week(other)), timedelta())
    if booked + length(shift) > timedelta(hours=limit):
        booked_hours = booked.total_seconds() / 3600
        raise refused(
            "WEEKLY_LIMIT",
            f"That would take you over the {limit} hour weekly limit. "
            f"You already hold {booked_hours:g} hours that week.",
        )
