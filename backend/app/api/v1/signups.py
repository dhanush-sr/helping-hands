"""Sign-ups.

HH-17 adds ``POST /api/v1/shifts/{shiftId}/signups`` for volunteers, as in the SAD:

    POST /api/v1/shifts/845/signups      (no body)
    201 {"signUpId": 12, "shiftId": 845, "status": "REQUESTED"}

Refused with 409 and the eligibility code (``SHIFT_FULL``, ``SHIFT_CANCELLED``,
``SHIFT_STARTED``, ``STORE_INACTIVE``; HH-18 adds ``NOTICE``, ``CLASH``, ``WEEKLY_LIMIT``),
409 ``ALREADY_SIGNED_UP`` for a second sign-up, 404 ``SHIFT_NOT_FOUND`` for an unknown shift
and 403 ``FORBIDDEN`` for any role other than volunteer.

HH-24 adds the store manager's decision, as in the SAD:

    PATCH /api/v1/signups/3310     {"decision": "APPROVE"}
    200 {"signUpId": 3310, "status": "CONFIRMED", "shiftStatus": "FILLED"}

Approving the last free slot sets the shift to FILLED; approving when none is left is 409
``SHIFT_FULL``, and only the manager of that shift's store may decide (403 otherwise).
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.api.deps import require_manager, require_volunteer, shift_in_scope
from app.api.v1.shifts import CamelModel
from app.db.session import get_db
from app.models import Shift, ShiftStatus, SignUp, SignUpStatus, User
from app.services import schedule as schedule_service
from app.services import shifts as shift_service
from app.services import signups

router = APIRouter(tags=["signups"])


class SignUpCreated(CamelModel):
    sign_up_id: int
    shift_id: int
    status: SignUpStatus


@router.post(
    "/shifts/{shift_id}/signups",
    response_model=SignUpCreated,
    response_model_by_alias=True,
    status_code=201,
)
def sign_up(
    shift_id: int, user: User = Depends(require_volunteer), db: Session = Depends(get_db)
) -> SignUpCreated:
    signup = signups.sign_up(db, user, shift_id)
    return SignUpCreated(sign_up_id=signup.id, shift_id=signup.shift_id, status=signup.status)


@router.post("/signups/{signup_id}/withdraw", response_model=SignUpCreated)
def withdraw(
    signup_id: int, user: User = Depends(require_volunteer), db: Session = Depends(get_db)
) -> SignUpCreated:
    signup = signups.withdraw(db, user, signup_id)
    return SignUpCreated(sign_up_id=signup.id, shift_id=signup.shift_id, status=signup.status)


class Decision(CamelModel):
    decision: str = Field(pattern="^(APPROVE|DECLINE)$")


class DecisionMade(CamelModel):
    sign_up_id: int
    status: SignUpStatus
    shift_status: ShiftStatus


@router.patch(
    "/signups/{signup_id}", response_model=DecisionMade, response_model_by_alias=True
)
def decide(
    signup_id: int,
    body: Decision,
    user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> DecisionMade:
    signup = signups.decide(db, user, signup_id, body.decision == "APPROVE")
    return DecisionMade(
        sign_up_id=signup.id, status=signup.status, shift_status=signup.shift.status
    )


class ShiftSignUp(CamelModel):
    sign_up_id: int
    volunteer: str
    status: SignUpStatus
    requested_at: datetime


class ShiftSignUps(CamelModel):
    """Everyone who has asked for this shift, so the manager can decide (HH-24)."""

    shift_id: int
    task: str
    slots_needed: int
    free_slots: int
    shift_status: ShiftStatus
    sign_ups: list[ShiftSignUp]


@router.get(
    "/shifts/{shift_id}/signups",
    response_model=ShiftSignUps,
    response_model_by_alias=True,
    dependencies=[Depends(require_manager)],
)
def shift_signups(
    shift: Shift = Depends(shift_in_scope), db: Session = Depends(get_db)
) -> ShiftSignUps:
    rows = db.execute(
        select(SignUp.id, User.full_name, SignUp.status, SignUp.created_at)
        .join(User, SignUp.volunteer_id == User.id)
        .where(SignUp.shift_id == shift.id)
        # Pending ones first: they are what the manager is here to act on.
        .order_by(SignUp.status != SignUpStatus.REQUESTED, SignUp.created_at, SignUp.id)
    )
    return ShiftSignUps(
        shift_id=shift.id,
        task=shift.task,
        slots_needed=shift.slots,
        free_slots=shift_service.free_slots(shift),
        shift_status=shift.status,
        sign_ups=[
            ShiftSignUp(
                sign_up_id=sid, volunteer=name, status=status, requested_at=security.as_utc(made)
            )
            for sid, name, status, made in rows
        ],
    )


class ScheduleEntry(CamelModel):
    sign_up_id: int
    shift_id: int
    store: str
    task: str
    date: str
    start_time: str
    end_time: str
    hours: float
    status: SignUpStatus
    attendance: str | None
    hours_worked: float | None
    can_withdraw: bool


class MySchedule(CamelModel):
    """A volunteer's own shifts and how much of this week's limit they have used (HH-26)."""

    upcoming: list[ScheduleEntry]
    past: list[ScheduleEntry]
    hours_this_week: float
    weekly_hour_limit: int


def _entry(entry) -> ScheduleEntry:
    day, start, end = schedule_service.local_times(entry)
    return ScheduleEntry(
        sign_up_id=entry.signup_id,
        shift_id=entry.shift_id,
        store=entry.store,
        task=entry.task,
        date=day,
        start_time=start,
        end_time=end,
        hours=entry.hours,
        status=entry.status,
        attendance=entry.attendance,
        hours_worked=entry.hours_worked,
        can_withdraw=entry.can_withdraw,
    )


@router.get(
    "/me/schedule", response_model=MySchedule, response_model_by_alias=True
)
def my_schedule(
    user: User = Depends(require_volunteer), db: Session = Depends(get_db)
) -> MySchedule:
    upcoming, past = schedule_service.entries(db, user)
    booked, limit = schedule_service.hours_this_week(db, user)
    return MySchedule(
        upcoming=[_entry(e) for e in upcoming],
        past=[_entry(e) for e in past],
        hours_this_week=booked,
        weekly_hour_limit=limit,
    )
