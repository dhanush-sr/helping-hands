"""Shifts (help requests).

HH-15 adds ``POST /api/v1/shifts`` for store managers, shaped as in the SAD (camelCase JSON,
store-local date and times):

    request  {"storeId": 1, "busyPeriodId": 1, "date": "2026-11-08", "startTime": "10:00",
              "endTime": "14:00", "task": "Billing", "slotsNeeded": 3, "notes": "Festive rush"}
    response 201 {"shiftId": 845, "status": "OPEN", "freeSlots": 3}

HH-16 adds ``GET /api/v1/shifts`` for everyone signed in, with the SAD's filters
(``status``, default OPEN; ``storeId``; ``busyPeriodId``; ``task``, part of the name) plus
``date`` (store-local YYYY-MM-DD). Filters combine; an unreadable one is 400 INVALID_FILTER:

    GET /api/v1/shifts?busyPeriodId=1&task=billing
    200 [{"shiftId": 845, "store": "Indiranagar", "storeId": 2, "busyPeriod": "Diwali weekend",
          "date": "2026-11-08", "startTime": "10:00", "endTime": "14:00", "task": "Billing",
          "slotsNeeded": 3, "freeSlots": 2, "status": "OPEN"}]
"""

from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from app.api.deps import require_any_role, require_manager
from app.db.session import get_db
from app.models import Shift, ShiftStatus, User
from app.services import shifts

router = APIRouter(prefix="/shifts", tags=["shifts"])


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ShiftIn(CamelModel):
    store_id: int
    busy_period_id: int | None = None
    date: date
    start_time: time
    end_time: time
    task: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    # Range checked by the service so a bad number gets 400 INVALID_SLOTS, as HH-15 asks.
    slots_needed: int
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = (
        Field(default=None)
    )


class ShiftCreated(CamelModel):
    shift_id: int
    status: ShiftStatus
    free_slots: int


@router.post("", response_model=ShiftCreated, response_model_by_alias=True, status_code=201)
def post_shift(
    body: ShiftIn, user: User = Depends(require_manager), db: Session = Depends(get_db)
) -> ShiftCreated:
    shift = shifts.create_shift(
        db,
        user,
        store_id=body.store_id,
        day=body.date,
        start_time=body.start_time,
        end_time=body.end_time,
        task=body.task,
        slots=body.slots_needed,
        busy_period_id=body.busy_period_id,
        notes=body.notes,
    )
    return ShiftCreated(shift_id=shift.id, status=shift.status, free_slots=shifts.free_slots(shift))


class ShiftListItem(CamelModel):
    shift_id: int
    store: str
    store_id: int
    busy_period: str | None
    busy_period_id: int | None
    date: date
    start_time: str
    end_time: str
    task: str
    slots_needed: int
    free_slots: int
    status: ShiftStatus


def list_item(shift: Shift) -> ShiftListItem:
    starts, ends = shifts.local(shift.starts_at), shifts.local(shift.ends_at)
    return ShiftListItem(
        shift_id=shift.id,
        store=shift.store.name,
        store_id=shift.store_id,
        busy_period=shift.busy_period.name if shift.busy_period else None,
        busy_period_id=shift.busy_period_id,
        date=starts.date(),
        start_time=starts.strftime("%H:%M"),
        end_time=ends.strftime("%H:%M"),
        task=shift.task,
        slots_needed=shift.slots,
        free_slots=shifts.free_slots(shift),
        status=shift.status,
    )


# Filters are read as text and checked by the service, so a bad one is 400 as the SAD says.
@router.get(
    "",
    response_model=list[ShiftListItem],
    response_model_by_alias=True,
    dependencies=[Depends(require_any_role)],
)
def browse_shifts(
    status: str | None = Query(default=None, max_length=20),
    store_id: str | None = Query(default=None, alias="storeId", max_length=12),
    busy_period_id: str | None = Query(default=None, alias="busyPeriodId", max_length=12),
    task: str | None = Query(default=None, max_length=120),
    day: str | None = Query(default=None, alias="date", max_length=10),
    db: Session = Depends(get_db),
) -> list[ShiftListItem]:
    found = shifts.list_shifts(
        db, status=status, store_id=store_id, busy_period_id=busy_period_id, task=task, day=day
    )
    return [list_item(shift) for shift in found]
