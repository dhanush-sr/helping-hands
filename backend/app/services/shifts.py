"""Posting (HH-15: HH-F-007, HH-F-008) and browsing (HH-16: HH-F-010) shifts.

A store manager posts a shift for their own store. Times arrive as store-local date and
times (IST, as the SAD's API uses) and are stored in UTC. A shift is refused with 400 when:
- the end time is not after the start time (no overnight shifts),
- it starts in the past,
- it asks for fewer than 1 or more than ``MAX_SLOTS`` volunteers,
- its busy period doesn't exist or doesn't include the shift's date,
- its store is deactivated.
Other stores give 403 STORE_FORBIDDEN and unknown stores 404 (store scope, HH-12).
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import security
from app.errors import ApiError
from app.models import BusyPeriod, Shift, ShiftStatus, SignUpStatus, Store, User
from app.services import access

STORE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), "IST")
MAX_SLOTS = 100


def free_slots(shift: Shift) -> int:
    # ponytail: counts all CONFIRMED sign-ups in Python; a COUNT query when lists get long.
    confirmed = sum(1 for signup in shift.signups if signup.status == SignUpStatus.CONFIRMED)
    return max(shift.slots - confirmed, 0)


def store_time(day: date, at: time) -> datetime:
    """A store-local date and time as a UTC datetime."""
    return datetime.combine(day, at, STORE_TIMEZONE).astimezone(UTC)


def create_shift(
    db: Session,
    manager: User,
    *,
    store_id: int,
    day: date,
    start_time: time,
    end_time: time,
    task: str,
    slots: int,
    busy_period_id: int | None = None,
    notes: str | None = None,
) -> Shift:
    store = access.get_store_in_scope(db, manager, store_id)
    if not store.is_active:
        raise ApiError(400, "STORE_INACTIVE", "This store is deactivated.")

    starts_at, ends_at = store_time(day, start_time), store_time(day, end_time)
    if ends_at <= starts_at:
        raise ApiError(400, "INVALID_SHIFT_TIMES", "The end time must be after the start time.")
    if starts_at <= security.utcnow():
        raise ApiError(400, "SHIFT_IN_PAST", "The shift must start in the future.")
    if not 1 <= slots <= MAX_SLOTS:
        raise ApiError(
            400, "INVALID_SLOTS", f"Volunteers needed must be between 1 and {MAX_SLOTS}."
        )

    busy_period = None
    if busy_period_id is not None:
        busy_period = db.get(BusyPeriod, busy_period_id)
        if busy_period is None:
            raise ApiError(400, "INVALID_BUSY_PERIOD", "No busy period with that id.")
        if not busy_period.start_date <= day <= busy_period.end_date:
            raise ApiError(
                400,
                "OUTSIDE_BUSY_PERIOD",
                f"The date must be within {busy_period.name} "
                f"({busy_period.start_date} to {busy_period.end_date}).",
            )

    shift = Shift(
        store=store,
        busy_period=busy_period,
        task=task,
        description=notes or None,
        starts_at=starts_at,
        ends_at=ends_at,
        slots=slots,
        status=ShiftStatus.OPEN,
        created_by=manager,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


# --- browsing (HH-16: HH-F-010) ---------------------------------------------------------------


def _invalid_filter(name: str, expected: str) -> ApiError:
    return ApiError(400, "INVALID_FILTER", f"Filter {name} must be {expected}.")


def _int_filter(name: str, value: str | None) -> int | None:
    if value is None or value == "":
        return None
    if not value.isdigit():
        raise _invalid_filter(name, "a whole number")
    return int(value)


def list_shifts(
    db: Session,
    *,
    status: str | None = "OPEN",
    store_id: str | None = None,
    busy_period_id: str | None = None,
    task: str | None = None,
    day: str | None = None,
) -> list[Shift]:
    """Upcoming shifts at active stores, earliest first. Filters combine (AND).

    Defaults to OPEN shifts. ``task`` matches part of the task, ignoring case. ``day`` is a
    store-local date (YYYY-MM-DD). A filter that can't be read gives 400 INVALID_FILTER.
    """
    try:
        wanted_status = ShiftStatus(status or "OPEN")
    except ValueError:
        options = ", ".join(s.value for s in ShiftStatus)
        raise _invalid_filter("status", f"one of {options}") from None

    query = (
        select(Shift)
        .join(Shift.store)
        .where(
            Shift.status == wanted_status,
            Shift.starts_at > security.utcnow(),
            Store.is_active.is_(True),
        )
        .options(selectinload(Shift.store), selectinload(Shift.busy_period))
        .options(selectinload(Shift.signups))
        .order_by(Shift.starts_at, Shift.id)
    )
    if (value := _int_filter("storeId", store_id)) is not None:
        query = query.where(Shift.store_id == value)
    if (value := _int_filter("busyPeriodId", busy_period_id)) is not None:
        query = query.where(Shift.busy_period_id == value)
    if task:
        query = query.where(Shift.task.ilike(f"%{task.strip()}%"))
    if day:
        try:
            start_of_day = store_time(date.fromisoformat(day), time(0))
        except ValueError:
            raise _invalid_filter("date", "a date like 2026-11-07") from None
        query = query.where(
            Shift.starts_at >= start_of_day, Shift.starts_at < start_of_day + timedelta(days=1)
        )
    # ponytail: no paging; fine for the 2,000-shift test data, add limit/offset if it grows.
    return list(db.scalars(query))


def local(value: datetime) -> datetime:
    """A stored (UTC) time as store-local time."""
    return security.as_utc(value).astimezone(STORE_TIMEZONE)
