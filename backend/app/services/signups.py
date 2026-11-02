"""Signing up for a shift (HH-17: HH-F-011).

A volunteer asks to help on a shift. The sign-up starts as REQUESTED and only takes a slot
once the store manager confirms it (HH-24). Before saving, ``eligibility.check`` decides
whether the volunteer may sign up at all (409 with its code if not).

One sign-up per volunteer per shift: asking again is 409 ``ALREADY_SIGNED_UP``, whatever
the first one's status, except after a withdrawal, when the same row goes back to
REQUESTED (the table is unique on shift and volunteer).
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Shift, SignUp, SignUpStatus, User
from app.services import eligibility


def already_signed_up() -> ApiError:
    return ApiError(409, "ALREADY_SIGNED_UP", "You have already signed up for this shift.")


def sign_up(db: Session, volunteer: User, shift_id: int) -> SignUp:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise ApiError(404, "SHIFT_NOT_FOUND", "No shift with that id.")

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
