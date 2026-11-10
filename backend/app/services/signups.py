"""Signing up for a shift (HH-17), and the manager's decision on it (HH-24).

A volunteer asks to help on a shift. The sign-up starts as REQUESTED and only takes a slot
once the store manager confirms it (HH-24). Before saving, ``eligibility.check`` decides
whether the volunteer may sign up at all (409 with its code if not).

One sign-up per volunteer per shift: asking again is 409 ``ALREADY_SIGNED_UP``, whatever
the first one's status, except after a withdrawal, when the same row goes back to
REQUESTED (the table is unique on shift and volunteer).
"""

from datetime import timedelta

from sqlalchemy import select
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
from app.services import access, eligibility, notifications, rules, shifts


def already_signed_up() -> ApiError:
    return ApiError(409, "ALREADY_SIGNED_UP", "You have already signed up for this shift.")


def sign_up(db: Session, volunteer: User, shift_id: int) -> SignUp:
    shift = shifts.lock_shift(db, shift_id)

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

    notifications.notify_store_manager(
        db, shift, f"{volunteer.full_name} asked to help with {shift.task}."
    )
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
    shift = shifts.lock_shift(db, signup.shift_id)
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
    notifications.notify_store_manager(
        db, shift, f"{volunteer.full_name} withdrew from {shift.task}."
    )
    db.commit()
    return signup


def confirmed_count(shift: Shift) -> int:
    return sum(signup.status == SignUpStatus.CONFIRMED for signup in shift.signups)


def decide(db: Session, manager: User, signup_id: int, approve: bool) -> SignUp:
    """Approve or decline a sign-up (HH-24: HH-F-014, HH-F-015, HH-NF-002).

    The shift row is locked before the confirmed sign-ups are counted, and the count, the
    decision and the shift's new status are written in that one transaction. Two managers
    approving the last slot at the same moment are therefore serialised: the second one
    reads the slot as already taken and is refused with ``SHIFT_FULL``, so a shift can
    never be overbooked.
    """
    signup = access.get_signup_in_scope(db, manager, signup_id)
    shift = shifts.lock_shift(db, signup.shift_id)
    db.refresh(signup)

    if signup.status != SignUpStatus.REQUESTED:
        raise ApiError(
            409, "ALREADY_DECIDED", f"This sign-up is already {signup.status.value.lower()}."
        )
    if shift.status == ShiftStatus.CANCELLED:
        raise ApiError(409, "SHIFT_CANCELLED", "This shift has been cancelled.")

    now = security.utcnow()
    if approve:
        # Counted while the row is held, so no other approval can slip in between.
        if confirmed_count(shift) >= shift.slots:
            raise ApiError(409, "SHIFT_FULL", "Every slot on this shift is already confirmed.")
        signup.status = SignUpStatus.CONFIRMED
        # The shift is full once this one is counted, so it drops out of the open list.
        if confirmed_count(shift) >= shift.slots:
            shift.status = ShiftStatus.FILLED
        action = "SIGNUP_CONFIRMED"
        message = f"Your sign-up for {shift.task} at {shift.store.name} was approved."
    else:
        # Only a pending sign-up reaches here, so declining never frees a slot; a
        # confirmed volunteer dropping out goes through withdraw() instead.
        signup.status = SignUpStatus.DECLINED
        action = "SIGNUP_DECLINED"
        message = f"Your sign-up for {shift.task} at {shift.store.name} was declined."

    signup.decided_by_id = manager.id
    signup.decided_at = now
    notifications.notify(db, signup.volunteer_id, message, shift)
    db.add(
        AuditEvent(actor_id=manager.id, action=action, target_id=signup.id, detail=message)
    )
    db.commit()
    db.refresh(signup)
    return signup
