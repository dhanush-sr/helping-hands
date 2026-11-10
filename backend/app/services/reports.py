"""Coverage and volunteer reports (HH-32: HH-F-021, HH-F-022).

Three reports, all built from the same filtered set of shifts:

- **coverage**: per shift, how many volunteers were asked for and how many are confirmed,
  so a manager can see the gaps before the day arrives (HH-F-021)
- **hours**: hours per volunteer, from the attendance the managers recorded
- **no-shows**: how often each volunteer did not turn up

A store manager only ever sees their own store; an admin sees every store, or one chosen
with the ``store_id`` filter. The scope is applied here, not in the page, so a crafted
request cannot read another store's numbers.
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Integer, Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.errors import ApiError
from app.models import (
    Attendance,
    BusyPeriod,
    Shift,
    ShiftStatus,
    SignUp,
    SignUpStatus,
    Store,
    User,
    UserRole,
)
from app.services import shifts as shift_service
from app.store_clock import end_of_day, start_of_day

ATTENDED = "ATTENDED"
NO_SHOW = "NO_SHOW"


@dataclass
class Filters:
    store_id: int | None = None
    busy_period_id: int | None = None
    since: date | None = None
    until: date | None = None


@dataclass
class CoverageRow:
    shift_id: int
    store: str
    busy_period: str | None
    date: str
    start_time: str
    end_time: str
    task: str
    slots_needed: int
    confirmed: int
    open_slots: int
    status: ShiftStatus


@dataclass
class VolunteerRow:
    volunteer_id: int
    volunteer: str
    shifts: int
    hours: float


@dataclass
class NoShowRow:
    volunteer_id: int
    volunteer: str
    no_shows: int
    attended: int


def visible_stores(db: Session, viewer: User, store_id: int | None) -> list[int]:
    """The store ids this viewer may report on, after their own filter is applied.

    A manager asking for another store's id gets 403 rather than an empty report, so the
    refusal is plain rather than looking like "no data".
    """
    if viewer.role == UserRole.ADMIN:
        if store_id is None:
            return list(db.scalars(select(Store.id)))
        if db.get(Store, store_id) is None:
            raise ApiError(404, "STORE_NOT_FOUND", "No store with that id.")
        return [store_id]

    mine = list(db.scalars(select(Store.id).where(Store.manager_id == viewer.id)))
    if store_id is not None and store_id not in mine:
        raise ApiError(
            403, "STORE_FORBIDDEN", "You can only report on your own store's shifts."
        )
    return [store_id] if store_id is not None else mine


def _day_bounds(filters: Filters) -> tuple[datetime | None, datetime | None]:
    """The date filters as UTC instants. Both ends are included, in store time."""
    starts = start_of_day(filters.since) if filters.since else None
    ends = end_of_day(filters.until) if filters.until else None
    return starts, ends


def _scoped(query: Select, store_ids: list[int], filters: Filters) -> Select:
    query = query.where(Shift.store_id.in_(store_ids))
    if filters.busy_period_id is not None:
        query = query.where(Shift.busy_period_id == filters.busy_period_id)
    starts, ends = _day_bounds(filters)
    if starts is not None:
        query = query.where(Shift.starts_at >= starts)
    if ends is not None:
        query = query.where(Shift.starts_at < ends)
    return query


def check_filters(db: Session, filters: Filters) -> None:
    if filters.since and filters.until and filters.until < filters.since:
        raise ApiError(400, "INVALID_DATE_RANGE", "The end date can't be before the start date.")
    if filters.busy_period_id is not None and db.get(BusyPeriod, filters.busy_period_id) is None:
        raise ApiError(400, "INVALID_BUSY_PERIOD", "No busy period with that id.")


def coverage(db: Session, store_ids: list[int], filters: Filters) -> list[CoverageRow]:
    """Every shift in scope with its gap, soonest first (HH-F-021)."""
    query = _scoped(
        select(Shift)
        .options(selectinload(Shift.store), selectinload(Shift.busy_period))
        .options(selectinload(Shift.signups))
        .order_by(Shift.starts_at, Shift.id),
        store_ids,
        filters,
    )
    rows = []
    for shift in db.scalars(query):
        confirmed = sum(s.status == SignUpStatus.CONFIRMED for s in shift.signups)
        starts = shift_service.local(shift.starts_at)
        ends = shift_service.local(shift.ends_at)
        rows.append(
            CoverageRow(
                shift_id=shift.id,
                store=shift.store.name,
                busy_period=shift.busy_period.name if shift.busy_period else None,
                date=starts.date().isoformat(),
                start_time=starts.strftime("%H:%M"),
                end_time=ends.strftime("%H:%M"),
                task=shift.task,
                slots_needed=shift.slots,
                confirmed=confirmed,
                open_slots=max(shift.slots - confirmed, 0),
                status=shift.status,
            )
        )
    return rows


def hours(db: Session, store_ids: list[int], filters: Filters) -> list[VolunteerRow]:
    """Hours each volunteer actually worked, from recorded attendance (HH-F-022)."""
    query = _scoped(
        select(
            User.id,
            User.full_name,
            func.count(Attendance.signup_id),
            func.coalesce(func.sum(Attendance.hours_worked), 0.0),
        )
        .select_from(Attendance)
        .join(SignUp, SignUp.id == Attendance.signup_id)
        .join(Shift, Shift.id == SignUp.shift_id)
        .join(User, User.id == SignUp.volunteer_id)
        .where(Attendance.status == ATTENDED)
        .group_by(User.id, User.full_name)
        .order_by(func.sum(Attendance.hours_worked).desc(), User.full_name),
        store_ids,
        filters,
    )
    return [
        VolunteerRow(volunteer_id=uid, volunteer=name, shifts=count, hours=float(total))
        for uid, name, count, total in db.execute(query)
    ]


def no_shows(db: Session, store_ids: list[int], filters: Filters) -> list[NoShowRow]:
    """Volunteers who missed a shift they were confirmed for (HH-F-022)."""
    missed = func.sum(func.cast(Attendance.status == NO_SHOW, Integer))
    came = func.sum(func.cast(Attendance.status == ATTENDED, Integer))
    query = _scoped(
        select(User.id, User.full_name, missed, came)
        .select_from(Attendance)
        .join(SignUp, SignUp.id == Attendance.signup_id)
        .join(Shift, Shift.id == SignUp.shift_id)
        .join(User, User.id == SignUp.volunteer_id)
        .group_by(User.id, User.full_name)
        .having(missed > 0)
        .order_by(missed.desc(), User.full_name),
        store_ids,
        filters,
    )
    return [
        NoShowRow(
            volunteer_id=uid,
            volunteer=name,
            no_shows=int(gone or 0),
            attended=int(here or 0),
        )
        for uid, name, gone, here in db.execute(query)
    ]
