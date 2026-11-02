"""Whether a volunteer may sign up for a shift (HH-F-012, HH-F-013).

Sign-up (HH-17) calls ``check`` before it saves anything. A refusal is a 409 ``ApiError``
whose code says why, as in the SAD:

- ``SHIFT_CANCELLED``: the shift was cancelled
- ``SHIFT_STARTED``: the shift has already started (or is over)
- ``STORE_INACTIVE``: the store has been deactivated
- ``SHIFT_FULL``: every slot is confirmed

HH-18 adds the volunteer's own rules here, so sign-up itself doesn't change:
``NOTICE`` (inside the minimum notice), ``CLASH`` (overlaps a shift they hold) and
``WEEKLY_LIMIT`` (over the weekly hour limit).
"""

from sqlalchemy.orm import Session

from app import security
from app.errors import ApiError
from app.models import Shift, ShiftStatus, User
from app.services.shifts import free_slots


def refused(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def check(db: Session, volunteer: User, shift: Shift) -> None:
    """Raise a 409 ``ApiError`` if ``volunteer`` can't sign up for ``shift``."""
    if shift.status == ShiftStatus.CANCELLED:
        raise refused("SHIFT_CANCELLED", "This shift has been cancelled.")
    if security.as_utc(shift.starts_at) <= security.utcnow():
        raise refused("SHIFT_STARTED", "This shift has already started.")
    if not shift.store.is_active:
        raise refused("STORE_INACTIVE", "This store is not taking volunteers.")
    if shift.status == ShiftStatus.FILLED or free_slots(shift) == 0:
        raise refused("SHIFT_FULL", "This shift is already full.")
