"""Signing up for a shift (HH-17: HH-F-011).

A volunteer asks to help on a shift. The sign-up starts as REQUESTED and only takes a slot
once the store manager confirms it (HH-24). Before saving, ``eligibility.check`` decides
whether the volunteer may sign up at all (409 with its code if not).

One sign-up per volunteer per shift: asking again is 409 ``ALREADY_SIGNED_UP``, whatever
the first one's status, except after a withdrawal, when the same row goes back to
REQUESTED (the table is unique on shift and volunteer).
"""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import security
from app.errors import ApiError
from app.models import (
    WITHDRAWAL_CUTOFF_HOURS,
    AuditEvent,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    User,
)
from app.services import access, eligibility, rules


def lock_shift(db: Session, shift_id: int) -> Shift:
    # SQLite has no row locks. Start its write transaction before reading mutable state.
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(Shift).where(Shift.id == shift_id).values(updated_at=Shift.updated_at))
    shift = db.get(Shift, shift_id, with_for_update=True, populate_existing=True)
    if shift is None:
        raise ApiError(404, "SHIFT_NOT_FOUND", "No shift with that id.")
    return shift


def already_signed_up() -> ApiError:
    return ApiError(409, "ALREADY_SIGNED_UP", "You have already signed up for this shift.")


def sign_up(db: Session, volunteer: User, shift_id: int) -> SignUp:
    shift = lock_shift(db, shift_id)

    existing = db.scalar(
        select(SignUp).where(SignUp.shift_id == shift.id, SignUp.volunteer_id == volunteer.id)
    )
    if existing is not None and existing.status != SignUpStatus.WITHDRAWN:
        raise already_signed_up()

    eligibility.check(db, volunteer, shift)

    if existing is not None:  # signing up again after withdrawing
        signup = existing
        signup.status = SignUpStatus.REQUESTED
        signup.decided_by_id = None
        signup.decided_at = None
        signup.withdrawn_at = None
    else:
        signup = SignUp(shift=shift, volunteer=volunteer, status=SignUpStatus.REQUESTED)
        db.add(signup)

    try:
        db.commit()
    except IntegrityError:
        # Two requests at once (a double tap): the unique constraint lets only one in.
        db.rollback()
        raise already_signed_up() from None
    db.refresh(signup)
    return signup


def withdraw(db: Session, volunteer: User, signup_id: int) -> SignUp:
    signup = access.get_signup_in_scope(db, volunteer, signup_id)
    shift = lock_shift(db, signup.shift_id)
    db.refresh(signup)
    if signup.status == SignUpStatus.WITHDRAWN:
        return signup
    if signup.status not in eligibility.HELD or shift.status not in {
        ShiftStatus.OPEN,
        ShiftStatus.FILLED,
    }:
        raise ApiError(409, "CANNOT_WITHDRAW", "This sign-up cannot be withdrawn.")

    now = security.utcnow()
    cutoff = rules.value(db, WITHDRAWAL_CUTOFF_HOURS)
    if security.as_utc(shift.starts_at) - now < timedelta(hours=cutoff):
        raise ApiError(
            409, "WITHDRAWAL_CUTOFF", f"Withdrawal closes {cutoff} hours before a shift."
        )

    if signup.status == SignUpStatus.CONFIRMED and shift.status == ShiftStatus.FILLED:
        shift.status = ShiftStatus.OPEN
    signup.status = SignUpStatus.WITHDRAWN
    signup.withdrawn_at = now
    db.add(
        AuditEvent(
            actor_id=volunteer.id,
            action="SIGNUP_WITHDRAWN",
            target_id=signup.id,
            detail="Volunteer withdrew their sign-up.",
        )
    )
    db.commit()
    return signup
