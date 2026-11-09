"""Attendance for store managers, and each volunteer's own attendance and notices."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, FiniteFloat
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.api.deps import require_manager, require_volunteer, shift_in_scope
from app.db.session import get_db
from app.errors import ApiError
from app.models import (
    Attendance,
    AuditEvent,
    Notification,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    User,
)
from app.services import access, shifts

router = APIRouter(tags=["attendance and notifications"])


class AttendanceInput(BaseModel):
    status: Literal["ATTENDED", "NO_SHOW"]
    hours_worked: FiniteFloat


class AttendanceRow(BaseModel):
    signup_id: int
    volunteer: str
    status: str | None
    hours_worked: float | None


class Notice(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shift_id: int
    message: str
    created_at: datetime


@router.get("/notifications", response_model=list[Notice])
def notifications(user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.id.desc())
        )
    )


@router.get("/shifts/{shift_id}/attendance", response_model=list[AttendanceRow])
def roster(
    user: User = Depends(require_manager),
    shift: Shift = Depends(shift_in_scope),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(SignUp.id, User.full_name, Attendance.status, Attendance.hours_worked)
        .join(User, SignUp.volunteer_id == User.id)
        .outerjoin(Attendance, Attendance.signup_id == SignUp.id)
        .where(SignUp.shift_id == shift.id, SignUp.status == SignUpStatus.CONFIRMED)
        .order_by(User.full_name, SignUp.id)
    )
    return [
        AttendanceRow(signup_id=sid, volunteer=name, status=status, hours_worked=hours)
        for sid, name, status, hours in rows
    ]


@router.put("/shifts/{shift_id}/attendance/{signup_id}", response_model=AttendanceRow)
def record(
    shift_id: int,
    signup_id: int,
    body: AttendanceInput,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    shift = shifts.lock_shift(db, shift_id)
    access.ensure_store_scope(manager, shift.store)
    if (
        shift.status == ShiftStatus.CANCELLED
        or security.as_utc(shift.starts_at) > security.utcnow()
    ):
        raise ApiError(
            409, "ATTENDANCE_UNAVAILABLE", "Attendance requires a shift that has started."
        )
    confirmed = {s.id: s for s in shift.signups if s.status == SignUpStatus.CONFIRMED}
    signup = confirmed.get(signup_id)
    if signup is None:
        raise ApiError(404, "CONFIRMED_SIGNUP_NOT_FOUND", "No confirmed sign-up for this shift.")
    duration = (security.as_utc(shift.ends_at) - security.as_utc(shift.starts_at)).total_seconds()
    if not 0 <= body.hours_worked * 3600 <= duration or (
        body.status == "NO_SHOW" and body.hours_worked != 0
    ):
        raise ApiError(400, "INVALID_HOURS", "Hours must fit the shift and be zero for a no-show.")

    row = db.get(Attendance, signup_id)
    if row is None or (row.status, row.hours_worked) != (body.status, body.hours_worked):
        if row is None:
            row = Attendance(signup_id=signup_id)
            db.add(row)
        row.status = body.status
        row.hours_worked = body.hours_worked
        row.recorded_by_id = manager.id
        db.add(
            AuditEvent(
                actor_id=manager.id,
                action="ATTENDANCE_RECORDED",
                target_id=signup_id,
                detail=f"{body.status}: {body.hours_worked:g} hours",
            )
        )
        db.flush()

    recorded = set(
        db.scalars(select(Attendance.signup_id).where(Attendance.signup_id.in_(confirmed)))
    )
    if recorded == confirmed.keys():
        shift.status = ShiftStatus.COMPLETED
    db.commit()
    return AttendanceRow(
        signup_id=signup.id,
        volunteer=signup.volunteer.full_name,
        status=row.status,
        hours_worked=row.hours_worked,
    )


@router.get("/attendance/me")
def my_attendance(user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Shift, Attendance)
        .join(SignUp, SignUp.shift_id == Shift.id)
        .join(Attendance, Attendance.signup_id == SignUp.id)
        .where(SignUp.volunteer_id == user.id)
        .order_by(Shift.starts_at.desc(), Shift.id)
    )
    return [
        {
            "shiftId": shift.id,
            "task": shift.task,
            "date": shifts.local(shift.starts_at).date(),
            "status": row.status,
            "hoursWorked": row.hours_worked,
        }
        for shift, row in rows
    ]
